// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

var sidecarBase = time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC)

// sampleSpec describes one synthetic sidecar sample: Ordinal is its
// position, Offset its capture time relative to sidecarBase, and pts is
// derived so MediaTimeSeconds == Offset in seconds.
type sampleSpec struct {
	Ordinal int
	Offset  time.Duration
}

func regularSpecs(n int, step time.Duration) []sampleSpec {
	specs := make([]sampleSpec, 0, n)
	for i := 0; i < n; i++ {
		specs = append(specs, sampleSpec{Ordinal: i, Offset: time.Duration(i) * step})
	}
	return specs
}

func sidecarDoc(recordingID, mediaPath string, specs []sampleSpec) map[string]any {
	samples := make([]map[string]any, 0, len(specs))
	for _, s := range specs {
		samples = append(samples, map[string]any{
			"ordinal":    s.Ordinal,
			"capture_ts": sidecarBase.Add(s.Offset).Format(time.RFC3339Nano),
			"pts":        s.Offset.Milliseconds(),
			"dts":        s.Offset.Milliseconds(),
			"duration":   500,
			"offset":     0,
			"length":     0,
			"keyframe":   s.Ordinal == 0,
		})
	}
	return map[string]any{
		"version":      SidecarVersion,
		"recording_id": recordingID,
		"media_path":   mediaPath,
		"timescale":    1000,
		"samples":      samples,
	}
}

func sidecarJSON(t *testing.T, doc map[string]any) string {
	t.Helper()
	data, err := json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func TestParseSidecarAcceptsCanonicalDocument(t *testing.T) {
	doc := sidecarDoc("rec-001", "recordings/rec-001/media.mp4", []sampleSpec{
		{Ordinal: 2, Offset: 1000 * time.Millisecond},
		{Ordinal: 0, Offset: 0},
		{Ordinal: 1, Offset: 500 * time.Millisecond},
	})
	sc, err := ParseSidecar(strings.NewReader(sidecarJSON(t, doc)))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if sc.RecordingID != "rec-001" || sc.Timescale != 1000 || len(sc.Samples) != 3 {
		t.Fatalf("unexpected sidecar %+v", sc)
	}
	for i, s := range sc.Samples {
		if s.Ordinal != i {
			t.Fatalf("samples not sorted by ordinal: %+v", sc.Samples)
		}
	}
	if sc.Samples[1].MediaTimeSeconds != 0.5 {
		t.Fatalf("media time = %v, want 0.5", sc.Samples[1].MediaTimeSeconds)
	}
	start, end := sc.Coverage()
	if !start.Equal(sidecarBase) || !end.Equal(sidecarBase.Add(time.Second)) {
		t.Fatalf("coverage = %v..%v", start, end)
	}
	if err := sc.VerifyIdentity("rec-001", "recordings/rec-001/media.mp4"); err != nil {
		t.Fatalf("identity: %v", err)
	}
}

func TestParseSidecarRejectsMalformedDocuments(t *testing.T) {
	good := func() map[string]any {
		return sidecarDoc("rec-001", "recordings/rec-001/media.mp4", regularSpecs(3, 500*time.Millisecond))
	}
	mutate := func(fn func(map[string]any)) string {
		doc := good()
		fn(doc)
		return sidecarJSON(t, doc)
	}
	sample := func(doc map[string]any, i int) map[string]any { return doc["samples"].([]map[string]any)[i] }

	cases := []struct {
		name string
		body string
		want error
	}{
		{"invalid json", `{"version": 1,`, ErrSidecarMalformed},
		{"trailing content", sidecarJSON(t, good()) + `{}`, ErrSidecarMalformed},
		{"unknown field", mutate(func(d map[string]any) { d["extra"] = true }), ErrSidecarMalformed},
		{"legacy record_id", mutate(func(d map[string]any) { delete(d, "recording_id"); d["record_id"] = "rec-001" }), ErrSidecarMalformed},
		{"wrong version", mutate(func(d map[string]any) { d["version"] = 2 }), ErrSidecarUnsupported},
		{"no samples", mutate(func(d map[string]any) { d["samples"] = []any{} }), ErrSidecarEmpty},
		{"zero timescale", mutate(func(d map[string]any) { d["timescale"] = 0 }), ErrSidecarInvalidTimescale},
		{"empty recording id", mutate(func(d map[string]any) { d["recording_id"] = " " }), ErrSidecarInvalidSample},
		{"empty media path", mutate(func(d map[string]any) { d["media_path"] = "" }), ErrSidecarInvalidSample},
		{"bad capture ts", mutate(func(d map[string]any) { sample(d, 1)["capture_ts"] = "2026-09-21 00:00:00" }), ErrSidecarInvalidSample},
		{"negative pts", mutate(func(d map[string]any) { sample(d, 1)["pts"] = -1 }), ErrSidecarInvalidSample},
		{"negative ordinal", mutate(func(d map[string]any) { sample(d, 1)["ordinal"] = -1 }), ErrSidecarInvalidSample},
		{"duplicate ordinal", mutate(func(d map[string]any) { sample(d, 1)["ordinal"] = 2 }), ErrSidecarDuplicateSample},
		{"capture clock regresses", mutate(func(d map[string]any) {
			sample(d, 2)["capture_ts"] = sidecarBase.Add(250 * time.Millisecond).Format(time.RFC3339Nano)
		}), ErrSidecarUnordered},
		{"media clock regresses", mutate(func(d map[string]any) { sample(d, 2)["pts"] = 100 }), ErrSidecarUnordered},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ParseSidecar(strings.NewReader(tc.body))
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
		})
	}
}

func TestVerifyIdentityRejectsMismatch(t *testing.T) {
	sc, err := ParseSidecar(strings.NewReader(sidecarJSON(t, sidecarDoc("rec-001", "recordings/rec-001/media.mp4", regularSpecs(2, time.Second)))))
	if err != nil {
		t.Fatal(err)
	}
	if err := sc.VerifyIdentity("rec-002", "recordings/rec-001/media.mp4"); !errors.Is(err, ErrSidecarMismatch) {
		t.Fatalf("wrong recording id accepted: %v", err)
	}
	if err := sc.VerifyIdentity("rec-001", "recordings/rec-002/media.mp4"); !errors.Is(err, ErrSidecarMismatch) {
		t.Fatalf("wrong media path accepted: %v", err)
	}
}

func TestFindByCaptureTimestamp(t *testing.T) {
	sc, err := ParseSidecar(strings.NewReader(sidecarJSON(t, sidecarDoc("rec-001", "recordings/rec-001/media.mp4", regularSpecs(5, time.Second)))))
	if err != nil {
		t.Fatal(err)
	}

	t.Run("exact hit", func(t *testing.T) {
		s, err := sc.FindByCaptureTimestamp(sidecarBase.Add(2*time.Second), MatchExact)
		if err != nil || s.Ordinal != 2 {
			t.Fatalf("got %+v, %v", s, err)
		}
	})
	t.Run("exact miss", func(t *testing.T) {
		_, err := sc.FindByCaptureTimestamp(sidecarBase.Add(2500*time.Millisecond), MatchExact)
		if !errors.Is(err, ErrNoExactMatch) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("nearest rounds to closest", func(t *testing.T) {
		s, err := sc.FindByCaptureTimestamp(sidecarBase.Add(2600*time.Millisecond), MatchNearest)
		if err != nil || s.Ordinal != 3 {
			t.Fatalf("got %+v, %v", s, err)
		}
	})
	t.Run("nearest tie prefers earlier", func(t *testing.T) {
		s, err := sc.FindByCaptureTimestamp(sidecarBase.Add(2500*time.Millisecond), MatchNearest)
		if err != nil || s.Ordinal != 2 {
			t.Fatalf("got %+v, %v", s, err)
		}
	})
	t.Run("zone-independent", func(t *testing.T) {
		local := sidecarBase.Add(3 * time.Second).In(time.FixedZone("IST", 19800))
		s, err := sc.FindByCaptureTimestamp(local, MatchExact)
		if err != nil || s.Ordinal != 3 {
			t.Fatalf("got %+v, %v", s, err)
		}
	})
	t.Run("before coverage", func(t *testing.T) {
		_, err := sc.FindByCaptureTimestamp(sidecarBase.Add(-time.Nanosecond), MatchNearest)
		if !errors.Is(err, ErrTimestampOutOfCoverage) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("after coverage", func(t *testing.T) {
		_, err := sc.FindByCaptureTimestamp(sidecarBase.Add(4*time.Second+time.Nanosecond), MatchNearest)
		if !errors.Is(err, ErrTimestampOutOfCoverage) {
			t.Fatalf("got %v", err)
		}
	})
}
