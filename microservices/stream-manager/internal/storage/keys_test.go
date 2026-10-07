// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"errors"
	"testing"
	"time"
)

func TestValidateIdentifierRejectsUnsafeValues(t *testing.T) {
	bad := []string{"", "  ", " rec-001", "rec/001", `rec\001`, ".", "..", "rec\x00"}
	for _, id := range bad {
		if err := ValidateIdentifier("recording_id", id); !errors.Is(err, ErrInvalidIdentifier) {
			t.Errorf("ValidateIdentifier(%q) = %v, want ErrInvalidIdentifier", id, err)
		}
	}
	if err := ValidateIdentifier("recording_id", "rec-001"); err != nil {
		t.Fatalf("ValidateIdentifier(rec-001) = %v", err)
	}
}

func TestValidateObjectKeyRejectsEscapes(t *testing.T) {
	bad := []string{
		"",
		"/recordings/rec-001/media.mp4",
		"s3://bucket/recordings/rec-001/media.mp4",
		"s3:bucket/recordings/rec-001/media.mp4",
		"http://host/recordings/rec-001/media.mp4",
		"recordings/../derived/rec-001/frames/x.jpeg",
		"recordings//rec-001/media.mp4",
		"recordings/rec-001/media.mp4/",
		`recordings\rec-001\media.mp4`,
		"other/rec-001/media.mp4",
		"recordings",
	}
	for _, key := range bad {
		if err := ValidateObjectKey(key); !errors.Is(err, ErrInvalidObjectKey) {
			t.Errorf("ValidateObjectKey(%q) = %v, want ErrInvalidObjectKey", key, err)
		}
	}
	good := []string{
		"recordings/rec-001/media.mp4",
		"recordings/rec-001/sidecar.json",
		"derived/rec-001/frames/20260921T000006-123456789.jpeg",
	}
	for _, key := range good {
		if err := ValidateObjectKey(key); err != nil {
			t.Errorf("ValidateObjectKey(%q) = %v, want nil", key, err)
		}
	}
}

func TestRecordingKeysFollowLayout(t *testing.T) {
	media, err := RecordingMediaKey("rec-001")
	if err != nil || media != "recordings/rec-001/media.mp4" {
		t.Fatalf("RecordingMediaKey = %q, %v", media, err)
	}
	sidecar, err := RecordingSidecarKey("rec-001")
	if err != nil || sidecar != "recordings/rec-001/sidecar.json" {
		t.Fatalf("RecordingSidecarKey = %q, %v", sidecar, err)
	}
	prefixes, err := RecordingObjectPrefixes("rec-001")
	if err != nil {
		t.Fatal(err)
	}
	if len(prefixes) != 2 || prefixes[0] != "recordings/rec-001/" || prefixes[1] != "derived/rec-001/" {
		t.Fatalf("RecordingObjectPrefixes = %v", prefixes)
	}
	if _, err := RecordingMediaKey("../x"); !errors.Is(err, ErrInvalidIdentifier) {
		t.Fatalf("traversal id accepted: %v", err)
	}
}

func TestLiveRecordingKeysFollowLayout(t *testing.T) {
	media, err := RecordingLiveMediaKey("rec-live-1")
	if err != nil || media != "recordings/rec-live-1/media.ts" {
		t.Fatalf("RecordingLiveMediaKey = %q, %v", media, err)
	}
	sidecar, err := RecordingLiveSidecarKey("rec-live-1")
	if err != nil || sidecar != "recordings/rec-live-1/sidecar.jsonl" {
		t.Fatalf("RecordingLiveSidecarKey = %q, %v", sidecar, err)
	}
	resolved, err := RecordingSidecarKeyForPath("rec-live-1", media)
	if err != nil || resolved != sidecar {
		t.Fatalf("RecordingSidecarKeyForPath = %q, %v", resolved, err)
	}

	for _, recordingPath := range []string{
		"recordings/rec-other/media.ts",
		"recordings/rec-live-1/other.ts",
		"recordings/rec-live-1/../rec-other/media.ts",
	} {
		if _, err := RecordingSidecarKeyForPath("rec-live-1", recordingPath); !errors.Is(err, ErrInvalidObjectKey) {
			t.Errorf("RecordingSidecarKeyForPath(%q) error = %v, want ErrInvalidObjectKey", recordingPath, err)
		}
	}
}

func TestDerivedKeysAreDeterministicAndDistinct(t *testing.T) {
	ts := time.Date(2026, time.September, 21, 0, 0, 6, 123456789, time.UTC)
	local := ts.In(time.FixedZone("IST", 5*3600+1800))

	a, err := DerivedFrameKey("rec-001", ts, "jpeg")
	if err != nil {
		t.Fatal(err)
	}
	b, err := DerivedFrameKey("rec-001", local, "jpeg")
	if err != nil {
		t.Fatal(err)
	}
	if a != b {
		t.Fatalf("frame key depends on zone: %q vs %q", a, b)
	}
	if a != "derived/rec-001/frames/20260921T000006-123456789.jpeg" {
		t.Fatalf("unexpected frame key %q", a)
	}

	png, _ := DerivedFrameKey("rec-001", ts, "png")
	if png == a {
		t.Fatalf("format not encoded in key")
	}

	clip, err := DerivedClipKey("rec-001", ts, ts.Add(1500*time.Millisecond), "mp4")
	if err != nil {
		t.Fatal(err)
	}
	if clip != "derived/rec-001/clips/20260921T000006-123456789_20260921T000007-623456789.mp4" {
		t.Fatalf("unexpected clip key %q", clip)
	}

	if _, err := DerivedFrameKey("rec-001", ts, "jp/eg"); !errors.Is(err, ErrInvalidIdentifier) {
		t.Fatalf("separator in format accepted: %v", err)
	}
	if err := ValidateObjectKey(clip); err != nil {
		t.Fatalf("derived key fails its own validation: %v", err)
	}
}
