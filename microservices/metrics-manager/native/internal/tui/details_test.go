// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"math"
	"reflect"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func detailsModel(t *testing.T, width, height int) Model {
	t.Helper()
	m := acceleratorModel(t, height)
	m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: height})
	m, _ = update(t, m, key("3"))
	return m
}

func TestFourTabsCycleInBothDirections(t *testing.T) {
	m := testModel(nil)
	for _, want := range []Tab{TrendsTab, DetailsTab, AlertsTab, OverviewTab} {
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyTab})
		if m.activeTab != want {
			t.Fatalf("forward tab = %v, want %v", m.activeTab, want)
		}
	}
	for _, want := range []Tab{AlertsTab, DetailsTab, TrendsTab, OverviewTab} {
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyShiftTab})
		if m.activeTab != want {
			t.Fatalf("backward tab = %v, want %v", m.activeTab, want)
		}
	}
}

func TestDetailsDefaultsToFullWidthCPUHistory(t *testing.T) {
	m := detailsModel(t, 140, 40)
	view := m.View()
	t.Log("\n" + view)
	wantContains(t, view, "[3 Details]")
	wantContains(t, view, "CPU utilization")
	wantContains(t, view, "-5m")
	wantContains(t, view, "last 4.8%")
	wantContains(t, view, "Select metric")
	frame := m.detailsLayout(140)
	if frame.items[frame.selected].spec.Metric != "cpu.totalPercent" {
		t.Fatal("Details did not select CPU by default")
	}
	rows := 0
	for _, line := range frame.chart {
		if strings.Contains(strings.TrimSuffix(strings.TrimRight(line, " "), "│"), " │") {
			rows++
			if lipgloss.Width(line) != 140 {
				t.Errorf("plot does not fill width: %d", lipgloss.Width(line))
			}
		}
	}
	if rows != m.chartsConfig.Details.ChartHeight {
		t.Errorf("plot height=%d, want %d", rows, m.chartsConfig.Details.ChartHeight)
	}
}

func TestDetailsShowsDRAMReadWriteTotalAndRAPLPerDomain(t *testing.T) {
	m := testModel(nil)
	m.now = func() time.Time { return fixedNow }
	exposition := hostExposition + `memory_bandwidth_read_bytes_per_second{host="itest"} 2147483648
memory_bandwidth_write_bytes_per_second{host="itest"} 134217728
memory_bandwidth_total_bytes_per_second{host="itest"} 2281701376
rapl_power_power_w{host="itest",domain="psys"} 9.83
rapl_power_power_w{host="itest",domain="package-0"} 6.51
`
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: fixedNow, Samples: parseFixture(t, exposition)}))
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 140, Height: 60})
	m, _ = update(t, m, key("3"))
	items := m.detailItems()
	want := map[string]float64{
		"memory.bandwidth":       2.281701376,
		"memory.bandwidth.read":  2.147483648,
		"memory.bandwidth.write": 0.134217728,
		"rapl.package-0":         6.51,
		"rapl.psys":              9.83,
	}
	for i, item := range items {
		value, ok := want[item.choice.key]
		if !ok {
			continue
		}
		if !item.value.OK || item.value.Value != value ||
			len(item.series.Points) != 1 || item.series.Points[0].Value != value {
			t.Errorf("%s has no current value or plot data: %+v", item.choice.key, item)
		}
		if strings.HasPrefix(item.choice.key, "rapl.") {
			_, _, group := detailGroup(item)
			if group != "RAPL power" {
				t.Errorf("RAPL metric grouped as %q", group)
			}
		}
		m.selectDetail(i)
		wantContains(t, m.View(), "last ")
		delete(want, item.choice.key)
	}
	if len(want) != 0 {
		t.Errorf("Details missing chart choices: %v", want)
	}
}

func TestDetailsHidesOptionalRAPLAndDRAMReadWriteUntilSamples(t *testing.T) {
	m := detailsModel(t, 120, 35)
	for _, item := range m.detailItems() {
		if item.spec.Metric == "rapl.powerW" ||
			item.spec.Metric == "memory.readGBps" || item.spec.Metric == "memory.writeGBps" {
			t.Errorf("missing optional metric appears in Details: %s", item.spec.Metric)
		}
	}
}

func TestDetailsKeyboardSelectsAndKeepsHistory(t *testing.T) {
	m := detailsModel(t, 120, 30)
	before := len(m.history.Series("cpu.totalPercent")[0].Points)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyRight})
	if m.detailSelection.metric != "cpu.classPercent" || m.detailSelection.label != "P" {
		t.Fatalf("right arrow selected %+v", m.detailSelection)
	}
	wantContains(t, m.View(), "Core class utilization")
	selected := m.detailSelection
	m, _ = update(t, m, key("2"))
	m, _ = update(t, m, key("3"))
	if m.detailSelection != selected || len(m.history.Series("cpu.totalPercent")[0].Points) != before {
		t.Fatal("switching tabs lost selection or history")
	}
	m, _ = update(t, m, key("a"))
	m, cmd := update(t, m, key("esc"))
	if isQuit(cmd) || m.detailSelection != selected || m.activeTab != DetailsTab {
		t.Fatal("closing alerts did not restore Details")
	}
}

func TestDetailsSelectionScrollsButChartStaysAtTop(t *testing.T) {
	m := detailsModel(t, 80, 24)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	frame := m.detailsLayout(80)
	if frame.selected != len(frame.items)-1 || frame.firstRow == 0 {
		t.Fatal("End did not reveal the final metric")
	}
	selectedRow := frame.itemRows[frame.selected]
	if selectedRow < frame.firstRow || selectedRow >= frame.firstRow+frame.visibleRows {
		t.Fatal("selected metric is not visible")
	}
	if m.offset != 0 {
		t.Fatal("metric navigation scrolled the whole Details page")
	}
	lines := strings.Split(m.View(), "\n")
	if !strings.Contains(lines[len(m.chromeLines(80))], "NPU memory") {
		t.Fatal("selected chart is not pinned immediately below the header")
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyHome})
	if m.detailSelection.metric != "cpu.totalPercent" || m.detailTop != 0 {
		t.Fatal("Home did not return to CPU")
	}
}

func TestDetailsMouseSelectsRenderedCell(t *testing.T) {
	for _, width := range []int{40, 80, 140} {
		m := detailsModel(t, width, 35)
		frame := m.detailsLayout(width)
		want := min(frame.columns, len(frame.items)-1)
		row, col := frame.itemPosition(want)
		msg := tea.MouseMsg{
			X:      1 + col*(frame.cellWidth+panelGap),
			Y:      len(m.chromeLines(width)) + len(frame.chart) + 1 + row - frame.firstRow,
			Button: tea.MouseButtonLeft, Action: tea.MouseActionPress,
		}
		m, _ = update(t, m, msg)
		if m.detailSelection != frame.items[want].choice {
			t.Errorf("width %d clicked %+v, want %+v", width, m.detailSelection, frame.items[want].choice)
		}
		selected := m.detailSelection
		msg.Y = 0
		m, _ = update(t, m, msg)
		if m.detailSelection != selected {
			t.Fatal("click on header changed selection")
		}
		msg.Action = tea.MouseActionRelease
		m, _ = update(t, m, msg)
		if m.detailSelection != selected {
			t.Fatal("release changed selection")
		}
	}
}

func TestDetailsMouseUsesScrolledListCoordinates(t *testing.T) {
	m := detailsModel(t, 120, 24)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	frame := m.detailsLayout(120)
	if frame.firstRow == 0 {
		t.Fatal("fixture did not scroll")
	}
	row := frame.firstRow
	for len(frame.rows[row].items) == 0 {
		row++
	}
	want := frame.items[frame.rows[row].items[0]].choice
	m, _ = update(t, m, tea.MouseMsg{
		X: 1, Y: len(m.chromeLines(120)) + len(frame.chart) + 1 + row - frame.firstRow,
		Button: tea.MouseButtonLeft, Action: tea.MouseActionPress,
	})
	if m.detailSelection != want {
		t.Fatalf("scrolled click selected %+v, want %+v", m.detailSelection, want)
	}
	m, _ = update(t, m, tea.MouseMsg{Button: tea.MouseButtonWheelUp, Action: tea.MouseActionPress})
	if m.detailSelection == want {
		t.Fatal("wheel did not move the selection")
	}
}

func TestDetailsFailedPollKeepsHistoryButNotCurrentValue(t *testing.T) {
	m := detailsModel(t, 120, 35)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At: fixedNow.Add(time.Second), Err: errors.New("offline"),
	}))
	frame := m.detailsLayout(120)
	item := frame.items[frame.selected]
	if item.value.OK || len(item.series.Points) == 0 || item.series.Available {
		t.Fatalf("failed poll was represented as current data: %+v", item)
	}
	wantContains(t, m.View(), "No current measurement")
}

func TestMouseCaptureAcrossTabsAndSelectionPreference(t *testing.T) {
	m := testModel(nil)
	m, cmd := update(t, m, key("3"))
	if cmd != nil || !m.mouseEnabled() || !m.detailsMouseEnabled() {
		t.Fatal("Details should retain global mouse capture")
	}
	m, cmd = update(t, m, key("a"))
	if cmd != nil || !m.mouseEnabled() || m.detailsMouseEnabled() {
		t.Fatal("alerts should retain tab clicks, not Details selection")
	}
	m, _ = update(t, m, key("esc"))
	m, cmd = update(t, m, key("1"))
	if cmd != nil || !m.mouseEnabled() {
		t.Fatal("Overview should retain tab clicks")
	}
	m.chartsConfig.Details.Mouse = false
	m, cmd = update(t, m, key("3"))
	if cmd != nil || m.detailsMouseEnabled() {
		t.Fatal("disabled mouse preference was ignored")
	}
}

func TestDetailsKeepsSelectedMissingGPUAfterExpiry(t *testing.T) {
	m := detailsModel(t, 120, 35)
	for i, item := range m.detailItems() {
		if item.choice.key == "gpu.0.engine.render" {
			m.selectDetail(i)
			break
		}
	}
	if m.detailSelection.key != "gpu.0.engine.render" {
		t.Fatal("fixture has no GPU render metric")
	}
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At:      fixedNow.Add(6 * time.Minute),
		Samples: parseFixture(t, hostExposition),
	}))
	m.now = func() time.Time { return fixedNow.Add(6 * time.Minute) }
	frame := m.detailsLayout(120)
	item := frame.items[frame.selected]
	if item.choice.key != "gpu.0.engine.render" || item.value.OK || len(item.series.Points) != 0 {
		t.Fatalf("missing GPU silently replaced: %+v", item)
	}
	wantContains(t, m.View(), "No samples in this time window.")
}

func TestDetailsBoundsAcrossTerminalSizes(t *testing.T) {
	for _, width := range []int{1, 12, 20, 40, 80, 140, 210} {
		for _, height := range []int{1, 5, 8, 12, 24, 40} {
			m := detailsModel(t, width, height)
			m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
			view := m.View()
			if len(strings.Split(view, "\n")) > height {
				t.Errorf("%dx%d: view exceeds height", width, height)
			}
			for _, line := range strings.Split(view, "\n") {
				if lipgloss.Width(line) > width {
					t.Errorf("%dx%d: view exceeds width: %q", width, height, line)
				}
			}
		}
	}
}

func TestDetailsUsesConfiguredOrderDefaultAndMouse(t *testing.T) {
	config := DefaultChartsConfig()
	config.Details.DefaultMetric = "memory.usedPercent"
	config.Details.Metrics = []ChartSpec{
		fixedChart("memory.usedPercent", "RAM", "%", 0, 100),
		fixedChart("cpu.totalPercent", "Processor", "%", 0, 100),
	}
	m := NewModelWithConfigs(nil, DefaultDashboardConfig(), config)
	m.now = func() time.Time { return fixedNow }
	m, _ = update(t, m, key("3"))
	frame := m.detailsLayout(80)
	if frame.items[frame.selected].spec.Metric != "memory.usedPercent" || len(frame.items) != 2 {
		t.Fatalf("configured selector ignored: %+v", frame)
	}
	wantContains(t, m.View(), "RAM")
}

func TestDetailObservationsConvertUnitsAndSeparateDevices(t *testing.T) {
	d := Dashboard{
		CPU: CPU{FrequencyKHz: reading(2400000), PackagePowerW: reading(25),
			Classes: []CoreClass{{Name: "P", UsageIdle: reading(30)}, {Name: "E", UsageIdle: reading(60)}}},
		GPUs: []GPU{
			{ID: "0", VRAMTotalBytes: reading(0), VRAMUsedBytes: reading(0),
				Tiles: []GPUTile{{Name: "gt0", ActualMHz: reading(800)}}},
			{ID: "1", VRAMTotalBytes: reading(800), VRAMUsedBytes: reading(200),
				Tiles: []GPUTile{{Name: "gt0", ActualMHz: reading(1200)}}},
		},
		NPU: NPU{FrequencyHz: reading(1400000000), PowerW: reading(2), MemoryMiB: reading(128)},
	}
	byKey := make(map[string]Reading)
	for _, observation := range chartObservations(d) {
		if !supportedCharts[observation.metric] {
			t.Errorf("unregistered metric %q", observation.metric)
		}
		byKey[observation.key] = observation.value
	}
	for key, want := range map[string]float64{
		"cpu.frequency": 2400, "cpu.power": 25, "cpu.class.P": 70, "cpu.class.E": 40,
		"gpu.0.tile.gt0": 800, "gpu.1.tile.gt0": 1200, "gpu.1.vram": 25,
		"npu.frequency": 1400, "npu.power": 2, "npu.memory": 128,
	} {
		if got := byKey[key]; !got.OK || math.Abs(got.Value-want) > 1e-6 {
			t.Errorf("%s = %+v, want %g", key, got, want)
		}
	}
	if byKey["gpu.0.vram"].OK || scaleReading(Reading{}, 1000).OK {
		t.Fatal("missing measurement became zero")
	}
}

func TestDetailsKeepsDeviceIdentityBeforeTruncatedTitles(t *testing.T) {
	m := detailsModel(t, 80, 40)
	for i, item := range m.detailItems() {
		if item.choice.key == "gpu.0.engine.render" {
			m.selectDetail(i)
			break
		}
	}
	wantContains(t, m.detailsBody(80), "> GPU 0 / render")
	frame := m.detailsLayout(80)
	if !strings.HasPrefix(frame.chart[0], "┌ GPU 0 / render") {
		t.Fatal("chart lost selected device/engine identity")
	}
}

func TestVRAMPercentRejectsUnavailableValues(t *testing.T) {
	for _, total := range []Reading{{}, reading(0), reading(math.Inf(1)), reading(math.NaN())} {
		if usedPercent(reading(10), total).OK {
			t.Fatalf("invalid total %+v became a measured percentage", total)
		}
	}
	if usedPercent(reading(-1), reading(100)).OK {
		t.Fatal("negative memory sentinel became a measured percentage")
	}
}

func TestDetailsSanitizesRemoteLabels(t *testing.T) {
	m := detailsModel(t, 140, 40)
	m.dash.GPUs = []GPU{{ID: "0\x1b[2J", Engines: []GPUEngine{{Name: "render\x07", Usage: reading(50)}}}}
	m.history.Update(m.dash, fixedNow)
	for i, item := range m.detailItems() {
		if item.spec.Metric == "gpu.enginePercent" && strings.Contains(item.choice.key, "\x1b") {
			m.selectDetail(i)
			break
		}
	}
	if view := m.View(); strings.Contains(view, "\x1b[2J") || strings.Contains(view, "\x07") {
		t.Fatalf("remote terminal controls survived: %q", view)
	}
}

func TestDetailsConfigValidationAndPackagedDefaults(t *testing.T) {
	for _, tt := range []struct{ body, want string }{
		{`{"details":{"chartHeight":2}}`, "details.chartHeight"},
		{`{"details":{"metrics":[]}}`, "details.metrics"},
		{`{"details":{"defaultMetric":"disk.io"}}`, "details.defaultMetric"},
		{`{"details":{"metrics":[{"metric":"disk.io","title":"Disk"}]}}`, "not supported"},
		{`{"details":{"metrics":[{"metric":"cpu.totalPercent","title":"CPU","min":100,"max":0}]}}`, "min < max"},
		{`{"details":{"metrics":[{"metric":"cpu.totalPercent","title":"CPU"},{"metric":"cpu.totalPercent","title":"CPU"}]}}`, "duplicated"},
	} {
		_, err := LoadChartsConfig(writeConfig(t, tt.body))
		if err == nil || !strings.Contains(err.Error(), tt.want) {
			t.Errorf("%s: error=%v, want %q", tt.body, err, tt.want)
		}
	}
	old, err := LoadChartsConfig(writeConfig(t, `{"historyDuration":"10m"}`))
	if err != nil || old.Details.DefaultMetric != "cpu.totalPercent" || !old.Details.Mouse {
		t.Fatalf("old configuration compatibility: %+v, %v", old, err)
	}
	packaged, err := LoadChartsConfig("../../packaging/etc/tui-charts.json")
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(packaged.Details, DefaultChartsConfig().Details) {
		t.Fatal("packaged Details defaults differ from built-in defaults")
	}
	if !reflect.DeepEqual(packaged.Charts, DefaultChartsConfig().Charts) {
		t.Fatal("packaged Trends defaults differ from built-in defaults")
	}
}

func TestDetailsNavigationWhileHistoryUpdates(t *testing.T) {
	m := detailsModel(t, 120, 30)
	for i := range 15 {
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyRight})
		choice := m.detailSelection
		m, _ = update(t, m, snapshotMsg(source.Snapshot{
			At:      fixedNow.Add(time.Duration(i) * time.Second),
			Samples: parseFixture(t, hostExposition+acceleratorExposition),
		}))
		if m.detailSelection != choice {
			t.Fatalf("sample %d changed selection", i)
		}
	}
	if len(m.history.Series("cpu.frequencyMHz")[0].Points) != 15 {
		t.Fatal("frequency history was not captured outside selection")
	}
}
