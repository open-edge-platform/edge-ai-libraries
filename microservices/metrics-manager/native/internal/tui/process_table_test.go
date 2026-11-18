// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"
)

func TestProcessTablesKeepOneRowPerProcess(t *testing.T) {
	m := testModel(nil)
	m.dash.Processes = []Process{
		{PID: "123456", Command: "first", Threads: reading(16), User: "metrics-manager", MemoryBytes: reading(64 << 20), CPUPercent: reading(90)},
		{PID: "789012", Command: "second", Threads: reading(8), User: "fst", MemoryBytes: reading(32 << 20), CPUPercent: reading(20)},
	}
	rows := m.processRows(m.sortedProcesses())
	for _, width := range []int{8, 20, 40, 60, 80, 160, 250} {
		for _, offset := range []int{0, 8, 24, 1000} {
			m.processColumnOffset = offset
			rendered := m.scrollingProcessTable(processColumns, rows, width)
			lines := strings.Split(strings.TrimRight(rendered, "\n"), "\n")
			if strings.HasPrefix(ansi.Strip(lines[0]), "Columns ") {
				lines = lines[1:]
			}
			if len(lines) != len(rows)+1 {
				t.Fatalf("width %d: got %d table lines for %d processes", width, len(lines), len(rows))
			}
			for _, line := range lines {
				if lipgloss.Width(line) > width {
					t.Fatalf("width %d: row overflowed: %q", width, line)
				}
			}
			if strings.Contains(rendered, "pid:") || strings.Contains(rendered, "threads:") {
				t.Fatal("table switched to vertical cards")
			}
		}
	}
	m.processColumnOffset = 0
	text := ansi.Strip(m.scrollingProcessTable(processColumns, rows, 160))
	for _, line := range strings.Split(text, "\n") {
		if strings.Contains(line, "123456") {
			for _, value := range []string{"first", "16", "metrics-manager", "64.0 MiB"} {
				wantContains(t, line, value)
			}
		}
	}
}

func TestGPUProcessTablesKeepOneRowPerClient(t *testing.T) {
	m := testModel(nil)
	processes := []GPUProcess{
		{PID: "123456", Command: "first", UsagePct: reading(90), MemoryBytes: reading(64 << 20)},
		{PID: "789012", Command: "second", UsagePct: reading(20), MemoryBytes: reading(32 << 20)},
	}
	for _, width := range []int{8, 20, 40, 80, 160} {
		for _, offset := range []int{0, 8, 1000} {
			m.processColumnOffset = offset
			lines := strings.Split(strings.TrimRight(m.gpuProcessTable(processes, width), "\n"), "\n")
			if strings.HasPrefix(ansi.Strip(lines[0]), "Columns ") {
				lines = lines[1:]
			}
			if len(lines) != len(processes)+1 {
				t.Fatalf("width %d: GPU clients not rendered as single rows", width)
			}
			for _, line := range lines {
				if lipgloss.Width(line) > width {
					t.Fatalf("width %d: GPU row overflowed: %q", width, line)
				}
			}
		}
	}
}

func TestProcessHorizontalScrollScopeBoundsAndResize(t *testing.T) {
	m := testModel(nil)
	m.dash.Processes = []Process{{PID: "123456", Command: "worker", User: "metrics-manager", CPUPercent: reading(1400)}}
	m.dash.GPUs = []GPU{{ID: "0", Processes: []GPUProcess{{PID: "111222", Command: "gpu-worker"}}}}
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 30, Height: 24})
	m, _ = update(t, m, key("right"))
	if m.processColumnOffset != 8 {
		t.Fatal("right arrow did not move process columns")
	}
	m, _ = update(t, m, key("h"))
	m, _ = update(t, m, key("right"))
	if m.processColumnOffset != 8 {
		t.Fatal("help changed process columns")
	}
	m, _ = update(t, m, key("h"))
	m.switchTab(TrendsTab)
	m, _ = update(t, m, key("right"))
	if m.processColumnOffset != 8 {
		t.Fatal("Trends changed process columns")
	}
	m.switchTab(DetailsTab)
	m, _ = update(t, m, key("right"))
	if m.processColumnOffset != 8 {
		t.Fatal("Details changed process columns")
	}
	m.switchTab(AlertsTab)
	m, _ = update(t, m, key("left"))
	if m.processColumnOffset != 8 {
		t.Fatal("Alerts changed process columns")
	}
	m.switchTab(OverviewTab)
	m.moveProcessColumns(10000)
	wantContains(t, m.processSection(), "cpu")
	m.moveProcessColumns(-10000)
	if m.processColumnOffset != 0 {
		t.Fatal("left boundary not clamped")
	}
	wantContains(t, m.processSection(), "123456")
	wantContains(t, m.gpuProcessTable(m.dash.GPUs[0].Processes, 28), "111222")
	m.moveProcessColumns(10000)
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 180, Height: 24})
	if m.processColumnOffset != 0 || strings.Contains(m.processSection(), "Left/Right scroll") {
		t.Fatal("wide resize did not restore complete table")
	}
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 30, Height: 24})
	m.moveProcessColumns(10000)
	m, _ = update(t, m, snapshotMsg{})
	if m.processColumnOffset != 0 {
		t.Fatal("disappearing process tables did not clamp the offset")
	}
}

func TestProcessScrollUsesActualOverviewColumnWidth(t *testing.T) {
	m := testModel(nil)
	m.dash.Platform.LogicalCPUs = reading(1)
	m.dash.Processes = []Process{{
		PID: "123456", Command: strings.Repeat("p", 20), User: strings.Repeat("u", 16),
		Threads: reading(123456789012), MemoryBytes: reading(1 << 30), CPUPercent: reading(97),
	}}
	m.dash.GPUs = []GPU{{ID: "0"}}
	for _, width := range []int{153, 224} {
		m.width = width
		widths := m.overviewColumnWidths(width)
		columnWidth := widths[len(widths)-1] - 2
		total := lipgloss.Width(fittedProcessTable(processColumns, m.processRows(m.sortedProcesses()), columnWidth))
		if total <= columnWidth {
			t.Fatal("fixture must overflow the process column, not the terminal")
		}
		m.processColumnOffset = 0
		m, _ = update(t, m, key("right"))
		if m.processColumnOffset != min(8, total-columnWidth) {
			t.Fatal("scroll was clamped to terminal width instead of panel width")
		}
		m.moveProcessColumns(10000)
		wantContains(t, m.panelGrid(width), "97.0%")
	}
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 400, Height: 18})
	if m.processColumnOffset != 0 {
		t.Fatal("resize did not reset the now-unnecessary horizontal offset")
	}
	wantContains(t, m.View(), "┌ Processes")
	m, _ = update(t, m, key("down"))
	if m.offset == 0 || strings.Contains(m.View(), "┌ Processes") {
		t.Fatal("CPU process frame was pinned rather than scrolling with Overview")
	}
}

func TestProcessTableScrollPreservesANSIAndWideText(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	defer lipgloss.SetColorProfile(profile)
	m := testModel(nil)
	rows := [][]string{{"1234", "測試-worker", "16", "fst", "10.0 MiB", criticalStyle.Render("99.0%")}}
	original := ansi.Strip(strings.Split(fittedProcessTable(processColumns, rows, 20), "\n")[1])
	for offset := 0; offset < 70; offset++ {
		m.processColumnOffset = offset
		rendered := m.scrollingProcessTable(processColumns, rows, 20)
		lines := strings.Split(strings.TrimRight(rendered, "\n"), "\n")
		for _, line := range lines[1:] {
			if lipgloss.Width(line) > 20 || strings.Contains(ansi.Strip(line), "\x1b") {
				t.Fatalf("invalid clipped row at column %d: %q", offset, line)
			}
		}
		row := ansi.Strip(lines[len(lines)-1])
		actualOffset := min(offset, lipgloss.Width(fittedProcessTable(processColumns, rows, 20))-20)
		for _, token := range []string{"16", "fst", "10.0 MiB", "99.0%"} {
			if index := strings.Index(row, token); index >= 0 {
				expected := lipgloss.Width(original[:strings.Index(original, token)]) - actualOffset
				if lipgloss.Width(row[:index]) != expected {
					t.Fatalf("column %s lost alignment at offset %d: %q", token, offset, row)
				}
			}
		}
	}
	m.processColumnOffset = 1000
	wantContains(t, m.scrollingProcessTable(processColumns, rows, 20), criticalStyle.Render("99.0%"))
}
