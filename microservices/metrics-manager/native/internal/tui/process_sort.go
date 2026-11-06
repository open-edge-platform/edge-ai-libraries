// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"cmp"
	"fmt"
	"math"
	"slices"
)

func (m *Model) cycleProcessSort() {
	switch m.config.Processes.SortBy {
	case "usage":
		m.config.Processes.SortBy = "memory"
	case "memory":
		m.config.Processes.SortBy = "pid"
	default:
		m.config.Processes.SortBy = "usage"
	}
	m.config.Processes.Descending = m.config.Processes.SortBy != "pid"
}

func (m Model) processSortLabel() string {
	direction := "asc"
	if m.config.Processes.Descending {
		direction = "desc"
	}
	return fmt.Sprintf("sort: %s %s | s sort / r reverse", m.config.Processes.SortBy, direction)
}

func finiteReading(r Reading) bool {
	return r.OK && !math.IsNaN(r.Value) && !math.IsInf(r.Value, 0)
}

func compareProcess(config ProcessConfig, aPID, bPID string, aUsage, bUsage, aMemory, bMemory Reading) int {
	pidOrder := cmp.Compare(numericPID(aPID), numericPID(bPID))
	if pidOrder == 0 {
		pidOrder = cmp.Compare(aPID, bPID)
	}
	order := pidOrder
	if config.SortBy != "pid" {
		a, b := aUsage, bUsage
		if config.SortBy == "memory" {
			a, b = aMemory, bMemory
		}
		aOK, bOK := finiteReading(a), finiteReading(b)
		if aOK != bOK {
			if aOK {
				return -1
			}
			return 1
		}
		order = 0
		if aOK {
			order = cmp.Compare(a.Value, b.Value)
		}
	}
	if config.Descending {
		order = -order
	}
	if order == 0 {
		return pidOrder
	}
	return order
}

func (m Model) sortedProcesses() []Process {
	processes := currentProcesses(m.dash, m.now(), m.alerts.processMaxAge)
	slices.SortFunc(processes, func(a, b Process) int {
		return compareProcess(m.config.Processes, a.PID, b.PID, a.CPUPercent, b.CPUPercent, a.MemoryBytes, b.MemoryBytes)
	})
	return processes[:min(len(processes), m.config.Processes.MaxDisplayed)]
}

func (m Model) sortedGPUProcesses(processes []GPUProcess) []GPUProcess {
	processes = slices.Clone(processes)
	slices.SortFunc(processes, func(a, b GPUProcess) int {
		return compareProcess(m.config.Processes, a.PID, b.PID, a.UsagePct, b.UsagePct, a.MemoryBytes, b.MemoryBytes)
	})
	return processes[:min(len(processes), m.config.Processes.MaxDisplayed)]
}
