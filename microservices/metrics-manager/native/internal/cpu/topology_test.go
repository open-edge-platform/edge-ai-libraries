// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// writeFile creates path and all of its parent directories.
func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("MkdirAll(%s): %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("WriteFile(%s): %v", path, err)
	}
}

func TestParseCPUList(t *testing.T) {
	tests := []struct {
		name    string
		raw     string
		want    []int
		wantErr bool
	}{
		{name: "single range", raw: "0-11\n", want: []int{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}},
		{name: "single id", raw: "7", want: []int{7}},
		{name: "mixed ids and ranges", raw: "0,2-3,8\n", want: []int{0, 2, 3, 8}},
		{name: "one element range", raw: "5-5", want: []int{5}},
		{name: "empty", raw: "\n", want: nil},
		{name: "non numeric", raw: "abc", wantErr: true},
		{name: "reversed range", raw: "8-2", wantErr: true},
		{name: "negative", raw: "-3", wantErr: true},
		{name: "oversized expansion", raw: "0-65536", wantErr: true},
		{name: "oversized repeated ranges", raw: "0-32768,0-32768", wantErr: true},
		{name: "CPU ID overflow", raw: "2147483648", wantErr: true},
		{name: "integer overflow", raw: "0-9223372036854775807", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseCPUList(tt.raw)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("ParseCPUList(%q) = %v, want an error", tt.raw, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("ParseCPUList(%q) error: %v", tt.raw, err)
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("ParseCPUList(%q) = %v, want %v", tt.raw, got, tt.want)
			}
		})
	}
}

func TestParseCPUListBounds(t *testing.T) {
	cpus, err := ParseCPUList("0-65535")
	if err != nil || len(cpus) != 65536 || cpus[0] != 0 || cpus[65535] != 65535 {
		t.Fatalf("maximum expansion = %d entries, %v", len(cpus), err)
	}
	cpus, err = ParseCPUList("2147483647")
	if err != nil || len(cpus) != 1 || cpus[0] != 2147483647 {
		t.Fatalf("maximum CPU ID = %v, %v", cpus, err)
	}
	if _, err := ParseCPUList(strings.Repeat(" ", (1<<20)+1)); err == nil {
		t.Fatal("oversized cpulist was accepted")
	}
}

func TestDetectTopologyHybrid(t *testing.T) {
	// Mirrors a real Intel hybrid CPU: 12 P threads and 10 E cores.
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "devices/cpu_core/cpus"), "0-11\n")
	writeFile(t, filepath.Join(root, "devices/cpu_atom/cpus"), "12-21\n")

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}
	if !topology.Hybrid {
		t.Error("Hybrid = false, want true")
	}
	if len(topology.Classes) != 2 {
		t.Fatalf("got %d classes, want 2", len(topology.Classes))
	}
	if topology.Classes[0].Class != ClassP || len(topology.Classes[0].CPUs) != 12 {
		t.Errorf("first class = %v with %d CPUs, want P with 12",
			topology.Classes[0].Class, len(topology.Classes[0].CPUs))
	}
	if topology.Classes[1].Class != ClassE || len(topology.Classes[1].CPUs) != 10 {
		t.Errorf("second class = %v with %d CPUs, want E with 10",
			topology.Classes[1].Class, len(topology.Classes[1].CPUs))
	}
}

func TestDetectTopologyReportsLowPowerCores(t *testing.T) {
	// Kernels that expose the low power island report a third PMU directory.
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "devices/cpu_core/cpus"), "0-7")
	writeFile(t, filepath.Join(root, "devices/cpu_atom/cpus"), "8-11")
	writeFile(t, filepath.Join(root, "devices/cpu_lowpower/cpus"), "12-13")

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}

	want := []ClassCPUs{
		{Class: ClassP, CPUs: []int{0, 1, 2, 3, 4, 5, 6, 7}, Source: SourcePMU},
		{Class: ClassE, CPUs: []int{8, 9, 10, 11}, Source: SourcePMU},
		{Class: ClassLPE, CPUs: []int{12, 13}, Source: SourcePMU},
	}
	if !reflect.DeepEqual(topology.Classes, want) {
		t.Errorf("Classes = %+v, want %+v", topology.Classes, want)
	}
}

func TestDetectTopologyFallsBackToOnlineCPUs(t *testing.T) {
	// A non-hybrid CPU exports no per-class PMU directories. Reporting a
	// single "core" class keeps the measurement shape identical everywhere.
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "devices/system/cpu/online"), "0-3\n")

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}
	if topology.Hybrid {
		t.Error("Hybrid = true, want false")
	}
	want := []ClassCPUs{{Class: ClassAll, CPUs: []int{0, 1, 2, 3}, Source: SourcePMU}}
	if !reflect.DeepEqual(topology.Classes, want) {
		t.Errorf("Classes = %+v, want %+v", topology.Classes, want)
	}
}

func TestDetectTopologyFailsWithoutAnySource(t *testing.T) {
	if _, err := DetectTopology(t.TempDir()); err == nil {
		t.Error("DetectTopology() succeeded on an empty sysfs, want an error")
	}
}

func TestCPUIDFromPath(t *testing.T) {
	tests := []struct {
		path   string
		want   int
		wantOK bool
	}{
		{path: "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", want: 0, wantOK: true},
		{path: "/sys/devices/system/cpu/cpu12/cpufreq/scaling_cur_freq", want: 12, wantOK: true},
		// "cpu_core" and "cpufreq" must not be mistaken for a CPU id.
		{path: "/sys/devices/cpu_core/cpus", wantOK: false},
		{path: "/sys/devices/system/cpu/cpufreq/policy0", wantOK: false},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			got, ok := cpuIDFromPath(tt.path)
			if ok != tt.wantOK {
				t.Fatalf("cpuIDFromPath(%q) ok = %v, want %v", tt.path, ok, tt.wantOK)
			}
			if ok && got != tt.want {
				t.Errorf("cpuIDFromPath(%q) = %d, want %d", tt.path, got, tt.want)
			}
		})
	}
}

func TestMeanFrequencyUsesIntegerDivision(t *testing.T) {
	// The shell script this collector replaces sums integers and divides with
	// the shell's integer arithmetic. Matching that exactly keeps the emitted
	// value byte-identical.
	frequencies := map[int]uint64{0: 1000, 1: 1001, 2: 1001}

	got, ok := meanFrequency(frequencies, nil)
	if !ok {
		t.Fatal("meanFrequency() reported no data")
	}
	if want := uint64(1000); got != want {
		t.Errorf("meanFrequency() = %d, want %d (truncated, not rounded)", got, want)
	}

	if _, ok := meanFrequency(frequencies, []int{7, 8}); ok {
		t.Error("meanFrequency() reported data for CPUs that have no frequency")
	}
}

func TestReadProcStat(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "stat"), `cpu  100 200 300 400 500 600 700 800 0 0
cpu0 1 2 3 4 5 6 7 8 0 0
cpu1 10 20 30 40 50 60 70 80 0 0
intr 12345
ctxt 999
`)

	times, err := readProcStat(root)
	if err != nil {
		t.Fatalf("readProcStat() error: %v", err)
	}
	if len(times) != 2 {
		t.Fatalf("got %d CPUs, want 2 (the aggregate line must be skipped)", len(times))
	}
	if got, want := times[0].total(), uint64(1+2+3+4+5+6+7+8); got != want {
		t.Errorf("cpu0 total = %d, want %d", got, want)
	}
	if got, want := times[1].system, uint64(30); got != want {
		t.Errorf("cpu1 system = %d, want %d", got, want)
	}
}

func TestReadProcStatRejectsFileWithoutPerCPULines(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "stat"), "cpu 1 2 3 4 5 6 7 8\nintr 1\n")

	if _, err := readProcStat(root); err == nil {
		t.Error("readProcStat() succeeded, want an error when no per-CPU lines exist")
	}
}

func TestCPUTimesSubDetectsCounterReset(t *testing.T) {
	before := cpuTimes{user: 100, idle: 100}
	after := cpuTimes{user: 10, idle: 100}

	if _, ok := after.sub(before); ok {
		t.Error("sub() accepted a counter that went backwards; a CPU that was " +
			"offlined and brought back would produce a bogus delta")
	}
}
