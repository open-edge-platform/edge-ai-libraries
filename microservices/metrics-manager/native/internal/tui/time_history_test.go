// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"math"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

func TestTimeBucketsUseActualTime(t *testing.T) {
	start := fixedNow.Add(-5 * time.Minute)
	points := []HistoryPoint{
		{At: start.Add(-time.Nanosecond), Value: 999},
		{At: start, Value: 10},
		{At: start.Add(time.Second), Value: 20},
		{At: start.Add(90 * time.Second), Value: 30},
		{At: fixedNow, Value: 0},
		{At: fixedNow.Add(time.Nanosecond), Value: 999},
	}
	got := timeBuckets(points, 10, start, fixedNow)
	for i, bucket := range got {
		want := map[int]float64{0: 20, 3: 30, 9: 0}
		value, present := want[i]
		if bucket.OK != present || (present && bucket.Value != value) {
			t.Errorf("bucket %d = %+v; want value=%v present=%v", i, bucket, value, present)
		}
	}
}

func TestTimeBucketsDoNotStretchStartupOrPointLimitedHistory(t *testing.T) {
	for _, window := range []time.Duration{10 * time.Second, 5 * time.Minute} {
		points := []HistoryPoint{{At: fixedNow.Add(-time.Millisecond), Value: 5}}
		buckets := timeBuckets(points, 20, fixedNow.Add(-window), fixedNow)
		for i, bucket := range buckets {
			if bucket.OK != (i == len(buckets)-1) {
				t.Errorf("startup placed a point in column %d, window %s: %+v", i, window, buckets)
			}
		}
	}
	config := DefaultChartsConfig()
	config.MaxPoints = 10
	h := NewHistory(config)
	for i := range 600 {
		h.Update(Dashboard{Memory: Memory{UsedPercent: reading(50)}},
			fixedNow.Add(time.Duration(i-599)*500*time.Millisecond))
	}
	series := h.Series("memory.usedPercent")[0]
	buckets := timeBuckets(series.Points, 10, fixedNow.Add(-5*time.Minute), fixedNow)
	for i, bucket := range buckets {
		if bucket.OK != (i == 9) {
			t.Errorf("point limit stretched the retained samples: %+v", buckets)
		}
	}
}

func TestTimeBucketsPreserveGapsAndShiftDuringOutage(t *testing.T) {
	points := []HistoryPoint{
		{At: fixedNow.Add(-225 * time.Second), Value: 10},
		{At: fixedNow.Add(-75 * time.Second), Value: 90},
	}
	buckets := timeBuckets(points, 5, fixedNow.Add(-5*time.Minute), fixedNow)
	if !buckets[1].OK || !buckets[3].OK || buckets[2].OK || buckets[4].OK {
		t.Fatalf("gap compressed or filled: %+v", buckets)
	}
	later := fixedNow.Add(75 * time.Second)
	buckets = timeBuckets(points, 5, later.Add(-5*time.Minute), later)
	if !buckets[0].OK || !buckets[2].OK || buckets[3].OK || buckets[4].OK {
		t.Fatalf("outage did not advance the axis: %+v", buckets)
	}
}

func TestTimeBucketsEmptyAndInvalidValues(t *testing.T) {
	start := fixedNow.Add(-time.Minute)
	for _, width := range []int{0, 1, 10} {
		got := timeBuckets([]HistoryPoint{
			{At: fixedNow, Value: math.NaN()}, {At: fixedNow, Value: math.Inf(1)},
		}, width, start, fixedNow)
		if len(got) != width {
			t.Fatalf("bucket count %d, want %d", len(got), width)
		}
		for _, point := range got {
			if point.OK {
				t.Fatal("invalid measurement turned into a point")
			}
		}
	}
	if got := timeBuckets(nil, 10, fixedNow, fixedNow); len(got) != 0 {
		t.Fatal("zero duration produced a plot")
	}
}

func TestHistoryOrdersAndReplacesTimestamps(t *testing.T) {
	h := NewHistory(DefaultChartsConfig())
	for _, point := range []HistoryPoint{
		{At: fixedNow.Add(2 * time.Second), Value: 2},
		{At: fixedNow, Value: 1},
		{At: fixedNow, Value: 3},
	} {
		h.Update(Dashboard{Memory: Memory{UsedPercent: reading(point.Value)}}, point.At)
	}
	points := h.Series("memory.usedPercent")[0].Points
	if len(points) != 2 || points[0].At != fixedNow || points[0].Value != 3 || points[1].Value != 2 {
		t.Fatalf("timestamps not ordered/deduplicated: %+v", points)
	}
}

func TestHistoryMissingDoesNotAppendZero(t *testing.T) {
	h := NewHistory(DefaultChartsConfig())
	h.Update(Dashboard{Memory: Memory{UsedPercent: reading(0)}}, fixedNow)
	for _, value := range []Reading{{}, reading(math.NaN()), reading(math.Inf(-1))} {
		h.Update(Dashboard{Memory: Memory{UsedPercent: value}}, fixedNow.Add(time.Second))
		series := h.Series("memory.usedPercent")[0]
		if series.Available || len(series.Points) != 1 || series.Points[0].Value != 0 {
			t.Fatalf("missing data corrupted a measured zero: %+v", series)
		}
	}
	h.Update(Dashboard{Memory: Memory{UsedPercent: reading(50)}}, fixedNow.Add(2*time.Second))
	if !h.Series("memory.usedPercent")[0].Available {
		t.Fatal("measurement did not recover")
	}
}

func TestHistoryPrunesBeforeAdmittingNewSeries(t *testing.T) {
	h := NewHistory(DefaultChartsConfig())
	dashboard := Dashboard{}
	for i := range maxHistorySeries + 1 {
		dashboard.GPUs = append(dashboard.GPUs, GPU{
			ID: fmt.Sprint(i), TempC: reading(60),
		})
	}
	h.Update(dashboard, fixedNow)
	if len(h.series) != maxHistorySeries || !h.limited {
		t.Fatalf("series bound not enforced/reported: %d, limited=%v", len(h.series), h.limited)
	}
	h.Update(Dashboard{Memory: Memory{UsedPercent: reading(50)}}, fixedNow.Add(6*time.Minute))
	if len(h.series) != 1 || h.limited || len(h.Series("memory.usedPercent")) != 1 {
		t.Fatal("expired series blocked a newly observed metric")
	}
}

func TestHistoryFiveMinuteWindowAcrossIntervals(t *testing.T) {
	for _, interval := range []time.Duration{100 * time.Millisecond, 500 * time.Millisecond, 2 * time.Second} {
		h := NewHistory(DefaultChartsConfig())
		for elapsed := time.Duration(0); elapsed <= 6*time.Minute; elapsed += interval {
			h.Update(Dashboard{Memory: Memory{UsedPercent: reading(42)}},
				fixedNow.Add(elapsed))
		}
		series := h.Series("memory.usedPercent")[0]
		if len(series.Points) > 600 {
			t.Fatalf("interval %s exceeded the point limit", interval)
		}
		cutoff := fixedNow.Add(time.Minute)
		for _, point := range series.Points {
			if point.At.Before(cutoff) {
				t.Errorf("interval %s retained an expired point: %v", interval, point.At)
			}
		}
		if last := series.Points[len(series.Points)-1]; last.At != fixedNow.Add(6*time.Minute) {
			t.Errorf("interval %s dropped the latest point", interval)
		}
	}
}

func TestClockPrunesWithoutSnapshotsAndRearms(t *testing.T) {
	m := testModel(nil)
	m.history.Update(Dashboard{Memory: Memory{UsedPercent: reading(42)}}, fixedNow)
	m.now = func() time.Time { return fixedNow.Add(6 * time.Minute) }
	next, cmd := update(t, m, clockMsg{})
	if len(next.history.series) != 0 {
		t.Fatal("history survived past its window without a new snapshot")
	}
	if cmd == nil {
		t.Fatal("clock did not re-arm")
	}
	next.activeTab = TrendsTab
	wantContains(t, next.View(), "No samples in the current window")
}

func TestFailedPollAgesHistoryWithoutReplayingLastDashboard(t *testing.T) {
	m := testModel(nil)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At: fixedNow, Samples: parseFixture(t, "mem_used_percent 42\n"),
	}))
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At: fixedNow.Add(time.Minute), Err: errors.New("offline"),
	}))
	series := m.history.Series("memory.usedPercent")[0]
	if series.Available || len(series.Points) != 1 || series.Points[0].At != fixedNow {
		t.Fatal("failed poll fabricated a sample")
	}
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At: fixedNow.Add(6 * time.Minute), Err: errors.New("offline"),
	}))
	if len(m.history.series) != 0 {
		t.Fatal("failed polls retained expired history")
	}
}

func TestChartStatsUseWindowSamplesNotBucketPeaks(t *testing.T) {
	m := testModel(nil)
	series := HistorySeries{Metric: "memory.usedPercent", Available: true, Points: []HistoryPoint{
		{At: fixedNow.Add(-6 * time.Minute), Value: 999},
		{At: fixedNow.Add(-time.Second), Value: 10},
		{At: fixedNow.Add(-500 * time.Millisecond), Value: 90},
		{At: fixedNow, Value: 20},
		{At: fixedNow.Add(time.Second), Value: 888},
	}}
	view := m.renderChart(fixedChart("memory.usedPercent", "Memory", "%", 0, 100), series, 100)
	for _, want := range []string{"last 20.0%", "min 10.0", "sample avg 40.0", "max 90.0"} {
		wantContains(t, view, want)
	}
	if strings.Contains(view, "999") || strings.Contains(view, "888") {
		t.Fatal("out-of-window values leaked into statistics")
	}
}

func TestRenderedChartUsesTimeColumns(t *testing.T) {
	m := testModel(nil)
	m.chartsConfig.GraphMode = "solid"
	spec := fixedChart("cpu.totalPercent", "CPU", "%", 0, 100)
	for _, tt := range []struct {
		name    string
		points  []HistoryPoint
		columns []int
	}{
		{
			name:    "startup zero is measured at the right edge",
			points:  []HistoryPoint{{At: fixedNow, Value: 0}},
			columns: []int{50},
		},
		{
			name: "outage stays blank",
			points: []HistoryPoint{
				{At: fixedNow.Add(-4 * time.Minute), Value: 30},
				{At: fixedNow.Add(-time.Minute), Value: 70},
			},
			columns: []int{10, 40},
		},
	} {
		t.Run(tt.name, func(t *testing.T) {
			// Fifty intervals plus the open bucket cover the full five minutes.
			view := m.renderChart(spec, HistorySeries{Points: tt.points, Available: true}, 59)
			occupied := make(map[int]bool)
			rows := 0
			for _, line := range strings.Split(view, "\n") {
				_, plot, ok := strings.Cut(line, " │")
				if !ok {
					continue
				}
				rows++
				if lipgloss.Width(plot) != 51 {
					t.Fatalf("plot width = %d, want 51", lipgloss.Width(plot))
				}
				for column, cell := range []rune(plot) {
					if strings.ContainsRune("▁▂▃▄▅▆▇█#", cell) {
						occupied[column] = true
					}
				}
			}
			if rows != m.chartsConfig.ChartHeight || len(occupied) != len(tt.columns) {
				t.Fatalf("unexpected plot: rows=%d occupied=%v\n%s", rows, occupied, view)
			}
			for _, column := range tt.columns {
				if !occupied[column] {
					t.Errorf("missing time column %d; occupied=%v", column, occupied)
				}
			}
		})
	}
}

func TestChartBoundsKeepConfiguredScaleWithoutSamples(t *testing.T) {
	minimum, maximum := chartBounds(fixedChart("cpu.totalPercent", "CPU", "%", 0, 100), nil)
	if minimum != 0 || maximum != 100 {
		t.Fatalf("empty chart scale = %g..%g", minimum, maximum)
	}
}

func TestTrendViewsFitAfterResizing(t *testing.T) {
	for _, width := range []int{1, 12, 20, 40, 80, 107, 210} {
		m := testModel(nil)
		m.history.Update(Dashboard{Memory: Memory{UsedPercent: reading(42)}}, fixedNow)
		m.activeTab = TrendsTab
		m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: 24})
		for _, line := range strings.Split(m.View(), "\n") {
			if lipgloss.Width(line) > width {
				t.Errorf("width %d overflow: %q", width, line)
			}
		}
		if len(strings.Split(m.View(), "\n")) > 24 {
			t.Errorf("width %d exceeded terminal height", width)
		}
	}
}

func TestMaxEngineUsageSkipsInvalidEngine(t *testing.T) {
	got := maxEngineUsage([]GPUEngine{
		{Name: "render", Usage: reading(math.NaN())},
		{Name: "compute", Usage: reading(75)},
		{Name: "copy", Usage: reading(math.Inf(1))},
	})
	if !got.OK || got.Value != 75 {
		t.Fatalf("invalid engine masked a valid reading: %+v", got)
	}
}
