// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package npu

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// Measurement is the single measurement this collector emits. It is part of
// the service's public contract and must not be renamed.
const Measurement = "npu"

// Collector samples NPU telemetry once per call.
//
// It is stateful: power, bandwidth and utilisation are deltas between
// consecutive samples, so one instance must live for the whole process.
//
// A Collector is not safe for concurrent use.
type Collector struct {
	telemetry *Telemetry
	hostname  string

	// Paths are empty when the driver does not expose the corresponding
	// attribute. These sysfs files are world-readable
	// where they exist, unlike the PMT region the rest of the telemetry
	// comes from.
	busyPath       string
	memoryPath     string
	maxFreqPath    string
	powerStatePath string

	prevEnergy    float64
	prevBandwidth float64
	prevBusyUS    uint64
	hasPrevBusy   bool
	prevTime      time.Time

	// now is overridden by tests to make elapsed time deterministic.
	now func() time.Time
}

// NewCollector opens the PMT device, locates the NPU PCI device and primes the
// delta counters.
//
// An error here means the machine has no usable Intel NPU. Callers should idle
// rather than exit, so Telegraf does not respawn the plugin in a tight loop.
func NewCollector(sysfsRoot, hostname string) (*Collector, error) {
	telemetry, err := Open(sysfsRoot)
	if err != nil {
		return nil, err
	}

	devPath, err := findDevice(sysfsRoot)
	if err != nil {
		return nil, err
	}

	collector := &Collector{
		telemetry: telemetry,
		hostname:  hostname,
		now:       time.Now,
	}

	busyPath := filepath.Join(devPath, "npu_busy_time_us")
	if _, err := os.Stat(busyPath); err == nil {
		collector.busyPath = busyPath
	}

	// Memory utilisation and the frequency ceiling come from the driver
	// rather than from PMT, and are world-readable, so neither needs the
	// privilege the telemetry region does.
	//
	// Presence is the only test applied. An earlier version also required
	// Panther Lake or newer, on the belief that older parts did not expose
	// memory utilisation; a Meteor Lake was then measured publishing
	// npu_memory_utilization with a perfectly good value, which the
	// generation check was discarding in favour of reporting -1. The Stat
	// below is the probe, so nothing is gained by guessing first.
	memoryPath := filepath.Join(devPath, "npu_memory_utilization")
	if _, err := os.Stat(memoryPath); err == nil {
		collector.memoryPath = memoryPath
	}

	maxFreqPath := filepath.Join(devPath, "npu_max_frequency_mhz")
	if _, err := os.Stat(maxFreqPath); err == nil {
		collector.maxFreqPath = maxFreqPath
	}

	powerStatePath := filepath.Join(devPath, "power_state")
	if _, err := os.Stat(powerStatePath); err == nil {
		collector.powerStatePath = powerStatePath
	}

	if err := telemetry.Update(); err != nil {
		return nil, err
	}
	collector.prevEnergy = telemetry.EnergyJoules()
	collector.prevBandwidth = telemetry.BandwidthBytes()
	collector.prevBusyUS, collector.hasPrevBusy = collector.readBusyUS()
	collector.prevTime = collector.now()

	return collector, nil
}

// BusyTimeSupported reports whether utilisation can be measured. When false,
// the utilization field is omitted.
func (c *Collector) BusyTimeSupported() bool { return c.busyPath != "" }

// MemoryUtilisationSupported reports whether NPU memory usage is exposed. When
// false, the memory_bytes field is omitted.
func (c *Collector) MemoryUtilisationSupported() bool { return c.memoryPath != "" }

// Gen reports the detected SoC generation.
func (c *Collector) Gen() CPUGen { return c.telemetry.Gen() }

// Collect takes one sample and returns the point to emit.
func (c *Collector) Collect() ([]lineproto.Point, error) {
	if err := c.telemetry.Update(); err != nil {
		return nil, err
	}

	sampleTime := c.now()
	elapsed := sampleTime.Sub(c.prevTime).Seconds()
	if elapsed <= 0 {
		return nil, fmt.Errorf("NPU sampling interval must be positive, got %s", sampleTime.Sub(c.prevTime))
	}
	c.prevTime = sampleTime

	// Power is the derivative of the energy counter over the interval that
	// actually elapsed, not the nominal one, so scheduling jitter does not
	// distort the reading.
	energy := c.telemetry.EnergyJoules()
	power := (energy - c.prevEnergy) / elapsed
	c.prevEnergy = energy

	bandwidth := c.telemetry.BandwidthBytes()
	bandwidthDelta := bandwidth - c.prevBandwidth
	if bandwidthDelta < 0 {
		bandwidthDelta += float64(uint64(1)<<32) * 1e3
	}
	c.prevBandwidth = bandwidth

	fields := []lineproto.Field{
		lineproto.FloatField("power_w", power),
		lineproto.FloatField("frequency_hz", c.telemetry.FrequencyHz()),
		lineproto.IntField("temperature_c", int64(c.telemetry.TemperatureC())),
		lineproto.FloatField("bandwidth_bytes_per_second", bandwidthDelta/elapsed),
		lineproto.IntField("tile_config", int64(c.telemetry.TileConfig())),
	}
	if utilization, ok := c.utilization(elapsed); ok {
		fields = append(fields, lineproto.IntField("utilization", utilization))
	}
	if memory, ok := c.memoryBytes(); ok {
		fields = append(fields, lineproto.NumberField("memory_bytes", strconv.FormatUint(memory, 10)))
	}
	fields = append(fields, lineproto.IntField("power_state", c.powerState()))

	// The ceiling gives the current frequency a meaning. It is static, so it
	// is omitted rather than reported as zero where the driver does not
	// publish it.
	if maxFreq, ok := c.maxFrequencyMHz(); ok {
		fields = append(fields, lineproto.FloatField("frequency_max_hz", maxFreq*1e6))
	}

	return []lineproto.Point{{
		Measurement: Measurement,
		Tags:        []lineproto.Tag{{Key: "host", Value: c.hostname}},
		Fields:      fields,
		Timestamp:   sampleTime,
	}}, nil
}

// powerState matches the tcmi reader's PCI D-state encoding. -1 means the
// attribute is absent, unreadable or reports an unrecognised state.
func (c *Collector) powerState() int64 {
	if c.powerStatePath == "" {
		return -1
	}
	value, err := os.ReadFile(c.powerStatePath)
	if err != nil {
		return -1
	}
	switch strings.TrimSpace(string(value)) {
	case "D0":
		return 0
	case "D1":
		return 1
	case "D2":
		return 2
	case "D3hot":
		return 3
	case "D3cold":
		return 4
	default:
		return -1
	}
}

// utilization returns the share of the interval the NPU spent busy, as a
// truncated percentage capped at 100.
func (c *Collector) utilization(elapsed float64) (int64, bool) {
	busyUS, ok := c.readBusyUS()
	prevBusyUS, hadPrev := c.prevBusyUS, c.hasPrevBusy
	c.prevBusyUS, c.hasPrevBusy = busyUS, ok

	if !ok || !hadPrev || elapsed <= 0 {
		return 0, false
	}

	// The counter resets when the NPU driver reloads. A negative delta is
	// meaningless, so report idle rather than a large negative number.
	if busyUS < prevBusyUS {
		return 0, true
	}

	percent := 100 * float64(busyUS-prevBusyUS) / (elapsed * 1e6)
	if percent > 100 {
		return 100, true
	}
	return int64(percent), true
}

// memoryBytes returns the driver's byte count without rounding, when available.
func (c *Collector) memoryBytes() (uint64, bool) {
	if c.memoryPath == "" {
		return 0, false
	}
	bytes, err := readUint(c.memoryPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-npu: omitting memory usage:", err)
		return 0, false
	}
	return bytes, true
}

// maxFrequencyMHz returns the frequency ceiling the driver reports, and
// whether it is available at all.
func (c *Collector) maxFrequencyMHz() (float64, bool) {
	if c.maxFreqPath == "" {
		return 0, false
	}

	mhz, err := readUint(c.maxFreqPath)
	if err != nil {
		return 0, false
	}

	return float64(mhz), true
}

// readBusyUS reads the monotonic busy-time counter in microseconds.
func (c *Collector) readBusyUS() (uint64, bool) {
	if c.busyPath == "" {
		return 0, false
	}
	value, err := readUint(c.busyPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "mm-plugin-npu: omitting utilization:", err)
		return 0, false
	}
	return value, true
}

// findDevice locates the PCI device bound to the intel_vpu driver.
func findDevice(sysfsRoot string) (string, error) {
	base := filepath.Join(sysfsRoot, "bus/pci/drivers/intel_vpu")

	entries, err := os.ReadDir(base)
	if err != nil {
		return "", fmt.Errorf("Intel NPU driver intel_vpu is not loaded: %w", err)
	}
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), "0000:") {
			return filepath.Join(base, entry.Name()), nil
		}
	}

	return "", fmt.Errorf("no PCI device bound to intel_vpu under %s", base)
}
