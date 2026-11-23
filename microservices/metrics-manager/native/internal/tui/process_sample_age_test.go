// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"
)

func TestProcessSampleAgeConfiguration(t *testing.T) {
	for _, tc := range []struct {
		text string
		want time.Duration
	}{
		{`{}`, 3 * time.Second},
		{`{"processes":{"maxDisplayed":20}}`, 3 * time.Second},
		{`{"processes":{"maxSampleAge":"1s"}}`, time.Second},
		{`{"processes":{"maxSampleAge":"1500ms"}}`, 1500 * time.Millisecond},
		{`{"processes":{"maxSampleAge":"10s"}}`, 10 * time.Second},
		{`{"processes":{"maxSampleAge":"5m"}}`, 5 * time.Minute},
	} {
		config, err := LoadDashboardConfig(writeConfig(t, tc.text))
		if err != nil || time.Duration(config.Processes.MaxSampleAge) != tc.want {
			t.Fatalf("%s: age=%v, err=%v", tc.text, config.Processes.MaxSampleAge, err)
		}
		m := NewModelWithConfig(nil, config)
		if m.alerts.processMaxAge != tc.want || config.Network.MaxSampleAge != "10s" {
			t.Fatal("process age was not applied independently of Network")
		}
		data, err := json.Marshal(config)
		if err != nil || !strings.Contains(string(data), `"maxSampleAge":"`+tc.want.String()+`"`) {
			t.Fatalf("duration did not retain its JSON string format: %s, %v", data, err)
		}
	}
	for _, value := range []string{`""`, `"bad"`, `"0s"`, `"-1s"`, `"999ms"`, `"301s"`, `3`, `null`, `true`} {
		_, err := LoadDashboardConfig(writeConfig(t, `{"processes":{"maxSampleAge":`+value+`}}`))
		if err == nil || !strings.Contains(err.Error(), "processes.maxSampleAge") {
			t.Fatalf("invalid age %s was not reported: %v", value, err)
		}
	}
}

func TestProcessSampleAgeSharedByTableAlertsAndDiagnostics(t *testing.T) {
	for _, age := range []string{"3s", "10s"} {
		t.Run(age, func(t *testing.T) {
			config, err := LoadDashboardConfig(writeConfig(t, fmt.Sprintf(`{"processes":{"maxDisplayed":1,"maxSampleAge":%q},"alerts":{"samplesToRaise":1}}`, age)))
			if err != nil {
				t.Fatal(err)
			}
			m := NewModelWithConfig(nil, config)
			m.now = func() time.Time { return fixedNow }
			m.dash.Platform.LogicalCPUs = reading(1)
			m.dash.Processes = []Process{
				{PID: "1", Command: "older", CPUPercent: reading(99), CPUAt: fixedNow.Add(-5 * time.Second)},
				{PID: "2", Command: "fresh", CPUPercent: reading(10), CPUAt: fixedNow},
			}
			rows := m.sortedProcesses()
			candidates := processAlertCandidates(m.dash, m.alerts.processLimit, fixedNow, m.alerts.processMaxAge)
			wantPID := "1"
			wantAlerts := 1
			if age == "3s" {
				wantPID, wantAlerts = "2", 0
			}
			if len(rows) != 1 || rows[0].PID != wantPID || len(candidates) != 1 || candidates[0].PID != wantPID {
				t.Fatal("table and alert candidates used different age limits")
			}
			m.alerts.Update(m.dash, config.Thresholds, fixedNow)
			if len(m.alerts.Active()) != wantAlerts || m.processCoverageLimited() {
				t.Fatal("unexpected alert evaluation or limited-coverage status")
			}
			details := strings.Join(strings.Fields(m.alertDetails(140)), " ")
			if age == "3s" {
				wantContains(t, details, "Retained process samples (1 excluded)")
				wantContains(t, details, "Samples older than 3s")
			} else if strings.Contains(details, "Retained process samples") {
				t.Fatal("custom age was ignored by diagnostics")
			}
		})
	}
}

func TestProcessSampleAgeExpiresOnClockWithoutNewScrape(t *testing.T) {
	for _, maxAge := range []time.Duration{3 * time.Second, 10 * time.Second} {
		config := DefaultDashboardConfig()
		config.Processes.MaxSampleAge = processSampleAge(maxAge)
		m := NewModelWithConfig(nil, config)
		now := fixedNow
		m.now = func() time.Time { return now }
		m.dash.Platform.LogicalCPUs = reading(1)
		m.dash.Processes = []Process{{PID: "1", Command: "worker", CPUPercent: reading(99), CPUAt: fixedNow}}
		for _, delta := range []time.Duration{maxAge - time.Nanosecond, maxAge, maxAge + time.Nanosecond} {
			now = fixedNow.Add(delta)
			m, _ = update(t, m, clockMsg{})
			expired := delta > maxAge
			if (len(m.sortedProcesses()) == 0) != expired ||
				m.processSourceMissing() != expired || m.processCoverageLimited() != expired ||
				freshProcessCPU(fixedNow, now, m.alerts.processMaxAge) == expired {
				t.Fatalf("max age=%s at %s: inconsistent expiration boundary", maxAge, delta)
			}
			if expired {
				text := strings.Join(strings.Fields(m.alertDetails(140)), " ")
				wantContains(t, text, fmt.Sprintf("Samples older than %s", maxAge))
				wantContains(t, processTimestampIssue(fixedNow, now, maxAge), maxAge.String())
			}
		}
		for _, stamp := range []time.Time{{}, now.Add(time.Second)} {
			m.dash.Processes[0].CPUAt = stamp
			if len(m.sortedProcesses()) != 1 || !m.processCoverageLimited() {
				t.Fatal("missing/future timestamps were incorrectly treated as expired")
			}
		}
	}
}
