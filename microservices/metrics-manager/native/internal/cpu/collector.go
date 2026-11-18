// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package cpu collects CPU frequency and per-core-class utilisation from the
// kernel's procfs and sysfs interfaces.
//
// It emits two measurements:
//
//	cpu_frequency_avg  the mean scaling_cur_freq across every CPU, in Hz.
//
//	cpu_core_class     the same frequency plus utilisation, broken down by
//	                   core class (P / E / LPE) on Intel hybrid CPUs.
//
// Nothing here executes a subprocess or opens a socket; the collector only
// reads well-known kernel files.
package cpu

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// Measurement names. These are part of the service's public contract: they
// appear in the Prometheus output, in Grafana dashboards and in the TUI's
// dashboard.json, so they must not be renamed casually.
const (
	MeasurementFrequencyAvg = "cpu_frequency_avg"
	MeasurementCoreClass    = "cpu_core_class"
)

// cpuTimes holds the jiffy counters of a single CPU as reported by /proc/stat.
type cpuTimes struct {
	user, nice, system, idle, iowait, irq, softirq, steal uint64
}

func (t cpuTimes) total() uint64 {
	return t.user + t.nice + t.system + t.idle + t.iowait + t.irq + t.softirq + t.steal
}

// sub returns t-other, and false if any counter went backwards.
//
// Counters reset when a CPU is taken offline and brought back, which would
// otherwise underflow into an enormous bogus delta.
func (t cpuTimes) sub(other cpuTimes) (cpuTimes, bool) {
	if t.user < other.user || t.nice < other.nice || t.system < other.system ||
		t.idle < other.idle || t.iowait < other.iowait || t.irq < other.irq ||
		t.softirq < other.softirq || t.steal < other.steal {
		return cpuTimes{}, false
	}
	return cpuTimes{
		user:    t.user - other.user,
		nice:    t.nice - other.nice,
		system:  t.system - other.system,
		idle:    t.idle - other.idle,
		iowait:  t.iowait - other.iowait,
		irq:     t.irq - other.irq,
		softirq: t.softirq - other.softirq,
		steal:   t.steal - other.steal,
	}, true
}

// Collector produces CPU metrics. It is stateful: utilisation is derived from
// the delta between consecutive samples, so a single instance must be reused
// across the whole lifetime of the process.
//
// A Collector is not safe for concurrent use.
type Collector struct {
	sysfsRoot string
	procRoot  string
	topology  Topology
	prev      map[int]cpuTimes

	// platform describes the machine. It is read once, because the model
	// name and the kernel release do not change while the process runs, and
	// re-reading /proc/cpuinfo every second would be waste.
	platform lineproto.Point

	// now is overridden by tests to make emitted timestamps deterministic.
	now func() time.Time
}

// NewCollector detects the core-class topology and takes a first utilisation
// sample so that the very first Collect already reports a real delta.
func NewCollector(sysfsRoot, procRoot string) (*Collector, error) {
	topology, err := DetectTopology(sysfsRoot)
	if err != nil {
		return nil, fmt.Errorf("detecting CPU topology: %w", err)
	}

	prev, err := readProcStat(procRoot)
	if err != nil {
		return nil, fmt.Errorf("reading %s/stat: %w", procRoot, err)
	}

	return &Collector{
		sysfsRoot: sysfsRoot,
		procRoot:  procRoot,
		topology:  topology,
		prev:      prev,
		platform:  PlatformPoint(procRoot),
		now:       time.Now,
	}, nil
}

// Topology exposes the detected layout, for logging at start-up.
func (c *Collector) Topology() Topology { return c.topology }

// Collect samples the current state and returns the points to emit.
//
// Missing data degrades gracefully: a machine without cpufreq (a VM, for
// example) simply yields no frequency fields rather than an error.
func (c *Collector) Collect() ([]lineproto.Point, error) {
	timestamp := c.now()

	frequencies, err := c.readFrequencies()
	if err != nil {
		return nil, err
	}

	current, err := readProcStat(c.procRoot)
	if err != nil {
		return nil, fmt.Errorf("reading %s/stat: %w", c.procRoot, err)
	}

	points := make([]lineproto.Point, 0, len(c.topology.Classes)+2)

	// Preserve arrival-time stamping for the overall average.
	if avg, ok := meanFrequency(frequencies, nil); ok {
		points = append(points, lineproto.Point{
			Measurement: MeasurementFrequencyAvg,
			Fields:      []lineproto.Field{lineproto.FloatField("frequency_hz", float64(avg)*1e3)},
		})
	}

	for _, class := range c.topology.Classes {
		fields := []lineproto.Field{lineproto.IntField("cores", int64(len(class.CPUs)))}

		if avg, ok := meanFrequency(frequencies, class.CPUs); ok {
			fields = append(fields, lineproto.FloatField("frequency_avg_hz", float64(avg)*1e3))
		}
		fields = append(fields, c.usageFields(class.CPUs, current)...)

		// The `source` tag distinguishes a class the kernel reported itself
		// from one inferred by inferLowPowerCores, so a dashboard never has to
		// take an inferred LP-E split on trust.
		points = append(points, lineproto.Point{
			Measurement: MeasurementCoreClass,
			Tags: []lineproto.Tag{
				{Key: "class", Value: string(class.Class)},
				{Key: "source", Value: string(class.Source)},
			},
			Fields:    fields,
			Timestamp: timestamp,
		})
	}

	// What the machine is, restated every interval so a scrape that starts
	// late still learns it. It goes last so the readings above keep the order
	// the shell script this collector replaced produced them in.
	platform := c.platform
	platform.Timestamp = timestamp
	points = append(points, platform)

	c.prev = current
	return points, nil
}

// usageFields aggregates the jiffy deltas of the given CPUs into percentages.
// It returns no fields when there is nothing meaningful to report yet, which
// is the case if every CPU in the class was offline or reset its counters.
func (c *Collector) usageFields(cpus []int, current map[int]cpuTimes) []lineproto.Field {
	var delta cpuTimes

	for _, id := range cpus {
		now, sampled := current[id]
		before, seen := c.prev[id]
		if !sampled || !seen {
			continue
		}
		diff, ok := now.sub(before)
		if !ok {
			continue
		}
		delta.user += diff.user
		delta.nice += diff.nice
		delta.system += diff.system
		delta.idle += diff.idle
		delta.iowait += diff.iowait
		delta.irq += diff.irq
		delta.softirq += diff.softirq
		delta.steal += diff.steal
	}

	total := delta.total()
	if total == 0 {
		return nil
	}

	percent := func(part uint64) float64 { return 100 * float64(part) / float64(total) }

	// The field set mirrors the `fieldinclude` of Telegraf's own inputs.cpu so
	// that per-class and total CPU usage can be compared directly.
	return []lineproto.Field{
		lineproto.FloatField("usage_user", percent(delta.user)),
		lineproto.FloatField("usage_system", percent(delta.system)),
		lineproto.FloatField("usage_idle", percent(delta.idle)),
	}
}

// readFrequencies returns the current scaling frequency, in kHz, per CPU id.
//
// The glob deliberately matches the one used by the shell script this
// collector replaces, so both see exactly the same set of CPUs.
func (c *Collector) readFrequencies() (map[int]uint64, error) {
	pattern := filepath.Join(c.sysfsRoot, "devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil, fmt.Errorf("globbing %s: %w", pattern, err)
	}

	frequencies := make(map[int]uint64, len(matches))
	for _, path := range matches {
		id, ok := cpuIDFromPath(path)
		if !ok {
			continue
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			// A CPU can go offline between the glob and the read, and some
			// drivers return EINVAL for idle cores. Neither is fatal.
			continue
		}
		khz, err := strconv.ParseUint(strings.TrimSpace(string(raw)), 10, 64)
		if err != nil {
			continue
		}
		frequencies[id] = khz
	}

	return frequencies, nil
}

// meanFrequency averages the frequencies of the given CPUs, or of every CPU
// when cpus is nil. Integer division is used to match the shell script.
func meanFrequency(frequencies map[int]uint64, cpus []int) (uint64, bool) {
	var sum uint64
	var count uint64

	if cpus == nil {
		for _, khz := range frequencies {
			sum += khz
			count++
		}
	} else {
		for _, id := range cpus {
			khz, ok := frequencies[id]
			if !ok {
				continue
			}
			sum += khz
			count++
		}
	}

	if count == 0 {
		return 0, false
	}
	return sum / count, true
}

// cpuIDFromPath extracts the logical CPU id from a path containing a "cpuN"
// component, for example ".../cpu/cpu12/cpufreq/scaling_cur_freq".
func cpuIDFromPath(path string) (int, bool) {
	for _, part := range strings.Split(path, string(os.PathSeparator)) {
		suffix, found := strings.CutPrefix(part, "cpu")
		if !found || suffix == "" {
			continue
		}
		if id, err := strconv.Atoi(suffix); err == nil {
			return id, true
		}
	}
	return 0, false
}

// readProcStat parses the per-CPU lines of /proc/stat. The aggregate "cpu"
// line is skipped: totals are recomputed per class instead.
func readProcStat(procRoot string) (map[int]cpuTimes, error) {
	raw, err := os.ReadFile(filepath.Join(procRoot, "stat"))
	if err != nil {
		return nil, err
	}

	times := make(map[int]cpuTimes)
	for _, line := range strings.Split(string(raw), "\n") {
		fields := strings.Fields(line)
		if len(fields) < 9 || !strings.HasPrefix(fields[0], "cpu") {
			continue
		}
		id, err := strconv.Atoi(strings.TrimPrefix(fields[0], "cpu"))
		if err != nil {
			continue // the aggregate "cpu" line
		}

		values := make([]uint64, 8)
		malformed := false
		for i := range values {
			if values[i], err = strconv.ParseUint(fields[i+1], 10, 64); err != nil {
				malformed = true
				break
			}
		}
		if malformed {
			continue
		}

		times[id] = cpuTimes{
			user:    values[0],
			nice:    values[1],
			system:  values[2],
			idle:    values[3],
			iowait:  values[4],
			irq:     values[5],
			softirq: values[6],
			steal:   values[7],
		}
	}

	if len(times) == 0 {
		return nil, fmt.Errorf("no per-CPU lines found")
	}
	return times, nil
}
