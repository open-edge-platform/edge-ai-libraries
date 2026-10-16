// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package record

import (
	"math"
	"testing"
	"time"
)

func TestSecondsPreservesFractionsAndRejectsOverflow(t *testing.T) {
	for _, tc := range []struct {
		seconds float64
		want    time.Duration
	}{
		{0, 0}, {0.125, 125 * time.Millisecond}, {1.000000001, time.Second + time.Nanosecond},
	} {
		got, err := Seconds(tc.seconds)
		if err != nil || got != tc.want {
			t.Fatalf("seconds %v: %v %v", tc.seconds, got, err)
		}
	}
	for _, seconds := range []float64{-1, math.Inf(1), math.NaN(), 1e300, 1e-12} {
		if _, err := Seconds(seconds); err == nil {
			t.Fatalf("unrepresentable duration %v accepted", seconds)
		}
	}
}
