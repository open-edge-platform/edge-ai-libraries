// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"reflect"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

func TestProcessSortingBeforeLimitWithoutMutatingObservations(t *testing.T) {
	m := testModel(nil)
	m.config.Processes.MaxDisplayed = 2
	m.dash.Processes = []Process{
		{PID: "20", CPUPercent: reading(99), MemoryBytes: reading(10)},
		{PID: "3", CPUPercent: reading(60), MemoryBytes: reading(30)},
		{PID: "2", CPUPercent: reading(60), MemoryBytes: reading(20)},
		{PID: "4", CPUPercent: reading(math.NaN())},
	}
	m.dash.GPUs = []GPU{{}}
	for _, p := range m.dash.Processes {
		m.dash.GPUs[0].Processes = append(m.dash.GPUs[0].Processes, GPUProcess{
			PID: p.PID, UsagePct: p.CPUPercent, MemoryBytes: p.MemoryBytes,
		})
	}
	before := dashboardObservations(m.dash, m.config.Processes.MaxDisplayed, fixedNow, m.alerts.processMaxAge)
	for _, tc := range []struct {
		sort string
		desc bool
		pids string
	}{
		{"usage", true, "20,2"},
		{"usage", false, "2,3"},
		{"memory", true, "3,2"},
		{"memory", false, "20,2"},
		{"pid", true, "20,4"},
		{"pid", false, "2,3"},
	} {
		m.config.Processes.SortBy, m.config.Processes.Descending = tc.sort, tc.desc
		var cpu, gpu []string
		for _, p := range m.sortedProcesses() {
			cpu = append(cpu, p.PID)
		}
		for _, p := range m.sortedGPUProcesses(m.dash.GPUs[0].Processes) {
			gpu = append(gpu, p.PID)
		}
		if strings.Join(cpu, ",") != tc.pids || strings.Join(gpu, ",") != tc.pids {
			t.Fatalf("%s desc=%v: CPU %v GPU %v, want %s", tc.sort, tc.desc, cpu, gpu, tc.pids)
		}
		if !reflect.DeepEqual(before, dashboardObservations(m.dash, m.config.Processes.MaxDisplayed, fixedNow, m.alerts.processMaxAge)) {
			t.Fatal("display sorting changed the alert population")
		}
	}
	if m.dash.Processes[0].PID != "20" {
		t.Fatal("display sorting mutated the source dashboard")
	}
}

func TestSortShortcutsAreScopedAndDisplayed(t *testing.T) {
	m := acceleratorModel(t, 40)
	m, _ = update(t, m, key("s"))
	if m.config.Processes.SortBy != "memory" {
		t.Fatal("s did not change the sorting key")
	}
	m, _ = update(t, m, key("r"))
	if m.config.Processes.Descending {
		t.Fatal("r did not reverse the direction")
	}
	wantContains(t, m.processSection(), "sort: memory asc")
	m, _ = update(t, m, key("h"))
	m, _ = update(t, m, key("s"))
	if m.config.Processes.SortBy != "memory" {
		t.Fatal("help changed process sorting")
	}
}

func TestMouseClicksEveryTabAtRenderedPositions(t *testing.T) {
	for _, width := range []int{30, 40, 80, 140} {
		for _, platform := range []bool{false, true} {
			m := acceleratorModel(t, 30)
			m.width = width
			if !platform {
				m.dash.Platform.Model = ""
			}
			for _, target := range []Tab{TrendsTab, DetailsTab, AlertsTab, OverviewTab} {
				x := 0
				for i, label := range m.tabLabels() {
					if Tab(i) == target {
						break
					}
					x += lipgloss.Width(label) + 3
					if Tab(i) == m.activeTab {
						x += 2
					}
				}
				y := 1
				if m.platformLine() != "" {
					y++
				}
				m, _ = update(t, m, tea.MouseMsg{X: x, Y: y, Button: tea.MouseButtonLeft, Action: tea.MouseActionPress})
				if m.activeTab != target {
					t.Fatalf("width %d platform=%v: click selected %d, want %d", width, platform, m.activeTab, target)
				}
			}
			m.config.Mouse = false
			m, _ = update(t, m, tea.MouseMsg{X: 8, Y: 1, Button: tea.MouseButtonLeft, Action: tea.MouseActionPress})
			if m.activeTab != OverviewTab {
				t.Fatal("disabled mouse changed tab")
			}
		}
	}
}

func TestAlertBottomBarHasFixedHeightAndHighestSeverity(t *testing.T) {
	m := acceleratorModel(t, 30)
	m.width = 100
	beforeRows, beforeView := m.visibleRows(), m.View()
	populateAlerts(&m, 20)
	if m.visibleRows() != beforeRows || len(strings.Split(beforeView, "\n")) != len(strings.Split(m.View(), "\n")) {
		t.Fatal("new alerts displaced the layout")
	}
	lines := m.bottomAlertLines(100)
	if len(lines) != 3 || !strings.Contains(lines[1], "20 critical") || !strings.Contains(lines[2], "CRITICAL") {
		t.Fatalf("unexpected bottom alert bar: %v", lines)
	}
	for tab := OverviewTab; tab < tabCount; tab++ {
		m.switchTab(tab)
		view := strings.Split(m.View(), "\n")
		if !strings.Contains(view[len(view)-4], "20 critical") {
			t.Fatalf("bottom bar moved on tab %d", tab)
		}
	}
	m.config.Alerts.BottomBar = false
	if len(m.bottomAlertLines(100)) != 0 || m.visibleRows() != beforeRows+3 {
		t.Fatal("disabling bottom bar did not restore its separator and two content rows")
	}
}

func TestThresholdColorsMatchAcrossOverviewAndDetails(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	for metric := range m.config.Thresholds {
		threshold := m.config.Thresholds[metric]
		for _, sample := range []struct {
			value    float64
			severity Severity
		}{
			{0, SeverityOK},
			{threshold.Careful, SeverityCareful},
			{threshold.Warning, SeverityWarning},
			{threshold.Critical, SeverityCritical},
		} {
			got := m.thresholdValue(metric, reading(sample.value), func(Reading) string { return "value" })
			want := severityStyle(sample.severity).Render("value")
			if got != want || !strings.Contains(got, "\x1b[") {
				t.Fatalf("%s: value %g rendered without correct ANSI severity", metric, sample.value)
			}
		}
	}
	if m.thresholdPercent("gpu.enginePercent", reading(95)) != m.thresholdPercent("gpu.utilizationPercent", reading(95)) {
		t.Fatal("Details engine colors differ from Overview")
	}
	for _, metric := range []string{"cpu.frequencyMHz", "gpu.powerW", "npu.memoryMiB", "memory.bandwidthGBps"} {
		if m.thresholdValue(metric, reading(9999), func(Reading) string { return "value" }) != "value" {
			t.Fatalf("%s invented a diagnostic limit", metric)
		}
	}
	m.dash.GPUs = []GPU{{ID: "0", TempC: reading(95), VRAMUsedBytes: reading(99), VRAMTotalBytes: reading(100),
		Engines:   []GPUEngine{{Name: "render", Usage: reading(99)}},
		Processes: []GPUProcess{{PID: "1", UsagePct: reading(99)}}}}
	gpu := m.gpuSection(m.dash.GPUs[0])
	for _, text := range []string{
		m.thresholdTemperature("gpu.temperatureC", reading(95)),
		m.thresholdPercent("gpu.utilizationPercent", reading(99)),
		m.thresholdPercent("gpu.processPercent", reading(99)),
		criticalStyle.Render(memoryPair(reading(99), reading(100))),
	} {
		if !strings.Contains(gpu, text) {
			t.Fatal("GPU panel dropped a colored measurement")
		}
	}
}

func TestFilledChartRendersAreaWithExactBoundsAndMissingColumns(t *testing.T) {
	m := testModel(nil)
	m.chartsConfig.GraphMode = "unicode"
	m.chartsConfig.ChartHeight = 3
	spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
	series := HistorySeries{Available: true, Points: []HistoryPoint{
		{At: fixedNow.Add(-5 * time.Minute), Value: 100},
		{At: fixedNow, Value: 0},
	}}
	view := m.renderChart(spec, series, 18)
	var grid [][]rune
	for _, line := range strings.Split(view, "\n") {
		if _, plot, ok := strings.Cut(line, " │"); ok {
			grid = append(grid, []rune(plot))
		}
	}
	if len(grid) != 3 {
		t.Fatalf("expected three plot rows, got %d", len(grid))
	}
	for row, cells := range grid {
		if cells[0] != '█' || strings.TrimSpace(string(cells[1:9])) != "" {
			t.Fatalf("row %d is not a filled peak followed by a gap: %q", row, string(cells))
		}
	}
	if grid[2][9] != '▁' || grid[0][9] != ' ' || strings.Contains(view, "●") {
		t.Fatal("measured zero should be a baseline block, not a dot or missing data")
	}
}

func TestRefreshIntervalIsVisibleAndControlsStaleness(t *testing.T) {
	m := acceleratorModel(t, 24)
	m.width = 40
	m.pollInterval = 10 * time.Second
	m.now = func() time.Time { return m.updatedAt.Add(30 * time.Second) }
	wantContains(t, m.View(), "interval: 10s")
	if strings.Contains(m.alertSummary(100), "stale") {
		t.Fatal("slow configured polling was falsely reported as stale")
	}
	m.now = func() time.Time { return m.updatedAt.Add(51 * time.Second) }
	if !strings.Contains(m.alertSummary(100), "stale") {
		t.Fatal("late data was not reported as stale")
	}
	m.pollInterval = time.Duration(1<<63 - 1)
	if m.staleAfter() != m.pollInterval {
		t.Fatal("long polling interval overflowed its stale threshold")
	}
}

func TestNewThresholdObservationsDebounceAndIgnoreUnavailableVRAM(t *testing.T) {
	m := testModel(nil)
	m.dash = Dashboard{
		CPU: CPU{Classes: []CoreClass{{Name: "P", UsageIdle: reading(0)}}},
		GPUs: []GPU{{ID: "0", VRAMUsedBytes: reading(99), VRAMTotalBytes: reading(100),
			Processes: []GPUProcess{{PID: "1", Command: "inference", UsagePct: reading(99)}}}},
	}
	for range m.config.Alerts.SamplesToRaise - 1 {
		m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	}
	if len(m.alerts.Visible()) != 0 {
		t.Fatal("new metrics bypassed alert debounce")
	}
	m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	if len(m.alerts.Visible()) != 3 {
		t.Fatalf("expected core-class, VRAM and GPU-process alerts, got %v", m.alerts.Visible())
	}
	m.dash.GPUs[0].VRAMTotalBytes = reading(0)
	for range m.config.Alerts.SamplesToClear {
		m.alerts.Update(m.dash, m.config.Thresholds, fixedNow.Add(time.Second))
	}
	if len(m.alerts.events) != 1 || m.alerts.events[0].Metric != "gpu.vramPercent" ||
		m.alerts.events[0].Outcome != "no longer observed" {
		t.Fatal("unavailable VRAM denominator was treated as recovery or measured zero")
	}
}

func TestDashboardPreferencesOverrideAndInheritDefaults(t *testing.T) {
	old, err := LoadDashboardConfig(writeConfig(t, `{"processes":{"maxDisplayed":20}}`))
	if err != nil {
		t.Fatal(err)
	}
	if old.Processes.SortBy != "usage" || !old.Processes.Descending || !old.Mouse || !old.Alerts.BottomBar {
		t.Fatal("old configuration did not inherit the new defaults")
	}
	disabled, err := LoadDashboardConfig(writeConfig(t,
		`{"mouse":false,"alerts":{"bottomBar":false},"processes":{"sortBy":"pid","descending":false}}`))
	if err != nil {
		t.Fatal(err)
	}
	if disabled.Mouse || disabled.Alerts.BottomBar || disabled.Processes.Descending || disabled.Processes.SortBy != "pid" {
		t.Fatal("explicit preferences were overridden")
	}
}

func TestCoreClassTableFitsInsideTwoColumnFrame(t *testing.T) {
	m := acceleratorModel(t, 40)
	m.width = 140
	table := m.coreClassTable(m.dash.CPU.Classes, m.panelWidth())
	if strings.Contains(table, "class:") || len(strings.Split(strings.TrimSpace(table), "\n")) != 4 {
		t.Fatal("borders unnecessarily expanded the core-class table into labelled records")
	}
	if strings.Contains(table, "classcores") {
		t.Fatal("adjacent column headings have no separator")
	}
	if lipgloss.Width(table) > m.panelWidth() {
		t.Fatal("core-class table exceeded the frame interior")
	}
}

func TestDashboardViewsFitTerminalBounds(t *testing.T) {
	for _, width := range []int{1, 2, 12, 20, 40, 80, 139, 210} {
		for _, height := range []int{1, 5, 8, 12, 24, 40} {
			m := acceleratorModel(t, height)
			m.width = width
			for tab := OverviewTab; tab < tabCount; tab++ {
				m.switchTab(tab)
				for _, line := range strings.Split(m.View(), "\n") {
					if lipgloss.Width(line) > width {
						t.Fatalf("%dx%d tab %d overflow: %q", width, height, tab, line)
					}
				}
				if len(strings.Split(m.View(), "\n")) > height {
					t.Fatalf("%dx%d tab %d exceeded height", width, height, tab)
				}
			}
		}
	}
	m := acceleratorModel(t, 40)
	m.width = 140
	t.Log("\n" + m.View())
	m.switchTab(DetailsTab)
	for i := range 601 {
		m.dash.CPU.UsageIdle = reading(float64(90 - (i/5%20)*4))
		m.history.Update(m.dash, fixedNow.Add(time.Duration(i-600)*500*time.Millisecond))
	}
	t.Log("\n" + m.View())
}
