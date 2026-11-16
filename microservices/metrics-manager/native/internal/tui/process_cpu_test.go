// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func TestProcessCPUModeConfiguration(t *testing.T) {
	for _, tc := range []struct {
		config, want string
	}{
		{`{}`, "total"},
		{`{"processes":{"maxDisplayed":20}}`, "total"},
		{`{"processes":{"cpuMode":"per-core"}}`, "per-core"},
		{`{"processes":{"cpuMode":"total"}}`, "total"},
	} {
		config, err := LoadDashboardConfig(writeConfig(t, tc.config))
		if err != nil {
			t.Fatal(err)
		}
		if config.Processes.CPUMode != tc.want {
			t.Fatalf("%s: CPU mode = %q, want %q", tc.config, config.Processes.CPUMode, tc.want)
		}
		m := NewModelWithConfig(nil, config)
		wantContains(t, m.processCPULabel(), "CPU: "+tc.want)
	}
}

func TestProcessCPUDisplayUsesReportedCPUCount(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	for _, tc := range []struct {
		value, cpus    float64
		perCore, total string
	}{
		{140, 14, "140.0%", "10.0%"},
		{280, 14, "280.0%", "20.0%"},
		{1400, 14, "1400.0%", "100.0%"},
		{100, 14, "100.0%", "7.1%"},
		{100, 1, "100.0%", "100.0%"},
		{0, 14, "0.0%", "0.0%"},
	} {
		m.dash.Platform.LogicalCPUs = reading(tc.cpus)
		raw := reading(tc.value)
		m.config.Processes.CPUMode = "per-core"
		if got := m.processCPUPercent(raw); got != tc.perCore {
			t.Errorf("%+v: per-core = %q", tc, got)
		}
		m.config.Processes.CPUMode = "total"
		if got := m.processCPUPercent(raw); got != tc.total {
			t.Errorf("%+v: total = %q", tc, got)
		}
		if raw.Value != tc.value {
			t.Fatal("formatting modified the raw measurement")
		}
	}
	for _, raw := range []Reading{{}, reading(math.NaN()), reading(math.Inf(1))} {
		if got, want := m.processCPUPercent(raw), formatPercent(raw); got != want {
			t.Errorf("placeholder = %q, want %q", got, want)
		}
	}
}

func TestProcessCPUTotalRejectsUnusableCountsAndRecovers(t *testing.T) {
	m := testModel(nil)
	m.config.Processes.CPUMode = "total"
	for _, count := range []Reading{
		{}, reading(0), reading(-1), reading(0.5), reading(1.5),
		reading(math.NaN()), reading(math.Inf(1)), reading(math.Inf(-1)),
	} {
		m.dash.Platform.LogicalCPUs = count
		if got := m.processCPUPercent(reading(140)); got != unavailable {
			t.Fatalf("count %+v produced %q instead of n/a", count, got)
		}
		wantContains(t, m.processCPULabel(), "CPU total unavailable")
	}
	m.dash.Platform.LogicalCPUs = reading(14)
	wantContains(t, m.processCPUPercent(reading(140)), "10.0%")
	wantContains(t, m.processCPULabel(), "100% = 14 CPUs")
	m.dash.Platform.LogicalCPUs = reading(7)
	wantContains(t, m.processCPUPercent(reading(140)), "20.0%")
	m.dash.Platform.LogicalCPUs = Reading{}
	m.toggleProcessCPUMode()
	wantContains(t, m.processCPUPercent(reading(140)), "140.0%")
}

func TestProcessCPUModeShortcutScopeAndPersistence(t *testing.T) {
	for _, tab := range []Tab{OverviewTab, TrendsTab, DetailsTab, AlertsTab} {
		for _, help := range []bool{false, true} {
			m := testModel(nil)
			m.activeTab, m.showHelp = tab, help
			m, _ = update(t, m, key("c"))
			want := "total"
			if tab == OverviewTab && !help {
				want = "per-core"
			}
			if m.config.Processes.CPUMode != want {
				t.Fatalf("tab=%d help=%v: mode=%q, want %q", tab, help, m.config.Processes.CPUMode, want)
			}
		}
	}
	m := testModel(nil)
	m, _ = update(t, m, key("c"))
	for _, keyName := range []string{"2", "3", "4", "1", "h", "h"} {
		m, _ = update(t, m, key(keyName))
		if m.config.Processes.CPUMode != "per-core" {
			t.Fatalf("%s reset the selected CPU mode", keyName)
		}
	}
	m, _ = update(t, m, key("c"))
	if m.config.Processes.CPUMode != "total" {
		t.Fatal("second toggle did not restore total")
	}
	wantContains(t, m.helpBody(120), "c: toggle process CPU")
	wantContains(t, CommandLineHelp(), "c CPU mode")
}

func TestProcessCPUModePreservesColorThresholds(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	m.config.Processes.CPUMode = "total"
	m.dash.Platform.LogicalCPUs = reading(14)
	for _, tc := range []struct {
		value    float64
		severity Severity
	}{
		{95.2, SeverityOK}, {49 * 14, SeverityOK}, {50 * 14, SeverityCareful},
		{70 * 14, SeverityWarning}, {90 * 14, SeverityCritical}, {100 * 14, SeverityCritical},
	} {
		m.config.Processes.CPUMode = "total"
		want := severityStyle(tc.severity).Render(formatPercent(reading(tc.value / 14)))
		if got := m.processCPUPercent(reading(tc.value)); got != want {
			t.Fatalf("%g: normalized CPU changed the threshold color: got %q, want %q", tc.value, got, want)
		}
		m.config.Processes.CPUMode = "per-core"
		want = severityStyle(tc.severity).Render(formatPercent(reading(tc.value)))
		if got := m.processCPUPercent(reading(tc.value)); got != want {
			t.Fatalf("%g: per-core display did not preserve total CPU health: %q", tc.value, got)
		}
	}
	m.config.Processes.CPUMode = "total"
	delete(m.config.Thresholds, "process.cpuPercent")
	if got := m.processCPUPercent(reading(140)); got != "10.0%" {
		t.Fatalf("disabled threshold still colored CPU: %q", got)
	}
}

func TestProcessCPUModePreservesMeasurementsSortingAndAlerts(t *testing.T) {
	m := testModel(nil)
	for i := range 3 {
		at := fixedNow.Add(time.Duration(i-2) * time.Second)
		m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: parseFixture(t,
			fmt.Sprintf("platform_logical_cpus 14\nprocess_cpu_percent{pid=\"42\",process=\"worker\"} 1330 %d\n"+
				"process_cpu_percent{pid=\"43\",process=\"other\"} 40 %d\n"+
				"process_memory_rss_bytes{pid=\"42\",process=\"worker\"} 1048576\n", at.UnixMilli(), at.UnixMilli()))}))
	}
	m.dash.GPUs = []GPU{{ID: "0", Processes: []GPUProcess{{PID: "42", UsagePct: reading(80)}}}}
	alerts := m.alerts.Active()
	if len(alerts) != 1 || alerts[0].Value != 95 {
		t.Fatalf("fixture did not raise a total CPU alert: %+v", alerts)
	}
	observations := dashboardObservations(m.dash, m.config.Processes.MaxDisplayed, fixedNow, m.alerts.processMaxAge)
	processes := m.sortedProcesses()
	gpu := m.gpuProcessTable(m.dash.GPUs[0].Processes, 80)
	host := m.cpuSection()
	m, _ = update(t, m, key("c"))
	wantContains(t, m.processSection(), "1330.0%")
	wantContains(t, m.processSection(), "Colors/alerts: total host CPU")
	m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	if !reflect.DeepEqual(observations, dashboardObservations(m.dash, m.config.Processes.MaxDisplayed, fixedNow, m.alerts.processMaxAge)) ||
		!reflect.DeepEqual(processes, m.sortedProcesses()) || !reflect.DeepEqual(alerts, m.alerts.Active()) {
		t.Fatal("CPU display mode changed measurements, sorting or alert evidence")
	}
	if gpu != m.gpuProcessTable(m.dash.GPUs[0].Processes, 80) || host != m.cpuSection() {
		t.Fatal("CPU display mode changed GPU process usage or host CPU")
	}
	wantContains(t, strings.Join(strings.Fields(m.alertDetails(120)), " "), "regardless of the Overview CPU display mode")
}

func TestProcessTotalCPUDoesNotAlertForOneBusyCore(t *testing.T) {
	m := testModel(nil)
	m.dash.Platform.LogicalCPUs = reading(14)
	for i := range 3 {
		at := fixedNow.Add(time.Duration(i-2) * time.Second)
		m.dash.Processes = []Process{{PID: "42", CPUPercent: reading(95.2), CPUAt: at}}
		m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	}
	if len(m.alerts.Active()) != 0 || m.processCoverageLimited() {
		t.Fatal("6.8% total CPU raised an alert or a false timestamp conflict")
	}
	wantContains(t, m.processCPUPercent(reading(95.2)), "6.8%")
	m, _ = update(t, m, key("c"))
	wantContains(t, m.processCPUPercent(reading(95.2)), "95.2%")
	if len(m.alerts.Active()) != 0 || m.processCoverageLimited() {
		t.Fatal("per-core display changed total CPU alert evaluation")
	}
	m.config.Thresholds["process.cpuPercent"] = Threshold{Careful: 1, Warning: 5, Critical: 10}
	for i := range 3 {
		m.dash.Processes[0].CPUAt = fixedNow.Add(time.Duration(i+1) * time.Second)
		m.alerts.Update(m.dash, m.config.Thresholds, m.dash.Processes[0].CPUAt)
	}
	alerts := m.alerts.Active()
	if len(alerts) != 1 || alerts[0].Severity != SeverityWarning || math.Abs(alerts[0].Value-6.8) > 1e-9 {
		t.Fatalf("custom total CPU thresholds were not respected: %+v", alerts)
	}
}

func TestProcessCPUAlertsRequireUsableHostCPUCount(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	for _, count := range []Reading{{}, reading(0), reading(-1), reading(1.5), reading(math.NaN()), reading(math.Inf(1))} {
		config := DefaultDashboardConfig()
		config.Alerts.SamplesToRaise = 1
		m := NewModelWithConfig(nil, config)
		m.now = func() time.Time { return fixedNow }
		m.dash.Platform.LogicalCPUs = count
		m.dash.Processes = []Process{{PID: "42", CPUPercent: reading(1330), CPUAt: fixedNow}}
		m.alerts.Update(m.dash, config.Thresholds, fixedNow)
		if len(m.alerts.Active()) != 0 || !m.processCoverageLimited() || m.processCPUPercent(reading(1330)) != unavailable {
			t.Fatalf("unusable CPU count %+v produced a total or an alert", count)
		}
		wantContains(t, m.processAlertIssues()[0].reason, "logical CPU count missing or invalid")
		m.toggleProcessCPUMode()
		if got := m.processCPUPercent(reading(1330)); got != "1330.0%" {
			t.Fatalf("per-core fallback was colored or lost the raw value: %q", got)
		}
		m.dash.Platform.LogicalCPUs = reading(14)
		m.alerts.Update(m.dash, config.Thresholds, fixedNow)
		if len(m.alerts.Active()) != 1 || m.processCoverageLimited() || m.alerts.Active()[0].Value != 95 {
			t.Fatal("restoring the CPU count did not restore total CPU evaluation")
		}
		m.dash.Platform.LogicalCPUs = count
		for range config.Alerts.SamplesToClear {
			m.alerts.Update(m.dash, config.Thresholds, fixedNow)
		}
		if len(m.alerts.events) != 1 || m.alerts.events[0].Outcome != "no longer observed" || m.alerts.events[0].RecoveryValue.OK {
			t.Fatal("loss of CPU count was reported as recovery")
		}
	}
}

func TestProcessCPUModesFitResponsivePanels(t *testing.T) {
	m := testModel(nil)
	m.dash.Processes = []Process{{PID: "42", Command: "worker", CPUPercent: reading(140)}}
	for _, width := range []int{30, 40, 80, 120, 180} {
		m.width = width
		for _, count := range []Reading{{}, reading(14)} {
			m.dash.Platform.LogicalCPUs = count
			for _, mode := range []string{"per-core", "total"} {
				m.config.Processes.CPUMode = mode
				m.moveProcessColumns(10000)
				panel := framePanel(m.processSection(), width)
				for _, line := range strings.Split(panel, "\n") {
					if lipgloss.Width(line) > width {
						t.Fatalf("width=%d mode=%s: panel overflow %q", width, mode, line)
					}
				}
				wantContains(t, panel, "CPU: "+mode)
				wantContains(t, panel, "c toggle")
				wantValue := "140.0%"
				if mode == "total" {
					wantValue = unavailable
					if count.OK {
						wantValue = "10.0%"
					}
				}
				wantContains(t, panel, wantValue)
			}
		}
	}
}
