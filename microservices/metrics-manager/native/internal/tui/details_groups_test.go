// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"reflect"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

func groupedDetailsModel(t *testing.T, width, height int) Model {
	t.Helper()
	config := DefaultChartsConfig()
	config.Details.Metrics = []ChartSpec{
		fixedChart("npu.utilizationPercent", "NPU utilization", "%", 0, 100),
		fixedChart("gpu.temperatureC", "GPU temperature", "C", 0, 110),
		{Metric: "cpu.powerW", Title: "Package power", Unit: "W"},
		fixedChart("memory.usedPercent", "Memory", "%", 0, 100),
		fixedChart("gpu.utilizationPercent", "GPU utilization", "%", 0, 100),
		fixedChart("cpu.totalPercent", "CPU utilization", "%", 0, 100),
	}
	m := NewModelWithConfigs(nil, DefaultDashboardConfig(), config)
	m.now = func() time.Time { return fixedNow }
	m.dash = BuildDashboard(parseFixture(t, hostExposition+acceleratorExposition))
	first, second := m.dash.GPUs[0], m.dash.GPUs[0]
	first.ID, second.ID = "10", "2"
	m.dash.GPUs = []GPU{first, second}
	m.history.Update(m.dash, fixedNow)
	m.updatedAt = fixedNow
	m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: height})
	m, _ = update(t, m, key("3"))
	return m
}

func TestDetailsGroupOrderAndConfigOrderWithinGroups(t *testing.T) {
	m := groupedDetailsModel(t, 140, 50)
	frame := m.detailsLayout(140)
	var groups []string
	for _, row := range frame.rows {
		if len(row.items) == 0 && !row.bottom {
			groups = append(groups, row.group)
		}
	}
	want := []string{"CPU", "Memory", "GPU 2", "GPU 10", "NPU"}
	if !reflect.DeepEqual(groups, want) {
		t.Fatalf("groups=%v, want %v", groups, want)
	}
	var metrics []string
	for _, item := range frame.items {
		metrics = append(metrics, item.spec.Metric)
	}
	wantMetrics := []string{
		"cpu.powerW", "cpu.totalPercent", "memory.usedPercent",
		"gpu.temperatureC", "gpu.utilizationPercent",
		"gpu.temperatureC", "gpu.utilizationPercent", "npu.utilizationPercent",
	}
	if !reflect.DeepEqual(metrics, wantMetrics) {
		t.Errorf("in-group configuration order changed: %v", metrics)
	}
	if frame.items[frame.selected].spec.Metric != "cpu.totalPercent" {
		t.Fatal("grouping ignored the configured default metric")
	}
	t.Log("\n" + m.View())
}

func TestDetailsRowsNeverMixHardwareGroups(t *testing.T) {
	for _, width := range []int{20, 40, 80, 140, 210} {
		m := groupedDetailsModel(t, width, 40)
		frame := m.detailsLayout(width)
		seen := make(map[int]bool)
		header := ""
		for rowIndex, row := range frame.rows {
			if len(row.items) == 0 {
				if !row.bottom {
					header = row.group
				}
				continue
			}
			if len(row.items) > frame.columns {
				t.Fatal("row exceeded its column budget")
			}
			for _, index := range row.items {
				_, _, group := detailGroup(frame.items[index])
				if group != header {
					t.Errorf("width %d row %d mixes %q with %q", width, rowIndex, header, group)
				}
				if seen[index] || frame.itemRows[index] != rowIndex {
					t.Errorf("item %d duplicated or mapped to the wrong row", index)
				}
				seen[index] = true
			}
		}
		if len(seen) != len(frame.items) {
			t.Fatal("grouping dropped metrics")
		}
	}
}

func TestDetailsGroupedVerticalNavigationSkipsHeadings(t *testing.T) {
	m := groupedDetailsModel(t, 140, 40)
	m.selectDetail(0)
	for _, group := range []string{"Memory", "GPU 2", "GPU 10", "NPU"} {
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyDown})
		frame := m.detailsLayout(140)
		_, _, got := detailGroup(frame.items[frame.selected])
		if got != group {
			t.Fatalf("down selected %q, want %q", got, group)
		}
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyDown})
	frame := m.detailsLayout(140)
	if frame.selected != len(frame.items)-1 {
		t.Fatal("down at the bottom moved off the last metric")
	}
	for _, group := range []string{"GPU 10", "GPU 2", "Memory", "CPU"} {
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyUp})
		frame = m.detailsLayout(140)
		_, _, got := detailGroup(frame.items[frame.selected])
		if got != group {
			t.Fatalf("up selected %q, want %q", got, group)
		}
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyPgUp})
	if m.detailSelection != frame.items[0].choice {
		t.Fatal("page-up past the first heading did not clamp to the first metric")
	}
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyPgDown})
	if m.detailSelection != frame.items[len(frame.items)-1].choice {
		t.Fatal("page-down past the last group did not clamp to the last metric")
	}
}

func TestDetailsIgnoresGroupHeadingAndEmptyCellClicks(t *testing.T) {
	m := groupedDetailsModel(t, 140, 50)
	frame := m.detailsLayout(140)
	before := frame.items[frame.selected].choice
	y := len(m.chromeLines(140)) + len(frame.chart) + 1
	for _, msg := range []tea.MouseMsg{
		{X: 0, Y: y, Button: tea.MouseButtonLeft, Action: tea.MouseActionPress},
		{X: 1 + 2*(frame.cellWidth+panelGap), Y: y + 1, Button: tea.MouseButtonLeft, Action: tea.MouseActionPress},
	} {
		m, _ = update(t, m, msg)
		next := m.detailsLayout(140)
		if next.items[next.selected].choice != before {
			t.Fatal("heading or unused cell was selectable")
		}
	}
}

func TestDetailsClicksAfterGroupingPagingAndResize(t *testing.T) {
	for _, width := range []int{40, 80, 140} {
		m := groupedDetailsModel(t, 140, 30)
		m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
		m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: 30})
		frame := m.detailsLayout(width)
		clicked := false
		for row := frame.firstRow; row < frame.firstRow+frame.visibleRows; row++ {
			if len(frame.rows[row].items) == 0 {
				continue
			}
			index := frame.rows[row].items[0]
			if index == frame.selected {
				t.Fatal("fixture needs an unselected visible metric to test hit detection")
			}
			m, _ = update(t, m, tea.MouseMsg{
				X: 1, Y: len(m.chromeLines(width)) + len(frame.chart) + 1 + row - frame.firstRow,
				Button: tea.MouseButtonLeft, Action: tea.MouseActionPress,
			})
			if m.detailSelection != frame.items[index].choice {
				t.Fatalf("width %d clicked wrong metric after resize/scroll", width)
			}
			clicked = true
			break
		}
		if !clicked {
			t.Fatal("no selectable metric was visible")
		}
	}
}

func TestDetailsRetainsDeviceGroupAfterHistoryExpiry(t *testing.T) {
	m := groupedDetailsModel(t, 140, 40)
	for i, item := range m.detailItems() {
		if item.choice.device == "2" {
			m.selectDetail(i)
			break
		}
	}
	m.dash.GPUs = nil
	m.history.Update(m.dash, fixedNow.Add(time.Minute))
	frame := m.detailsLayout(140)
	item := frame.items[frame.selected]
	if item.choice.device != "2" || len(item.series.Points) == 0 {
		t.Fatalf("retained history lost its device group: %+v", item)
	}
	m.history.Update(m.dash, fixedNow.Add(6*time.Minute))
	frame = m.detailsLayout(140)
	item = frame.items[frame.selected]
	_, device, group := detailGroup(item)
	if device != "2" || group != "GPU 2" || len(item.series.Points) != 0 {
		t.Fatalf("selected device lost its group after expiry: %+v", item)
	}
}

func TestDetailsGroupHeadersSanitizeDeviceIDs(t *testing.T) {
	m := groupedDetailsModel(t, 140, 80)
	m.dash.GPUs[0].ID = "10\x1b[2J\x07"
	m.history.Update(m.dash, fixedNow)
	view := m.View()
	if strings.Contains(view, "\x1b[2J") || strings.Contains(view, "\x07") {
		t.Fatalf("group header passed through terminal control characters: %q", view)
	}
}
