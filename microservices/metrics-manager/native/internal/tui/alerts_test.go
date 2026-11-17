// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"testing"
	"time"
)

func TestAlertTrackerRaisesAfterConsecutiveSamples(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	dashboard := Dashboard{Memory: Memory{UsedPercent: reading(75)}}

	for sample := 1; sample <= 2; sample++ {
		tracker.Update(dashboard, config.Thresholds, fixedNow.Add(time.Duration(sample)*time.Second))
		if alerts := tracker.Active(); len(alerts) != 0 {
			t.Fatalf("sample %d raised alerts: %+v", sample, alerts)
		}
	}
	tracker.Update(dashboard, config.Thresholds, fixedNow.Add(3*time.Second))

	alerts := tracker.Active()
	if len(alerts) != 1 || alerts[0].Severity != SeverityWarning {
		t.Fatalf("alerts = %+v, want one warning", alerts)
	}
}

func TestAlertTrackerUsesHysteresisAndConsecutiveClearSamples(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	updateMemory := func(percent float64) {
		tracker.Update(
			Dashboard{Memory: Memory{UsedPercent: reading(percent)}},
			config.Thresholds,
			fixedNow,
		)
	}

	for range 3 {
		updateMemory(55)
	}
	if len(tracker.Active()) != 1 {
		t.Fatal("careful alert was not raised")
	}

	// Five percent hysteresis puts the careful exit at 47.5%.
	for range 3 {
		updateMemory(48)
	}
	if len(tracker.Active()) != 1 {
		t.Fatal("alert cleared inside the hysteresis band")
	}
	for range 2 {
		updateMemory(47)
	}
	if len(tracker.Active()) != 1 {
		t.Fatal("alert cleared before three consecutive samples")
	}
	updateMemory(47)
	if len(tracker.Active()) != 0 {
		t.Fatal("alert did not clear after three samples below the exit threshold")
	}
}

func TestAlertTrackerDropsMissingMeasurements(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for range 3 {
		tracker.Update(
			Dashboard{CPU: CPU{PackageTempC: reading(100)}},
			config.Thresholds,
			fixedNow,
		)
	}
	for range 2 {
		tracker.Update(Dashboard{}, config.Thresholds, fixedNow)
	}
	if len(tracker.Active()) != 1 {
		t.Fatal("alert disappeared after a transient missing sample")
	}
	tracker.Update(Dashboard{}, config.Thresholds, fixedNow)
	if len(tracker.Active()) != 0 {
		t.Fatal("alert remained after the measurement disappeared")
	}
}

func TestAlertTrackerSortsBySeverity(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	dashboard := Dashboard{
		CPU:    CPU{PackageTempC: reading(100)},
		Memory: Memory{UsedPercent: reading(55)},
	}
	for range 3 {
		tracker.Update(dashboard, config.Thresholds, fixedNow)
	}

	alerts := tracker.Active()
	if len(alerts) != 2 {
		t.Fatalf("alerts = %+v, want two", alerts)
	}
	if alerts[0].Severity != SeverityCritical || alerts[1].Severity != SeverityCareful {
		t.Errorf("alerts are not ordered by severity: %+v", alerts)
	}
}

func TestTotalCPUUsageRejectsInvalidAndClampsRange(t *testing.T) {
	tests := []struct {
		name string
		idle Reading
		want Reading
	}{
		{"missing", Reading{}, Reading{}},
		{"negative idle", reading(-10), reading(100)},
		{"idle over one hundred", reading(110), reading(0)},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := totalCPUUsage(CPU{UsageIdle: tt.idle}); got != tt.want {
				t.Errorf("totalCPUUsage() = %+v, want %+v", got, tt.want)
			}
		})
	}
}

func TestAlertTrackerCountsSeverityChangesInSameDirection(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for _, percent := range []float64{80, 90, 80} {
		tracker.Update(
			Dashboard{Memory: Memory{UsedPercent: reading(percent)}},
			config.Thresholds,
			fixedNow,
		)
	}

	alerts := tracker.Active()
	if len(alerts) != 1 || alerts[0].Severity != SeverityWarning {
		t.Fatalf("alerts = %+v, want one warning after a warning/critical/warning run", alerts)
	}
}

func TestAlertTrackerDowngradesAcrossVaryingLowerSeverities(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	update := func(percent float64) {
		tracker.Update(
			Dashboard{Memory: Memory{UsedPercent: reading(percent)}},
			config.Thresholds,
			fixedNow,
		)
	}
	for range 3 {
		update(95)
	}
	for _, percent := range []float64{60, 40, 60} {
		update(percent)
	}

	alerts := tracker.Active()
	if len(alerts) != 1 || alerts[0].Severity != SeverityCareful {
		t.Fatalf("alerts = %+v, want a downgrade to careful", alerts)
	}
}

func TestAlertTrackerOnlyChecksDisplayedProcesses(t *testing.T) {
	config := DefaultDashboardConfig()
	config.Processes.MaxDisplayed = 1
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	dashboard := Dashboard{Platform: Platform{LogicalCPUs: reading(1)}, Processes: []Process{
		{PID: "1", Command: "visible", CPUPercent: reading(1)},
		{PID: "2", Command: "hidden", CPUPercent: reading(99)},
	}}
	for i := range 3 {
		at := fixedNow.Add(time.Duration(i) * time.Second)
		for j := range dashboard.Processes {
			dashboard.Processes[j].CPUAt = at
		}
		tracker.Update(dashboard, config.Thresholds, at)
	}

	if alerts := tracker.Active(); len(alerts) != 0 {
		t.Fatalf("hidden process raised an alert: %+v", alerts)
	}
}

func TestAlertTrackerCarefulVisibility(t *testing.T) {
	for _, show := range []bool{false, true} {
		config := DefaultDashboardConfig()
		config.Alerts.ShowCareful = show
		tracker := NewAlertTracker(config.Alerts, config.Processes)
		for range 3 {
			tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(55)}}, config.Thresholds, fixedNow)
		}
		if got := len(tracker.Visible()) > 0; got != show {
			t.Errorf("visible careful = %v, want %v", got, show)
		}
		for range 3 {
			tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(10)}}, config.Thresholds, fixedNow)
		}
		if got := len(tracker.events) > 0; got != show {
			t.Errorf("careful history = %v, want %v", got, show)
		}
	}
}

func TestAlertTrackerArchivesEpisodesAndPreservesStart(t *testing.T) {
	config := DefaultDashboardConfig()
	config.Alerts.SamplesToRaise = 1
	config.Alerts.SamplesToClear = 1
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for i, value := range []float64{75, 95, 75, 55} {
		tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(value)}},
			config.Thresholds, fixedNow.Add(time.Duration(i)*time.Second))
	}
	if len(tracker.Visible()) != 0 || len(tracker.events) != 1 {
		t.Fatalf("visible=%+v history=%+v", tracker.Visible(), tracker.events)
	}
	event := tracker.events[0]
	if event.Outcome != "recovered" || event.Since != fixedNow ||
		event.EndedAt != fixedNow.Add(3*time.Second) {
		t.Errorf("unexpected recovered event: %+v", event)
	}
}

func TestAlertTrackerHistoryIsBoundedAndNewestFirst(t *testing.T) {
	for _, limit := range []int{0, 2} {
		config := DefaultDashboardConfig()
		config.Alerts.MaxHistory = limit
		config.Alerts.SamplesToRaise = 1
		config.Alerts.SamplesToClear = 1
		tracker := NewAlertTracker(config.Alerts, config.Processes)
		for i := range 10 {
			at := fixedNow.Add(time.Duration(i) * time.Second)
			tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(95)}}, config.Thresholds, at)
			tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(10)}}, config.Thresholds, at)
		}
		if len(tracker.events) != limit {
			t.Fatalf("history length = %d, want %d", len(tracker.events), limit)
		}
		if limit > 0 && tracker.events[0].EndedAt != fixedNow.Add(9*time.Second) {
			t.Errorf("history not newest first: %+v", tracker.events)
		}
	}
}

func TestAlertTrackerMissingIsNotRecovery(t *testing.T) {
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for range 3 {
		tracker.Update(Dashboard{Memory: Memory{UsedPercent: reading(95)}}, config.Thresholds, fixedNow)
	}
	tracker.Update(Dashboard{}, config.Thresholds, fixedNow.Add(time.Second))
	if alerts := tracker.Visible(); len(alerts) != 1 || !alerts[0].Unavailable {
		t.Fatalf("missing reading not marked: %+v", alerts)
	}
	for range 2 {
		tracker.Update(Dashboard{}, config.Thresholds, fixedNow.Add(3*time.Second))
	}
	if len(tracker.events) != 1 || tracker.events[0].Outcome != "no longer observed" {
		t.Fatalf("missing reading recorded as recovery: %+v", tracker.events)
	}
}

func TestAlertTrackerBreaksStreakOnMissingOrFailedSample(t *testing.T) {
	for _, transportFailure := range []bool{false, true} {
		config := DefaultDashboardConfig()
		tracker := NewAlertTracker(config.Alerts, config.Processes)
		high := Dashboard{Memory: Memory{UsedPercent: reading(95)}}
		for range 2 {
			tracker.Update(high, config.Thresholds, fixedNow)
		}
		if transportFailure {
			tracker.Interrupt()
		} else {
			tracker.Update(Dashboard{}, config.Thresholds, fixedNow)
		}
		tracker.Update(high, config.Thresholds, fixedNow)
		if len(tracker.Visible()) != 0 {
			t.Fatal("non-consecutive samples raised an alert")
		}
		for range 2 {
			tracker.Update(high, config.Thresholds, fixedNow)
		}
		if len(tracker.Visible()) != 1 {
			t.Fatal("new consecutive run did not raise an alert")
		}
	}
}
