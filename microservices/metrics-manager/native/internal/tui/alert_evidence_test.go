// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func TestProcessAlertsRequireDistinctMeasurementsAndRetainEpisodeEvidence(t *testing.T) {
	m := testModel(nil)
	values := []float64{91, 94, 96, 99, 7, 4, 3}
	for i, value := range values {
		at := fixedNow.Add(time.Duration(i) * time.Second)
		text := fmt.Sprintf("platform_logical_cpus 14\nprocess_cpu_percent{pid=\"42\",process=\"mm-tui\"} %.1f %d\n", value*14, at.UnixMilli())
		for poll := 0; poll < 4; poll++ {
			m, _ = update(t, m, snapshotMsg(source.Snapshot{
				At: at.Add(time.Duration(poll) * 100 * time.Millisecond), Samples: parseFixture(t, text),
			}))
		}
		if i < 2 && len(m.alerts.Visible()) != 0 {
			t.Fatal("cached process samples raised an alert")
		}
		if i >= 2 && i < 6 && len(m.alerts.Visible()) != 1 {
			t.Fatal("cached recovery samples closed the alert")
		}
		if i == 4 {
			wantContains(t, renderAlert(m.alerts.Visible()[0], at, "active"), "recovery is not yet confirmed")
		}
	}
	if len(m.alerts.events) != 1 || len(m.alerts.Visible()) != 0 {
		t.Fatalf("events = %+v", m.alerts.events)
	}
	event := m.alerts.events[0]
	if event.TriggerValue != reading(96) || event.TriggerThreshold != 90 ||
		event.PeakValue != reading(99) || !event.PeakAt.Equal(fixedNow.Add(3*time.Second)) ||
		event.RecoveryValue != reading(3) || event.Value != 4 || event.Outcome != "recovered" {
		t.Fatalf("episode evidence was replaced by a low recovery reading: %+v", event)
	}
	text := renderAlert(event.Alert, event.EndedAt, event.Outcome)
	for _, want := range []string{
		"mm-tui (PID 42)", "activated at 96.0% | activation threshold 90.0%",
		"peak since activation 99.0%", "confirmed recovery at 3.0%", "last observed 4.0%",
	} {
		wantContains(t, text, want)
	}
}

func TestProcessAlertStreakBreaksOnMissingInvalidAndOldTimestamps(t *testing.T) {
	for _, stamp := range []int64{0, fixedNow.Add(-11 * time.Second).UnixMilli(), fixedNow.Add(time.Minute).UnixMilli()} {
		m := testModel(nil)
		send := func(measuredMS int64, at time.Time) {
			t.Helper()
			text := fmt.Sprintf("platform_logical_cpus 1\nprocess_cpu_percent{pid=\"42\",process=\"worker\"} 99 %d\n", measuredMS)
			m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: parseFixture(t, text)}))
		}
		send(fixedNow.UnixMilli(), fixedNow)
		send(fixedNow.Add(time.Second).UnixMilli(), fixedNow.Add(time.Second))
		send(stamp, fixedNow.Add(2*time.Second))
		send(fixedNow.Add(3*time.Second).UnixMilli(), fixedNow.Add(3*time.Second))
		if len(m.alerts.Visible()) != 0 {
			t.Fatalf("timestamp %d failed to break a process alert streak", stamp)
		}
	}
}

func TestProcessAlertMissingDataKeepsEvidenceWithoutClaimingRecovery(t *testing.T) {
	config := DefaultDashboardConfig()
	config.Alerts.SamplesToRaise = 1
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	tracker.Update(Dashboard{Platform: Platform{LogicalCPUs: reading(1)}, Processes: []Process{{PID: "1", CPUPercent: reading(99), CPUAt: fixedNow}}},
		config.Thresholds, fixedNow)
	for i := 1; i <= config.Alerts.SamplesToClear; i++ {
		tracker.Update(Dashboard{}, config.Thresholds, fixedNow.Add(time.Duration(i)*time.Second))
	}
	if len(tracker.events) != 1 {
		t.Fatal("expected ended process episode")
	}
	event := tracker.events[0]
	if event.RecoveryValue.OK || event.TriggerValue != reading(99) || event.PeakValue != reading(99) ||
		event.Outcome != "no longer observed" {
		t.Fatalf("missing process fabricated recovery or lost evidence: %+v", event)
	}
}

func TestAlertEvidenceSurvivesEscalationAndRecoveryDebounce(t *testing.T) {
	config := DefaultDashboardConfig()
	config.Alerts.SamplesToRaise = 1
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for i, value := range []float64{75, 95, 4, 3, 2} {
		tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(value)}}, config.Thresholds,
			fixedNow.Add(time.Duration(i)*time.Second))
	}
	event := tracker.events[0]
	if event.TriggerValue != reading(75) || event.TriggerThreshold != 70 ||
		event.PeakValue != reading(95) || event.RecoveryValue != reading(2) || event.Severity != SeverityCritical {
		t.Fatalf("severity changes lost original evidence: %+v", event)
	}
}

func TestMissingProcessTimestampsAreExplainedInAlertsNotTheProcessTable(t *testing.T) {
	m := testModel(nil)
	m.dash = BuildDashboard(parseFixture(t, `process_cpu_percent{pid="42",process="worker"} 99`))
	m.dash.Platform.LogicalCPUs = reading(1)
	m.updatedAt = fixedNow
	if strings.Contains(m.processSection(), "CPU alerts") {
		t.Fatal("technical alert diagnostic still occupies the process table")
	}
	wantContains(t, m.alertDetails(120), "worker (PID 42): measurement timestamp missing")
	wantContains(t, m.alertSummary(120), "Process CPU alerts: limited")
	m.alerts.Update(m.dash, m.config.Thresholds, fixedNow)
	if len(m.alerts.Active()) != 0 {
		t.Fatal("untimestamped process raised an alert")
	}

	m.dash.Processes[0].CPUAt = fixedNow
	if len(m.processAlertIssues()) != 0 {
		t.Fatal("fresh timestamp still reports limited CPU alerts")
	}
}

func TestProcessAlertStreakBreaksOnConflictingOrRewoundMeasurements(t *testing.T) {
	for _, rewind := range []bool{false, true} {
		config := DefaultDashboardConfig()
		tracker := NewAlertTracker(config.Alerts, config.Processes)
		send := func(stamp, now time.Time, value float64) {
			tracker.Update(Dashboard{Platform: Platform{LogicalCPUs: reading(1)}, Processes: []Process{{PID: "42", CPUPercent: reading(value), CPUAt: stamp}}},
				config.Thresholds, now)
		}
		send(fixedNow, fixedNow, 99)
		at := fixedNow.Add(time.Second)
		send(at, at, 99)
		if rewind {
			send(fixedNow, at, 99)
		} else {
			send(at, at, 0)
		}
		at = at.Add(time.Second)
		send(at, at, 99)
		if len(tracker.Visible()) != 0 {
			t.Fatal("invalid source ordering failed to interrupt the streak")
		}
	}
}
