// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"testing"
	"time"
)

func TestBestEffortClockAnchorsAndUnwrapsPTS(t *testing.T) {
	clock := bestEffortClock{}
	anchor := time.Date(2026, time.October, 4, 12, 0, 0, 0, time.UTC)
	firstPTS := int64(1<<33) - 90000
	if got := clock.captureTS(firstPTS, anchor); !got.Equal(anchor) {
		t.Fatalf("first timestamp = %v, want anchor %v", got, anchor)
	}
	wrapped := clock.captureTS(0, anchor.Add(time.Hour))
	if want := anchor.Add(time.Second); !wrapped.Equal(want) {
		t.Fatalf("wrapped timestamp = %v, want %v", wrapped, want)
	}
	if got := clock.captureTS(45000, anchor.Add(2*time.Hour)); !got.Equal(anchor.Add(1500 * time.Millisecond)) {
		t.Fatalf("post-wrap timestamp = %v, want %v", got, anchor.Add(1500*time.Millisecond))
	}
}
