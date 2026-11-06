// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"
)

func plotRaster(text, mode string) [][]rune {
	var rows [][]rune
	axis := " │"
	if mode == "ascii" {
		axis = " |"
	}
	for _, line := range strings.Split(ansi.Strip(text), "\n") {
		label, plot, ok := strings.Cut(line, axis)
		if !ok || strings.Trim(label, " 0123456789.-") != "" {
			continue
		}
		if mode != "braille" {
			rows = append(rows, []rune(plot))
			continue
		}
		var pixels []rune
		for _, cell := range plot {
			for _, bits := range [2][4]uint{{0, 1, 2, 6}, {3, 4, 5, 7}} {
				var column rune
				if cell >= '\u2800' && cell <= '\u28ff' {
					for dot, bit := range bits {
						column |= ((cell >> bit) & 1) << dot
					}
				}
				pixels = append(pixels, column)
			}
		}
		rows = append(rows, pixels)
	}
	return rows
}

func TestChartFramesPreserveClosedColumnsAndShiftAsAWhole(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	for _, mode := range []string{"solid", "unicode", "ascii", "braille"} {
		t.Run(mode, func(t *testing.T) {
			m := testModel(nil)
			m.chartsConfig.GraphMode = mode
			columns := 61
			if mode == "braille" {
				columns *= 2
			}
			window := 5 * time.Minute
			step := (window + time.Duration(columns-2)) / time.Duration(columns-1)
			anchor := fixedNow.Truncate(step)
			now := anchor.Add(step / 4)
			m.now = func() time.Time { return now }
			spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
			series := HistorySeries{Available: true, Points: []HistoryPoint{
				{At: anchor.Add(-5*step + step/3), Value: 20},
				{At: anchor.Add(-4*step + step/3), Value: 100},
				{At: anchor.Add(-3*step + step/3), Value: 40},
			}}
			render := func() [][]rune { return plotRaster(m.renderChart(spec, series, 69), mode) }
			first := render()
			if len(first) != m.chartsConfig.ChartHeight || len(first[0]) != columns {
				t.Fatalf("unexpected raster dimensions: %+v", first)
			}
			now = now.Add(step / 4)
			if !reflect.DeepEqual(first, render()) {
				t.Fatal("redrawing within an interval changed historical columns")
			}
			series.Points = append(series.Points, HistoryPoint{At: now, Value: 80})
			withLatest := render()
			for row := range first {
				if !reflect.DeepEqual(first[row][:columns-1], withLatest[row][:columns-1]) {
					t.Fatal("a new sample changed a closed column")
				}
			}
			now = now.Add(step)
			shifted := render()
			for row := range shifted {
				if !reflect.DeepEqual(shifted[row][:columns-1], withLatest[row][1:]) {
					t.Fatal("historical shape changed instead of shifting one time column")
				}
			}
		})
	}
}

func TestBrailleCombinesDotColumnsAndKeepsZerosDistinctFromGaps(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.ANSI256)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	m.chartsConfig.GraphMode, m.chartsConfig.ChartHeight = "braille", 3
	step := (5*time.Minute + 18) / 19
	now := fixedNow.Truncate(step).Add(step / 2)
	m.now = func() time.Time { return now }
	spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
	series := HistorySeries{Available: true, Points: []HistoryPoint{
		{At: now.Add(-step), Value: 100}, {At: now, Value: 100},
	}}
	full := m.renderChart(spec, series, 18)
	if strings.Count(ansi.Strip(full), "⣿") != 3 {
		t.Fatalf("two full-height dot columns were not combined: %q", full)
	}
	for row := range 3 {
		wantContains(t, full, chartRowStyle(row, 3).Render("⣿"))
	}
	series.Points = []HistoryPoint{{At: now, Value: 0}}
	raster := plotRaster(m.renderChart(spec, series, 18), "braille")
	for row, cells := range raster {
		for column, dots := range cells {
			want := rune(0)
			if row == 2 && column == 19 {
				want = 8
			}
			if dots != want {
				t.Fatalf("zero/gap at %d,%d = %d, want %d", row, column, dots, want)
			}
		}
	}
}

func TestSmallChartValuesDoNotRoundToFalseZeros(t *testing.T) {
	m := testModel(nil)
	spec := ChartSpec{Metric: "network.rxMiBps", Title: "RX", Unit: "MiB/s"}
	text := m.renderChart(spec, HistorySeries{Points: []HistoryPoint{{At: fixedNow, Value: 0.0003}}}, 50)
	wantContains(t, text, "last 0.0003MiB/s")
	wantContains(t, text, "min 0.0003")
	wantContains(t, text, "sample avg 0.0003")
	wantContains(t, text, "max 0.0003")
}
