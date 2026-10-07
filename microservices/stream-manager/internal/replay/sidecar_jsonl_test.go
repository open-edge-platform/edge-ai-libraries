// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"errors"
	"strings"
	"testing"
	"time"
)

// jsonlDoc renders a version 2 sidecar as JSONL: a header line followed by
// one sample line per spec.
func jsonlDoc(t *testing.T, recordingID, mediaPath string, specs []sampleSpec) string {
	t.Helper()
	header := map[string]any{
		"version":      2,
		"recording_id": recordingID,
		"media_path":   mediaPath,
		"timescale":    1000,
	}
	lines := []string{sidecarJSON(t, header)}
	for _, s := range specs {
		sample := map[string]any{
			"ordinal":    s.Ordinal,
			"capture_ts": sidecarBase.Add(s.Offset).Format(time.RFC3339Nano),
			"pts":        s.Offset.Milliseconds(),
			"dts":        s.Offset.Milliseconds(),
			"duration":   500,
			"offset":     s.Ordinal * 1000,
			"length":     900,
			"keyframe":   s.Ordinal == 0,
		}
		lines = append(lines, sidecarJSON(t, sample))
	}
	return strings.Join(lines, "\n") + "\n"
}

func TestParseSidecarJSONLAcceptsCanonicalStream(t *testing.T) {
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", regularSpecs(3, 500*time.Millisecond))
	sc, err := ParseSidecarJSONL(strings.NewReader(doc))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if sc.Version != 2 || sc.RecordingID != "rec-001" || sc.MediaPath != "recordings/rec-001/media.ts" {
		t.Fatalf("unexpected sidecar %+v", sc)
	}
	if len(sc.Samples) != 3 {
		t.Fatalf("got %d samples, want 3", len(sc.Samples))
	}
}

func TestParseSidecarJSONLToleratesPartialFinalLine(t *testing.T) {
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", regularSpecs(3, 500*time.Millisecond))
	// Simulate an interrupted append: truncate the final line mid-object.
	truncated := doc[:len(doc)-15]

	sc, err := ParseSidecarJSONL(strings.NewReader(truncated))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(sc.Samples) != 2 {
		t.Fatalf("got %d samples, want 2 (partial final line dropped)", len(sc.Samples))
	}
}

func TestParseSidecarJSONLRejectsMalformedEarlierLine(t *testing.T) {
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", regularSpecs(3, 500*time.Millisecond))
	lines := strings.Split(strings.TrimRight(doc, "\n"), "\n")
	// Corrupt the first sample line (index 1, since 0 is the header),
	// which is not the final line, so this must fail hard rather than be
	// tolerated as a partial write.
	lines[1] = lines[1][:len(lines[1])-15]
	corrupted := strings.Join(lines, "\n") + "\n"

	if _, err := ParseSidecarJSONL(strings.NewReader(corrupted)); !errors.Is(err, ErrSidecarMalformed) {
		t.Fatalf("got %v, want ErrSidecarMalformed", err)
	}
}

func TestParseSidecarJSONLRejectsCompleteMalformedFinalLine(t *testing.T) {
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", regularSpecs(2, 500*time.Millisecond))
	if _, err := ParseSidecarJSONL(strings.NewReader(doc + "{invalid}\n")); !errors.Is(err, ErrSidecarMalformed) {
		t.Fatalf("got %v, want ErrSidecarMalformed", err)
	}
}

func TestParseSidecarJSONLRejectsOutOfOrderAppend(t *testing.T) {
	specs := []sampleSpec{
		{Ordinal: 1, Offset: time.Second},
		{Ordinal: 0, Offset: 0},
	}
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", specs)
	if _, err := ParseSidecarJSONL(strings.NewReader(doc)); !errors.Is(err, ErrSidecarUnordered) {
		t.Fatalf("got %v, want ErrSidecarUnordered", err)
	}
}

func TestParseSidecarJSONLRejectsWrongVersion(t *testing.T) {
	header := sidecarJSON(t, map[string]any{
		"version": 1, "recording_id": "rec-001", "media_path": "recordings/rec-001/media.ts", "timescale": 1000,
	})
	if _, err := ParseSidecarJSONL(strings.NewReader(header + "\n")); !errors.Is(err, ErrSidecarUnsupported) {
		t.Fatalf("got %v, want ErrSidecarUnsupported", err)
	}
}

func TestParseSidecarJSONLRejectsDuplicateOrdinal(t *testing.T) {
	specs := regularSpecs(2, 500*time.Millisecond)
	specs = append(specs, sampleSpec{Ordinal: 1, Offset: 900 * time.Millisecond})
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", specs)
	if _, err := ParseSidecarJSONL(strings.NewReader(doc)); !errors.Is(err, ErrSidecarDuplicateSample) {
		t.Fatalf("got %v, want ErrSidecarDuplicateSample", err)
	}
}

func TestParseSidecarJSONLRejectsUnorderedCaptureTS(t *testing.T) {
	specs := []sampleSpec{
		{Ordinal: 0, Offset: 500 * time.Millisecond},
		{Ordinal: 1, Offset: 0}, // capture_ts goes backwards at ordinal 1
	}
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", specs)
	if _, err := ParseSidecarJSONL(strings.NewReader(doc)); !errors.Is(err, ErrSidecarUnordered) {
		t.Fatalf("got %v, want ErrSidecarUnordered", err)
	}
}

func TestParseSidecarJSONLRejectsEmptyStream(t *testing.T) {
	if _, err := ParseSidecarJSONL(strings.NewReader("")); !errors.Is(err, ErrSidecarEmpty) {
		t.Fatalf("got %v, want ErrSidecarEmpty", err)
	}
}

func TestParseSidecarJSONLRejectsHeaderOnly(t *testing.T) {
	header := sidecarJSON(t, map[string]any{
		"version": 2, "recording_id": "rec-001", "media_path": "recordings/rec-001/media.ts", "timescale": 1000,
	})
	if _, err := ParseSidecarJSONL(strings.NewReader(header + "\n")); !errors.Is(err, ErrSidecarEmpty) {
		t.Fatalf("got %v, want ErrSidecarEmpty", err)
	}
}

func TestParseSidecarAutoPicksVersion1(t *testing.T) {
	doc := sidecarDoc("rec-001", "recordings/rec-001/media.mp4", regularSpecs(3, 500*time.Millisecond))
	sc, err := ParseSidecarAuto(strings.NewReader(sidecarJSON(t, doc)))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if sc.Version != 1 {
		t.Fatalf("got version %d, want 1", sc.Version)
	}
}

func TestParseSidecarAutoPicksVersion2(t *testing.T) {
	doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", regularSpecs(3, 500*time.Millisecond))
	sc, err := ParseSidecarAuto(strings.NewReader(doc))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if sc.Version != 2 {
		t.Fatalf("got version %d, want 2", sc.Version)
	}
}

func TestParseSidecarAutoRejectsUnknownVersion(t *testing.T) {
	if _, err := ParseSidecarAuto(strings.NewReader(`{"version":3}`)); !errors.Is(err, ErrSidecarUnsupported) {
		t.Fatalf("got %v, want ErrSidecarUnsupported", err)
	}
}

// TestParseSidecarJSONLSamplesMatchV1Semantics confirms a v2 stream carrying
// the same samples as a v1 document resolves to equivalent SidecarSample
// values, so the resolver's downstream logic is agnostic to which schema
// produced them.
func TestParseSidecarJSONLSamplesMatchV1Semantics(t *testing.T) {
	specs := regularSpecs(4, 250*time.Millisecond)

	v1doc := sidecarDoc("rec-001", "recordings/rec-001/media.mp4", specs)
	v1, err := ParseSidecar(strings.NewReader(sidecarJSON(t, v1doc)))
	if err != nil {
		t.Fatalf("parse v1: %v", err)
	}

	v2doc := jsonlDoc(t, "rec-001", "recordings/rec-001/media.ts", specs)
	v2, err := ParseSidecarJSONL(strings.NewReader(v2doc))
	if err != nil {
		t.Fatalf("parse v2: %v", err)
	}

	if len(v1.Samples) != len(v2.Samples) {
		t.Fatalf("sample count mismatch: v1=%d v2=%d", len(v1.Samples), len(v2.Samples))
	}
	for i := range v1.Samples {
		a, b := v1.Samples[i], v2.Samples[i]
		if a.Ordinal != b.Ordinal || !a.CaptureTS.Equal(b.CaptureTS) || a.PTS != b.PTS || a.MediaTimeSeconds != b.MediaTimeSeconds {
			t.Fatalf("sample %d differs: v1=%+v v2=%+v", i, a, b)
		}
	}
}
