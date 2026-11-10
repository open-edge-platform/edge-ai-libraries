// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

const chartMinWidth = 52

func (m Model) trendsGrid(width int) string {
	columns := (width + panelGap) / (chartMinWidth + panelGap)
	if columns < 1 {
		columns = 1
	}
	if columns > 2 {
		columns = 2
	}
	columnWidth := (width - panelGap*(columns-1)) / columns

	var panels []string
	for _, spec := range m.chartsConfig.Charts {
		for _, series := range m.history.Series(spec.Metric) {
			panels = append(panels, framePanel(m.renderChart(spec, series, max(1, columnWidth-2)), columnWidth))
		}
	}
	if len(panels) == 0 {
		return labelStyle.Render("No samples in the current window. Waiting for trend data.")
	}

	grid := packPanels(panels, width, chartMinWidth, 2)
	if m.history.limited {
		return labelStyle.Render(fmt.Sprintf("History series limit (%d) reached; additional series omitted.",
			maxHistorySeries)) + "\n" + grid
	}
	return grid
}

func (m Model) renderChart(spec ChartSpec, series HistorySeries, width int) string {
	end := m.now()
	window := m.chartsConfig.historyWindow()
	start := end.Add(-window)
	points := windowPoints(series.Points, start, end)
	minValue, maxValue := series.scale.bounds(spec, points)

	var b strings.Builder
	b.WriteString(headingStyle.Render(sanitize(seriesTitle(spec, series), width)) + "\n")
	if len(points) > 0 {
		last, minimum, average, maximum := pointStats(points)
		unit := sanitize(spec.Unit, 16)
		latest := points[len(points)-1]
		lastText := m.thresholdValue(spec.Metric, reading(last), func(Reading) string { return chartNumber(last) + unit })
		b.WriteString(fmt.Sprintf("last %s | %s\n", lastText, formatAge(end.Sub(latest.At))))
		b.WriteString(fmt.Sprintf("min %s | sample avg %s | max %s\n", chartNumber(minimum), chartNumber(average), chartNumber(maximum)))
		if !series.Available || m.err != nil {
			b.WriteString("No current measurement; showing retained samples.\n")
		}
	} else {
		b.WriteString("No samples in this time window.\n")
	}

	labelWidth := max(6, len(chartNumber(minValue)), len(chartNumber(maxValue)))
	axisWidth := labelWidth + 2
	plotWidth := width - axisWidth
	if plotWidth < 4 {
		b.WriteString("Widen terminal for plot.\n")
		return lipgloss.NewStyle().Width(max(1, width)).Render(b.String())
	}
	bucketWidth, cellLevels := plotWidth, 8
	if m.chartsConfig.GraphMode == "braille" {
		bucketWidth *= 2
		cellLevels = 4
	}
	buckets := timeBuckets(points, bucketWidth, start, end)
	height := m.chartsConfig.ChartHeight
	grid := make([][]rune, height)
	for row := range grid {
		grid[row] = []rune(strings.Repeat(" ", plotWidth))
	}
	for column, point := range buckets {
		if !point.OK {
			continue
		}
		// Keep measured zero visible at the baseline, unlike missing buckets.
		fraction := (point.Value - minValue) / (maxValue - minValue)
		fraction = math.Max(0, math.Min(1, fraction))
		level := int(math.Round(fraction * float64(height*cellLevels)))
		level = max(1, min(height*cellLevels, level))
		if m.chartsConfig.GraphMode == "solid" {
			level = max(1, int(math.Ceil(fraction*float64(height)))) * 8
		}
		blocks := []rune(" ▁▂▃▄▅▆▇█")
		for row := height - 1; row >= 0 && level > 0; row-- {
			fill := min(cellLevels, level)
			if m.chartsConfig.GraphMode == "braille" {
				x := column / 2
				cell := grid[row][x]
				if cell == ' ' {
					cell = '\u2800'
				}
				dots := [2][4]uint{{0, 1, 2, 6}, {3, 4, 5, 7}}
				for dot := 4 - fill; dot < 4; dot++ {
					cell |= 1 << dots[column%2][dot]
				}
				grid[row][x] = cell
				level -= fill
				continue
			}
			cell := blocks[fill]
			if m.chartsConfig.GraphMode == "ascii" {
				cell = '+'
				if fill == 8 {
					cell = '#'
				} else if fill == 1 {
					cell = '_'
				}
			}
			grid[row][column] = cell
			level -= fill
		}
	}

	for row := range grid {
		label := strings.Repeat(" ", labelWidth)
		if row == 0 {
			label = fmt.Sprintf("%*s", labelWidth, chartNumber(maxValue))
		} else if row == height-1 {
			label = fmt.Sprintf("%*s", labelWidth, chartNumber(minValue))
		}
		axis := " │"
		if m.chartsConfig.GraphMode == "ascii" {
			axis = " |"
		}
		b.WriteString(labelStyle.Render(label + axis))
		style := chartRowStyle(row, height)
		solidBackground := m.chartsConfig.GraphMode == "solid" && lipgloss.ColorProfile() != termenv.Ascii
		if solidBackground {
			style = lipgloss.NewStyle().Background(style.GetForeground())
		}
		// Style contiguous runs rather than every cell to keep terminal output
		// compact on wide plots.
		for start := 0; start < plotWidth; {
			end := start + 1
			empty := grid[row][start] == ' '
			for end < plotWidth && (grid[row][end] == ' ') == empty {
				end++
			}
			text := string(grid[row][start:end])
			if !empty {
				if solidBackground {
					text = strings.Repeat(" ", end-start)
				} else if m.chartsConfig.GraphMode == "solid" {
					text = strings.Repeat("#", end-start)
				}
				text = style.Render(text)
			}
			b.WriteString(text)
			start = end
		}
		b.WriteString("\n")
	}
	horizontal := "─"
	if m.chartsConfig.GraphMode == "ascii" {
		horizontal = "-"
	}
	b.WriteString(labelStyle.Render(strings.Repeat(" ", axisWidth) + strings.Repeat(horizontal, plotWidth)))
	b.WriteString("\n")
	left := "-" + formatWindow(window)
	timeline := "now"
	if plotWidth >= len(left)+4 {
		timeline = left + strings.Repeat(" ", plotWidth-len(left)-3) + "now"
	}
	b.WriteString(labelStyle.Render(strings.Repeat(" ", axisWidth) + timeline))

	return lipgloss.NewStyle().Width(width).Render(b.String())
}

func chartRowStyle(row, height int) lipgloss.Style {
	level, span := max(0, min(height-1, height-1-row)), max(1, height-1)
	brightness := float64(level) / float64(span)
	if lipgloss.ColorProfile() == termenv.ANSI {
		// Keep limited palettes blue instead of quantizing pale shades to white.
		color := lipgloss.Color("4")
		if brightness >= 0.5 {
			color = lipgloss.Color("12")
		}
		return lipgloss.NewStyle().Foreground(color)
	}
	mix := func(low, high [3]int, amount float64) string {
		var rgb [3]int
		for channel := range rgb {
			rgb[channel] = low[channel] + int(math.Round(float64(high[channel]-low[channel])*amount))
		}
		return fmt.Sprintf("#%02x%02x%02x", rgb[0], rgb[1], rgb[2])
	}
	return lipgloss.NewStyle().Foreground(lipgloss.AdaptiveColor{
		Light: mix([3]int{15, 52, 100}, [3]int{45, 110, 180}, brightness),
		Dark:  mix([3]int{30, 90, 150}, [3]int{105, 169, 223}, brightness),
	})
}

func windowPoints(points []HistoryPoint, start, end time.Time) []HistoryPoint {
	var visible []HistoryPoint
	for _, point := range points {
		if !point.At.Before(start) && !point.At.After(end) &&
			!math.IsNaN(point.Value) && !math.IsInf(point.Value, 0) {
			visible = append(visible, point)
		}
	}
	return visible
}

// Absolute bucket boundaries do not change between frames. The first and last
// buckets may be partial, so reserve one interval less than the column count
// to cover the full window. Missing data and startup remain empty.
func timeBuckets(points []HistoryPoint, width int, start, end time.Time) []Reading {
	if width <= 0 || !end.After(start) {
		return nil
	}
	buckets := make([]Reading, width)
	intervals := time.Duration(max(1, width-1))
	step := end.Sub(start) / intervals
	if end.Sub(start)%intervals != 0 {
		step++
	}
	right := end.Truncate(step)
	for _, point := range points {
		if point.At.Before(start) || point.At.After(end) ||
			math.IsNaN(point.Value) || math.IsInf(point.Value, 0) {
			continue
		}
		column := 0
		if width > 1 {
			column = width - 1 - int(right.Sub(point.At.Truncate(step))/step)
		}
		if column < 0 || column >= width {
			continue
		}
		if !buckets[column].OK || point.Value > buckets[column].Value {
			buckets[column] = reading(point.Value)
		}
	}
	return buckets
}

func chartNumber(value float64) string {
	if value != 0 && math.Abs(value) < 0.1 {
		return fmt.Sprintf("%.2g", value)
	}
	return fmt.Sprintf("%.1f", value)
}

func chartBounds(spec ChartSpec, points []HistoryPoint) (float64, float64) {
	if spec.Min == nil && nonnegativeChart(spec.Metric) {
		zero := 0.0
		spec.Min = &zero
	}
	minValue, maxValue := 0.0, 1.0
	if len(points) > 0 {
		minValue, maxValue = points[0].Value, points[0].Value
	}
	for _, point := range points {
		minValue = math.Min(minValue, point.Value)
		maxValue = math.Max(maxValue, point.Value)
	}
	if spec.Min != nil {
		minValue = *spec.Min
	}
	if spec.Max != nil {
		maxValue = *spec.Max
	}
	if minValue >= maxValue {
		switch {
		case spec.Min != nil && spec.Max == nil:
			maxValue = minValue + math.Max(1, math.Abs(minValue)*0.1)
		case spec.Min == nil && spec.Max != nil:
			minValue = maxValue - math.Max(1, math.Abs(maxValue)*0.1)
		default:
			padding := math.Max(1, math.Abs(minValue)*0.1)
			minValue -= padding
			maxValue += padding
		}
	}

	return minValue, maxValue
}

func pointStats(points []HistoryPoint) (last, minimum, average, maximum float64) {
	minimum, maximum = points[0].Value, points[0].Value
	for _, point := range points {
		average += point.Value
		minimum = math.Min(minimum, point.Value)
		maximum = math.Max(maximum, point.Value)
	}

	return points[len(points)-1].Value, minimum, average / float64(len(points)), maximum
}

func formatWindow(window time.Duration) string {
	if window%time.Hour == 0 {
		return fmt.Sprintf("%dh", int(window.Hours()))
	}
	if window%time.Minute == 0 {
		return fmt.Sprintf("%dm", int(window.Minutes()))
	}

	return fmt.Sprintf("%ds", int(window.Seconds()))
}
