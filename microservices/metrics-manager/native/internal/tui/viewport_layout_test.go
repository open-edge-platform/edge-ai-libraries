// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"
)

func TestOverviewKeepsPrimaryPanelsInPlace(t *testing.T) {
	rowOf := func(text, marker string) int {
		t.Helper()
		for i, line := range strings.Split(text, "\n") {
			if strings.Contains(line, marker) {
				return i
			}
		}
		t.Fatalf("missing panel %s", marker)
		return -1
	}
	m := testModel(nil)
	m.dash = BuildDashboard(parseFixture(t, hostExposition+acceleratorExposition))
	m.dash.GPUs[0].Processes = []GPUProcess{{PID: "300", Command: "gpu-worker"}}
	m.dash.GPUs = append(m.dash.GPUs, GPU{ID: "1", Processes: []GPUProcess{{PID: "301", Command: "other-gpu"}}})
	m.dash.NPU.Present = true
	m.dash.Processes = []Process{{PID: "200", Command: "cpu-worker"}}
	var network networkTracker
	m.dash.Network, _ = network.update(networkSamples(fixedNow, 0, "eth0", "host"), fixedNow, m.config.Network)
	var storage storageTracker
	m.dash.Storage, _ = storage.update(storageSamples(fixedNow, 0, 50), fixedNow, m.config.Storage)
	for _, width := range []int{80, 152, 153, 200, 223, 224, 240, 300} {
		m.width = width
		view := ansi.Strip(m.panelGrid(width))
		primary := m
		primary.dash.Network = nil
		primary.dash.Storage = nil
		baseline := ansi.Strip(primary.panelGrid(width))
		for _, marker := range []string{"┌ CPU", "┌ Memory", "┌ NPU", "┌ GPU 0 ", "┌ GPU 1", "┌ Processes", "gpu-worker", "other-gpu", "cpu-worker"} {
			if rowOf(view, marker) != rowOf(baseline, marker) {
				t.Fatalf("auxiliary panels displaced %s at width %d:\n%s", marker, width, view)
			}
		}
		wantContains(t, view, "┌ Network eth0")
		wantContains(t, view, "┌ Filesystem /data")
		widths := m.overviewColumnWidths(width)
		expectedColumns := 1
		if width >= 153 {
			expectedColumns = 2
		}
		if width >= 224 {
			expectedColumns = 3
		}
		if len(widths) != expectedColumns {
			t.Fatalf("width %d: got %d columns, want %d", width, len(widths), expectedColumns)
		}
		if len(widths) > 1 {
			if rowOf(view, "┌ Processes") != 0 {
				t.Fatalf("CPU processes not at top at width %d", width)
			}
			start := width - widths[len(widths)-1]
			if !strings.HasPrefix(ansi.Cut(strings.Split(view, "\n")[0], start, width), "┌ Processes") {
				t.Fatalf("CPU processes not on the right at width %d", width)
			}
		}
		if len(widths) == 3 && rowOf(view, "┌ GPU 0 ") != 0 {
			t.Fatal("GPU not at top of middle column")
		}
		gpuStart, gpuWidth := 0, widths[0]
		if len(widths) == 3 {
			gpuStart, gpuWidth = widths[0]+panelGap, widths[1]
		}
		var gpuLines []string
		for _, line := range strings.Split(view, "\n") {
			if lipgloss.Width(line) > width {
				t.Fatalf("width %d overflow: %q", width, line)
			}
			gpuLines = append(gpuLines, ansi.Cut(line, gpuStart, gpuStart+gpuWidth))
		}
		gpuColumn := strings.Join(gpuLines, "\n")
		for _, pair := range [][2]string{{"┌ GPU 0 ", "gpu-worker"}, {"┌ GPU 1", "other-gpu"}} {
			start := strings.Index(gpuColumn, pair[0])
			frame, _, _ := strings.Cut(gpuColumn[start:], "└")
			wantContains(t, frame, pair[1])
			if strings.Count(view, pair[1]) != 1 {
				t.Fatal("GPU process list was duplicated")
			}
		}
	}
}

func TestOverviewNetworkFillsShortColumnWithoutAddingRows(t *testing.T) {
	m := testModel(nil)
	m.dash = BuildDashboard(parseFixture(t, hostExposition+acceleratorExposition))
	m.dash.Processes = []Process{{PID: "200", Command: "cpu-worker"}}
	for _, width := range []int{200, 240} {
		m.width = width
		m.dash.Network = nil
		before := m.panelGrid(width)
		columns := m.overviewPrimaryColumns(width)
		last := len(columns) - 1
		expectedRow := lipgloss.Height(columns[last]) + 1
		var network networkTracker
		m.dash.Network, _ = network.update(networkSamples(fixedNow, 0, "eth0", "host"), fixedNow, m.config.Network)
		after := m.panelGrid(width)
		if lipgloss.Height(after) != lipgloss.Height(before) {
			t.Fatalf("width %d: Network added rows instead of filling the existing gap", width)
		}
		widths := m.overviewColumnWidths(width)
		line := ansi.Strip(strings.Split(after, "\n")[expectedRow])
		start := width - widths[last]
		if !strings.HasPrefix(ansi.Cut(line, start, width), "┌ Network eth0") {
			t.Fatalf("width %d: Network was not placed immediately below the right-hand panels: %q", width, line)
		}
		if strings.Count(ansi.Strip(after), "┌ Network eth0") != 1 {
			t.Fatal("Network panel duplicated")
		}
	}
}

func TestOverviewPreservesAuxiliaryLimitPanels(t *testing.T) {
	m := testModel(nil)
	m.dash.GPUs = []GPU{{ID: "0"}}
	m.dash.NetworkLimited = true
	m.dash.StorageLimited = true
	for _, width := range []int{80, 153, 224} {
		m.width = width
		view := ansi.Strip(m.panelGrid(width))
		for _, warning := range []string{"Interface limit reached", "Resource limit reached"} {
			if strings.Count(view, warning) != 1 {
				t.Fatalf("width %d: missing or duplicated warning %q", width, warning)
			}
		}
		for _, line := range strings.Split(view, "\n") {
			if lipgloss.Width(line) > width {
				t.Fatalf("width %d: warning panel overflowed", width)
			}
		}
	}
}

func TestDetailsClosesVisibleGroupAfterEverySelectionAndResize(t *testing.T) {
	for _, width := range []int{40, 80, 140, 190} {
		for _, height := range []int{24, 30, 40} {
			m := groupedDetailsModel(t, width, height)
			var tracker networkTracker
			m.dash.Network, _ = tracker.update(networkSamples(fixedNow, 0, "eth0", "host"), fixedNow, m.config.Network)
			for i := range m.detailItems() {
				m.selectDetail(i)
				frame := m.detailsLayout(width)
				if frame.visibleRows == 0 {
					continue
				}
				selectedRow := frame.itemRows[frame.selected]
				if selectedRow < frame.firstRow || selectedRow >= frame.firstRow+frame.visibleRows {
					t.Fatalf("%dx%d selection %d hidden by closing border", width, height, i)
				}
				body := strings.Split(ansi.Strip(m.detailsBody(width)), "\n")
				last := body[len(body)-1]
				if !strings.HasPrefix(last, "└") || !strings.HasSuffix(last, "┘") {
					t.Fatalf("%dx%d selection %d has no closing edge: %q", width, height, i, last)
				}
				if len(body) > m.visibleRows() {
					t.Fatalf("%dx%d closing edge was drawn outside viewport", width, height)
				}
				choice := m.detailSelection
				y := len(m.chromeLines(width)) + len(body) - 1
				m, _ = update(t, m, tea.MouseMsg{X: 2, Y: y, Button: tea.MouseButtonLeft, Action: tea.MouseActionPress})
				if m.detailSelection != choice {
					t.Fatal("click on closing edge selected a hidden metric")
				}
			}
		}
	}
}

func TestSolidChartsUseOnlyBackgroundSpacesForPeaksAndZeros(t *testing.T) {
	profile := lipgloss.ColorProfile()
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	for _, profile := range []termenv.Profile{termenv.ANSI, termenv.ANSI256} {
		lipgloss.SetColorProfile(profile)
		m := testModel(nil)
		m.chartsConfig.GraphMode = "solid"
		m.chartsConfig.ChartHeight = 3
		spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
		text := m.renderChart(spec, HistorySeries{Available: true, Points: []HistoryPoint{
			{At: fixedNow.Add(-5 * time.Minute), Value: 100},
			{At: fixedNow, Value: 0},
		}}, 18)
		if strings.ContainsAny(text, "▁▂▃▄▅▆▇█#+_") {
			t.Fatalf("solid mode emitted glyph-based bars: %q", text)
		}
		row := 0
		for _, line := range strings.Split(text, "\n") {
			if !strings.Contains(ansi.Strip(line), " │") {
				continue
			}
			fill := lipgloss.NewStyle().Background(chartRowStyle(row, 3).GetForeground()).Render(" ")
			wantRuns := 1
			if row == 2 {
				wantRuns = 2
			}
			if strings.Count(line, fill) != wantRuns {
				t.Fatalf("row %d confused measured zero with gap: %q", row, line)
			}
			_, plot, _ := strings.Cut(ansi.Strip(line), " │")
			if plot != strings.Repeat(" ", 10) {
				t.Fatalf("solid plot contains non-space text or wrong width: %q", plot)
			}
			row++
		}
		if row != 3 {
			t.Fatalf("plot rows = %d", row)
		}
	}
}

func TestSolidChartsRemainVisibleWithoutColorSupport(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	m.chartsConfig.GraphMode = "solid"
	text := m.renderChart(fixedChart("cpu.totalPercent", "CPU", "%", 0, 100),
		HistorySeries{Available: true, Points: []HistoryPoint{{At: fixedNow, Value: 100}}}, 30)
	if !strings.Contains(text, "#") || strings.ContainsAny(text, "▁▂▃▄▅▆▇█") {
		t.Fatal("monochrome output hid the solid chart")
	}
}
