// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"sort"
	"strconv"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type detailChoice struct {
	key, metric, label, device string
}

type detailItem struct {
	choice detailChoice
	spec   ChartSpec
	series HistorySeries
	value  Reading
}

type detailsFrame struct {
	items                 []detailItem
	rows                  []detailRow
	itemRows              []int
	chart                 []string
	selected              int
	columns, cellWidth    int
	firstRow, visibleRows int
}

type detailRow struct {
	group  string
	items  []int
	bottom bool
}

func detailGroup(item detailItem) (rank int, device, title string) {
	switch {
	case strings.HasPrefix(item.spec.Metric, "cpu."):
		return 0, "", "CPU"
	case strings.HasPrefix(item.spec.Metric, "memory."):
		return 1, "", "Memory"
	case strings.HasPrefix(item.spec.Metric, "rapl."):
		return 2, "", "RAPL power"
	case strings.HasPrefix(item.spec.Metric, "gpu."):
		if item.choice.device != "" {
			return 3, item.choice.device, "GPU " + item.choice.device
		}
		return 3, "", "GPU"
	case strings.HasPrefix(item.spec.Metric, "npu."):
		return 4, "", "NPU"
	case strings.HasPrefix(item.spec.Metric, "network."):
		return 5, item.choice.device, item.choice.label
	case strings.HasPrefix(item.spec.Metric, "storage."):
		return 6, item.choice.device, item.choice.label
	default:
		return 7, "", "Other"
	}
}

func groupDetailItems(items []detailItem) {
	sort.SliceStable(items, func(i, j int) bool {
		a, aDevice, _ := detailGroup(items[i])
		b, bDevice, _ := detailGroup(items[j])
		if a != b {
			return a < b
		}
		aID, aErr := strconv.ParseUint(aDevice, 10, 64)
		bID, bErr := strconv.ParseUint(bDevice, 10, 64)
		if aErr == nil && bErr == nil && aID != bID {
			return aID < bID
		}
		if (aErr == nil) != (bErr == nil) {
			return aErr == nil
		}
		return aDevice < bDevice
	})
}

func detailTitle(item detailItem) string {
	if item.series.Label != "" && !strings.HasPrefix(item.spec.Title, item.series.Label+" ") {
		return item.series.Label + " / " + item.spec.Title
	}
	return item.spec.Title
}

func detailCellTitle(item detailItem) string {
	if strings.HasPrefix(item.spec.Metric, "network.") || strings.HasPrefix(item.spec.Metric, "storage.") {
		return item.spec.Title
	}
	return detailTitle(item)
}

func (m Model) detailItems() []detailItem {
	observations := chartObservations(m.dash)
	var items []detailItem
	for _, spec := range m.chartsConfig.Details.Metrics {
		instances := make(map[string]detailItem)
		for _, series := range m.history.Series(spec.Metric) {
			instances[series.Key] = detailItem{
				choice: detailChoice{key: series.Key, metric: series.Metric, label: series.Label, device: series.Device},
				spec:   spec, series: series,
			}
		}
		for _, observation := range observations {
			if observation.metric != spec.Metric {
				continue
			}
			item := instances[observation.key]
			item.choice = detailChoice{key: observation.key, metric: spec.Metric, label: observation.label, device: observation.device}
			item.spec = spec
			item.value = observation.value
			if m.err != nil {
				item.value = Reading{}
			}
			if item.series.Key == "" {
				item.series = HistorySeries{Key: observation.key, Metric: spec.Metric, Label: observation.label, Device: observation.device}
			}
			instances[observation.key] = item
		}
		// Keep a selected device visible after its history expires instead of
		// silently switching the plot to another device.
		if m.detailSelection.metric == spec.Metric && m.detailSelection.key != "" {
			if _, exists := instances[m.detailSelection.key]; !exists {
				instances[m.detailSelection.key] = detailItem{
					choice: m.detailSelection, spec: spec,
					series: HistorySeries{Key: m.detailSelection.key, Metric: spec.Metric, Label: m.detailSelection.label, Device: m.detailSelection.device},
				}
			}
		}
		keys := make([]string, 0, len(instances))
		for key := range instances {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		if spec.Metric == "cpu.classPercent" {
			sort.SliceStable(keys, func(i, j int) bool {
				a, aKnown := classOrder[instances[keys[i]].series.Label]
				b, bKnown := classOrder[instances[keys[j]].series.Label]
				if aKnown != bKnown {
					return aKnown
				}
				return aKnown && a < b
			})
		}
		for _, key := range keys {
			items = append(items, instances[key])
		}
		if len(keys) == 0 {
			if (strings.HasPrefix(spec.Metric, "network.") || strings.HasPrefix(spec.Metric, "storage.") ||
				strings.HasPrefix(spec.Metric, "rapl.") || spec.Metric == "memory.readGBps" ||
				spec.Metric == "memory.writeGBps") && m.detailSelection.metric != spec.Metric {
				continue
			}
			items = append(items, detailItem{
				choice: detailChoice{metric: spec.Metric}, spec: spec,
				series: HistorySeries{Metric: spec.Metric},
			})
		}
	}
	groupDetailItems(items)
	return items
}

func (frame *detailsFrame) buildRows() {
	frame.itemRows = make([]int, len(frame.items))
	previousRank, previousDevice := -1, ""
	for i, item := range frame.items {
		rank, device, title := detailGroup(item)
		if rank != previousRank || device != previousDevice {
			if len(frame.rows) > 0 {
				frame.rows = append(frame.rows, detailRow{bottom: true})
			}
			frame.rows = append(frame.rows, detailRow{group: title})
			previousRank, previousDevice = rank, device
		}
		if len(frame.rows[len(frame.rows)-1].items) == 0 ||
			len(frame.rows[len(frame.rows)-1].items) == frame.columns {
			frame.rows = append(frame.rows, detailRow{items: []int{i}})
		} else {
			row := &frame.rows[len(frame.rows)-1]
			row.items = append(row.items, i)
		}
		frame.itemRows[i] = len(frame.rows) - 1
	}
	frame.rows = append(frame.rows, detailRow{bottom: true})
}

func (frame detailsFrame) itemPosition(index int) (row, column int) {
	row = frame.itemRows[index]
	return row, index - frame.rows[row].items[0]
}

func (frame detailsFrame) moveRows(delta int) int {
	row, column := frame.itemPosition(frame.selected)
	target := max(0, min(len(frame.rows)-1, row+delta))
	step := 1
	if delta < 0 {
		step = -1
	}
	for target >= 0 && target < len(frame.rows) && len(frame.rows[target].items) == 0 {
		target += step
	}
	if target < 0 {
		return 0
	}
	if target >= len(frame.rows) {
		return len(frame.items) - 1
	}
	items := frame.rows[target].items
	return items[min(column, len(items)-1)]
}

func (m Model) detailIndex(items []detailItem) int {
	for i, item := range items {
		if m.detailSelection.key != "" {
			if item.choice.key == m.detailSelection.key && item.choice.metric == m.detailSelection.metric {
				return i
			}
		} else if item.spec.Metric == m.detailSelection.metric {
			return i
		}
	}
	return 0
}

func (m Model) detailsLayout(width int) detailsFrame {
	frame := detailsFrame{items: m.detailItems()}
	frame.selected = m.detailIndex(frame.items)
	innerWidth := max(1, width-2)
	frame.columns = max(1, min(3, (innerWidth+panelGap)/(36+panelGap)))
	frame.cellWidth = (innerWidth - panelGap*(frame.columns-1)) / frame.columns
	frame.buildRows()
	item := frame.items[frame.selected]
	plotSpec, plotSeries := item.spec, item.series
	plotSpec.Title = detailTitle(item)
	plotSeries.Label = ""
	chartModel := m
	chartModel.chartsConfig.ChartHeight = m.chartsConfig.Details.ChartHeight
	render := func() []string {
		return strings.Split(framePanel(chartModel.renderChart(plotSpec, plotSeries, innerWidth), width), "\n")
	}
	frame.chart = render()
	available := m.visibleRows()
	if m.height > 0 {
		for len(frame.chart)+6 > available && chartModel.chartsConfig.ChartHeight > 3 {
			chartModel.chartsConfig.ChartHeight--
			frame.chart = render()
		}
		if len(frame.chart)+3 > available {
			frame.chart = []string{
				fitWidth(headingStyle.Render(sanitize(detailTitle(item), width)), width),
				"Taller terminal needed for plot.",
			}
			frame.chart = frame.chart[:min(len(frame.chart), max(0, available-3))]
		}
	}
	totalRows := len(frame.rows)
	frame.visibleRows = totalRows
	if m.height > 0 {
		frame.visibleRows = min(totalRows, max(0, available-len(frame.chart)-2))
	}
	frame.firstRow = min(m.detailTop, max(0, totalRows-frame.visibleRows))
	selectedRow := frame.itemRows[frame.selected]
	if selectedRow < frame.firstRow {
		frame.firstRow = selectedRow
	} else if frame.visibleRows > 0 && selectedRow >= frame.firstRow+frame.visibleRows {
		frame.firstRow = selectedRow - frame.visibleRows + 1
	}
	if frame.visibleRows >= 2 && selectedRow > 0 &&
		len(frame.rows[selectedRow-1].items) == 0 && frame.firstRow == selectedRow {
		frame.firstRow--
	}
	return frame
}

func (m Model) detailsBody(width int) string {
	frame := m.detailsLayout(width)
	lines := append([]string(nil), frame.chart...)
	_, _, group := detailGroup(frame.items[frame.selected])
	status := fmt.Sprintf("%s | Select metric (%d/%d)", sanitize(group, 80), frame.selected+1, len(frame.items))
	if m.history.limited {
		status += " | history series limit reached"
	}
	lines = append(lines, headingStyle.Render(status))
	for row := frame.firstRow; row < frame.firstRow+frame.visibleRows; row++ {
		if len(frame.rows[row].items) == 0 {
			lines = append(lines, panelEdge(sanitize(frame.rows[row].group, 80), width, frame.rows[row].bottom))
			continue
		}
		var cells []string
		for _, i := range frame.rows[row].items {
			item := frame.items[i]
			value := m.thresholdValue(item.spec.Metric, item.value, func(value Reading) string {
				if text, missing := placeholder(value); missing {
					return text
				}
				return fmt.Sprintf("%.1f%s", value.Value, sanitize(item.spec.Unit, 16))
			})
			label := sanitize(detailCellTitle(item), 180)
			marker := "  "
			if i == frame.selected {
				marker = "> "
			}
			labelWidth := max(0, frame.cellWidth-lipgloss.Width(value)-3)
			cell := marker + fitWidth(label, labelWidth)
			// fitWidth intentionally leaves width=0 unchanged.
			if labelWidth == 0 {
				cell = marker
			}
			cell += strings.Repeat(" ", max(1, frame.cellWidth-lipgloss.Width(cell)-lipgloss.Width(value))) + value
			cell = fitWidth(cell, frame.cellWidth)
			if i == frame.selected {
				cell = titleStyle.Render(cell)
			}
			cells = append(cells, cell)
		}
		lines = append(lines, panelRow(strings.Join(cells, strings.Repeat(" ", panelGap)), width))
	}
	if frame.visibleRows > 0 {
		last := frame.firstRow + frame.visibleRows - 1
		if !frame.rows[last].bottom {
			title := ""
			if last < len(frame.rows)-2 {
				title = "more metrics below"
			}
			lines = append(lines, panelEdge(title, width, true))
		}
	}
	return strings.Join(lines, "\n")
}

func (m *Model) selectDetail(index int) {
	items := m.detailItems()
	index = max(0, min(len(items)-1, index))
	m.detailSelection = items[index].choice
	m.detailTop = m.detailsLayout(m.renderWidth()).firstRow
}

func (m *Model) detailKey(key string) bool {
	frame := m.detailsLayout(m.renderWidth())
	index := frame.selected
	switch key {
	case "up", "k":
		index = frame.moveRows(-1)
	case "down", "j":
		index = frame.moveRows(1)
	case "left":
		index--
	case "right", "l":
		index++
	case "pgup":
		index = frame.moveRows(-max(1, frame.visibleRows))
	case "pgdown", " ":
		index = frame.moveRows(max(1, frame.visibleRows))
	case "home", "g":
		index = 0
	case "end", "G":
		index = len(frame.items) - 1
	case "enter":
	default:
		return false
	}
	m.selectDetail(index)
	return true
}

func (m Model) detailsMouseEnabled() bool {
	return m.activeTab == DetailsTab && m.mouseEnabled() && m.chartsConfig.Details.Mouse
}

func (m *Model) detailMouse(msg tea.MouseMsg) {
	if !m.detailsMouseEnabled() || msg.Action != tea.MouseActionPress {
		return
	}
	switch msg.Button {
	case tea.MouseButtonWheelUp:
		m.detailKey("up")
	case tea.MouseButtonWheelDown:
		m.detailKey("down")
	case tea.MouseButtonLeft:
		width := m.renderWidth()
		frame := m.detailsLayout(width)
		row := msg.Y - len(m.chromeLines(width)) - len(frame.chart) - 1
		if row < 0 || row >= frame.visibleRows || msg.X < 1 || msg.X >= width-1 {
			return
		}
		x := msg.X - 1
		col := x / (frame.cellWidth + panelGap)
		if col >= frame.columns || x%(frame.cellWidth+panelGap) >= frame.cellWidth {
			return
		}
		items := frame.rows[frame.firstRow+row].items
		if col < len(items) {
			m.selectDetail(items[col])
		}
	}
}
