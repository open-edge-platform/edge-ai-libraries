// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package membw reports system memory bandwidth from the integrated memory
// controller.
//
// This is not GPU bandwidth, and it is important not to read it as such.
//
// Neither Intel GPU driver publishes a per-device byte counter. On i915 this
// was checked on the machine: the PMU carries engine occupancy, frequencies
// and rc6 residency; DRM fdinfo carries engine time and resident memory sizes,
// which are sizes rather than transfers; the card's sysfs attributes are
// frequencies; and no OA metric sets are registered. On xe it was checked in
// the driver, which defines exactly five events -- gt-c6-residency,
// engine-active-ticks, engine-total-ticks, gt-actual-frequency and
// gt-requested-frequency -- and no byte counter among them.
//
// What the memory controller sees is every access from the whole package,
// attributable to nothing in particular. On a machine whose GPU has no
// dedicated memory that is still the closest available signal, because the GPU
// is competing for exactly this bandwidth. It is reported under its own name
// rather than folded into the GPU panel, so nobody mistakes it for a
// per-device figure. On a discrete card, whose traffic goes to its own memory,
// it says correspondingly less.
//
// Telegraf's intel_pmu input can read arbitrary PMU events, but only from
// per-CPU-model event definition files published separately by Intel. The
// free-running controller counters are described by sysfs itself, which is why
// this reads them directly and works on any part that exposes them.
package membw

import (
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strconv"
	"strings"
	"time"

	"golang.org/x/sys/unix"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/cpu"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// Measurement carries memory controller throughput.
const Measurement = "memory_bandwidth"

// pmuGlob matches every memory controller PMU.
//
// The pattern is deliberately wider than the counters actually used. A machine
// exposes several of these and only some carry events: this one has
// uncore_imc_free_running_0 and _1 with counters, alongside uncore_imc_0 and _1
// whose event directories are empty. Matching broadly and then looking for
// usable events is what keeps this working across parts, where the naming
// differs.
const pmuGlob = "/sys/bus/event_source/devices/uncore_imc*"

// eventPair is one controller's read and write counters, under whatever names
// that generation uses.
type eventPair struct {
	read  string
	write string
}

// eventPairs lists the spellings seen across Intel parts, most recent first.
//
// Which one a machine uses is a property of its generation, not of its GPU, so
// this is discovered rather than configured.
var eventPairs = []eventPair{
	// Free-running counters on current client parts.
	{read: "data_read", write: "data_write"},
	// Older client integrated memory controllers.
	{read: "data_reads", write: "data_writes"},
	// Server parts count column address strobes instead.
	{read: "cas_count_read", write: "cas_count_write"},
}

// expectedUnit is the unit every known counter publishes. It is checked rather
// than assumed: a counter measured in something else would be reported under a
// field name claiming bytes per second, and the number would look
// perfectly ordinary while being wrong.
const expectedUnit = "MiB"

// counter is one opened perf event.
type counter struct {
	// canonical is "read" or "write". It is kept apart from the sysfs event
	// name so the field names on the endpoint stay the same whichever
	// spelling the machine uses.
	canonical string
	event     string
	device    string
	cpu       int

	// scale converts a raw count into MiB, as published by sysfs alongside
	// the event. It is 1/16384 on current parts, one count per 64 bytes,
	// but reading it is what keeps this correct on a part that differs.
	scale float64
	fd    int

	previous uint64
	primed   bool
}

// Collector reads the memory controllers.
type Collector struct {
	hostname string
	counters []counter
	sampled  time.Time

	now func() time.Time
}

// eventNames are the canonical counters reported. "data_total", where a
// machine publishes it, is deliberately not read: it is the sum of the other
// two, and deriving it costs nothing while opening it costs another file
// descriptor.
var eventNames = []string{"read", "write"}

// NewCollector opens the counters of every memory controller that publishes a
// usable pair, and takes a first reading so that the very first Collect
// already reports a real interval rather than nothing.
//
// A controller without events is skipped rather than treated as a failure:
// machines routinely expose several, only some of which carry counters. It is
// finding none at all that is an error, because a collector silently reporting
// nothing is worse than one that says why. The usual reason is a missing
// CAP_PERFMON, and that is worth an error message.
func NewCollector(sysfsGlob, hostname string) (*Collector, error) {
	return newCollector(sysfsGlob, hostname, unix.PerfEventOpen)
}

type perfOpener func(*unix.PerfEventAttr, int, int, int, int) (int, error)

func newCollector(sysfsGlob, hostname string, open perfOpener) (_ *Collector, err error) {
	devices, err := filepath.Glob(sysfsGlob)
	if err != nil {
		return nil, fmt.Errorf("bad device pattern %q: %w", sysfsGlob, err)
	}
	sort.Strings(devices)

	collector := &Collector{hostname: hostname, now: time.Now}
	defer func() {
		if err != nil {
			err = errors.Join(err, collector.Close())
		}
	}()

	type controller struct {
		device string
		pairs  []eventPair
		kind   uint32
		cpus   []int
	}
	var controllers []controller
	families := make(map[bool]bool)
	seenPMUs := make(map[uint32]bool)

	for _, device := range devices {
		pairs, found, err := discoverEvents(device)
		if err != nil {
			return nil, err
		}
		if !found {
			continue
		}

		pmuType, err := readUint(filepath.Join(device, "type"))
		if err != nil {
			return nil, err
		}
		if seenPMUs[uint32(pmuType)] {
			continue
		}
		seenPMUs[uint32(pmuType)] = true
		cpus, err := controllerCPUs(device)
		if err != nil {
			return nil, err
		}
		controllers = append(controllers, controller{device, pairs, uint32(pmuType), cpus})
		canonical, err := filepath.EvalSymlinks(device)
		if err != nil {
			return nil, fmt.Errorf("resolving PMU %s: %w", device, err)
		}
		families[strings.Contains(filepath.Base(canonical), "free_running")] = true
	}
	if len(families) > 1 {
		return nil, fmt.Errorf("both free-running and programmable IMC counters are available; use -devices to select one complete family after verifying coverage, rather than double-counting bandwidth")
	}

	// A PMU type identifies a kernel PMU, even if sysfs exposes aliases.
	// Its cpumask lists one representative per die, not all eligible threads.
	for _, controller := range controllers {
		for _, cpuID := range controller.cpus {
			for _, pair := range controller.pairs {
				for i, event := range []string{pair.read, pair.write} {
					opened, err := openCounter(controller.device, eventNames[i], event, controller.kind, cpuID, open)
					if err != nil {
						return nil, err
					}
					collector.counters = append(collector.counters, opened)
				}
			}
		}
	}

	if len(collector.counters) == 0 {
		return nil, fmt.Errorf(
			"no memory controller at %s publishes a usable read/write counter pair", sysfsGlob)
	}

	for i := range collector.counters {
		if _, err := collector.counters[i].prime(); err != nil {
			return nil, err
		}
	}

	collector.sampled = collector.now()

	return collector, nil
}

// discoverEvents prefers an aggregate pair; otherwise every advertised DDR
// subchannel must have both directions. Never add subchannels to an aggregate.
func discoverEvents(device string) ([]eventPair, bool, error) {
	entries, err := os.ReadDir(filepath.Join(device, "events"))
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("discovering events on %s: %w", device, err)
	}
	names := make(map[string]bool, len(entries))
	for _, entry := range entries {
		names[entry.Name()] = true
	}
	partial := false
	for _, pair := range eventPairs {
		if names[pair.read] && names[pair.write] {
			return []eventPair{pair}, true, nil
		}
		partial = partial || names[pair.read] || names[pair.write]
	}
	channels := make(map[int]eventPair)
	for name := range names {
		for _, direction := range eventNames {
			suffix, found := strings.CutPrefix(name, "cas_count_"+direction+"_sch")
			if !found || strings.Contains(suffix, ".") {
				continue
			}
			index, err := strconv.ParseUint(suffix, 10, 16)
			if err != nil || strconv.FormatUint(index, 10) != suffix {
				return nil, false, fmt.Errorf("invalid memory subchannel event %s on %s", name, device)
			}
			pair := channels[int(index)]
			if direction == "read" {
				pair.read = name
			} else {
				pair.write = name
			}
			channels[int(index)] = pair
		}
	}
	if len(channels) > 0 {
		indices := make([]int, 0, len(channels))
		for index := range channels {
			indices = append(indices, index)
		}
		slices.Sort(indices)
		pairs := make([]eventPair, 0, len(indices))
		for _, index := range indices {
			pair := channels[index]
			if pair.read == "" || pair.write == "" {
				return nil, false, fmt.Errorf("incomplete memory read/write counter pair for subchannel %d on %s", index, device)
			}
			pairs = append(pairs, pair)
		}
		return pairs, true, nil
	}
	if partial {
		return nil, false, fmt.Errorf("incomplete memory read/write counter pair on %s", device)
	}
	return nil, false, nil
}

func controllerCPUs(device string) ([]int, error) {
	path := filepath.Join(device, "cpumask")
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading PMU CPU affinity: %w", err)
	}
	// Unlike a hexadecimal bitmap, Intel uncore cpumask is a decimal cpulist.
	for _, part := range strings.Split(strings.TrimSpace(string(raw)), ",") {
		if strings.TrimSpace(part) == "" {
			return nil, fmt.Errorf("empty PMU CPU affinity entry in %s", path)
		}
	}
	cpus, err := cpu.ParseCPUList(string(raw))
	if err != nil {
		return nil, fmt.Errorf("invalid PMU CPU affinity in %s: %w", path, err)
	}
	slices.Sort(cpus)
	return slices.Compact(cpus), nil
}

// openCounter opens one event of one controller.
func openCounter(device, canonical, event string, pmuType uint32, cpuID int, open perfOpener) (counter, error) {
	config, err := readConfig(filepath.Join(device, "events", event))
	if err != nil {
		return counter{}, err
	}

	if err := checkUnit(device, event); err != nil {
		return counter{}, err
	}

	scale, err := readFloat(filepath.Join(device, "events", event+".scale"))
	if err != nil {
		return counter{}, err
	}
	if scale <= 0 || math.IsNaN(scale) || math.IsInf(scale, 0) {
		return counter{}, fmt.Errorf("invalid scale for %s on %s: must be positive and finite", event, device)
	}

	attr := unix.PerfEventAttr{
		Type:   pmuType,
		Size:   uint32(unsafeSizeofPerfEventAttr),
		Config: config,
		// Refuse multiplexed undercounts; an unschedulable pinned event reads EOF.
		Bits: unix.PerfBitPinned,
	}

	fd, err := open(&attr, -1, cpuID, -1, unix.PERF_FLAG_FD_CLOEXEC)
	if err != nil {
		return counter{}, fmt.Errorf(
			"cannot open %s on %s CPU %d: %w (check CPU availability and perf permissions, including CAP_PERFMON)",
			event, filepath.Base(device), cpuID, err)
	}

	return counter{
		canonical: canonical,
		event:     event,
		device:    filepath.Base(device),
		cpu:       cpuID,
		scale:     scale,
		fd:        fd,
	}, nil
}

// checkUnit refuses a counter that does not measure what the field names
// promise.
//
// Where sysfs publishes no unit at all the counter is accepted: older parts
// omit the file, and the scale still says how to convert it.
func checkUnit(device, event string) error {
	raw, err := os.ReadFile(filepath.Join(device, "events", event+".unit"))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("reading unit for %s on %s: %w", event, device, err)
	}

	if unit := strings.TrimSpace(string(raw)); unit != expectedUnit {
		return fmt.Errorf("%s on %s is measured in %q, want %q",
			event, filepath.Base(device), unit, expectedUnit)
	}

	return nil
}

// unsafeSizeofPerfEventAttr is the size the kernel expects in attr.Size. The
// constant provided by the unix package is the authority on it.
const unsafeSizeofPerfEventAttr = unix.PERF_ATTR_SIZE_VER1

// Collect returns read and write throughput since the previous call.
func (c *Collector) Collect() ([]lineproto.Point, error) {
	now := c.now()
	elapsed := now.Sub(c.sampled).Seconds()
	raw := make([]uint64, len(c.counters))
	var baselineError error
	if elapsed <= 0 {
		baselineError = fmt.Errorf("non-positive memory bandwidth interval; resetting all counter baselines")
	}
	for i := range c.counters {
		counter := &c.counters[i]
		value, err := counter.read()
		if err != nil {
			return nil, err
		}
		raw[i] = value
		if !counter.primed || value < counter.previous {
			baselineError = fmt.Errorf("counter %s on %s CPU %d reset, wrapped or unprimed; resetting all counter baselines",
				counter.event, counter.device, counter.cpu)
		}
	}
	// Commit only a complete snapshot. A failed read leaves every baseline and
	// its timestamp untouched, so recovery spans the same interval on all dies.
	totals := make(map[string]float64, len(eventNames))
	for i := range c.counters {
		counter := &c.counters[i]
		if baselineError == nil {
			totals[counter.canonical] += float64(raw[i]-counter.previous) * counter.scale * (1 << 20) / elapsed
		}
		counter.previous, counter.primed = raw[i], true
	}
	c.sampled = now
	if baselineError != nil {
		return nil, baselineError
	}

	fields := make([]lineproto.Field, 0, len(eventNames)+1)
	total := 0.0
	for _, event := range eventNames {
		fields = append(fields, lineproto.FloatField(fieldName(event), totals[event]))
		total += totals[event]
	}
	fields = append(fields, lineproto.FloatField("total_bytes_per_second", total))

	return []lineproto.Point{{
		Measurement: Measurement,
		Tags:        []lineproto.Tag{{Key: "host", Value: c.hostname}},
		Fields:      fields,
		Timestamp:   now,
	}}, nil
}

// fieldName turns a canonical counter name into a field name carrying its
// unit. It is built from the canonical name rather than the sysfs one, so the
// endpoint looks the same whichever spelling the machine uses.
func fieldName(canonical string) string {
	return canonical + "_bytes_per_second"
}

// prime takes the first reading, which later deltas are measured against.
func (c *counter) prime() (uint64, error) {
	raw, err := c.read()
	if err != nil {
		return 0, err
	}

	c.previous, c.primed = raw, true

	return raw, nil
}

// read returns the current value of the counter.
func (c *counter) read() (uint64, error) {
	var buf [8]byte

	n, err := unix.Read(c.fd, buf[:])
	if err != nil {
		return 0, fmt.Errorf("reading %s on %s CPU %d: %w", c.event, c.device, c.cpu, err)
	}
	if n != len(buf) {
		return 0, fmt.Errorf("reading %s on %s CPU %d: got %d bytes, want %d (check PMU scheduling and CPU availability)",
			c.event, c.device, c.cpu, n, len(buf))
	}

	return uint64(buf[0]) | uint64(buf[1])<<8 | uint64(buf[2])<<16 | uint64(buf[3])<<24 |
		uint64(buf[4])<<32 | uint64(buf[5])<<40 | uint64(buf[6])<<48 | uint64(buf[7])<<56, nil
}

// Close releases the perf file descriptors.
func (c *Collector) Close() error {
	var errs []error
	for _, counter := range c.counters {
		if err := unix.Close(counter.fd); err != nil {
			errs = append(errs, fmt.Errorf("closing %s on %s CPU %d: %w",
				counter.event, counter.device, counter.cpu, err))
		}
	}
	c.counters = nil

	return errors.Join(errs...)
}

// readConfig parses an event definition such as "event=0xff,umask=0x20" into
// the config word perf_event_open expects.
//
// The layout is the PMU's own: the event selector occupies the low byte and
// the unit mask the next one. Both are what sysfs publishes, so nothing here
// is hard-coded per model.
func readConfig(path string) (uint64, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("reading event definition: %w", err)
	}

	var config uint64
	for _, part := range strings.Split(strings.TrimSpace(string(raw)), ",") {
		key, value, found := strings.Cut(part, "=")
		if !found {
			continue
		}

		number, err := strconv.ParseUint(strings.TrimPrefix(strings.TrimSpace(value), "0x"), 16, 64)
		if err != nil {
			return 0, fmt.Errorf("event definition %q: %w", part, err)
		}

		switch strings.TrimSpace(key) {
		case "event":
			config |= number
		case "umask":
			config |= number << 8
		default:
			return 0, fmt.Errorf("event definition %q: unsupported field %q", raw, key)
		}
	}

	if config == 0 {
		return 0, fmt.Errorf("event definition %q names no event", raw)
	}

	return config, nil
}

func readUint(path string) (uint64, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("reading %s: %w", path, err)
	}

	return strconv.ParseUint(strings.TrimSpace(string(raw)), 10, 32)
}

func readFloat(path string) (float64, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("reading %s: %w", path, err)
	}

	return strconv.ParseFloat(strings.TrimSpace(string(raw)), 64)
}
