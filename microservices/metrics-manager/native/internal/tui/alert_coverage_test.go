// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"math"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

func TestProcessCoverageIdentifiesReasonsAndUsesActualAlertCandidates(t *testing.T) {
	m := testModel(nil)
	m.dash.Platform.LogicalCPUs = reading(1)
	m.updatedAt = fixedNow
	m.dash.Processes = []Process{
		{PID: "1", Command: "fresh", CPUPercent: reading(10), CPUAt: fixedNow},
		{PID: "2", Command: "missing", CPUPercent: reading(20)},
		{PID: "3", Command: "old", CPUPercent: reading(30), CPUAt: fixedNow.Add(-11 * time.Second)},
		{PID: "4", Command: "future", CPUPercent: reading(40), CPUAt: fixedNow.Add(time.Second)},
		{PID: "5", Command: "invalid", CPUPercent: reading(math.NaN()), CPUAt: fixedNow},
		{PID: "6", Command: "rewound", CPUPercent: reading(60), CPUAt: fixedNow.Add(-time.Second)},
		{PID: "7", Command: "conflict", CPUPercent: reading(70), CPUAt: fixedNow},
	}
	m.alerts.states["process.6"] = &alertState{observedAt: fixedNow, observedValue: 60}
	m.alerts.states["process.7"] = &alertState{observedAt: fixedNow, observedValue: 71}
	issues := m.processAlertIssues()
	wantReasons := []string{
		"measurement timestamp missing", "measurement timestamp is in the future",
		"CPU measurement missing or non-finite", "out-of-order measurement timestamp", "conflicting CPU values at one timestamp",
	}
	if len(issues) != len(wantReasons) {
		t.Fatalf("issues = %+v", issues)
	}
	for i, reason := range wantReasons {
		if issues[i].reason != reason {
			t.Fatalf("issue %d = %+v, want %q", i, issues[i], reason)
		}
	}
	view := m.alertDetails(140)
	for _, want := range []string{
		"Process CPU alert coverage (5/6 limited)", "missing (PID 2): measurement timestamp missing",
		"source time", "checked", "export_timestamp=true",
		"this does not block process collection or display",
	} {
		wantContains(t, view, want)
	}
	m.config.Processes.SortBy = "pid"
	m.config.Processes.Descending = true
	for i, issue := range m.processAlertIssues() {
		if issue.reason != issues[i].reason || issue.process.PID != issues[i].process.PID {
			t.Fatal("display sorting changed the diagnostic population")
		}
	}
	m.alerts.processLimit = 1
	if m.sortedProcesses()[0].PID == "1" {
		t.Fatal("fixture must display different processes from those evaluated for alerts")
	}
	if len(m.processAlertIssues()) != 0 {
		t.Fatal("a process outside the alert population limited coverage")
	}
	m.alerts.processLimit = 2
	if got := m.processAlertIssues(); len(got) != 1 || got[0].process.PID != "2" {
		t.Fatalf("coverage did not respect the evaluation limit: %+v", got)
	}
	delete(m.config.Thresholds, "process.cpuPercent")
	if len(m.processAlertIssues()) != 0 {
		t.Fatal("unmonitored process CPU produced a coverage warning")
	}
}

func TestAlertShortcutsAndCoverageStayVisibleWithoutAddingFooterRows(t *testing.T) {
	m := testModel(nil)
	m.dash.Platform.LogicalCPUs = reading(1)
	m.updatedAt = fixedNow
	m.dash.Processes = []Process{{PID: "42", Command: "worker", CPUPercent: reading(10)}}
	for _, width := range []int{40, 70, 80, 100, 140} {
		text := ansi.Strip(m.alertSummary(width))
		if !strings.Contains(text, "[4/a]") || !strings.Contains(text, "CPU") ||
			strings.Contains(text, "details") || lipgloss.Width(text) > width {
			t.Fatalf("width %d ambiguous or clipped status: %q", width, text)
		}
		if len(m.bottomAlertLines(width)) != 3 {
			t.Fatal("coverage expanded the fixed footer")
		}
		m.config.Alerts.ShowCareful = true
		if text := ansi.Strip(m.alertSummary(width)); lipgloss.Width(text) > width || !strings.Contains(text, "CPU") {
			t.Fatalf("width %d careful counts hid limited coverage: %q", width, text)
		}
		m.config.Alerts.ShowCareful = false
	}
	for _, err := range []error{nil, errors.New("test disconnect")} {
		m.err = err
		for _, at := range []time.Time{fixedNow, fixedNow.Add(-time.Minute), {}} {
			m.updatedAt = at
			text := m.alertSummary(140)
			if !strings.Contains(text, "[4/a] Open alerts") || strings.Contains(text, "a details") {
				t.Fatalf("connection state used ambiguous navigation: %q", text)
			}
		}
	}
	m.err, m.updatedAt = nil, fixedNow
	m.config.Alerts.BottomBar = false
	for _, width := range []int{70, 100, 140} {
		text := strings.Join(m.chromeLines(width), "\n")
		if !strings.Contains(text, "CPU") || !strings.Contains(text, "[4/a]") {
			t.Fatalf("width %d disabled bottom bar hid coverage or navigation: %q", width, text)
		}
	}
	m.dash.Processes[0].CPUAt = fixedNow
	if strings.Contains(m.alertSummary(140), "limited") || strings.Contains(m.alertDetails(140), "alert coverage") {
		t.Fatal("healthy timestamps retained a data-quality warning")
	}
}

func TestProcessCoverageDiagnosticsSanitizeUntrustedLabels(t *testing.T) {
	m := testModel(nil)
	m.dash.Processes = []Process{{PID: "4\x1b[2J2", Command: "worker\n\u009b2J", CPUPercent: reading(5)}}
	text := m.alertDetails(120)
	for _, unsafe := range []string{"\x1b[2J", "\u009b", "worker\n"} {
		if strings.Contains(text, unsafe) {
			t.Fatalf("diagnostic emitted terminal control %q", unsafe)
		}
	}
}

func TestCachedProcessesDoNotCrowdOutCurrentProcessesOrRaiseLimitedStatus(t *testing.T) {
	m := testModel(nil)
	m.config.Processes.MaxDisplayed = 1
	m.alerts.processLimit = 1
	now := fixedNow
	m.now = func() time.Time { return now }
	old := fixedNow.Add(-30 * time.Second)
	for i := 0; i < 3; i++ {
		now = fixedNow.Add(time.Duration(i) * time.Second)
		text := fmt.Sprintf("platform_logical_cpus 1\nprocess_cpu_percent{pid=\"1\",process=\"systemd\"} 999 %d\n"+
			"process_memory_rss_bytes{pid=\"1\",process=\"systemd\"} 999999 %d\n"+
			"process_cpu_percent{pid=\"42\",process=\"worker\"} 99 %d\n"+
			"process_memory_rss_bytes{pid=\"42\",process=\"worker\"} 100 %d\n",
			old.UnixMilli(), old.UnixMilli(), now.UnixMilli(), now.UnixMilli())
		model, _ := m.Update(snapshotMsg{Samples: parseFixture(t, text), At: now})
		m = model.(Model)
	}
	for _, sort := range []string{"usage", "memory", "pid"} {
		m.config.Processes.SortBy = sort
		if rows := m.sortedProcesses(); len(rows) != 1 || rows[0].PID != "42" {
			t.Fatalf("%s let retained data crowd out current data: %+v", sort, rows)
		}
	}
	if m.processCoverageLimited() || strings.Contains(m.alertSummary(140), "limited") {
		t.Fatal("normal cache retention raised limited coverage")
	}
	wantContains(t, m.alertDetails(140), "Retained process samples (1 excluded)")
	active := m.alerts.Active()
	if len(active) != 1 || active[0].Key != "process.42" {
		t.Fatalf("current process could not raise an alert: %+v", active)
	}

	now = now.Add(11 * time.Second)
	if !m.processCoverageLimited() || len(m.sortedProcesses()) != 0 {
		t.Fatal("loss of all fresh samples did not report unavailable process data")
	}
	wantContains(t, m.alertDetails(140), "Process CPU data unavailable")
	// Telegraf eventually expires the cached series altogether.
	for i := 0; i < 3; i++ {
		model, _ := m.Update(snapshotMsg{At: now})
		m = model.(Model)
	}
	if !m.processCoverageLimited() {
		t.Fatal("cache expiration hid loss of the previously observed source")
	}
	if len(m.alerts.events) != 1 || m.alerts.events[0].Outcome != "no longer observed" {
		t.Fatalf("disappearance was incorrectly treated as recovery: %+v", m.alerts.events)
	}
	now = now.Add(time.Second)
	text := fmt.Sprintf("platform_logical_cpus 1\nprocess_cpu_percent{pid=\"42\",process=\"worker\"} 0 %d", now.UnixMilli())
	model, _ := m.Update(snapshotMsg{Samples: parseFixture(t, text), At: now})
	m = model.(Model)
	if m.processCoverageLimited() {
		t.Fatal("fresh samples did not restore process coverage")
	}
}

func TestProcessExpirationBoundaryAndOptionalSource(t *testing.T) {
	m := testModel(nil)
	if m.processCoverageLimited() {
		t.Fatal("a source never observed should remain optional")
	}
	for _, tc := range []struct {
		stamp   time.Time
		expired bool
	}{
		{fixedNow.Add(-3 * time.Second), false},
		{fixedNow.Add(-3*time.Second - time.Nanosecond), true},
		{time.Time{}, false},
		{fixedNow.Add(time.Second), false},
	} {
		m.dash.Processes = []Process{{PID: "1", Command: "systemd", CPUPercent: reading(99), CPUAt: tc.stamp}}
		if got := len(currentProcesses(m.dash, fixedNow, m.alerts.processMaxAge)) == 0; got != tc.expired {
			t.Fatalf("timestamp %v expired=%v, want %v", tc.stamp, got, tc.expired)
		}
		if !tc.expired && !freshProcessCPU(tc.stamp, fixedNow, m.alerts.processMaxAge) && !m.processCoverageLimited() {
			t.Fatal("missing/future timestamps were silently ignored as cached entries")
		}
	}
}
