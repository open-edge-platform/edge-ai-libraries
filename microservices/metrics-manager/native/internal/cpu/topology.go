// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Class identifies a group of CPUs that share a microarchitecture.
//
// On Intel hybrid parts the classes map to Performance cores, Efficient cores
// and the Low Power Efficient cores that sit on the SoC tile.
type Class string

const (
	ClassP   Class = "P"
	ClassE   Class = "E"
	ClassLPE Class = "LPE"

	// ClassAll is used on non-hybrid CPUs, where every core is identical.
	// Reporting a single class keeps the measurement shape the same on every
	// machine, so a dashboard does not have to special-case homogeneous CPUs.
	ClassAll Class = "core"
)

// Source records how a class was identified. It is attached to every emitted
// metric so a consumer can tell an authoritative reading from an inferred one
// instead of having to trust the class blindly.
type Source string

const (
	// SourcePMU means the kernel itself grouped these CPUs, by exporting a
	// per-microarchitecture PMU directory. This is authoritative.
	SourcePMU Source = "pmu"

	// SourceHeuristic means the grouping was inferred from secondary evidence
	// because the kernel did not export a cpu_lowpower PMU. See
	// inferLowPowerCores for the rules and their limits.
	SourceHeuristic Source = "heuristic"
)

// ClassCPUs is the set of logical CPU ids belonging to one class.
type ClassCPUs struct {
	Class  Class
	CPUs   []int
	Source Source
}

// Topology is the detected core-class layout, ordered P, E, LPE.
type Topology struct {
	Classes []ClassCPUs

	// Hybrid reports whether per-class PMU directories were found. When false
	// the topology holds exactly one ClassAll entry.
	Hybrid bool

	// LowPowerNote explains, in one line, how the LP-E cores were identified
	// or why they could not be. It is written to stderr at start-up so an
	// operator can see what the plugin concluded on a new machine.
	LowPowerNote string
}

// classSources maps the per-microarchitecture PMU directories exported by the
// kernel onto our class names.
//
// `cpu_lowpower` only appears on recent kernels. When it is missing,
// inferLowPowerCores tries to recover the split from secondary evidence.
var classSources = []struct {
	dir   string
	class Class
}{
	{"devices/cpu_core", ClassP},
	{"devices/cpu_atom", ClassE},
	{"devices/cpu_lowpower", ClassLPE},
}

// DetectTopology reads the core-class layout from sysfs.
//
// sysfsRoot is normally "/sys"; tests point it at a fixture directory.
func DetectTopology(sysfsRoot string) (Topology, error) {
	var topo Topology

	for _, source := range classSources {
		raw, err := os.ReadFile(filepath.Join(sysfsRoot, source.dir, "cpus"))
		if err != nil {
			// A missing directory just means this class is not present on
			// this CPU, which is the normal case for most machines.
			continue
		}
		cpus, err := ParseCPUList(string(raw))
		if err != nil {
			return Topology{}, fmt.Errorf("%s/cpus: %w", source.dir, err)
		}
		if len(cpus) == 0 {
			continue
		}
		topo.Classes = append(topo.Classes, ClassCPUs{
			Class:  source.class,
			CPUs:   cpus,
			Source: SourcePMU,
		})
	}

	if len(topo.Classes) > 0 {
		topo.Hybrid = true
		topo.splitLowPower(sysfsRoot)
		return topo, nil
	}

	// Non-hybrid CPU: fall back to the set of online CPUs.
	raw, err := os.ReadFile(filepath.Join(sysfsRoot, "devices/system/cpu/online"))
	if err != nil {
		return Topology{}, fmt.Errorf("no per-class PMU directories and no online CPU list: %w", err)
	}
	cpus, err := ParseCPUList(string(raw))
	if err != nil {
		return Topology{}, fmt.Errorf("devices/system/cpu/online: %w", err)
	}
	if len(cpus) == 0 {
		return Topology{}, fmt.Errorf("devices/system/cpu/online lists no CPUs")
	}
	topo.Classes = []ClassCPUs{{Class: ClassAll, CPUs: cpus, Source: SourcePMU}}
	topo.LowPowerNote = "not applicable: CPU is not hybrid"
	return topo, nil
}

// splitLowPower carves the LP-E cores out of the efficient-core class when the
// kernel did not report them itself, and records what it concluded.
func (t *Topology) splitLowPower(sysfsRoot string) {
	efficientIdx := -1
	for i, class := range t.Classes {
		switch class.Class {
		case ClassLPE:
			t.LowPowerNote = "read from the cpu_lowpower PMU"
			return
		case ClassE:
			efficientIdx = i
		}
	}
	if efficientIdx < 0 {
		t.LowPowerNote = "not applicable: no efficient cores present"
		return
	}

	efficient := t.Classes[efficientIdx].CPUs
	lowPower, note := inferLowPowerCores(sysfsRoot, efficient)
	t.LowPowerNote = note
	if len(lowPower) == 0 {
		return
	}

	remaining := make([]int, 0, len(efficient)-len(lowPower))
	isLowPower := make(map[int]bool, len(lowPower))
	for _, id := range lowPower {
		isLowPower[id] = true
	}
	for _, id := range efficient {
		if !isLowPower[id] {
			remaining = append(remaining, id)
		}
	}

	// Both classes are now heuristic: the LP-E set was inferred, and the E set
	// is whatever was left after removing it.
	t.Classes[efficientIdx].CPUs = remaining
	t.Classes[efficientIdx].Source = SourceHeuristic
	t.Classes = append(t.Classes, ClassCPUs{
		Class:  ClassLPE,
		CPUs:   lowPower,
		Source: SourceHeuristic,
	})
}

// lowPowerMaxFreqRatio is how much lower an LP-E core's maximum frequency has
// to be before the gap is accepted as a microarchitecture difference.
//
// Real hardware is far below this: on Meteor Lake the LP-E cores top out at
// 2.5 GHz against 3.8 GHz for the ordinary E cores, a ratio of 0.66. Per-part
// turbo binning, the effect this threshold exists to reject, moves the maximum
// by only a few percent.
const lowPowerMaxFreqRatio = 0.90

// inferLowPowerCores identifies the LP-E cores among the efficient cores on a
// kernel that does not export the cpu_lowpower PMU.
//
// Two independent signals are evaluated, and how much weight each carries was
// settled by measurement rather than by symmetry:
//
//   - Cache: LP-E cores sit on the SoC tile and have no L3 slice, so their
//     sysfs cache directory has no level 3 entry.
//   - Frequency: LP-E cores have a distinctly lower cpuinfo_max_freq.
//
// Cache evidence stands on its own, because which cores have an L3 slice is a
// fact about how the die is wired rather than a threshold someone chose. On a
// Core Ultra X7 358H the four LP-E cores have no L3 and are unmistakable, yet
// they clock to 3.3 GHz against the E cores' 3.5 GHz, close enough that the
// frequency test declines to call them different core types. Requiring the two
// signals to agree lost that split entirely and reported twelve E cores where
// the part has eight.
//
// Frequency evidence alone is not acted on. It rests on a chosen ratio rather
// than on the layout of the part, and on Meteor Lake the P cores carry two
// different maximum frequencies purely because of favoured-core binning, which
// frequency clustering on its own would read as two classes.
//
// Signals naming different CPUs remain a refusal to split: that is genuine
// ambiguity, and picking one would put cores in the wrong class silently.
//
// The returned note explains the decision either way and is never empty.
//
// A part where every efficient core is an LP-E core would present no split for
// either signal to find, and would be reported as ordinary E cores;
// distinguishing that case needs a CPU family/model table. Panther Lake was
// expected to be such a part and turned out not to be: the 358H has both
// kinds, eight E cores with an L3 slice and four LP-E cores without.
func inferLowPowerCores(sysfsRoot string, efficient []int) ([]int, string) {
	if len(efficient) < 2 {
		return nil, "no cpu_lowpower PMU; too few efficient cores to split"
	}

	byCache, cacheNote := lowPowerByCache(sysfsRoot, efficient)
	byFreq, freqNote := lowPowerByMaxFreq(sysfsRoot, efficient)

	switch {
	case byCache != nil && byFreq != nil && sameCPUs(byCache, byFreq):
		return byCache, fmt.Sprintf(
			"no cpu_lowpower PMU; inferred from agreeing cache and frequency evidence (CPUs %v)", byCache)

	case byCache != nil && byFreq != nil:
		return nil, fmt.Sprintf(
			"no cpu_lowpower PMU; not split: cache evidence (%v) and frequency evidence (%v) disagree",
			byCache, byFreq)

	case byCache != nil:
		return byCache, fmt.Sprintf(
			"no cpu_lowpower PMU; inferred from cache topology (CPUs %v); frequency evidence inconclusive: %s",
			byCache, freqNote)

	case byFreq != nil:
		return nil, fmt.Sprintf(
			"no cpu_lowpower PMU; not split: frequency evidence (%v) is unconfirmed by cache topology: %s",
			byFreq, cacheNote)

	default:
		return nil, "no cpu_lowpower PMU; not split: " + cacheNote
	}
}

// lowPowerByCache returns the efficient cores that have no L3 slice.
//
// A nil result means the signal is unusable, with the reason in the note.
func lowPowerByCache(sysfsRoot string, efficient []int) ([]int, string) {
	var withoutL3 []int

	for _, id := range efficient {
		hasL3, known := cpuHasL3(sysfsRoot, id)
		if !known {
			return nil, fmt.Sprintf("the kernel reports no cache topology for cpu%d", id)
		}
		if !hasL3 {
			withoutL3 = append(withoutL3, id)
		}
	}

	switch len(withoutL3) {
	case 0:
		return nil, "every efficient core has an L3 slice"
	case len(efficient):
		return nil, "no efficient core has an L3 slice, so there is nothing to separate"
	default:
		return withoutL3, ""
	}
}

// cpuHasL3 reports whether the CPU has a level 3 cache. The second return
// value is false when the kernel exposes no cache topology at all, which must
// not be confused with a genuine absence of L3.
func cpuHasL3(sysfsRoot string, id int) (hasL3, known bool) {
	dir := filepath.Join(sysfsRoot, "devices/system/cpu", "cpu"+strconv.Itoa(id), "cache")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return false, false
	}

	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "index") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, entry.Name(), "level"))
		if err != nil {
			continue
		}
		known = true
		if strings.TrimSpace(string(raw)) == "3" {
			return true, true
		}
	}

	return false, known
}

// lowPowerByMaxFreq returns the efficient cores in the lower of exactly two
// cpuinfo_max_freq groups, provided the two are far enough apart.
//
// A nil result means the signal is unusable, with the reason in the note.
func lowPowerByMaxFreq(sysfsRoot string, efficient []int) ([]int, string) {
	maxFreq := make(map[int]uint64, len(efficient))
	distinct := make(map[uint64]struct{}, 2)

	for _, id := range efficient {
		khz, ok := readMaxFreq(sysfsRoot, id)
		if !ok {
			return nil, fmt.Sprintf("cpufreq reports no maximum frequency for cpu%d", id)
		}
		maxFreq[id] = khz
		distinct[khz] = struct{}{}
	}

	if len(distinct) != 2 {
		return nil, fmt.Sprintf(
			"efficient cores have %d distinct maximum frequencies, expected exactly 2", len(distinct))
	}

	var low, high uint64
	for khz := range distinct {
		if low == 0 || khz < low {
			low = khz
		}
		if khz > high {
			high = khz
		}
	}

	if float64(low) > lowPowerMaxFreqRatio*float64(high) {
		return nil, fmt.Sprintf(
			"maximum frequencies %d and %d kHz are too close to be different core types", low, high)
	}

	var lowPower []int
	for _, id := range efficient {
		if maxFreq[id] == low {
			lowPower = append(lowPower, id)
		}
	}
	return lowPower, ""
}

// readMaxFreq reads cpuinfo_max_freq, in kHz, for one CPU.
func readMaxFreq(sysfsRoot string, id int) (uint64, bool) {
	path := filepath.Join(sysfsRoot, "devices/system/cpu", "cpu"+strconv.Itoa(id),
		"cpufreq/cpuinfo_max_freq")
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, false
	}
	khz, err := strconv.ParseUint(strings.TrimSpace(string(raw)), 10, 64)
	if err != nil {
		return 0, false
	}
	return khz, true
}

// sameCPUs reports whether two CPU sets hold the same ids. Both are built by
// iterating the same ascending slice, so a positional comparison is enough.
func sameCPUs(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// ParseCPUList parses the kernel's cpulist format, a comma separated list of
// single ids and inclusive ranges, for example "0-11" or "0,2-3,8".
func ParseCPUList(raw string) ([]int, error) {
	if len(raw) > 1<<20 {
		return nil, fmt.Errorf("cpulist exceeds 1 MiB")
	}
	var cpus []int

	for _, part := range strings.Split(strings.TrimSpace(raw), ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		lo, hi, isRange := strings.Cut(part, "-")
		start, err := strconv.Atoi(strings.TrimSpace(lo))
		if err != nil {
			return nil, fmt.Errorf("invalid cpulist entry %q", part)
		}
		end := start
		if isRange {
			if end, err = strconv.Atoi(strings.TrimSpace(hi)); err != nil {
				return nil, fmt.Errorf("invalid cpulist entry %q", part)
			}
		}
		if start < 0 || end < start {
			return nil, fmt.Errorf("invalid cpulist range %q", part)
		}
		// Bound expansion before iterating, including repeated/overlapping ranges.
		if end > 1<<31-1 || end-start >= 65536-len(cpus) {
			return nil, fmt.Errorf("cpulist exceeds 65536 entries or signed 32-bit CPU IDs")
		}

		for offset := 0; offset <= end-start; offset++ {
			cpus = append(cpus, start+offset)
		}
	}

	return cpus, nil
}
