// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"
)

func TestNonnegativeChartsUseZeroBaselineWithOldOrDefaultConfiguration(t *testing.T) {
	for metric := range supportedCharts {
		isTemperature := strings.HasSuffix(metric, ".temperatureC")
		if nonnegativeChart(metric) == isTemperature {
			t.Fatalf("incorrect metric domain for %s", metric)
		}
		if isTemperature {
			continue
		}
		spec := ChartSpec{Metric: metric, Title: metric}
		for _, points := range [][]HistoryPoint{nil, {{Value: 0}}, {{Value: 0}, {Value: 0}}, {{Value: 500}}, {{Value: 2}, {Value: 700}}} {
			minimum, maximum := chartBounds(spec, points)
			if minimum != 0 || maximum <= minimum {
				t.Fatalf("%s bounds=%g..%g for %+v", metric, minimum, maximum, points)
			}
			for _, point := range points {
				if point.Value > maximum {
					t.Fatalf("%s auto scale cut off %g at %g", metric, point.Value, maximum)
				}
			}
		}
	}
}

func TestChartDomainValidationPreservesTemperatureAndExplicitZoom(t *testing.T) {
	for metric := range supportedCharts {
		spec := ChartSpec{Metric: metric, Title: metric, Min: floatPointer(-1)}
		err := validateChartSpecs("charts", []ChartSpec{spec})
		if nonnegativeChart(metric) != (err != nil) {
			t.Fatalf("%s negative minimum validation: %v", metric, err)
		}
		if !nonnegativeChart(metric) {
			minimum, maximum := chartBounds(ChartSpec{Metric: metric}, []HistoryPoint{{Value: -5}})
			if minimum >= -5 || maximum <= -5 {
				t.Fatalf("negative temperature cannot be plotted: %g..%g", minimum, maximum)
			}
			continue
		}
		spec.Min, spec.Max = nil, floatPointer(0)
		if validateChartSpecs("charts", []ChartSpec{spec}) == nil {
			t.Fatalf("%s accepted an unusable maximum of zero", metric)
		}
		spec.Min, spec.Max = floatPointer(100), floatPointer(200)
		minimum, maximum := chartBounds(spec, []HistoryPoint{{Value: 150}})
		if minimum != 100 || maximum != 200 {
			t.Fatalf("%s lost explicit zoom range", metric)
		}
	}
}

func TestZeroFrequencyOnlyFillsTheBaseline(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	m.chartsConfig.GraphMode = "solid"
	m.chartsConfig.ChartHeight = 6
	spec := ChartSpec{Metric: "gpu.frequencyMHz", Title: "Frequency", Unit: "MHz"}
	text := ansi.Strip(m.renderChart(spec, HistorySeries{Available: true, Points: []HistoryPoint{{At: fixedNow, Value: 0}}}, 30))
	if strings.Contains(text, "-1.0") {
		t.Fatal("zero frequency generated a negative axis")
	}
	minimum, maximum := chartBounds(spec, []HistoryPoint{{Value: 0}})
	if minimum != 0 || maximum != 1 {
		t.Fatalf("zero-only fallback = %g..%g, want 0..1", minimum, maximum)
	}
	// Monochrome solid plots use #, so occupied rows can be checked exactly.
	rows, occupied := 0, 0
	for _, line := range strings.Split(text, "\n") {
		if label, plot, ok := strings.Cut(line, " │"); ok && len(label) == 6 {
			if strings.TrimSpace(plot) != "" {
				occupied++
				if rows != 5 {
					t.Fatalf("zero filled a row above the baseline: %q", line)
				}
			}
			rows++
		}
	}
	if rows != 6 || occupied != 1 {
		t.Fatalf("zero plot rows=%d occupied=%d", rows, occupied)
	}
}
