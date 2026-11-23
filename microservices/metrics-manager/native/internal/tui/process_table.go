// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"slices"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

func (m Model) processViewportWidth() int {
	if m.panelContentWidth > 0 {
		return m.panelContentWidth
	}
	return max(1, m.renderWidth()-2)
}

// Compact padding, never cell contents: every process remains one row and
// horizontally hidden columns remain reachable without losing numeric values.
func fittedProcessTable(columns []column, rows [][]string, width int) string {
	fitted := slices.Clone(columns)
	for i := range fitted {
		for _, cells := range rows {
			fitted[i].width = max(fitted[i].width, lipgloss.Width(cells[i])+2)
		}
	}
	expanded := table(fitted, rows)
	if lipgloss.Width(expanded) <= width {
		return expanded
	}
	for i := range fitted {
		fitted[i].width = lipgloss.Width(fitted[i].title)
		for _, cells := range rows {
			fitted[i].width = max(fitted[i].width, lipgloss.Width(cells[i]))
		}
		fitted[i].width += 2
	}
	return table(fitted, rows)
}

func (m Model) scrollingProcessTable(columns []column, rows [][]string, width int) string {
	content := strings.TrimRight(fittedProcessTable(columns, rows, width), "\n")
	total := lipgloss.Width(content)
	if total <= width {
		return content + "\n"
	}
	offset := min(m.processColumnOffset, total-width)
	lines := strings.Split(content, "\n")
	for i, line := range lines {
		// Cut retains a wide glyph crossing its left boundary. Skip that
		// partial glyph and pad the gap so the remaining columns stay aligned.
		start := offset
		for start < offset+width && start < lipgloss.Width(line) &&
			lipgloss.Width(ansi.Truncate(line, start, "")) < start {
			start++
		}
		lines[i] = strings.Repeat(" ", start-offset) + ansi.Cut(line, start, offset+width)
	}
	hint := fmt.Sprintf("Columns %d-%d/%d | Left/Right scroll", offset+1, offset+width, total)
	return labelStyle.Render(hint) + "\n" + strings.Join(lines, "\n") + "\n"
}

func (m *Model) moveProcessColumns(delta int) {
	if m.processColumnOffset == 0 && delta <= 0 {
		return
	}
	widths := m.overviewColumnWidths(m.renderWidth())
	width := max(1, widths[len(widths)-1]-2)
	limit := 0
	if len(m.dash.Processes) > 0 {
		limit = max(limit, lipgloss.Width(fittedProcessTable(processColumns, m.processRows(m.sortedProcesses()), width))-width)
	}
	gpuColumn := 0
	if len(widths) == 3 {
		gpuColumn = 1
	}
	width = max(1, widths[gpuColumn]-2)
	for _, gpu := range m.dash.GPUs {
		if len(gpu.Processes) > 0 {
			limit = max(limit, lipgloss.Width(fittedProcessTable(gpuProcessColumns, m.gpuProcessRows(m.sortedGPUProcesses(gpu.Processes)), width))-width)
		}
	}
	m.processColumnOffset = max(0, min(m.processColumnOffset+delta, limit))
}
