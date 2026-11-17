// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"strings"
	"testing"
	"time"
)

func TestCounterRatesUseMeasurementTimeAndRetainCachedResults(t *testing.T) {
	var state counterRateState
	start := time.Unix(1000, 0)
	add := func(value float64, source, poll time.Time) timedReading {
		return state.update(reading(value), source.UnixMilli(), poll, 10*time.Second)
	}
	if got := add(100, start, start); got.OK || !strings.Contains(got.Reason, "second") {
		t.Fatalf("initial sample = %+v", got)
	}
	next := start.Add(2 * time.Second)
	got := add(400, next, next.Add(500*time.Millisecond))
	if !got.OK || got.Value != 150 || got.At != next {
		t.Fatalf("source-timed rate = %+v, want 150/s at %v", got, next)
	}
	if cached := add(400, next, next.Add(time.Second)); cached != got {
		t.Fatalf("cached sample changed rate: %+v != %+v", cached, got)
	}
	zero := add(400, next.Add(time.Second), next.Add(time.Second))
	if !zero.OK || zero.Value != 0 {
		t.Fatalf("genuine zero traffic = %+v", zero)
	}
	if reset := add(1, next.Add(2*time.Second), next.Add(2*time.Second)); reset.OK || !strings.Contains(reset.Reason, "reset") {
		t.Fatalf("counter reset = %+v", reset)
	}
	if resumed := add(11, next.Add(3*time.Second), next.Add(3*time.Second)); !resumed.OK || resumed.Value != 10 {
		t.Fatalf("after reset = %+v", resumed)
	}
}

func TestCounterRatesRejectInvalidSamplesAndRebaseline(t *testing.T) {
	now := time.Unix(1000, 0)
	for _, tc := range []struct {
		name   string
		value  Reading
		stamp  int64
		reason string
	}{
		{"absent", Reading{}, now.UnixMilli(), "missing or invalid"},
		{"negative", reading(-1), now.UnixMilli(), "missing or invalid"},
		{"nan", reading(math.NaN()), now.UnixMilli(), "missing or invalid"},
		{"infinite", reading(math.Inf(1)), now.UnixMilli(), "missing or invalid"},
		{"no timestamp", reading(2), 0, "timestamp missing"},
		{"future", reading(2), now.Add(time.Second).UnixMilli(), "future"},
		{"stale", reading(2), now.Add(-11 * time.Second).UnixMilli(), "stale"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			state := counterRateState{}
			state.update(reading(1), now.Add(-time.Second).UnixMilli(), now, 10*time.Second)
			got := state.update(tc.value, tc.stamp, now, 10*time.Second)
			if got.OK || !strings.Contains(got.Reason, tc.reason) {
				t.Fatalf("invalid sample = %+v", got)
			}
			if next := state.update(reading(10), now.UnixMilli(), now, 10*time.Second); next.OK {
				t.Fatalf("invalid interval was bridged: %+v", next)
			}
		})
	}
}

func TestCounterRatesDoNotRewindAndRejectConflictingTimestamps(t *testing.T) {
	now := time.Unix(1000, 0)
	var state counterRateState
	state.update(reading(100), now.UnixMilli(), now, 10*time.Second)
	old := state.update(reading(50), now.Add(-time.Second).UnixMilli(), now, 10*time.Second)
	if old.OK || !strings.Contains(old.Reason, "out-of-order") {
		t.Fatalf("out-of-order = %+v", old)
	}
	got := state.update(reading(200), now.Add(time.Second).UnixMilli(), now.Add(time.Second), 10*time.Second)
	if !got.OK || got.Value != 100 {
		t.Fatalf("out-of-order rewound baseline: %+v", got)
	}
	conflict := state.update(reading(201), now.Add(time.Second).UnixMilli(), now.Add(time.Second), 10*time.Second)
	if conflict.OK || !strings.Contains(conflict.Reason, "conflicting") {
		t.Fatalf("conflict = %+v", conflict)
	}
}
