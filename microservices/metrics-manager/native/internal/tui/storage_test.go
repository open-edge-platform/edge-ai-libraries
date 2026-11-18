// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"maps"
	"math"
	"os"
	"reflect"
	"slices"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func storageSamples(at time.Time, step int, used float64) []promtext.Sample {
	var samples []promtext.Sample
	for kind, values := range map[string]map[string]float64{
		"disk": {
			"used_percent": used, "inodes_used_percent": used, "inodes_total": 1000,
			"free": 20 * (1 << 30), "total": 100 * (1 << 30), "used": 80 * (1 << 30),
		},
		"diskio": {
			"read_bytes": float64(step) * 2 * (1 << 20), "write_bytes": float64(step) * (1 << 20),
			"reads": float64(step) * 100, "writes": float64(step) * 50,
			"read_time": float64(step) * 1000, "write_time": float64(step) * 1000,
			"io_time": float64(step) * 900, "weighted_io_time": float64(step) * 2000, "iops_in_progress": 3,
		},
	} {
		for field, value := range values {
			labels := map[string]string{"host": "host", "name": "nvme0n1"}
			if kind == "disk" {
				labels = map[string]string{"host": "host", "path": "/data", "device": "nvme0n1p1", "fstype": "ext4", "mode": "rw"}
			}
			samples = append(samples, promtext.Sample{Name: kind + "_" + field, Labels: labels, Value: value, TimestampMS: at.UnixMilli()})
		}
	}
	return samples
}

func storageValue(resources []StorageResource, metric string) timedReading {
	for _, resource := range resources {
		if value, ok := resource.Metrics[metric]; ok {
			return value
		}
	}
	return timedReading{}
}

func TestStorageUnitsRatesAndIdleLatency(t *testing.T) {
	var tracker storageTracker
	cfg := DefaultDashboardConfig().Storage
	at := fixedNow
	first, _ := tracker.update(storageSamples(at, 0, 80), at, cfg)
	if storageValue(first, "storage.readMiBps").OK || storageValue(first, "storage.freeGiB").Value != 20 {
		t.Fatal("first sample must show capacity but not invent a rate")
	}
	at = at.Add(time.Second)
	next, _ := tracker.update(storageSamples(at, 1, 80), at, cfg)
	for metric, want := range map[string]float64{
		"storage.readMiBps": 2, "storage.writeMiBps": 1, "storage.readIOPS": 100, "storage.writeIOPS": 50,
		"storage.readAwaitMs": 10, "storage.writeAwaitMs": 20, "storage.busyPercent": 90,
		"storage.queueDepth": 2, "storage.inProgress": 3, "storage.inodesPercent": 80,
	} {
		got := storageValue(next, metric)
		if !got.OK || got.Value != want || !got.At.Equal(at) {
			t.Errorf("%s = %+v, want %g at %v", metric, got, want, at)
		}
	}
	at = at.Add(time.Second)
	idle, _ := tracker.update(storageSamples(at, 1, 80), at, cfg)
	if value := storageValue(idle, "storage.readMiBps"); !value.OK || value.Value != 0 {
		t.Fatalf("real idle interval = %+v", value)
	}
	if value := storageValue(idle, "storage.readAwaitMs"); value.OK || !strings.Contains(value.Reason, "no completed") {
		t.Fatalf("idle latency must be unavailable, not zero: %+v", value)
	}
}

func TestStorageBadSamplesAndResets(t *testing.T) {
	for _, tc := range []struct {
		name string
		edit func(*promtext.Sample)
		age  time.Duration
	}{
		{"negative", func(s *promtext.Sample) { s.Value = -1 }, 0},
		{"nan", func(s *promtext.Sample) { s.Value = math.NaN() }, 0},
		{"infinite", func(s *promtext.Sample) { s.Value = math.Inf(1) }, 0},
		{"missing time", func(s *promtext.Sample) { s.TimestampMS = 0 }, 0},
		{"future", func(s *promtext.Sample) {}, -time.Second},
		{"stale", func(s *promtext.Sample) {}, 11 * time.Second},
		{"reset", func(s *promtext.Sample) { s.Value = 0 }, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var tracker storageTracker
			cfg := DefaultDashboardConfig().Storage
			tracker.update(storageSamples(fixedNow, 5, 80), fixedNow, cfg)
			at := fixedNow.Add(time.Second)
			samples := storageSamples(at, 6, 80)
			for i := range samples {
				if samples[i].Name == "diskio_read_bytes" {
					tc.edit(&samples[i])
				}
			}
			got, _ := tracker.update(samples, at.Add(tc.age), cfg)
			if value := storageValue(got, "storage.readMiBps"); value.OK || value.Reason == "" {
				t.Fatalf("invalid sample produced a rate: %+v", value)
			}
		})
	}
}

func TestStorageGaugeConflictsAndInodeAvailability(t *testing.T) {
	cfg := DefaultDashboardConfig().Storage
	for _, metric := range []string{"disk_used_percent", "diskio_read_bytes"} {
		var tracker storageTracker
		samples := storageSamples(fixedNow, 1, 80)
		for _, sample := range samples {
			if sample.Name == metric {
				sample.Labels = maps.Clone(sample.Labels)
				sample.Labels["extra"] = "ambiguous"
				samples = append(samples, sample)
				break
			}
		}
		got, _ := tracker.update(samples, fixedNow, cfg)
		check := "storage.usedPercent"
		if metric == "diskio_read_bytes" {
			check = "storage.readMiBps"
		}
		if value := storageValue(got, check); value.OK || !strings.Contains(value.Reason, "ambiguous") {
			t.Fatalf("ambiguous labels accepted: %+v", value)
		}
	}
	for _, value := range []float64{0, -1, math.NaN()} {
		var tracker storageTracker
		samples := storageSamples(fixedNow, 0, 80)
		for i := range samples {
			if samples[i].Name == "disk_inodes_total" {
				samples[i].Value = value
			}
		}
		got, _ := tracker.update(samples, fixedNow, cfg)
		if storageValue(got, "storage.inodesPercent").OK {
			t.Fatal("unsupported inode count became a valid utilization")
		}
	}
	var tracker storageTracker
	tracker.update(storageSamples(fixedNow, 0, 80), fixedNow, cfg)
	conflict, _ := tracker.update(storageSamples(fixedNow, 0, 85), fixedNow, cfg)
	if storageValue(conflict, "storage.usedPercent").OK {
		t.Fatal("changed gauge at cached timestamp was accepted")
	}
	older, _ := tracker.update(storageSamples(fixedNow.Add(-time.Second), 0, 70), fixedNow, cfg)
	if storageValue(older, "storage.usedPercent").OK {
		t.Fatal("out-of-order gauge was accepted")
	}
	future := storageSamples(fixedNow.Add(time.Hour), 0, 80)
	tracker.update(future, fixedNow, cfg)
	at := fixedNow.Add(time.Second)
	valid, _ := tracker.update(storageSamples(at, 1, 80), at, cfg)
	if !storageValue(valid, "storage.usedPercent").OK {
		t.Fatal("rejected future timestamp poisoned subsequent valid gauges")
	}
}

func TestStorageRatiosRequireMatchingIntervals(t *testing.T) {
	cfg := DefaultDashboardConfig().Storage
	var tracker storageTracker
	first := storageSamples(fixedNow, 0, 80)
	for i := range first {
		if first[i].Name == "diskio_read_time" {
			first[i].TimestampMS -= 500
		}
	}
	tracker.update(first, fixedNow, cfg)
	at := fixedNow.Add(time.Second)
	got, _ := tracker.update(storageSamples(at, 1, 80), at, cfg)
	if storageValue(got, "storage.readAwaitMs").OK {
		t.Fatal("latency combined counters with different starting timestamps")
	}
}

func TestStorageFilesystemInvalidCapacityAndCacheOrder(t *testing.T) {
	cfg := DefaultDashboardConfig().Storage
	for _, field := range []string{"disk_total", "disk_inodes_total", "disk_used_percent", "disk_inodes_used_percent"} {
		for _, invalid := range []float64{-1, math.Inf(1), math.NaN()} {
			samples := storageSamples(fixedNow, 0, 80)
			for i := range samples {
				if samples[i].Name == field {
					samples[i].Value = invalid
				}
			}
			var tracker storageTracker
			got, _ := tracker.update(samples, fixedNow, cfg)
			key := "storage.usedPercent"
			if strings.Contains(field, "inodes") {
				key = "storage.inodesPercent"
			}
			if storageValue(got, key).OK {
				t.Fatalf("%s=%g generated valid utilization", field, invalid)
			}
		}
	}
	samples := storageSamples(fixedNow, 0, 80)
	newer := storageSamples(fixedNow.Add(time.Second), 1, 90)
	for _, batch := range [][]promtext.Sample{append(slices.Clone(samples), newer...), append(slices.Clone(newer), samples...)} {
		var tracker storageTracker
		got, _ := tracker.update(batch, fixedNow.Add(time.Second), cfg)
		if value := storageValue(got, "storage.usedPercent"); !value.OK || value.Value != 90 {
			t.Fatalf("cached order selected old gauge: %+v", value)
		}
	}
}

func TestStorageThresholdRecoveryCustomIOAndRetention(t *testing.T) {
	m := NewModel(nil)
	m.config.Thresholds["storage.readMiBps"] = Threshold{Careful: 0.5, Warning: 1, Critical: 1.5}
	at := fixedNow
	m.now = func() time.Time { return at }
	for step := 0; step <= 3; step++ {
		at = fixedNow.Add(time.Duration(step) * time.Second)
		m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: storageSamples(at, step, 95)}))
	}
	if len(m.alerts.Visible()) != 3 {
		t.Fatalf("capacity/inodes/custom I/O alerts = %+v", m.alerts.Visible())
	}
	for _, item := range m.detailItems() {
		if item.spec.Metric == "storage.readMiBps" {
			m.detailSelection = item.choice
			break
		}
	}
	selection := m.detailSelection
	for step := 4; step <= 6; step++ {
		at = fixedNow.Add(time.Duration(step) * time.Second)
		for poll := 0; poll < 4; poll++ {
			m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Samples: storageSamples(at, 3, 60)}))
		}
		if step < 6 && len(m.alerts.Visible()) != 3 {
			t.Fatal("cached samples confirmed recovery")
		}
	}
	if len(m.alerts.Visible()) != 0 || len(m.alerts.events) != 3 {
		t.Fatal("distinct samples failed to recover")
	}
	for _, event := range m.alerts.events {
		if event.Outcome != "recovered" || !event.RecoveryValue.OK {
			t.Fatalf("incorrect recovery evidence: %+v", event)
		}
	}
	at = at.Add(6 * time.Minute)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at}))
	if len(m.history.Series("storage.readMiBps")) != 0 {
		t.Fatal("expired storage history retained")
	}
	for _, item := range m.detailItems() {
		if item.choice == selection {
			if item.value.OK {
				t.Fatal("expired selection contains a reading")
			}
			return
		}
	}
	t.Fatal("selected storage resource vanished instead of showing unavailable")
}

func TestStorageHistoryAlertsAndClockExpiry(t *testing.T) {
	m := NewModel(nil)
	at := fixedNow
	m.now = func() time.Time { return at }
	for step := 0; step < 3; step++ {
		at = fixedNow.Add(time.Duration(step) * time.Second)
		for poll := 0; poll < 5; poll++ {
			m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: storageSamples(at, step, 95), At: at}))
		}
		if step < 2 && len(m.alerts.Visible()) != 0 {
			t.Fatal("cached sample advanced alerts")
		}
	}
	if len(m.alerts.Visible()) != 2 {
		t.Fatalf("want space and inode alerts only, got %+v", m.alerts.Visible())
	}
	series := m.history.Series("storage.usedPercent")
	if len(series) != 1 || len(series[0].Points) != 3 {
		t.Fatalf("cached scrapes duplicated history: %+v", series)
	}
	at = at.Add(11 * time.Second)
	m, _ = update(t, m, clockMsg{})
	if storageValue(m.dash.Storage, "storage.usedPercent").OK || m.history.Series("storage.usedPercent")[0].Available {
		t.Fatal("clock did not age current readings")
	}
	wantContains(t, m.alertDetails(140), "Storage alert coverage limited")
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at, Err: errors.New("offline")}))
	if len(m.storage.states) != 0 {
		t.Fatal("poll failure did not release counter state")
	}
	for step := 0; step < 3; step++ {
		at = at.Add(time.Second)
		m, _ = update(t, m, snapshotMsg(source.Snapshot{At: at}))
	}
	for _, event := range m.alerts.events {
		if event.Outcome == "recovered" {
			t.Fatal("missing data reported recovery")
		}
	}
	wantContains(t, m.alertDetails(140), "Previously observed storage data is unavailable")
	at = at.Add(time.Second)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{Samples: storageSamples(at, 40, 50), At: at}))
	if storageValue(m.dash.Storage, "storage.readMiBps").OK {
		t.Fatal("reappearance bridged missing samples")
	}
}

func TestStorageFilteringIdentityAndBounds(t *testing.T) {
	cfg := DefaultDashboardConfig().Storage
	cfg.MaxDevices, cfg.MaxFilesystems = 1, 1
	var samples []promtext.Sample
	for _, host := range []string{"z", "a", "b"} {
		for _, sample := range storageSamples(fixedNow, 0, 80) {
			sample.Labels["host"] = host
			samples = append(samples, sample)
		}
	}
	var tracker storageTracker
	got, limited := tracker.update(samples, fixedNow, cfg)
	if len(got) != 2 || len(tracker.states) != 2 || !limited || got[0].Host != "a" || got[1].Host != "a" {
		t.Fatalf("unstable or unbounded admission: %+v", got)
	}
	cfg.Devices, cfg.MountPoints = []string{"sda"}, []string{"/"}
	got, limited = tracker.update(samples, fixedNow, cfg)
	if len(got) != 0 || len(tracker.states) != 0 || limited {
		t.Fatal("filters did not release resource state")
	}
	for i := 0; i < 100; i++ {
		samples := storageSamples(fixedNow, i, 80)
		for j := range samples {
			samples[j].Labels["host"] = fmt.Sprint(i)
		}
		tracker.update(samples, fixedNow, DefaultDashboardConfig().Storage)
		if len(tracker.states) != 2 {
			t.Fatal("resource churn leaked state")
		}
	}
}

func TestStorageConfigDefaultsValidationAndPackaging(t *testing.T) {
	for _, input := range []string{
		`{"storage":{"maxDevices":0}}`, `{"storage":{"maxFilesystems":33}}`,
		`{"storage":{"maxSampleAge":"bad"}}`, `{"storage":{"maxSampleAge":"0s"}}`,
		`{"storage":{"maxSampleAge":"6m"}}`, `{"storage":{"devices":["x","x"]}}`,
		`{"storage":{"mountPoints":["relative"]}}`, `{"storage":{"mountPoints":["/data\n"]}}`,
	} {
		if _, err := LoadDashboardConfig(writeConfig(t, input)); err == nil {
			t.Fatalf("accepted %s", input)
		}
	}
	cfg, err := LoadDashboardConfig(writeConfig(t, `{"processes":{"maxDisplayed":10}}`))
	if err != nil || !reflect.DeepEqual(cfg.Storage, DefaultDashboardConfig().Storage) {
		t.Fatalf("old config failed storage inheritance: %+v %v", cfg.Storage, err)
	}
	packaged, err := LoadDashboardConfig("../../packaging/etc/tui-dashboard.json")
	if err != nil || packaged.Storage.MaxDevices != cfg.Storage.MaxDevices ||
		!reflect.DeepEqual(packaged.Storage.IgnoreFilesystems, cfg.Storage.IgnoreFilesystems) {
		t.Fatalf("packaged storage settings mismatch: %+v %v", packaged.Storage, err)
	}
	charts, err := LoadChartsConfig("../../packaging/etc/tui-charts.json")
	if err != nil || !reflect.DeepEqual(charts.Charts, DefaultChartsConfig().Charts) ||
		!reflect.DeepEqual(charts.Details, DefaultChartsConfig().Details) {
		t.Fatalf("packaged charts mismatch: %v", err)
	}
	example, err := os.ReadFile("../../packaging/etc/telegraf-storage.conf.example")
	if err != nil {
		t.Fatal(err)
	}
	for _, text := range []string{"[[inputs.disk]]", "[[inputs.diskio]]", `device_tags = ["ID_MODEL"]`, `skip_serial_number = true`, `tagexclude = ["serial", "wwid"]`, `name = ["loop*", "ram*"]`, `precision = "1ns"`} {
		wantContains(t, string(example), text)
	}
	main, err := os.ReadFile("../../packaging/etc/telegraf.conf")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(main), "[[inputs.disk") {
		t.Fatal("storage was enabled without opt-in")
	}
	manifest, err := os.ReadFile("../../packaging/nfpm.yaml")
	if err != nil {
		t.Fatal(err)
	}
	wantContains(t, string(manifest), "src: etc/telegraf-storage.conf.example")
	wantContains(t, string(manifest), "dst: /usr/share/doc/metrics-manager/examples/telegraf-storage.conf")
	if err := validateChartSpecs("details.metrics", make([]ChartSpec, 65)); err == nil {
		t.Fatal("chart definitions are unbounded")
	}
}

func TestStorageColorsLayoutAndDetails(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	defer lipgloss.SetColorProfile(profile)
	m := NewModel(nil)
	m.now = func() time.Time { return fixedNow }
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: fixedNow, Samples: storageSamples(fixedNow, 0, 80)}))
	for _, metric := range []string{"storage.usedPercent", "storage.inodesPercent"} {
		for _, tc := range []struct {
			value float64
			level Severity
		}{{69.9, SeverityOK}, {70, SeverityCareful}, {80, SeverityWarning}, {90, SeverityCritical}} {
			text := m.thresholdValue(metric, reading(tc.value), func(Reading) string { return "value" })
			if text != severityStyle(tc.level).Render("value") {
				t.Fatalf("%s %g disagrees with thresholds", metric, tc.value)
			}
		}
	}
	if m.thresholdValue("storage.busyPercent", reading(100), func(Reading) string { return "100" }) != "100" {
		t.Fatal("busy time colored without configured threshold")
	}
	for _, size := range [][2]int{{20, 8}, {80, 24}, {140, 40}, {200, 50}} {
		m, _ = update(t, m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		for _, tab := range []Tab{OverviewTab, TrendsTab, DetailsTab, AlertsTab} {
			m.switchTab(tab)
			view := m.View()
			if len(strings.Split(view, "\n")) > size[1] {
				t.Fatalf("%v tab %v exceeds height", size, tab)
			}
			for _, line := range strings.Split(view, "\n") {
				if lipgloss.Width(line) > size[0] {
					t.Fatalf("%v tab %v exceeds width", size, tab)
				}
			}
		}
	}
	count := 0
	for _, item := range m.detailItems() {
		if strings.HasPrefix(item.spec.Metric, "storage.") {
			count++
			if detailCellTitle(item) != item.spec.Title {
				t.Fatal("storage detail title repeats device identity")
			}
		}
	}
	if count != len(storageChartSpecs()) {
		t.Fatalf("storage details = %d", count)
	}
	empty := NewModel(nil)
	for _, item := range empty.detailItems() {
		if strings.HasPrefix(item.spec.Metric, "storage.") {
			t.Fatal("storage placeholder shown before source observed")
		}
	}
}
