// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

func populateAlerts(m *Model, count int) {
	m.updatedAt = fixedNow
	m.dash.GPUs = nil
	for i := range count {
		m.dash.GPUs = append(m.dash.GPUs, GPU{
			ID:      fmt.Sprint(i),
			Engines: []GPUEngine{{Name: "render", Usage: reading(99)}},
		})
	}
	for range m.config.Alerts.SamplesToRaise {
		m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	}
}

func TestAlertsDoNotChangePanelPositions(t *testing.T) {
	for _, width := range []int{40, 80, 139, 210} {
		m := acceleratorModel(t, 24)
		m.width = width
		before := m.panelGrid(width)
		headerHeight := len(m.chromeLines(width))
		for range 3 {
			m.alerts.Update(Dashboard{Memory: Memory{UsedPercent: reading(95)}},
				m.config.Thresholds, fixedNow)
		}
		if after := m.panelGrid(width); before != after {
			t.Errorf("alerts changed panel layout at width %d", width)
		}
		if len(m.chromeLines(width)) != headerHeight {
			t.Errorf("unexpected header height at width %d", width)
		}
	}
}

func TestAlertDetailsScrollAndRestoreTab(t *testing.T) {
	m := acceleratorModel(t, 24)
	populateAlerts(&m, 30)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	overviewOffset := m.offset
	m, _ = update(t, m, key("a"))
	if m.activeTab != AlertsTab || m.offset != 0 {
		t.Fatal("details did not open at top")
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	detailOffset := m.offset
	if detailOffset == 0 {
		t.Fatal("details did not scroll")
	}
	m, cmd := update(t, m, key("esc"))
	if isQuit(cmd) || m.activeTab == AlertsTab || m.offset != overviewOffset {
		t.Fatal("escape did not restore Overview without quitting")
	}
	m, _ = update(t, m, key("a"))
	if m.offset != detailOffset {
		t.Fatal("details lost independent scroll position")
	}
	m, _ = update(t, m, key("2"))
	if m.activeTab != TrendsTab {
		t.Fatal("tab shortcut did not close details and select Trends")
	}
}

func TestAlertSummaryStaysVisibleAcrossTabsAndScrolling(t *testing.T) {
	m := acceleratorModel(t, 24)
	populateAlerts(&m, 20)
	for _, tab := range []Tab{OverviewTab, TrendsTab} {
		m.switchTab(tab)
		m.setOffset(m.maxOffset())
		view := m.View()
		wantContains(t, view, "Alerts: 20 critical")
		wantContains(t, view, "Overview")
	}
	m.err = errors.New("offline")
	wantContains(t, m.View(), "Alerts: no contact")
	m.err = nil
	m.updatedAt = fixedNow.Add(-time.Minute)
	wantContains(t, m.View(), "Alerts: stale data")
}

func TestAlertDetailsFitTerminalSizes(t *testing.T) {
	for _, width := range []int{20, 40, 80, 139, 210} {
		for _, height := range []int{1, 2, 5, 8, 24, 50} {
			m := testModel(nil)
			populateAlerts(&m, 20)
			m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: height})
			for _, details := range []bool{false, true} {
				m.switchTab(OverviewTab)
				if details {
					m.switchTab(AlertsTab)
				}
				view := m.View()
				lines := strings.Split(view, "\n")
				if len(lines) > height {
					t.Errorf("%dx%d details=%v: got %d lines", width, height, details, len(lines))
				}
				for _, line := range lines {
					if lipgloss.Width(line) > width {
						t.Errorf("%dx%d: line too wide: %q", width, height, line)
					}
				}
			}
		}
	}
}

func TestCompactTablesKeepMeasurements(t *testing.T) {
	m := testModel(nil)
	m.width = 40
	m.dash = Dashboard{
		Platform: Platform{LogicalCPUs: reading(1)},
		CPU: CPU{Classes: []CoreClass{{
			Name: "P", Cores: reading(4), FrequencyKHz: reading(2300000),
			UsageUser: reading(15), UsageSystem: reading(20), UsageIdle: reading(65), Source: "pmu",
		}}},
		Processes: []Process{{PID: "123", Command: "worker", CPUPercent: reading(87), MemoryBytes: reading(1073741824)}},
		GPUs: []GPU{{ID: "0", Tiles: []GPUTile{{
			Name: "gt0", ActualMHz: reading(900), RequestedMHz: reading(1200),
			ThrottleReported: true, ThrottleReasons: []string{"thermal"},
		}}}},
	}
	view := m.View()
	for _, want := range []string{"system: 20.0%", "idle: 65.0%", "source: pmu",
		"throttle: thermal"} {
		wantContains(t, view, want)
	}
	m.moveProcessColumns(10000)
	for _, want := range []string{"87.0%", "1.0 GiB"} {
		wantContains(t, m.View(), want)
	}
}

func TestAlertDetailsSanitizeNamesAndShowUnits(t *testing.T) {
	alert := Alert{Metric: "cpu.temperatureC", Device: "GPU\x1b[2J\x07\n0",
		Severity: SeverityCritical, Value: 99, Threshold: 95, Since: fixedNow,
		Message: "Check\x1b[2J cooling"}
	view := renderAlert(alert, fixedNow.Add(5*time.Second), "active")
	if strings.Contains(view, "\x1b[2J") || strings.Contains(view, "\x07") {
		t.Fatalf("terminal controls survived: %q", view)
	}
	wantContains(t, view, "99.0 C")
	wantContains(t, view, "duration 5s")
	alert.Unavailable = true
	view = renderAlert(alert, fixedNow, "active")
	wantContains(t, view, "waiting for data")
	wantContains(t, view, "last observed")
}

func TestColoredTablesKeepColumnAlignment(t *testing.T) {
	plain := []string{"7", "worker", "16", "test-user", "1.0 GiB", "87.0%"}
	colored := []string{"7", "worker", "16", "test-user", "1.0 GiB", "\x1b[31m87.0%\x1b[0m"}
	want := tableRow(processColumns, plain)
	got := tableRow(processColumns, colored)
	got = strings.ReplaceAll(strings.ReplaceAll(got, "\x1b[31m", ""), "\x1b[0m", "")
	if got != want {
		t.Errorf("color moved columns:\ngot  %q\nwant %q", got, want)
	}
}

func TestAlertHistoryDetails(t *testing.T) {
	m := testModel(nil)
	populateAlerts(&m, 1)
	for range m.config.Alerts.SamplesToClear {
		m.alerts.Update(Dashboard{}, m.config.Thresholds, fixedNow.Add(time.Second))
	}
	m.switchTab(AlertsTab)
	view := m.View()
	for _, want := range []string{"Active (0)", "Recent history (1/50)", "[no longer observed]", "GPU 0 / render", "last observed 99.0%"} {
		wantContains(t, view, want)
	}
}

func TestViewLimitsGPUProcessesToo(t *testing.T) {
	m := testModel(nil)
	m.config.Processes.MaxDisplayed = 1
	m.dash.GPUs = []GPU{{ID: "0", Processes: []GPUProcess{
		{PID: "1", Command: "visible"}, {PID: "2", Command: "hidden"},
	}}}
	view := m.View()
	wantContains(t, view, "visible")
	if strings.Contains(view, "hidden") {
		t.Fatal("GPU process table exceeded display limit")
	}
}
