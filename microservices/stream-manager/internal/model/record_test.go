// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import (
	"encoding/json"
	"testing"
	"time"
)

// TestRecordingJSONUsesCanonicalNames pins the wire contract. The rename to
// canonical names was deliberately breaking, so a regression that
// reintroduces a legacy key must fail here rather than quietly ship.
func TestRecordingJSONUsesCanonicalNames(t *testing.T) {
	endTS := time.Date(2026, time.September, 21, 0, 0, 10, 0, time.UTC)
	expiryTS := time.Date(2026, time.September, 28, 0, 0, 0, 0, time.UTC)

	recording := Recording{
		RecordingID:   "rec-001",
		SensorID:      "sensor-01",
		StreamID:      "stream-01",
		Origin:        RecordingOriginLive,
		State:         RecordingStateReady,
		StartTS:       time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC),
		EndTS:         &endTS,
		RecordingPath: "recordings/rec-001/media.mp4",
		Codec:         "h264",
		Container:     "mp4",
		SizeBytes:     1024,
		Metadata:      map[string]any{"fixture": "development"},
		CreationTS:    time.Date(2026, time.September, 21, 0, 0, 11, 0, time.UTC),
		ExpiryTS:      &expiryTS,
		ErrorDetails:  "none",
	}

	encoded := map[string]any{}
	marshalInto(t, recording, &encoded)

	assertKeysPresent(t, encoded,
		"recording_id", "sensor_id", "stream_id", "origin", "state",
		"start_ts", "end_ts", "recording_path", "codec", "container",
		"size_bytes", "metadata", "creation_ts", "expiry_ts", "error_details",
	)
	assertKeysAbsent(t, encoded, "record_id", "created_ns", "expires_ns", "error_detail")

	if got := encoded["recording_id"]; got != "rec-001" {
		t.Fatalf("unexpected recording_id: got %v", got)
	}
	// Wall-clock instants stay RFC3339 on the wire; the Unix-nanosecond
	// form is confined to the persistence layer.
	if got, ok := encoded["creation_ts"].(string); !ok || got != "2026-09-21T00:00:11Z" {
		t.Fatalf("unexpected creation_ts: got %v", encoded["creation_ts"])
	}
}

func TestRecordingOmitsEmptyOptionalFields(t *testing.T) {
	encoded := map[string]any{}
	marshalInto(t, Recording{RecordingID: "rec-001"}, &encoded)

	assertKeysAbsent(t, encoded, "stream_id", "end_ts", "codec", "container", "size_bytes", "expiry_ts", "error_details")
	assertKeysPresent(t, encoded, "recording_id", "sensor_id", "origin", "state", "start_ts", "recording_path", "metadata", "creation_ts")
}

func TestMediaResultJSONUsesCanonicalNames(t *testing.T) {
	endTS := time.Date(2026, time.September, 21, 0, 0, 8, 0, time.UTC)

	result := MediaResult{
		RecordingID:      "rec-001",
		SensorID:         "sensor-01",
		MediaType:        "clip",
		ContentType:      "video/mp4",
		RequestedStartTS: time.Date(2026, time.September, 21, 0, 0, 6, 0, time.UTC),
		RequestedEndTS:   &endTS,
		StartTS:          time.Date(2026, time.September, 21, 0, 0, 6, 0, time.UTC),
		EndTS:            &endTS,
		ExactMatch:       true,
		URL:              "http://localhost:8333/signed",
		ExpiryTS:         time.Date(2026, time.September, 21, 0, 5, 0, 0, time.UTC),
		DerivedKey:       "derived/rec-001/clips/x.mp4",
	}

	encoded := map[string]any{}
	marshalInto(t, result, &encoded)

	assertKeysPresent(t, encoded,
		"recording_id", "sensor_id", "media_type", "content_type",
		"requested_start_ts", "requested_end_ts", "start_ts", "end_ts",
		"exact_match", "url", "expiry_ts",
	)
	assertKeysAbsent(t, encoded, "record_id", "expires_at")

	// The derived key is an internal storage address; exposing it would
	// hand callers a path they must not be able to address directly.
	assertKeysAbsent(t, encoded, "derived_key", "DerivedKey")
}

func TestErrorResponseJSONUsesCanonicalNames(t *testing.T) {
	encoded := map[string]any{}
	marshalInto(t, ErrorResponse{Status: 404, ErrorCode: "recording_not_found", ErrorDetails: "recording not found"}, &encoded)

	assertKeysPresent(t, encoded, "status", "error_code", "error_details")
	assertKeysAbsent(t, encoded, "error_detail")
}

func TestFrameAndClipRequestsRoundTripWallClock(t *testing.T) {
	// Requests are built by hand from query parameters, so the only
	// contract worth pinning is that they carry wall-clock instants
	// unchanged rather than a numeric encoding.
	start := time.Date(2026, time.September, 21, 0, 0, 6, 123456789, time.UTC)
	end := start.Add(2 * time.Second)
	duration := 2.5

	frame := FrameRequest{RecordingID: "rec-001", StartTS: start, Format: "jpeg", Match: "exact"}
	if !frame.StartTS.Equal(start) {
		t.Fatalf("frame start timestamp changed: got %s", frame.StartTS)
	}

	clip := ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &end, ClipDuration: &duration, Format: "mp4"}
	if !clip.StartTS.Equal(start) || !clip.EndTS.Equal(end) || *clip.ClipDuration != duration {
		t.Fatalf("clip request fields changed: %+v", clip)
	}
}

func TestIsReadyOnlyAcceptsReadyState(t *testing.T) {
	for _, state := range []string{RecordingStateRecording, RecordingStateFinalizing, RecordingStateFailed, "", "READY"} {
		if (Recording{State: state}).IsReady() {
			t.Fatalf("state %q must not be considered ready", state)
		}
	}
	if !(Recording{State: RecordingStateReady}).IsReady() {
		t.Fatal("ready state must be considered ready")
	}
}

func TestIsLive(t *testing.T) {
	endTS := time.Now()
	cases := []struct {
		name string
		r    Recording
		want bool
	}{
		{"recording, no end_ts", Recording{State: RecordingStateRecording, EndTS: nil}, true},
		{"recording, with end_ts", Recording{State: RecordingStateRecording, EndTS: &endTS}, false},
		{"ready, with end_ts", Recording{State: RecordingStateReady, EndTS: &endTS}, false},
		{"ready, no end_ts", Recording{State: RecordingStateReady, EndTS: nil}, false},
		{"finalizing", Recording{State: RecordingStateFinalizing}, false},
		{"failed", Recording{State: RecordingStateFailed}, false},
	}
	for _, tc := range cases {
		if got := tc.r.IsLive(); got != tc.want {
			t.Errorf("%s: IsLive() = %v, want %v", tc.name, got, tc.want)
		}
	}
}

// TestIsServable pins the state/end_ts servability table: a live
// in-progress recording and a finalized recording are both servable; every
// other state, and every combination the producer contract forbids, is not.
func TestIsServable(t *testing.T) {
	endTS := time.Now()
	cases := []struct {
		name string
		r    Recording
		want bool
	}{
		{"recording, no end_ts (live)", Recording{State: RecordingStateRecording, EndTS: nil}, true},
		{"recording, with end_ts (invalid producer state)", Recording{State: RecordingStateRecording, EndTS: &endTS}, false},
		{"finalizing", Recording{State: RecordingStateFinalizing, EndTS: nil}, false},
		{"finalizing, with end_ts", Recording{State: RecordingStateFinalizing, EndTS: &endTS}, false},
		{"ready, with end_ts", Recording{State: RecordingStateReady, EndTS: &endTS}, true},
		{"ready, no end_ts (invalid producer state)", Recording{State: RecordingStateReady, EndTS: nil}, false},
		{"failed", Recording{State: RecordingStateFailed, EndTS: nil}, false},
		{"failed, with end_ts", Recording{State: RecordingStateFailed, EndTS: &endTS}, false},
	}
	for _, tc := range cases {
		if got := tc.r.IsServable(); got != tc.want {
			t.Errorf("%s: IsServable() = %v, want %v", tc.name, got, tc.want)
		}
	}
}

func marshalInto(t *testing.T, value any, target *map[string]any) {
	t.Helper()

	data, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
}

func assertKeysPresent(t *testing.T, encoded map[string]any, keys ...string) {
	t.Helper()
	for _, key := range keys {
		if _, ok := encoded[key]; !ok {
			t.Errorf("expected key %q to be present, got keys %v", key, sortedKeys(encoded))
		}
	}
}

func assertKeysAbsent(t *testing.T, encoded map[string]any, keys ...string) {
	t.Helper()
	for _, key := range keys {
		if _, ok := encoded[key]; ok {
			t.Errorf("expected key %q to be absent, got keys %v", key, sortedKeys(encoded))
		}
	}
}

func sortedKeys(encoded map[string]any) []string {
	keys := make([]string, 0, len(encoded))
	for key := range encoded {
		keys = append(keys, key)
	}
	return keys
}
