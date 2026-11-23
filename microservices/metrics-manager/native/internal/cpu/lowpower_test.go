// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// cpuSpec describes one logical CPU in a synthetic sysfs tree.
type cpuSpec struct {
	id      int
	maxFreq string // empty means cpufreq exposes nothing for this CPU
	hasL3   bool
	noCache bool // the kernel exposes no cache topology at all
}

// buildSysfs creates a sysfs tree with the given PMU groups and CPUs.
func buildSysfs(t *testing.T, pmuGroups map[string]string, cpus []cpuSpec) string {
	t.Helper()

	root := t.TempDir()
	for dir, cpuList := range pmuGroups {
		writeFile(t, filepath.Join(root, "devices", dir, "cpus"), cpuList)
	}

	for _, spec := range cpus {
		base := filepath.Join(root, "devices/system/cpu", "cpu"+strconv.Itoa(spec.id))
		if spec.maxFreq != "" {
			writeFile(t, filepath.Join(base, "cpufreq/cpuinfo_max_freq"), spec.maxFreq+"\n")
		}
		if spec.noCache {
			continue
		}
		// Every core has L1d, L1i and L2; only cores attached to the ring bus
		// also get an L3 slice.
		writeFile(t, filepath.Join(base, "cache/index0/level"), "1\n")
		writeFile(t, filepath.Join(base, "cache/index1/level"), "1\n")
		writeFile(t, filepath.Join(base, "cache/index2/level"), "2\n")
		if spec.hasL3 {
			writeFile(t, filepath.Join(base, "cache/index3/level"), "3\n")
		}
	}

	return root
}

// meteorLakeCPUs reproduces the layout measured on a Core Ultra 7 165H:
// 12 P threads at two binned frequencies, 8 E cores with L3, and 2 LP-E cores
// without L3 at a much lower maximum frequency.
func meteorLakeCPUs() []cpuSpec {
	var cpus []cpuSpec
	for id := 0; id <= 11; id++ {
		freq := "4700000"
		if id >= 1 && id <= 4 {
			freq = "5000000" // favoured-core binning
		}
		cpus = append(cpus, cpuSpec{id: id, maxFreq: freq, hasL3: true})
	}
	for id := 12; id <= 19; id++ {
		cpus = append(cpus, cpuSpec{id: id, maxFreq: "3800000", hasL3: true})
	}
	for id := 20; id <= 21; id++ {
		cpus = append(cpus, cpuSpec{id: id, maxFreq: "2500000", hasL3: false})
	}
	return cpus
}

func classByName(t *testing.T, topology Topology, want Class) ClassCPUs {
	t.Helper()
	for _, class := range topology.Classes {
		if class.Class == want {
			return class
		}
	}
	t.Fatalf("class %s not found in %v", want, topology.Classes)
	return ClassCPUs{}
}

// findClass reports whether a class was detected, for the cases where its
// absence is the expected outcome.
func findClass(topology Topology, want Class) (ClassCPUs, bool) {
	for _, class := range topology.Classes {
		if class.Class == want {
			return class, true
		}
	}

	return ClassCPUs{}, false
}

// pantherLakeCPUs mirrors a Core Ultra X7 358H as the kernel reports it: four
// P cores whose top bin differs by binning, eight E cores with an L3 slice,
// and four LP-E cores without one whose clocks sit close to the E cores'.
func pantherLakeCPUs() []cpuSpec {
	cpus := []cpuSpec{
		{id: 0, maxFreq: "4800000", hasL3: true},
		{id: 1, maxFreq: "4700000", hasL3: true},
		{id: 2, maxFreq: "4700000", hasL3: true},
		{id: 3, maxFreq: "4700000", hasL3: true},
	}
	for id := 4; id <= 11; id++ {
		cpus = append(cpus, cpuSpec{id: id, maxFreq: "3500000", hasL3: true})
	}
	for id := 12; id <= 15; id++ {
		cpus = append(cpus, cpuSpec{id: id, maxFreq: "3300000", hasL3: false})
	}

	return cpus
}

// TestDetectTopologyInfersLowPowerCores is the case this heuristic exists for:
// a Meteor Lake kernel with no cpu_lowpower PMU.
func TestDetectTopologyInfersLowPowerCores(t *testing.T) {
	root := buildSysfs(t,
		map[string]string{"cpu_core": "0-11\n", "cpu_atom": "12-21\n"},
		meteorLakeCPUs())

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}

	performance := classByName(t, topology, ClassP)
	if len(performance.CPUs) != 12 {
		t.Errorf("P cores = %d, want 12", len(performance.CPUs))
	}
	// The P cores carry two distinct maximum frequencies because of binning.
	// They must never be split by the frequency signal.
	if performance.Source != SourcePMU {
		t.Errorf("P source = %s, want %s", performance.Source, SourcePMU)
	}

	efficient := classByName(t, topology, ClassE)
	if got := formatCPUList(efficient.CPUs); got != "12-19" {
		t.Errorf("E cores = %s, want 12-19", got)
	}
	if efficient.Source != SourceHeuristic {
		t.Errorf("E source = %s, want %s", efficient.Source, SourceHeuristic)
	}

	lowPower := classByName(t, topology, ClassLPE)
	if got := formatCPUList(lowPower.CPUs); got != "20,21" {
		t.Errorf("LP-E cores = %s, want 20,21", got)
	}
	if lowPower.Source != SourceHeuristic {
		t.Errorf("LP-E source = %s, want %s", lowPower.Source, SourceHeuristic)
	}

	if !strings.Contains(topology.LowPowerNote, "agreeing") {
		t.Errorf("LowPowerNote = %q, want it to record the agreement", topology.LowPowerNote)
	}
}

// TestDetectTopologySplitsOnCacheAloneCovers a Core Ultra X7 358H, where the
// LP-E cores have no L3 slice and are unmistakable, but clock to 3.3 GHz
// against the E cores' 3.5 GHz. That gap is too small for the frequency test,
// and demanding both signals agree reported twelve E cores where the part has
// eight.
func TestDetectTopologySplitsOnCacheAlone(t *testing.T) {
	root := buildSysfs(t,
		map[string]string{"cpu_core": "0-3\n", "cpu_atom": "4-15\n"},
		pantherLakeCPUs())

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}

	efficient := classByName(t, topology, ClassE)
	if got := formatCPUList(efficient.CPUs); got != "4-11" {
		t.Errorf("E cores = %s, want 4-11", got)
	}

	lowPower := classByName(t, topology, ClassLPE)
	if got := formatCPUList(lowPower.CPUs); got != "12-15" {
		t.Errorf("LP-E cores = %s, want 12-15", got)
	}
	if lowPower.Source != SourceHeuristic {
		t.Errorf("LP-E source = %s, want %s", lowPower.Source, SourceHeuristic)
	}

	// The note has to say the split rests on cache alone, so nobody reads it
	// as the stronger two-signal answer.
	for _, want := range []string{"cache topology", "inconclusive"} {
		if !strings.Contains(topology.LowPowerNote, want) {
			t.Errorf("LowPowerNote = %q, want it to mention %q", topology.LowPowerNote, want)
		}
	}
}

// TestDetectTopologyIgnoresFrequencyAlone guards the asymmetry: an unusual set
// of clock limits must not invent a core class on its own, because binning
// produces exactly that on parts with no LP-E cores at all.
func TestDetectTopologyIgnoresFrequencyAlone(t *testing.T) {
	root := buildSysfs(t,
		map[string]string{"cpu_core": "0-3\n", "cpu_atom": "4-7\n"},
		[]cpuSpec{
			{id: 0, maxFreq: "4800000", hasL3: true},
			{id: 1, maxFreq: "4800000", hasL3: true},
			{id: 2, maxFreq: "4800000", hasL3: true},
			{id: 3, maxFreq: "4800000", hasL3: true},
			// Every efficient core keeps its L3 slice, so the cache signal
			// says there is nothing to separate; only the clocks differ.
			{id: 4, maxFreq: "3800000", hasL3: true},
			{id: 5, maxFreq: "3800000", hasL3: true},
			{id: 6, maxFreq: "2000000", hasL3: true},
			{id: 7, maxFreq: "2000000", hasL3: true},
		})

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}

	if _, found := findClass(topology, ClassLPE); found {
		t.Error("DetectTopology() split on frequency evidence alone, want the efficient cores kept together")
	}
	if !strings.Contains(topology.LowPowerNote, "unconfirmed by cache topology") {
		t.Errorf("LowPowerNote = %q, want it to say the frequency signal was unconfirmed", topology.LowPowerNote)
	}
}

// TestDetectTopologyPrefersPMU checks that the kernel's own answer wins and the
// heuristic is not consulted at all.
func TestDetectTopologyPrefersPMU(t *testing.T) {
	root := buildSysfs(t,
		map[string]string{"cpu_core": "0-11\n", "cpu_atom": "12-19\n", "cpu_lowpower": "20-21\n"},
		meteorLakeCPUs())

	topology, err := DetectTopology(root)
	if err != nil {
		t.Fatalf("DetectTopology() error: %v", err)
	}

	for _, class := range topology.Classes {
		if class.Source != SourcePMU {
			t.Errorf("class %s source = %s, want %s", class.Class, class.Source, SourcePMU)
		}
	}
	if got := formatCPUList(classByName(t, topology, ClassLPE).CPUs); got != "20,21" {
		t.Errorf("LP-E cores = %s, want 20,21", got)
	}
	if !strings.Contains(topology.LowPowerNote, "cpu_lowpower PMU") {
		t.Errorf("LowPowerNote = %q, want it to cite the PMU", topology.LowPowerNote)
	}
}

// TestDetectTopologySplitsOnCacheWhereFrequencyCannotDecide collects the cases
// where the cache signal is unambiguous and the frequency one has nothing to
// say. Requiring both to agree threw all of these away.
func TestDetectTopologySplitsOnCacheWhereFrequencyCannotDecide(t *testing.T) {
	tests := map[string][]cpuSpec{
		// Binning leaves the efficient cores with three different top
		// bins, which the frequency test cannot reduce to two classes.
		"three distinct frequencies": {
			{id: 12, maxFreq: "3800000", hasL3: true},
			{id: 13, maxFreq: "3600000", hasL3: true},
			{id: 14, maxFreq: "2500000", hasL3: false},
			{id: 15, maxFreq: "2500000", hasL3: false},
		},
		// A guest with no cpufreq at all still reports cache topology.
		"no cpufreq, as in a virtual machine": {
			{id: 12, hasL3: true},
			{id: 13, hasL3: true},
			{id: 14, hasL3: false},
			{id: 15, hasL3: false},
		},
	}

	for name, cpus := range tests {
		t.Run(name, func(t *testing.T) {
			root := buildSysfs(t,
				map[string]string{"cpu_core": "0-11\n", "cpu_atom": "12-15\n"},
				append(performanceCores(), cpus...))

			topology, err := DetectTopology(root)
			if err != nil {
				t.Fatalf("DetectTopology() error: %v", err)
			}

			lowPower, found := findClass(topology, ClassLPE)
			if !found {
				t.Fatalf("no LP-E class; note was %q", topology.LowPowerNote)
			}
			if got := formatCPUList(lowPower.CPUs); got != "14,15" {
				t.Errorf("LP-E cores = %s, want 14,15", got)
			}
			if !strings.Contains(topology.LowPowerNote, "cache topology") {
				t.Errorf("LowPowerNote = %q, want it to name the cache evidence", topology.LowPowerNote)
			}
		})
	}
}

// performanceCores returns twelve ordinary P cores, so a test can describe
// only the efficient half it cares about.
func performanceCores() []cpuSpec {
	var cpus []cpuSpec
	for id := 0; id <= 11; id++ {
		cpus = append(cpus, cpuSpec{id: id, maxFreq: "4700000", hasL3: true})
	}

	return cpus
}

// TestDetectTopologyRefusesToSplit covers every way the evidence can fail. In
// all of them the efficient cores must stay in one authoritative class.
func TestDetectTopologyRefusesToSplit(t *testing.T) {
	tests := []struct {
		name     string
		cpus     []cpuSpec
		wantNote string
	}{
		{
			name: "signals disagree",
			cpus: []cpuSpec{
				{id: 12, maxFreq: "3800000", hasL3: true},
				{id: 13, maxFreq: "3800000", hasL3: true},
				// Lower frequency but still on the ring bus, so the two
				// signals name different CPUs.
				{id: 14, maxFreq: "2500000", hasL3: true},
				{id: 15, maxFreq: "3800000", hasL3: false},
			},
			wantNote: "disagree",
		},
		{
			name: "no L3 anywhere, as on Lunar Lake",
			cpus: []cpuSpec{
				{id: 12, maxFreq: "2500000", hasL3: false},
				{id: 13, maxFreq: "2500000", hasL3: false},
				{id: 14, maxFreq: "2500000", hasL3: false},
				{id: 15, maxFreq: "2500000", hasL3: false},
			},
			wantNote: "no efficient core has an L3 slice",
		},
		{
			name: "every core has L3",
			cpus: []cpuSpec{
				{id: 12, maxFreq: "3800000", hasL3: true},
				{id: 13, maxFreq: "3800000", hasL3: true},
				{id: 14, maxFreq: "2500000", hasL3: true},
				{id: 15, maxFreq: "2500000", hasL3: true},
			},
			wantNote: "every efficient core has an L3 slice",
		},
		{
			name: "no cache topology exposed",
			cpus: []cpuSpec{
				{id: 12, maxFreq: "3800000", noCache: true},
				{id: 13, maxFreq: "3800000", noCache: true},
				{id: 14, maxFreq: "2500000", noCache: true},
				{id: 15, maxFreq: "2500000", noCache: true},
			},
			wantNote: "no cache topology",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ids := make([]string, 0, len(tt.cpus))
			for _, spec := range tt.cpus {
				ids = append(ids, strconv.Itoa(spec.id))
			}
			root := buildSysfs(t,
				map[string]string{
					"cpu_core": "0-11\n",
					"cpu_atom": strings.Join(ids, ",") + "\n",
				},
				append(tt.cpus, cpuSpec{id: 0, maxFreq: "4700000", hasL3: true}))

			topology, err := DetectTopology(root)
			if err != nil {
				t.Fatalf("DetectTopology() error: %v", err)
			}

			for _, class := range topology.Classes {
				if class.Class == ClassLPE {
					t.Errorf("LP-E class was reported from ambiguous evidence: %v", class.CPUs)
				}
				if class.Source != SourcePMU {
					t.Errorf("class %s source = %s, want %s when no split is made",
						class.Class, class.Source, SourcePMU)
				}
			}

			if efficient := classByName(t, topology, ClassE); len(efficient.CPUs) != len(tt.cpus) {
				t.Errorf("E cores = %d, want all %d to be kept together",
					len(efficient.CPUs), len(tt.cpus))
			}
			if !strings.Contains(topology.LowPowerNote, tt.wantNote) {
				t.Errorf("LowPowerNote = %q, want it to contain %q", topology.LowPowerNote, tt.wantNote)
			}
		})
	}
}

func TestFormatCPUList(t *testing.T) {
	tests := []struct {
		cpus []int
		want string
	}{
		{cpus: nil, want: "none"},
		{cpus: []int{5}, want: "5"},
		{cpus: []int{20, 21}, want: "20,21"},
		{cpus: []int{12, 13, 14, 15}, want: "12-15"},
		{cpus: []int{0, 2, 3, 4, 9}, want: "0,2-4,9"},
	}

	for _, tt := range tests {
		if got := formatCPUList(tt.cpus); got != tt.want {
			t.Errorf("formatCPUList(%v) = %q, want %q", tt.cpus, got, tt.want)
		}
	}
}

func TestDescribeReportsEvidence(t *testing.T) {
	root := buildSysfs(t,
		map[string]string{"cpu_core": "0-11\n", "cpu_atom": "12-21\n"},
		meteorLakeCPUs())

	description, err := Describe(root)
	if err != nil {
		t.Fatalf("Describe() error: %v", err)
	}

	for _, want := range []string{"LPE", "heuristic", "2500000", "false"} {
		if !strings.Contains(description, want) {
			t.Errorf("Describe() output is missing %q:\n%s", want, description)
		}
	}
}
