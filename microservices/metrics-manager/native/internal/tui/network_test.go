// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"math"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func networkSamples(at time.Time, step int, name, host string) []promtext.Sample {
	values := map[string]float64{
		"bytes_recv": float64(step) * 11875000, "bytes_sent": float64(step) * 1250000,
		"packets_recv": float64(step) * 1000, "packets_sent": float64(step) * 200,
		"err_in": float64(step) * 2, "err_out": 0, "drop_in": float64(step), "drop_out": 0, "speed": 100,
	}
	var samples []promtext.Sample
	for field, value := range values {
		samples = append(samples, promtext.Sample{
			Name: "net_" + field, Labels: map[string]string{"interface": name, "host": host},
			Value: value, TimestampMS: at.UnixMilli(),
		})
	}
	return samples
}

func TestNetworkRatesCapacityUnitsAndUnknownSpeed(t *testing.T) {
	start := time.Unix(1000, 0)
	config := DefaultDashboardConfig().Network
	var tracker networkTracker
	first, _ := tracker.update(networkSamples(start, 1, "eth0", "host"), start, config)
	if first[0].Metrics["network.rxMiBps"].OK || first[0].ReceivedBytes.Value != 11875000 {
		t.Fatalf("first reading must show totals without rates: %+v", first)
	}
	at := start.Add(time.Second)
	next := networkSamples(at, 2, "eth0", "host")
	got, _ := tracker.update(next, at, config)
	for metric, expected := range map[string]float64{
		"network.rxMiBps": 11875000.0 / (1 << 20), "network.txMiBps": 1250000.0 / (1 << 20),
		"network.rxPercent": 95, "network.txPercent": 10,
		"network.rxPacketsPerSecond": 1000, "network.txPacketsPerSecond": 200,
		"network.rxErrorsPerSecond": 2, "network.txErrorsPerSecond": 0,
		"network.rxDropsPerSecond": 1, "network.txDropsPerSecond": 0,
	} {
		value := got[0].Metrics[metric]
		if !value.OK || math.Abs(value.Value-expected) > 1e-10 || !value.At.Equal(at) {
			t.Errorf("%s = %+v, want %g at %v", metric, value, expected, at)
		}
	}
	for i := range next {
		if next[i].Name == "net_speed" {
			next[i].Value = -1
		}
	}
	unknown, _ := tracker.update(next, at, config)
	if unknown[0].Metrics["network.rxPercent"].OK || !unknown[0].Metrics["network.rxMiBps"].OK {
		t.Fatal("unknown speed suppressed transfer or fabricated capacity")
	}
	config.SpeedMbps = map[string]float64{"eth0": 1000}
	override, _ := tracker.update(next, at, config)
	if value := override[0].Metrics["network.rxPercent"]; !value.OK || value.Value != 9.5 {
		t.Fatalf("explicit capacity = %+v", value)
	}
}

func TestNetworkSourceIdentityFilteringBoundsAndReappearance(t *testing.T) {
	start := time.Unix(1000, 0)
	config := DefaultDashboardConfig().Network
	config.MaxInterfaces = 2
	var tracker networkTracker
	var samples []promtext.Sample
	for _, host := range []string{"c", "a", "b"} {
		samples = append(samples, networkSamples(start, 1, "eth0", host)...)
	}
	devices, limited := tracker.update(samples, start, config)
	if len(devices) != 2 || !limited || len(tracker.states) != 2 || devices[0].Host != "a" || devices[1].Host != "b" {
		t.Fatalf("bounded deterministic admission = %+v, limited %v", devices, limited)
	}
	if devices[0].Key == devices[1].Key {
		t.Fatal("same interface on different hosts collided")
	}
	config.Interfaces = []string{"eth1"}
	filtered, limited := tracker.update(samples, start, config)
	if len(filtered) != 0 || limited || len(tracker.states) != 0 {
		t.Fatal("filter did not release counter state")
	}
	config.Interfaces = nil
	at := start.Add(time.Second)
	reappeared, _ := tracker.update(networkSamples(at, 2, "eth0", "a"), at, config)
	if reappeared[0].Metrics["network.rxMiBps"].OK {
		t.Fatal("reappearance bridged a missing interval")
	}
	for i := 0; i < 100; i++ {
		at = at.Add(time.Second)
		tracker.update(networkSamples(at, i, "eth0", fmt.Sprint(i)), at, config)
		if len(tracker.states) != 1 {
			t.Fatal("source churn leaked counter state")
		}
	}
}

func TestNetworkMissingInvalidAndStaleMeasurements(t *testing.T) {
	start := time.Unix(1000, 0)
	config := DefaultDashboardConfig().Network
	for _, tc := range []struct {
		name string
		edit func([]promtext.Sample) []promtext.Sample
		age  time.Duration
	}{
		{"timestamps absent", func(samples []promtext.Sample) []promtext.Sample {
			for i := range samples {
				samples[i].TimestampMS = 0
			}
			return samples
		}, 0},
		{"counter absent", func(samples []promtext.Sample) []promtext.Sample {
			var out []promtext.Sample
			for _, s := range samples {
				if s.Name != "net_bytes_recv" {
					out = append(out, s)
				}
			}
			return out
		}, 0},
		{"negative counter", func(samples []promtext.Sample) []promtext.Sample {
			for i := range samples {
				if samples[i].Name == "net_bytes_recv" {
					samples[i].Value = -1
				}
			}
			return samples
		}, 0},
		{"nan counter", func(samples []promtext.Sample) []promtext.Sample {
			for i := range samples {
				if samples[i].Name == "net_bytes_recv" {
					samples[i].Value = math.NaN()
				}
			}
			return samples
		}, 0},
		{"stale", func(samples []promtext.Sample) []promtext.Sample { return samples }, 11 * time.Second},
		{"future", func(samples []promtext.Sample) []promtext.Sample { return samples }, -time.Second},
		{"conflicting labels", func(samples []promtext.Sample) []promtext.Sample {
			for _, s := range samples {
				if s.Name == "net_bytes_recv" {
					s.Value++
					samples = append(samples, s)
					break
				}
			}
			return samples
		}, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var tracker networkTracker
			tracker.update(networkSamples(start, 1, "eth0", "host"), start, config)
			at := start.Add(time.Second)
			got, _ := tracker.update(tc.edit(networkSamples(at, 2, "eth0", "host")), at.Add(tc.age), config)
			if value := got[0].Metrics["network.rxMiBps"]; value.OK || value.Reason == "" {
				t.Fatalf("missing interval became a valid rate: %+v", value)
			}
		})
	}
}

func TestNetworkHistoryAndAlertsOnlyAdvanceOnNewMeasurements(t *testing.T) {
	start := time.Unix(1000, 0)
	m := NewModel(nil)
	m.now = func() time.Time { return start.Add(time.Minute) }
	send := func(samples []promtext.Sample, poll time.Time) {
		t.Helper()
		m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: samples, At: poll}))
	}
	send(networkSamples(start, 0, "eth0", "host"), start)
	for step := 1; step <= 3; step++ {
		at := start.Add(time.Duration(step) * time.Second)
		samples := networkSamples(at, step, "eth0", "host")
		for poll := 0; poll < 5; poll++ {
			send(samples, at.Add(time.Duration(poll)*100*time.Millisecond))
		}
		series := m.history.Series("network.rxMiBps")
		if len(series) != 1 || len(series[0].Points) != step || !series[0].Points[step-1].At.Equal(at) {
			t.Fatalf("cached polls replayed history: %+v", series)
		}
		if step < 3 && len(m.alerts.Visible()) != 0 {
			t.Fatal("cached polls raised an alert")
		}
	}
	if len(m.alerts.Visible()) != 3 {
		t.Fatalf("want utilization, errors and drops alerts, got %+v", m.alerts.Visible())
	}
	// New zero-delta samples, not repeated scrapes, must confirm recovery.
	for step := 4; step <= 6; step++ {
		at := start.Add(time.Duration(step) * time.Second)
		for poll := 0; poll < 5; poll++ {
			send(networkSamples(at, 3, "eth0", "host"), at.Add(time.Duration(poll)*100*time.Millisecond))
		}
		if step < 6 && len(m.alerts.Visible()) != 3 {
			t.Fatal("cached polls cleared an alert")
		}
	}
	if len(m.alerts.Visible()) != 0 || len(m.alerts.events) != 3 {
		t.Fatalf("three new recovery samples did not clear alerts: %+v", m.alerts)
	}
	for _, event := range m.alerts.events {
		if event.Outcome != "recovered" {
			t.Fatalf("outcome = %q", event.Outcome)
		}
	}
}

func TestNetworkPollFailureRebaselinesAndMissingDataNeverRecovers(t *testing.T) {
	start := time.Unix(1000, 0)
	m := NewModel(nil)
	for step := 0; step <= 3; step++ {
		at := start.Add(time.Duration(step) * time.Second)
		m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: networkSamples(at, step, "eth0", "host"), At: at}))
	}
	m, _ = update(t, m, snapshotMsg(source.Snapshot{Err: errors.New("test disconnect"), At: start.Add(4 * time.Second)}))
	at := start.Add(5 * time.Second)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: networkSamples(at, 5, "eth0", "host"), At: at}))
	if m.dash.Network[0].Metrics["network.rxMiBps"].OK {
		t.Fatal("failed poll did not reset counter baselines")
	}
	for i := 0; i < 3; i++ {
		m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at.Add(time.Duration(i+1) * time.Second)}))
	}
	if len(m.alerts.events) != 3 {
		t.Fatalf("missing events = %+v", m.alerts.events)
	}
	for _, event := range m.alerts.events {
		if event.Outcome != "no longer observed" {
			t.Fatalf("missing data recovered alert: %+v", event)
		}
	}
}

func TestNetworkViewsGroupsColorsAndOnceMode(t *testing.T) {
	previousProfile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	defer lipgloss.SetColorProfile(previousProfile)
	at := time.Unix(1000, 0)
	m := NewModel(nil)
	m.now = func() time.Time { return at.Add(time.Second) }
	first := source.Snapshot{Samples: networkSamples(at, 0, "eth0", "host"), At: at}
	m, _ = update(t, m, snapshotMsg(first))
	once := RenderOnce(first, 160)
	for _, text := range []string{"Network eth0 @ host", "waiting for a second measurement", "total bytes"} {
		wantContains(t, once, text)
	}
	at = at.Add(time.Second)
	samples := append(networkSamples(at, 1, "eth0", "host"), networkSamples(at, 1, "eth1", "host")...)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: samples, At: at}))
	panel := m.networkSection(m.dash.Network[0])
	wantContains(t, panel, criticalStyle.Render("95.00%"))
	wantContains(t, panel, warningStyle.Render("2.00/s"))
	if strings.Contains(panel, criticalStyle.Render("11.32 MiB/s")) {
		t.Fatal("absolute throughput received a health color")
	}
	var groups []string
	last := ""
	for _, item := range m.detailItems() {
		if strings.HasPrefix(item.spec.Metric, "network.") {
			_, _, group := detailGroup(item)
			if group != last {
				groups = append(groups, group)
				last = group
			}
		}
	}
	if !reflect.DeepEqual(groups, []string{"Network eth0 @ host", "Network eth1 @ host"}) {
		t.Fatalf("network groups interleaved: %v", groups)
	}
	for _, width := range []int{30, 80, 140, 220} {
		for _, tab := range []Tab{OverviewTab, TrendsTab, DetailsTab, AlertsTab} {
			m.width, m.height, m.activeTab = width, 30, tab
			for _, line := range strings.Split(m.View(), "\n") {
				if lipgloss.Width(line) > width {
					t.Fatalf("tab %v width %d overflow: %q", tab, width, line)
				}
			}
		}
	}
}

func TestNetworkConfigurationValidationAndDefaults(t *testing.T) {
	for _, input := range []string{
		`{"network":{"maxInterfaces":0}}`, `{"network":{"maxInterfaces":33}}`,
		`{"network":{"maxSampleAge":"0s"}}`, `{"network":{"maxSampleAge":"6m"}}`,
		`{"network":{"maxSampleAge":"invalid"}}`,
		`{"network":{"interfaces":["eth0","eth0"]}}`, `{"network":{"interfaces":[""]}}`,
		`{"network":{"interfaces":["eth0\n"]}}`,
		`{"network":{"interfaces":["eth0\u009b"]}}`,
		`{"network":{"speedMbps":{"eth0":0}}}`, `{"network":{"speedMbps":{"eth0":-1}}}`,
	} {
		if _, err := LoadDashboardConfig(writeConfig(t, input)); err == nil {
			t.Fatalf("accepted %s", input)
		}
	}

	config, err := LoadDashboardConfig(writeConfig(t, `{"network":{"interfaces":["eth0"],"speedMbps":{"eth0":1000}}}`))
	if err != nil {
		t.Fatal(err)
	}
	if config.Network.MaxInterfaces != 8 || config.Network.MaxSampleAge != "10s" || config.Network.SpeedMbps["eth0"] != 1000 {
		t.Fatalf("network defaults/override = %+v", config.Network)
	}
	packaged, err := LoadDashboardConfig("../../packaging/etc/tui-dashboard.json")
	if err != nil {
		t.Fatal(err)
	}
	defaults := DefaultDashboardConfig()
	if packaged.Network.MaxInterfaces != defaults.Network.MaxInterfaces || packaged.Network.MaxSampleAge != defaults.Network.MaxSampleAge ||
		len(packaged.Network.Interfaces) != 0 || len(packaged.Network.SpeedMbps) != 0 || !reflect.DeepEqual(packaged.Thresholds, defaults.Thresholds) {
		t.Fatal("packaged network settings or thresholds differ from defaults")
	}
	// Event rates are not percentages and may legitimately exceed 100/s.
	config.Thresholds["network.errorsPerSecond"] = Threshold{Careful: 10, Warning: 100, Critical: 1000}
	if err := config.Validate(); err != nil {
		t.Fatal(err)
	}
	if thresholdUnit("network.errorsPerSecond") != "/s" || thresholdUnit("network.rxPercent") != "%" {
		t.Fatal("network alert units are incorrect")
	}
}

func TestNetworkThresholdBoundariesShareColorsAndAlerts(t *testing.T) {
	previousProfile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	defer lipgloss.SetColorProfile(previousProfile)
	m := NewModel(nil)
	m.config.Alerts.SamplesToRaise = 1
	m.config.Alerts.ShowCareful = true
	for _, metric := range []string{
		"network.rxPercent", "network.txPercent",
		"network.rxErrorsPerSecond", "network.txErrorsPerSecond",
		"network.rxDropsPerSecond", "network.txDropsPerSecond",
	} {
		threshold := m.config.Thresholds[thresholdMetric(metric)]
		for _, tc := range []struct {
			value float64
			want  Severity
		}{
			{threshold.Careful - 0.001, SeverityOK},
			{threshold.Careful, SeverityCareful},
			{threshold.Warning - 0.001, SeverityCareful},
			{threshold.Warning, SeverityWarning},
			{threshold.Critical - 0.001, SeverityWarning},
			{threshold.Critical, SeverityCritical},
		} {
			label := fmt.Sprintf("%.3f", tc.value)
			colored := m.thresholdValue(metric, reading(tc.value), func(Reading) string { return label })
			if colored != severityStyle(tc.want).Render(label) {
				t.Errorf("%s value %g color disagrees with %v", metric, tc.value, tc.want)
			}
			at := time.Unix(1000, 0)
			tracker := NewAlertTracker(m.config.Alerts, m.config.Processes)
			dashboard := Dashboard{Network: []NetworkInterface{{
				Key: "device", Name: "eth0",
				Metrics: map[string]timedReading{metric: {Reading: reading(tc.value), At: at}},
			}}}
			tracker.Update(dashboard, m.config.Thresholds, at)
			alerts := tracker.Visible()
			if tc.want == SeverityOK {
				if len(alerts) != 0 {
					t.Errorf("%s below careful raised alert", metric)
				}
			} else if len(alerts) != 1 || alerts[0].Severity != tc.want {
				t.Errorf("%s value %g alerts = %+v, want %v", metric, tc.value, alerts, tc.want)
			}
		}
		if got := m.thresholdValue(metric, Reading{}, func(Reading) string { return "unavailable" }); got != "unavailable" {
			t.Errorf("%s missing data was colored", metric)
		}
	}
}

func TestNetworkStalenessHistoryExpiryAndRetainedSelection(t *testing.T) {
	at := time.Unix(1000, 0)
	m := NewModel(nil)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: networkSamples(at, 0, "eth0", "host")}))
	at = at.Add(time.Second)
	samples := networkSamples(at, 1, "eth0", "host")
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: samples}))
	for _, item := range m.detailItems() {
		if item.spec.Metric == "network.rxMiBps" {
			m.detailSelection = item.choice
			break
		}
	}
	selected := m.detailSelection
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at.Add(11 * time.Second), Samples: samples}))
	series := m.history.Series("network.rxMiBps")
	if len(series) != 1 || series[0].Available || len(series[0].Points) != 1 {
		t.Fatalf("stale samples replayed history or stayed available: %+v", series)
	}
	if value := m.dash.Network[0].Metrics["network.rxMiBps"]; value.OK || !strings.Contains(value.Reason, "stale") {
		t.Fatalf("stale sample = %+v", value)
	}
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at.Add(6 * time.Minute)}))
	if len(m.history.Series("network.rxMiBps")) != 0 {
		t.Fatal("network history did not expire")
	}
	found := false
	for _, item := range m.detailItems() {
		if item.choice == selected {
			found = true
			if item.value.OK {
				t.Fatal("expired selection contains a current reading")
			}
		}
	}
	if !found {
		t.Fatal("expired interface selection disappeared")
	}
}

func TestNetworkUtilizationBeyondChartRangeFillsRatherThanOverflows(t *testing.T) {
	at := time.Unix(1000, 0)
	m := NewModel(nil)
	m.chartsConfig.GraphMode = "unicode"
	m.now = func() time.Time { return at }
	m.chartsConfig.ChartHeight = 3
	series := HistorySeries{Available: true, Points: []HistoryPoint{{At: at, Value: 1e100}}}
	chart := m.renderChart(fixedChart("network.rxPercent", "RX", "%", 0, 100), series, 50)
	topFound := false
	for _, line := range strings.Split(chart, "\n") {
		if strings.Contains(line, "100.0") && strings.Contains(line, "\u2588") {
			topFound = true
		}
	}
	if !topFound {
		t.Fatal("above-capacity utilization overflowed the chart height instead of filling it")
	}
}

func TestNetworkLabelIdentityAndTerminalSanitization(t *testing.T) {
	at := time.Unix(1000, 0)
	samples := append(networkSamples(at, 0, "b\x00c", "a"), networkSamples(at, 0, "c", "a\x00b")...)
	var tracker networkTracker
	devices, _ := tracker.update(samples, at, DefaultDashboardConfig().Network)
	if len(devices) != 2 || devices[0].Key == devices[1].Key {
		t.Fatal("label separators caused an identity collision")
	}

	m := NewModel(nil)
	m.now = func() time.Time { return at }
	m.dash.Network, _ = tracker.update(networkSamples(at, 0, "eth0\x1b[2J", "host\n\u009b2J"), at, m.config.Network)
	for _, tab := range []Tab{OverviewTab, DetailsTab} {
		m.activeTab = tab
		text := m.View()
		for _, control := range []string{"\x1b[2J", "\u009b", "\x00"} {
			if strings.Contains(text, control) {
				t.Fatalf("unsafe label escaped into tab %v", tab)
			}
		}
	}
}
