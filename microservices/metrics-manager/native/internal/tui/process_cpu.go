// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
)

func (m *Model) toggleProcessCPUMode() {
	if m.config.Processes.CPUMode == "total" {
		m.config.Processes.CPUMode = "per-core"
	} else {
		m.config.Processes.CPUMode = "total"
	}
}

func usableCPUCount(count Reading) bool {
	return finiteReading(count) && count.Value >= 1 && math.Trunc(count.Value) == count.Value
}

func processTotalCPU(value, count Reading) Reading {
	if !usableCPUCount(count) {
		return Reading{}
	}
	return Reading{Value: value.Value / count.Value, OK: value.OK}
}

func (m Model) processCPULabel() string {
	count := m.dash.Platform.LogicalCPUs
	if m.config.Processes.CPUMode != "total" {
		label := "CPU: per-core | c toggle (100% = 1 CPU)"
		if !usableCPUCount(count) {
			return label + "\nColors/alerts unavailable: logical CPU count missing or invalid."
		}
		return label + "\nColors/alerts: total host CPU (h help)"
	}
	if !usableCPUCount(count) {
		return "CPU: total | c toggle\nCPU total unavailable: logical CPU count missing or invalid.\nColors/alerts unavailable."
	}
	return fmt.Sprintf("CPU: total | c toggle (100%% = %.0f CPUs)", count.Value)
}

func (m Model) processCPUPercent(value Reading) string {
	count := m.dash.Platform.LogicalCPUs
	if !usableCPUCount(count) {
		if m.config.Processes.CPUMode == "per-core" {
			return formatPercent(value)
		}
		return unavailable
	}
	total := processTotalCPU(value, count)
	if m.config.Processes.CPUMode == "total" {
		return m.thresholdPercent("process.cpuPercent", total)
	}
	// Per-core is only a presentation choice; health uses the same total
	// value as alerts, independent of the selected view.
	return m.thresholdValue("process.cpuPercent", total, func(Reading) string {
		return formatPercent(value)
	})
}
