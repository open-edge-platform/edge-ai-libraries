// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package gpu turns qmassa telemetry into line protocol points.
//
// qmassa (https://github.com/ulissesf/qmassa) writes a stream of JSON objects,
// one per line, when run with --no-tui --to-json. This package parses that
// stream; it never launches qmassa itself, so the container (supervisord) and
// the bare-metal package (systemd) stay in charge of its lifecycle.
//
// The types below mirror qmlib's DrmDevice* structures. Numbers are kept as
// json.Number so every value is reproduced exactly as qmassa reported it,
// without a decode-and-re-encode round trip rewriting "0.0" as "0".
package gpu

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// Measurement names emitted by this package. They are part of the service's
// public contract, consumed by Grafana dashboards, and must not be renamed.
const (
	MeasurementEngineUsage = "gpu_engine_usage"
	MeasurementFrequency   = "gpu_frequency"
	MeasurementPower       = "gpu_power"
	MeasurementThrottle    = "gpu_throttle"
	MeasurementTemperature = "gpu_temperature"
	MeasurementFan         = "gpu_fan"
	MeasurementMemory      = "gpu_memory"
)

// renderNodeOffset is the minor number of the first DRM render node. Linux
// numbers them from 128, so subtracting it yields a zero-based GPU index.
const renderNodeOffset = 128

// renderNodePattern extracts the render node minor number from the comma
// separated dev_nodes field, for example "card1, renderD128".
var renderNodePattern = regexp.MustCompile(`renderD(\d+)`)

// state is one sample line from qmassa.
//
// Every array carries a rolling window of the last 40 samples rather than a
// single reading, so only the final element of each is current.
type state struct {
	Timestamps []json.Number `json:"timestamps"`
	DevsState  []device      `json:"devs_state"`
}

type device struct {
	DevNodes string `json:"dev_nodes"`

	// DrvName is the kernel driver bound to the device, "i915" or "xe".
	// The two differ in which counters they populate, so the name is
	// forwarded as a tag: without it a consumer cannot tell a real zero
	// from a counter this driver never fills in.
	DrvName string `json:"drv_name"`

	// FreqLimits names each graphics tile, for example gt0 and gt1. It is
	// positional: entry i describes tile i of every freqs sample.
	FreqLimits []freqLimit `json:"freq_limits"`

	DevStats stats `json:"dev_stats"`

	// ClisStats sits beside dev_stats rather than inside it, and lists the
	// processes currently holding a DRM client on this device.
	ClisStats []clientStats `json:"clis_stats"`
}

type freqLimit struct {
	Name string `json:"name"`
}

type stats struct {
	EngUsage map[string][]json.Number `json:"eng_usage"`

	// Freqs, Temps and Fans are windows of samples, each holding one entry
	// per graphics tile or per hardware sensor.
	Freqs [][]freqEntry `json:"freqs"`
	Temps [][]sensor    `json:"temps"`
	Fans  [][]fan       `json:"fans"`

	// Power and MemInfo are decoded as maps rather than structs so fields
	// added by a future qmassa release are forwarded instead of dropped.
	Power   []map[string]json.Number `json:"power"`
	MemInfo []map[string]json.Number `json:"mem_info"`
}

type freqEntry struct {
	// The frequencies are pointers so a tile that omits a key is
	// distinguishable from one reporting zero.
	MinFreq *json.Number `json:"min_freq"`
	CurFreq *json.Number `json:"cur_freq"`
	ActFreq *json.Number `json:"act_freq"`
	MaxFreq *json.Number `json:"max_freq"`

	// Throttle is a map for the same forward-compatibility reason as Power.
	Throttle map[string]bool `json:"throttle_reasons"`
}

type sensor struct {
	Name string       `json:"name"`
	Temp *json.Number `json:"temp"`
}

type fan struct {
	Name  string       `json:"name"`
	Speed *json.Number `json:"speed"`
}

// Parser converts qmassa JSON lines into points.
//
// It is stateless apart from the host tag and the clock, so a single instance
// can process the whole stream.
type Parser struct {
	hostname string

	// clientStats enables the opt-in per-process measurement.
	clientStats bool

	// clientLimit caps how many processes are reported per GPU. Zero means
	// every process is reported.
	clientLimit int

	// now is overridden by tests to make timestamps deterministic.
	now func() time.Time
}

// Option adjusts an optional parser behaviour.
type Option func(*Parser)

// WithClientStats additionally emits the per-process MeasurementClient points,
// keeping at most limit of them per GPU, ranked by how much of the GPU each
// process is using. A limit of zero keeps all of them.
//
// The cap is the point of the option rather than an afterthought. Those points
// are tagged with a process id, so an uncapped stream would add a time series
// for every process that ever touches the GPU, and a Prometheus scrape would
// accumulate them for as long as it runs. Ranking before truncating is what
// makes a small cap useful: what a developer wants to see is whichever
// processes are actually using the device.
func WithClientStats(limit int) Option {
	return func(p *Parser) {
		p.clientStats = true
		p.clientLimit = limit
	}
}

// NewParser returns a parser tagging every point with hostname.
func NewParser(hostname string, opts ...Option) *Parser {
	parser := &Parser{hostname: hostname, now: time.Now}
	for _, opt := range opts {
		opt(parser)
	}
	return parser
}

// Parse converts one JSON line into points.
//
// Lines that carry no telemetry return no points and no error: qmassa prefixes
// its stream with a version string and an options object, and both are
// expected. A line that is not valid JSON at all is reported as an error.
func (p *Parser) Parse(line []byte) ([]lineproto.Point, error) {
	// The stream starts with a bare JSON string ("2.1"), which is valid JSON
	// but not an object, so decode leniently and inspect the result.
	var decoded state
	if err := json.Unmarshal(line, &decoded); err != nil {
		if !json.Valid(line) {
			return nil, fmt.Errorf("line is not valid JSON: %w", err)
		}
		return nil, nil
	}

	// The options object qmassa prints on startup has neither field.
	if len(decoded.Timestamps) == 0 || len(decoded.DevsState) == 0 {
		return nil, nil
	}

	// qmassa's own timestamps are milliseconds since it started, not wall
	// clock, so the sample is stamped on arrival instead.
	timestamp := p.now()

	var points []lineproto.Point
	for _, dev := range decoded.DevsState {
		gpuID, ok := renderNodeID(dev.DevNodes)
		if !ok {
			continue
		}

		// emit supplies the tags every point of this device shares.
		emit := func(measurement string, tags []lineproto.Tag, fields []lineproto.Field) {
			if len(fields) == 0 {
				return
			}
			tags = append(tags,
				lineproto.Tag{Key: "host", Value: p.hostname},
				lineproto.Tag{Key: "gpu_id", Value: strconv.Itoa(gpuID)})

			// An empty tag value is not a usable label, so a device
			// that reports no driver name carries no driver tag
			// rather than an empty one.
			if dev.DrvName != "" {
				tags = append(tags, lineproto.Tag{Key: "driver", Value: dev.DrvName})
			}

			points = append(points, lineproto.Point{
				Measurement: measurement,
				Tags:        tags,
				Fields:      fields,
				Timestamp:   timestamp,
			})
		}

		appendEngineUsage(dev, emit)
		if err := appendFrequencies(dev, emit); err != nil {
			return nil, err
		}
		appendPower(dev, emit)
		appendMemory(dev, emit)
		if err := appendSensors(dev, emit); err != nil {
			return nil, err
		}
		if p.clientStats {
			appendClients(dev, p.clientLimit, emit)
		}
	}

	return points, nil
}

// emitFunc adds one point; the host and gpu_id tags are appended by the
// closure that implements it.
type emitFunc func(measurement string, tags []lineproto.Tag, fields []lineproto.Field)

func appendEngineUsage(dev device, emit emitFunc) {
	// Engines are keyed by driver-specific names: i915 reports "compute",
	// "render", "copy", "video" and "video-enhance", whereas xe reports
	// "ccs", "rcs", "bcs", "vcs" and "vecs". Both are passed through as-is so
	// a dashboard can tell the two apart.
	//
	// Map iteration order is randomised, so engines are sorted to keep the
	// output stable across runs.
	for _, engine := range sortedKeys(dev.DevStats.EngUsage) {
		samples := dev.DevStats.EngUsage[engine]
		if len(samples) == 0 {
			continue
		}
		emit(MeasurementEngineUsage,
			// "type" duplicates "engine" for compatibility with dashboards
			// written against the Python reader.
			[]lineproto.Tag{{Key: "engine", Value: engine}, {Key: "type", Value: engine}},
			[]lineproto.Field{lineproto.NumberField("usage", samples[len(samples)-1].String())})
	}
}

// appendFrequencies emits one point per graphics tile.
//
// A part such as Meteor Lake has two tiles with different limits (gt0 up to
// 2300 MHz, gt1 up to 1300 MHz), so reporting only the first would hide half
// the GPU.
func appendFrequencies(dev device, emit emitFunc) error {
	for index, tile := range lastOf(dev.DevStats.Freqs) {
		name := tileName(dev.FreqLimits, index)

		fields, err := scaledNumberFields(map[string]*json.Number{
			"cur_freq_hz": tile.CurFreq,
			"act_freq_hz": tile.ActFreq,
			"min_freq_hz": tile.MinFreq,
			"max_freq_hz": tile.MaxFreq,
		}, 1e6)
		if err != nil {
			return err
		}
		emit(MeasurementFrequency,
			[]lineproto.Tag{{Key: "type", Value: "cur_freq"}, {Key: "tile", Value: name}},
			fields)

		// Throttle reasons explain why act_freq sits below cur_freq. They are
		// emitted as 0 or 1 rather than as line protocol booleans because the
		// Prometheus output only exposes numeric fields.
		var throttle []lineproto.Field
		for _, reason := range sortedKeys(tile.Throttle) {
			value := int64(0)
			if tile.Throttle[reason] {
				value = 1
			}
			throttle = append(throttle, lineproto.IntField(reason, value))
		}
		emit(MeasurementThrottle, []lineproto.Tag{{Key: "tile", Value: name}}, throttle)
	}
	return nil
}

func appendPower(dev device, emit emitFunc) {
	latest := lastMap(dev.DevStats.Power)
	for _, key := range sortedKeys(latest) {
		emit(MeasurementPower,
			[]lineproto.Tag{{Key: "type", Value: key}},
			[]lineproto.Field{lineproto.NumberField("power_w", latest[key].String())})
	}
}

// appendMemory reports GPU memory usage.
//
// vram_* is zero on an integrated part, which has no dedicated memory, and the
// i915 driver reports smem_used as zero because it does not expose shared
// memory usage the way xe does. Neither zero is suppressed here: the raw
// counter is passed through, and the driver tag on every point is what lets a
// consumer tell such a zero apart from a measured one.
func appendMemory(dev device, emit emitFunc) {
	latest := lastMap(dev.DevStats.MemInfo)

	var fields []lineproto.Field
	for _, key := range sortedKeys(latest) {
		fields = append(fields, lineproto.NumberField(key+"_bytes", latest[key].String()))
	}
	emit(MeasurementMemory, nil, fields)
}

// appendSensors reports hwmon temperature and fan readings. An integrated GPU
// exposes a package temperature and no fans.
func appendSensors(dev device, emit emitFunc) error {
	for _, reading := range lastOf(dev.DevStats.Temps) {
		if reading.Temp == nil {
			continue
		}
		emit(MeasurementTemperature,
			[]lineproto.Tag{{Key: "sensor", Value: reading.Name}},
			[]lineproto.Field{lineproto.NumberField("temperature_c", reading.Temp.String())})
	}

	for _, reading := range lastOf(dev.DevStats.Fans) {
		if reading.Speed == nil {
			continue
		}
		fields, err := scaledNumberFields(map[string]*json.Number{"speed_hz": reading.Speed}, 1.0/60)
		if err != nil {
			return err
		}
		emit(MeasurementFan,
			[]lineproto.Tag{{Key: "fan", Value: reading.Name}},
			fields)
	}
	return nil
}

// scaledNumberFields converts present readings to base units in a stable order.
func scaledNumberFields(values map[string]*json.Number, factor float64) ([]lineproto.Field, error) {
	var fields []lineproto.Field
	for _, key := range sortedKeys(values) {
		if value := values[key]; value != nil {
			number, err := value.Float64()
			if err != nil {
				return nil, fmt.Errorf("GPU field %s is outside the supported numeric range", key)
			}
			fields = append(fields, lineproto.FloatField(key, number*factor))
		}
	}
	return fields, nil
}

// tileName returns the name qmassa gave tile index, falling back to a
// positional name when freq_limits is absent or shorter than expected.
func tileName(limits []freqLimit, index int) string {
	if index < len(limits) && limits[index].Name != "" {
		return limits[index].Name
	}
	return "gt" + strconv.Itoa(index)
}

// renderNodeID converts a dev_nodes string into a zero-based GPU index.
func renderNodeID(devNodes string) (int, bool) {
	match := renderNodePattern.FindStringSubmatch(devNodes)
	if match == nil {
		return 0, false
	}
	minor, err := strconv.Atoi(match[1])
	if err != nil || minor < renderNodeOffset {
		return 0, false
	}
	return minor - renderNodeOffset, true
}

// lastOf returns the most recent entry of a sample window.
func lastOf[T any](window [][]T) []T {
	if len(window) == 0 {
		return nil
	}
	return window[len(window)-1]
}

// lastMap returns the most recent entry of a window of keyed readings.
func lastMap(window []map[string]json.Number) map[string]json.Number {
	if len(window) == 0 {
		return nil
	}
	return window[len(window)-1]
}

// sortedKeys returns a map's keys in a stable order.
func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
