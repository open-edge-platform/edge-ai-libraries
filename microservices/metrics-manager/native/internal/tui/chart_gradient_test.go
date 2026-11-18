// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
	"github.com/muesli/termenv"
)

func TestBlueGradientUsesRowShadesInEveryChartModeAndTheme(t *testing.T) {
	profile, dark := lipgloss.ColorProfile(), lipgloss.HasDarkBackground()
	t.Cleanup(func() {
		lipgloss.SetColorProfile(profile)
		lipgloss.SetHasDarkBackground(dark)
	})
	for _, dark := range []bool{false, true} {
		lipgloss.SetHasDarkBackground(dark)
		for _, profile := range []termenv.Profile{termenv.TrueColor, termenv.ANSI256, termenv.ANSI} {
			lipgloss.SetColorProfile(profile)
			colors := []string{"#2d6eb4", "#1e518c", "#0f3464"}
			if dark {
				colors = []string{"#69a9df", "#4482bb", "#1e5a96"}
			}
			if profile == termenv.ANSI {
				colors = []string{"12", "12", "4"}
			}
			for _, mode := range []string{"solid", "unicode", "ascii", "braille"} {
				m := testModel(nil)
				m.chartsConfig.GraphMode, m.chartsConfig.ChartHeight = mode, 3
				series := HistorySeries{Available: true}
				for second := -300; second <= 0; second++ {
					series.Points = append(series.Points, HistoryPoint{At: fixedNow.Add(time.Duration(second) * time.Second), Value: 100})
				}
				text := m.renderChart(fixedChart("cpu.totalPercent", "CPU", "%", 0, 100), series, 18)
				axis, cell := " │", "█"
				switch mode {
				case "solid":
					cell = " "
				case "braille":
					cell = "⣿"
				case "ascii":
					axis, cell = " |", "#"
				}
				row := 0
				for _, line := range strings.Split(text, "\n") {
					label, _, ok := strings.Cut(ansi.Strip(line), axis)
					if !ok || strings.Trim(label, " 0123456789.-") != "" {
						continue
					}
					if row >= len(colors) {
						t.Fatal("unexpected additional plot row")
					}
					color := lipgloss.Color(colors[row])
					style := lipgloss.NewStyle().Foreground(color)
					if mode == "solid" {
						style = lipgloss.NewStyle().Background(color)
					}
					if !strings.Contains(line, style.Render(strings.Repeat(cell, 10))) {
						t.Fatalf("mode=%s profile=%v dark=%v row=%d does not use shade %s: %q",
							mode, profile, dark, row, colors[row], line)
					}
					if lipgloss.Width(line) != 18 {
						t.Fatal("gradient changed the chart width")
					}
					row++
				}
				if row != 3 {
					t.Fatalf("%s produced %d plot rows", mode, row)
				}
			}
		}
	}
}

func TestBlueGradientBrightensMonotonicallyAcrossSupportedHeights(t *testing.T) {
	profile, dark := lipgloss.ColorProfile(), lipgloss.HasDarkBackground()
	lipgloss.SetColorProfile(termenv.TrueColor)
	t.Cleanup(func() {
		lipgloss.SetColorProfile(profile)
		lipgloss.SetHasDarkBackground(dark)
	})
	color := regexp.MustCompile(`38;2;(\d+);(\d+);(\d+)`)
	for _, dark := range []bool{false, true} {
		lipgloss.SetHasDarkBackground(dark)
		for height := 3; height <= 20; height++ {
			previous := [3]int{}
			for row := height - 1; row >= 0; row-- {
				match := color.FindStringSubmatch(chartRowStyle(row, height).Render("x"))
				if len(match) != 4 {
					t.Fatal("true-color gradient did not render an RGB shade")
				}
				var rgb [3]int
				for channel := range rgb {
					var err error
					rgb[channel], err = strconv.Atoi(match[channel+1])
					if err != nil {
						t.Fatal(err)
					}
					if rgb[channel] < previous[channel] {
						t.Fatalf("height=%d row=%d did not brighten: %v after %v", height, row, rgb, previous)
					}
				}
				if rgb == previous {
					t.Fatalf("height=%d row=%d repeated the previous shade %v", height, row, rgb)
				}
				if rgb[2] <= rgb[1] || rgb[1] <= rgb[0] {
					t.Fatalf("shade left the blue palette: %v", rgb)
				}
				previous = rgb
			}
		}
	}
}

func TestLowRangeBrailleHasSubtleBrightnessContrast(t *testing.T) {
	profile, dark := lipgloss.ColorProfile(), lipgloss.HasDarkBackground()
	t.Cleanup(func() {
		lipgloss.SetColorProfile(profile)
		lipgloss.SetHasDarkBackground(dark)
	})
	lipgloss.SetHasDarkBackground(true)
	for _, profile := range []termenv.Profile{termenv.TrueColor, termenv.ANSI256} {
		lipgloss.SetColorProfile(profile)
		m := testModel(nil)
		m.chartsConfig.GraphMode, m.chartsConfig.ChartHeight = "braille", 8
		series := HistorySeries{Available: true, Points: []HistoryPoint{
			{At: fixedNow.Add(-10 * time.Second), Value: 664},
			{At: fixedNow, Value: 2111},
		}}
		text := m.renderChart(fixedChart("cpu.frequencyMHz", "CPU", "MHz", 0, 5000), series, 40)
		var filled []string
		row, first := 0, -1
		for _, line := range strings.Split(text, "\n") {
			_, plot, ok := strings.Cut(ansi.Strip(line), " │")
			if !ok {
				continue
			}
			if strings.TrimSpace(plot) != "" {
				if first < 0 {
					first = row
				}
				filled = append(filled, line)
			}
			row++
		}
		if row != 8 || first != 4 || len(filled) != 4 {
			t.Fatalf("profile %v: gradient changed the plot geometry", profile)
		}
		bottom := plotLuminance(t, filled[len(filled)-1])
		top := plotLuminance(t, filled[0])
		if contrast := top - bottom; contrast < 0.02 || contrast > 0.16 {
			t.Fatalf("profile %v: lower-range luminance difference %.3f is outside 0.02-0.16", profile, contrast)
		}
		shades := make(map[string]bool)
		for row := 6; row < 10; row++ {
			shades[chartRowStyle(row, 10).Render("x")] = true
		}
		if len(shades) < 2 {
			t.Fatalf("profile %v: lower rows collapsed into only %d shades", profile, len(shades))
		}
	}
}

func TestDarkGradientKeepsModerateContrastAcrossProfiles(t *testing.T) {
	profile, dark := lipgloss.ColorProfile(), lipgloss.HasDarkBackground()
	t.Cleanup(func() {
		lipgloss.SetColorProfile(profile)
		lipgloss.SetHasDarkBackground(dark)
	})
	lipgloss.SetHasDarkBackground(true)
	for _, profile := range []termenv.Profile{termenv.TrueColor, termenv.ANSI256} {
		lipgloss.SetColorProfile(profile)
		bottom := plotLuminance(t, chartRowStyle(7, 8).Render("x"))
		top := plotLuminance(t, chartRowStyle(0, 8).Render("x"))
		if bottom < 0.025 || top-bottom < 0.15 || top-bottom > 0.40 {
			t.Fatalf("profile %v: expected a visible baseline and moderate contrast, got %.3f to %.3f", profile, bottom, top)
		}
		want := lipgloss.NewStyle().Foreground(lipgloss.Color("#69a9df")).Render("x")
		if chartRowStyle(0, 8).Render("x") != want {
			t.Fatal("gradient lost the muted blue peak")
		}
	}
}

func TestGradientColorResolutionMatchesTerminalProfile(t *testing.T) {
	profile, dark := lipgloss.ColorProfile(), lipgloss.HasDarkBackground()
	t.Cleanup(func() {
		lipgloss.SetColorProfile(profile)
		lipgloss.SetHasDarkBackground(dark)
	})
	lipgloss.SetHasDarkBackground(true)
	for _, tc := range []struct {
		profile termenv.Profile
		minimum int
		maximum int
	}{
		{termenv.TrueColor, 20, 20},
		{termenv.ANSI256, 3, 8},
		{termenv.ANSI, 2, 2},
	} {
		lipgloss.SetColorProfile(tc.profile)
		shades := make(map[string]bool)
		for row := 0; row < 20; row++ {
			shades[chartRowStyle(row, 20).Render("x")] = true
		}
		if len(shades) < tc.minimum || len(shades) > tc.maximum {
			t.Fatalf("profile %v: got %d shades, want %d-%d", tc.profile, len(shades), tc.minimum, tc.maximum)
		}
	}
	lipgloss.SetColorProfile(termenv.TrueColor)
	want := lipgloss.NewStyle().Foreground(lipgloss.Color("#4482bb")).Render("x")
	if chartRowStyle(8, 17).Render("x") != want {
		t.Fatal("gradient midpoint is not a linear blue blend")
	}
}

func plotLuminance(t *testing.T, line string) float64 {
	t.Helper()
	colors := regexp.MustCompile(`38;(2;(\d+);(\d+);(\d+)|5;(\d+))`).FindAllStringSubmatch(line, -1)
	if len(colors) == 0 {
		t.Fatal("plot has no RGB or 256-color foreground")
	}
	last := colors[len(colors)-1]
	number := func(s string) int {
		value, err := strconv.Atoi(s)
		if err != nil {
			t.Fatal(err)
		}
		return value
	}
	var color termenv.Color
	if last[5] != "" {
		color = termenv.ANSI256Color(number(last[5]))
	} else {
		color = termenv.RGBColor(fmt.Sprintf("#%02x%02x%02x", number(last[2]), number(last[3]), number(last[4])))
	}
	rgb := termenv.ConvertToRGB(color)
	linear := func(v float64) float64 {
		if v <= 0.04045 {
			return v / 12.92
		}
		return math.Pow((v+0.055)/1.055, 2.4)
	}
	return 0.2126*linear(rgb.R) + 0.7152*linear(rgb.G) + 0.0722*linear(rgb.B)
}

func TestGradientRetainsMonochromeFallbackAndBlankGaps(t *testing.T) {
	profile := lipgloss.ColorProfile()
	lipgloss.SetColorProfile(termenv.Ascii)
	t.Cleanup(func() { lipgloss.SetColorProfile(profile) })
	m := testModel(nil)
	m.chartsConfig.GraphMode = "solid"
	m.chartsConfig.ChartHeight = 3
	spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
	series := HistorySeries{Available: true, Points: []HistoryPoint{{At: fixedNow, Value: 100}}}
	text := m.renderChart(spec, series, 18)
	rows := plotRaster(text, "solid")
	if len(rows) != 3 {
		t.Fatal("missing monochrome plot")
	}
	for _, row := range rows {
		if string(row) != strings.Repeat(" ", 9)+"#" {
			t.Fatalf("gradient hid data or filled gaps: %q", string(row))
		}
	}
}
