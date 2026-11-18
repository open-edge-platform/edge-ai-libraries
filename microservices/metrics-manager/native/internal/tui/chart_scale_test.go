// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"testing"
	"time"
)

func TestChartScaleExpandsImmediatelyAndDelaysSignificantShrink(t *testing.T) {
	var scale chartScale
	set := func(seconds int, value float64) {
		scale.update("network.rxMiBps", []HistoryPoint{{Value: value}}, fixedNow.Add(time.Duration(seconds)*time.Second))
	}
	set(0, 1.1)
	for second, value := range []float64{1.2, 1.9, 1.01} {
		set(second+1, value)
		if scale.minimum != 0 || scale.maximum != 2 {
			t.Fatalf("small changes moved the scale: %+v", scale)
		}
	}
	set(4, 2.1)
	if scale.maximum != 5 {
		t.Fatal("new peak did not expand the scale immediately")
	}
	set(5, 0.9)
	set(34, 0.9)
	if scale.maximum != 5 {
		t.Fatal("scale shrank before 30 seconds")
	}
	set(35, 0.9)
	if scale.maximum != 1 {
		t.Fatal("sustained lower range did not shrink the scale")
	}
	set(36, 7)
	set(37, 1)
	set(66, 6)
	set(67, 1)
	set(96, 1)
	if scale.maximum != 10 {
		t.Fatal("renewed load failed to interrupt shrink confirmation")
	}
	set(97, 1)
	if scale.maximum != 1 {
		t.Fatal("a new continuous low-load period did not shrink")
	}
}

func TestHistoryRetainsScaleAfterPeakExpires(t *testing.T) {
	config := DefaultChartsConfig()
	config.HistoryDuration = "10s"
	h := NewHistory(config)
	h.Update(Dashboard{Memory: Memory{UsedPercent: reading(99)}}, fixedNow)
	for second := 1; second <= 41; second++ {
		h.Update(Dashboard{Memory: Memory{UsedPercent: reading(4)}}, fixedNow.Add(time.Duration(second)*time.Second))
		series := h.Series("memory.usedPercent")[0]
		want := 100.0
		if second == 41 {
			want = 5
		}
		if series.scale.maximum != want {
			t.Fatalf("at %ds maximum=%g, want %g", second, series.scale.maximum, want)
		}
	}
}

func TestChartScaleKeepsExplicitBoundsAndSupportsSignedValues(t *testing.T) {
	var scale chartScale
	points := []HistoryPoint{{Value: -3}, {Value: 8}}
	scale.update("cpu.temperatureC", points, fixedNow)
	if scale.minimum != -5 || scale.maximum != 10 {
		t.Fatalf("signed automatic scale = %+v", scale)
	}
	spec := fixedChart("cpu.temperatureC", "Temperature", "C", -20, 110)
	minimum, maximum := scale.bounds(spec, points)
	if minimum != -20 || maximum != 110 {
		t.Fatal("automatic scale overrode explicit bounds")
	}
	spec.Min = nil
	minimum, maximum = scale.bounds(spec, points)
	if minimum != -5 || maximum != 110 {
		t.Fatal("one-sided configured range was not preserved")
	}
	var zero chartScale
	zero.update("gpu.frequencyMHz", []HistoryPoint{{Value: 0}}, fixedNow)
	if zero.minimum != 0 || zero.maximum != 1 {
		t.Fatal("zero-only frequency lost its 0..1 baseline")
	}
}

func TestNiceChartBoundsStayFiniteAndOutward(t *testing.T) {
	for _, value := range []float64{math.SmallestNonzeroFloat64, 0.00001, 0.003, 1, 1.01, 9, 99, math.MaxFloat64} {
		for _, signed := range []float64{value, -value} {
			lower, upper := niceChartBound(signed, false), niceChartBound(signed, true)
			if lower > signed || upper < signed || math.IsInf(lower, 0) || math.IsInf(upper, 0) {
				t.Fatalf("%g is not within finite outward bounds %g..%g", signed, lower, upper)
			}
		}
	}
}
