// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"fmt"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"
)

// fakeSystem builds a sysfs/procfs pair describing a hybrid CPU with the given
// per-CPU frequencies, and returns the two roots.
func fakeSystem(t *testing.T, pCPUs, eCPUs []int, freqKHz map[int]uint64, stat string) (sysfsRoot, procRoot string) {
	t.Helper()

	sysfsRoot = t.TempDir()
	procRoot = t.TempDir()

	writeFile(t, filepath.Join(sysfsRoot, "devices/cpu_core/cpus"), cpuList(pCPUs))
	writeFile(t, filepath.Join(sysfsRoot, "devices/cpu_atom/cpus"), cpuList(eCPUs))

	for id, khz := range freqKHz {
		writeFile(t,
			filepath.Join(sysfsRoot, fmt.Sprintf("devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq", id)),
			fmt.Sprintf("%d\n", khz))
	}
	writeFile(t, filepath.Join(procRoot, "stat"), stat)

	return sysfsRoot, procRoot
}

func cpuList(cpus []int) string {
	parts := make([]string, 0, len(cpus))
	for _, id := range cpus {
		parts = append(parts, fmt.Sprint(id))
	}
	return strings.Join(parts, ",")
}

// procStat renders a /proc/stat where every listed CPU has the same counters.
func procStat(cpus []int, user, system, idle uint64) string {
	var b strings.Builder
	b.WriteString("cpu  0 0 0 0 0 0 0 0 0 0\n")
	for _, id := range cpus {
		fmt.Fprintf(&b, "cpu%d %d 0 %d %d 0 0 0 0 0 0\n", id, user, system, idle)
	}
	return b.String()
}

// collect renders one Collect() call as the plugin would write it to stdout.
func collect(t *testing.T, c *Collector) string {
	t.Helper()

	points, err := c.Collect()
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}

	var out []byte
	for _, point := range points {
		out, err = point.Append(out)
		if err != nil {
			t.Fatalf("rendering point %q: %v", point.Measurement, err)
		}
	}
	return string(out)
}

func TestCollectorEmitsFrequencyAndPerClassUsage(t *testing.T) {
	pCPUs, eCPUs := []int{0, 1}, []int{2, 3}
	all := append(append([]int{}, pCPUs...), eCPUs...)

	// P cores run at 4 GHz, E cores at 2 GHz, so the overall mean is 3 GHz.
	frequencies := map[int]uint64{0: 4000000, 1: 4000000, 2: 2000000, 3: 2000000}

	sysfsRoot, procRoot := fakeSystem(t, pCPUs, eCPUs, frequencies,
		procStat(all, 100, 100, 800))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}
	collector.now = func() time.Time { return time.Unix(0, 1725062400000000000) }

	// Advance the counters by 25 user, 25 system and 50 idle jiffies, so the
	// interval totals 100 jiffies and the percentages are exact.
	writeFile(t, filepath.Join(procRoot, "stat"), procStat(all, 125, 125, 850))

	want := strings.Join([]string{
		"cpu_frequency_avg frequency_hz=3000000000",
		"cpu_core_class,class=P,source=pmu cores=2i,frequency_avg_hz=4000000000,usage_user=25,usage_system=25,usage_idle=50 1725062400000000000",
		"cpu_core_class,class=E,source=pmu cores=2i,frequency_avg_hz=2000000000,usage_user=25,usage_system=25,usage_idle=50 1725062400000000000",
		// The fake proc tree has no cpuinfo or osrelease, which is what an
		// unreadable value looks like: named as unknown rather than dropped.
		"platform,model=unknown,kernel=unknown,arch=" + runtime.GOARCH +
			" logical_cpus=" + strconv.Itoa(runtime.NumCPU()) + "i 1725062400000000000",
		"",
	}, "\n")

	if got := collect(t, collector); got != want {
		t.Errorf("Collect()\n got:\n%s\nwant:\n%s", got, want)
	}
}

func TestCollectorFrequencyAveragePreservesShapeWithHz(t *testing.T) {
	// Only the field name and scale change; tags, arrival-time stamping
	// and the floating-point field type remain as before.
	pCPUs, eCPUs := []int{0}, []int{1}
	sysfsRoot, procRoot := fakeSystem(t, pCPUs, eCPUs,
		map[int]uint64{0: 3000000, 1: 1000001},
		procStat([]int{0, 1}, 1, 1, 1))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}
	if points[0].Measurement != MeasurementFrequencyAvg {
		t.Fatalf("first point is %q, want %q", points[0].Measurement, MeasurementFrequencyAvg)
	}

	line, err := points[0].Append(nil)
	if err != nil {
		t.Fatalf("Append() error: %v", err)
	}
	// (3000000 + 1000001) / 2 == 2000000 with integer division.
	if want := "cpu_frequency_avg frequency_hz=2000000000\n"; string(line) != want {
		t.Errorf("line = %q, want %q", line, want)
	}
}

func TestCollectorOmitsFrequencyWhenCpufreqIsUnavailable(t *testing.T) {
	// Virtual machines commonly expose no cpufreq driver at all. The collector
	// must still report utilisation instead of failing.
	sysfsRoot, procRoot := fakeSystem(t, []int{0}, []int{1}, nil,
		procStat([]int{0, 1}, 10, 10, 80))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}
	writeFile(t, filepath.Join(procRoot, "stat"), procStat([]int{0, 1}, 20, 20, 160))

	got := collect(t, collector)
	if strings.Contains(got, MeasurementFrequencyAvg) {
		t.Errorf("output contains %s despite no cpufreq data:\n%s", MeasurementFrequencyAvg, got)
	}
	if !strings.Contains(got, "usage_user=") {
		t.Errorf("output is missing utilisation fields:\n%s", got)
	}
	if strings.Contains(got, "frequency_avg_hz=") {
		t.Errorf("output contains a per-class frequency despite no cpufreq data:\n%s", got)
	}
}

func TestCollectorOmitsUsageWhenCountersDidNotAdvance(t *testing.T) {
	// Two samples taken within the same jiffy produce a zero denominator.
	// Reporting no utilisation is correct; reporting NaN would poison the
	// whole Telegraf batch.
	sysfsRoot, procRoot := fakeSystem(t, []int{0}, []int{1}, nil,
		procStat([]int{0, 1}, 10, 10, 80))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}

	got := collect(t, collector)
	if strings.Contains(got, "usage_") {
		t.Errorf("output contains utilisation fields for a zero-length interval:\n%s", got)
	}
	if !strings.Contains(got, "cores=1i") {
		t.Errorf("output is missing the core count:\n%s", got)
	}
}

func TestCollectorUsesConsecutiveDeltas(t *testing.T) {
	// The second interval must be measured against the first sample, not
	// against the process start, otherwise utilisation would slowly converge
	// to a long-run average instead of tracking the current load.
	cpus := []int{0}
	sysfsRoot, procRoot := fakeSystem(t, cpus, nil, nil, procStat(cpus, 0, 0, 100))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}

	// Interval 1: fully idle.
	writeFile(t, filepath.Join(procRoot, "stat"), procStat(cpus, 0, 0, 200))
	if got := collect(t, collector); !strings.Contains(got, "usage_idle=100") {
		t.Fatalf("first interval should be fully idle, got:\n%s", got)
	}

	// Interval 2: fully busy.
	writeFile(t, filepath.Join(procRoot, "stat"), procStat(cpus, 100, 0, 200))
	got := collect(t, collector)
	if !strings.Contains(got, "usage_user=100") {
		t.Errorf("second interval should be fully busy, got:\n%s", got)
	}
}

func TestCollectorSkipsCPUsThatWentOffline(t *testing.T) {
	cpus := []int{0, 1}
	sysfsRoot, procRoot := fakeSystem(t, cpus, nil, nil, procStat(cpus, 0, 0, 100))

	collector, err := NewCollector(sysfsRoot, procRoot)
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}

	// cpu1 disappears from /proc/stat; cpu0 becomes fully busy.
	writeFile(t, filepath.Join(procRoot, "stat"),
		"cpu  0 0 0 0 0 0 0 0 0 0\ncpu0 100 0 0 100 0 0 0 0 0 0\n")

	got := collect(t, collector)
	if !strings.Contains(got, "cores=2i") {
		t.Errorf("core count should still reflect the topology, got:\n%s", got)
	}
	if !strings.Contains(got, "usage_user=100") {
		t.Errorf("utilisation should be derived from the CPUs still reporting, got:\n%s", got)
	}
}
