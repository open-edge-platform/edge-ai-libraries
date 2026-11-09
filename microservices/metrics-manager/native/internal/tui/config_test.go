// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadDashboardConfigDefaultsWhenAbsent(t *testing.T) {
	config, err := LoadDashboardConfig(filepath.Join(t.TempDir(), "missing.json"))
	if err != nil {
		t.Fatal(err)
	}
	if config.Processes.MaxDisplayed != 10 || config.Processes.CPUMode != "total" || config.Alerts.SamplesToRaise != 3 ||
		config.Alerts.MaxHistory != 50 || config.Alerts.ShowCareful {
		t.Errorf("unexpected defaults: %+v", config)
	}
}

func TestLoadDashboardConfigOverridesDefaults(t *testing.T) {
	path := writeConfig(t, `{
		"processes": {"maxDisplayed": 25},
		"alerts": {"samplesToRaise": 4, "samplesToClear": 2, "hysteresisPercent": 7},
		"thresholds": {
			"cpu.totalPercent": {"careful": 60, "warning": 75, "critical": 90}
		}
	}`)

	config, err := LoadDashboardConfig(path)
	if err != nil {
		t.Fatal(err)
	}
	if config.Processes.MaxDisplayed != 25 {
		t.Errorf("maxDisplayed = %d, want 25", config.Processes.MaxDisplayed)
	}
	if config.Thresholds["memory.usedPercent"].Critical != 90 {
		t.Error("an omitted threshold did not keep its default")
	}
	if config.Alerts.MaxHistory != 50 {
		t.Error("an old configuration did not retain the new history default")
	}
}

func TestLoadDashboardConfigAlertPreferences(t *testing.T) {
	config, err := LoadDashboardConfig(writeConfig(t, `{"alerts":{"showCareful":true,"maxHistory":0}}`))
	if err != nil {
		t.Fatal(err)
	}
	if !config.Alerts.ShowCareful || config.Alerts.MaxHistory != 0 {
		t.Errorf("alert preferences = %+v", config.Alerts)
	}
}

func TestLoadDashboardConfigRejectsInvalidInput(t *testing.T) {
	tests := []struct {
		name, content, want string
	}{
		{"unknown field", `{"unknown": true}`, "unknown field"},
		{"unknown sort", `{"processes":{"sortBy":"command"}}`, "sortBy"},
		{"empty sort", `{"processes":{"sortBy":""}}`, "sortBy"},
		{"unknown CPU mode", `{"processes":{"cpuMode":"host"}}`, "cpuMode"},
		{"empty CPU mode", `{"processes":{"cpuMode":""}}`, "cpuMode"},
		{"multiple values", `{}` + "\n" + `{}`, "more than one"},
		{"negative history", `{"alerts":{"maxHistory":-1}}`, "between 0 and 1000"},
		{"unbounded history", `{"alerts":{"maxHistory":1001}}`, "between 0 and 1000"},
		{
			"unordered threshold",
			`{"thresholds":{"cpu.totalPercent":{"careful":80,"warning":70,"critical":90}}}`,
			"careful < warning",
		},
		{
			"unknown threshold",
			`{"thresholds":{"disk.usedPercent":{"careful":50,"warning":70,"critical":90}}}`,
			"not supported",
		},
		{
			"unbounded process count",
			`{"processes":{"maxDisplayed":1001}}`,
			"between 1 and 1000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := LoadDashboardConfig(writeConfig(t, tt.content))
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Errorf("error = %v, want it to contain %q", err, tt.want)
			}
		})
	}
}

func TestPackagedDashboardConfigMatchesDefaults(t *testing.T) {
	config, err := LoadDashboardConfig("../../packaging/etc/tui-dashboard.json")
	if err != nil {
		t.Fatal(err)
	}
	want := DefaultDashboardConfig()
	if config.Alerts != want.Alerts || config.Processes != want.Processes || config.Mouse != want.Mouse {
		t.Errorf("packaged defaults differ: %+v", config)
	}
}

func TestLoadDashboardConfigRejectsOversizedFile(t *testing.T) {
	_, err := LoadDashboardConfig(writeConfig(t, strings.Repeat(" ", maxConfigSize+1)))
	if err == nil || !strings.Contains(err.Error(), "exceeds") {
		t.Errorf("error = %v, want an oversized-file error", err)
	}
}

func writeConfig(t *testing.T, content string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "dashboard.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}

	return path
}
