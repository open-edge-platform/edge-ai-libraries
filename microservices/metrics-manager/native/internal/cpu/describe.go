// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
)

// Describe renders the detected topology together with the per-CPU evidence it
// was derived from.
//
// This exists so that the LP-E split, which on some kernels is inferred rather
// than read from the kernel, can be checked by hand on a new machine before
// its numbers are trusted. It is what `mm-plugin-cpu -topology` prints.
func Describe(sysfsRoot string) (string, error) {
	topology, err := DetectTopology(sysfsRoot)
	if err != nil {
		return "", err
	}

	var b strings.Builder

	fmt.Fprintf(&b, "hybrid:     %t\n", topology.Hybrid)
	fmt.Fprintf(&b, "LP-E cores: %s\n\n", topology.LowPowerNote)

	fmt.Fprintf(&b, "%-6s %-10s %-6s %s\n", "class", "source", "cores", "cpus")
	fmt.Fprintf(&b, "%-6s %-10s %-6s %s\n", "-----", "------", "-----", "----")
	for _, class := range topology.Classes {
		fmt.Fprintf(&b, "%-6s %-10s %-6d %s\n",
			class.Class, class.Source, len(class.CPUs), formatCPUList(class.CPUs))
	}

	fmt.Fprintf(&b, "\nper-CPU evidence:\n")
	fmt.Fprintf(&b, "%-6s %-6s %-14s %s\n", "cpu", "class", "max freq kHz", "has L3")
	fmt.Fprintf(&b, "%-6s %-6s %-14s %s\n", "---", "-----", "------------", "------")

	classOf := make(map[int]Class)
	var ids []int
	for _, class := range topology.Classes {
		for _, id := range class.CPUs {
			classOf[id] = class.Class
			ids = append(ids, id)
		}
	}
	sort.Ints(ids)

	for _, id := range ids {
		maxFreq := "unknown"
		if khz, ok := readMaxFreq(sysfsRoot, id); ok {
			maxFreq = strconv.FormatUint(khz, 10)
		}

		l3 := "unknown"
		if hasL3, known := cpuHasL3(sysfsRoot, id); known {
			l3 = strconv.FormatBool(hasL3)
		}

		fmt.Fprintf(&b, "%-6d %-6s %-14s %s\n", id, classOf[id], maxFreq, l3)
	}

	return b.String(), nil
}

// formatCPUList renders ids back into the kernel's compact cpulist notation,
// collapsing runs of consecutive ids into ranges.
func formatCPUList(cpus []int) string {
	if len(cpus) == 0 {
		return "none"
	}

	var parts []string
	start, prev := cpus[0], cpus[0]

	flush := func() {
		switch {
		case start == prev:
			parts = append(parts, strconv.Itoa(start))
		case prev == start+1:
			parts = append(parts, strconv.Itoa(start), strconv.Itoa(prev))
		default:
			parts = append(parts, strconv.Itoa(start)+"-"+strconv.Itoa(prev))
		}
	}

	for _, id := range cpus[1:] {
		if id != prev+1 {
			flush()
			start = id
		}
		prev = id
	}
	flush()

	return strings.Join(parts, ",")
}
