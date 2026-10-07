// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func seededResolver(t *testing.T, specs []sampleSpec) (*JSONSidecarResolver, *fakeMediaStore) {
	t.Helper()
	media := newFakeMediaStore()
	media.Set("recordings/rec-001/sidecar.json", []byte(sidecarJSON(t, sidecarDoc("rec-001", "recordings/rec-001/media.mp4", specs))))
	return NewJSONSidecarResolver(media), media
}

func TestResolveFrameUsesSidecarAndVerifiesIdentity(t *testing.T) {
	ctx := context.Background()
	resolver, media := seededResolver(t, regularSpecs(5, time.Second))
	rec := readyRecording("rec-001")

	sample, err := resolver.ResolveFrame(ctx, rec, sidecarBase.Add(2*time.Second), MatchExact)
	if err != nil || sample.Ordinal != 2 || sample.MediaTimeSeconds != 2 {
		t.Fatalf("got %+v, %v", sample, err)
	}

	// Metadata pointing at different media than the sidecar names must be
	// rejected rather than resolved against the wrong footage.
	rec.RecordingPath = "recordings/rec-001/other.mp4"
	if _, err := resolver.ResolveFrame(ctx, rec, sidecarBase, MatchNearest); !errors.Is(err, ErrSidecarMismatch) {
		t.Fatalf("mismatched media path accepted: %v", err)
	}

	// A sidecar stored under one recording that names another is likewise
	// rejected.
	media.Set("recordings/rec-002/sidecar.json", []byte(sidecarJSON(t, sidecarDoc("rec-001", "recordings/rec-002/media.mp4", regularSpecs(2, time.Second)))))
	if _, err := resolver.ResolveFrame(ctx, readyRecording("rec-002"), sidecarBase, MatchNearest); !errors.Is(err, ErrSidecarMismatch) {
		t.Fatalf("mismatched recording id accepted: %v", err)
	}
}

func TestResolveLiveFrameUsesRecordingRelativePTS(t *testing.T) {
	rec := liveRecording("rec-live-pts", 1024)
	media := newFakeMediaStore()
	media.Set("recordings/rec-live-pts/sidecar.jsonl", []byte(jsonlDoc(t, rec.RecordingID, rec.RecordingPath, []sampleSpec{
		{Ordinal: 0, Offset: 24 * time.Second},
		{Ordinal: 1, Offset: 26 * time.Second},
	})))
	resolver := NewJSONSidecarResolver(media)
	for _, test := range []struct {
		timestamp time.Time
		want      float64
	}{
		{sidecarBase.Add(24 * time.Second), 0},
		{sidecarBase.Add(26 * time.Second), 2},
	} {
		rec.State, rec.EndTS = model.RecordingStateRecording, nil
		sample, err := resolver.ResolveFrame(context.Background(), rec, test.timestamp, MatchExact)
		if err != nil || sample.MediaTimeSeconds != test.want {
			t.Fatalf("timestamp %s: got %+v, %v; want media time %v", test.timestamp, sample, err, test.want)
		}
		end := sidecarBase.Add(28 * time.Second)
		rec.State, rec.EndTS = model.RecordingStateReady, &end
		sample, err = resolver.ResolveFrame(context.Background(), rec, test.timestamp, MatchExact)
		if err != nil || sample.MediaTimeSeconds != test.want {
			t.Fatalf("ready timestamp %s: got %+v, %v; want media time %v", test.timestamp, sample, err, test.want)
		}
	}
}

func TestResolveFrameReportsMissingOrMalformedSidecar(t *testing.T) {
	ctx := context.Background()
	media := newFakeMediaStore()
	resolver := NewJSONSidecarResolver(media)

	if _, err := resolver.ResolveFrame(ctx, readyRecording("rec-001"), sidecarBase, MatchNearest); !errors.Is(err, ErrSidecarUnavailable) {
		t.Fatalf("missing sidecar: got %v", err)
	}

	media.Set("recordings/rec-001/sidecar.json", []byte(`{"version":1,"samples":[`))
	if _, err := resolver.ResolveFrame(ctx, readyRecording("rec-001"), sidecarBase, MatchNearest); !errors.Is(err, ErrSidecarMalformed) {
		t.Fatalf("malformed sidecar: got %v", err)
	}
}

func TestResolveRange(t *testing.T) {
	ctx := context.Background()
	rec := readyRecording("rec-001")

	t.Run("nearest boundaries on contiguous samples", func(t *testing.T) {
		resolver, _ := seededResolver(t, regularSpecs(11, time.Second))
		got, err := resolver.ResolveRange(ctx, rec, sidecarBase.Add(1200*time.Millisecond), sidecarBase.Add(5900*time.Millisecond), MatchNearest)
		if err != nil {
			t.Fatal(err)
		}
		if got.Start.Ordinal != 1 || got.End.Ordinal != 6 {
			t.Fatalf("resolved %d..%d, want 1..6", got.Start.Ordinal, got.End.Ordinal)
		}
	})

	t.Run("collapsing to one sample is rejected", func(t *testing.T) {
		resolver, _ := seededResolver(t, regularSpecs(11, time.Second))
		_, err := resolver.ResolveRange(ctx, rec, sidecarBase.Add(1100*time.Millisecond), sidecarBase.Add(1400*time.Millisecond), MatchNearest)
		if !errors.Is(err, ErrClipIntervalNotCovered) {
			t.Fatalf("got %v", err)
		}
	})

	t.Run("gap in ordinals is rejected", func(t *testing.T) {
		resolver, _ := seededResolver(t, []sampleSpec{
			{0, 0}, {1, time.Second}, {2, 2 * time.Second}, {5, 5 * time.Second}, {6, 6 * time.Second},
		})
		_, err := resolver.ResolveRange(ctx, rec, sidecarBase.Add(time.Second), sidecarBase.Add(6*time.Second), MatchNearest)
		if !errors.Is(err, ErrClipIntervalNotCovered) {
			t.Fatalf("got %v", err)
		}
		// A range that does not straddle the gap is still fine.
		if _, err := resolver.ResolveRange(ctx, rec, sidecarBase, sidecarBase.Add(2*time.Second), MatchNearest); err != nil {
			t.Fatalf("range before gap rejected: %v", err)
		}
	})

	t.Run("end outside coverage", func(t *testing.T) {
		resolver, _ := seededResolver(t, regularSpecs(3, time.Second))
		_, err := resolver.ResolveRange(ctx, rec, sidecarBase, sidecarBase.Add(time.Hour), MatchNearest)
		if !errors.Is(err, ErrTimestampOutOfCoverage) {
			t.Fatalf("got %v", err)
		}
	})
}

func TestResolveLiveRangeRequiresCompleteLookahead(t *testing.T) {
	ctx := context.Background()
	newLiveResolver := func(specs []sampleSpec) (*JSONSidecarResolver, model.Recording) {
		rec := liveRecording("rec-live-range", 1024)
		media := newFakeMediaStore()
		media.Set("recordings/rec-live-range/sidecar.jsonl", []byte(jsonlDoc(t, rec.RecordingID, rec.RecordingPath, specs)))
		return NewJSONSidecarResolver(media), rec
	}

	t.Run("later sample covers requested end", func(t *testing.T) {
		resolver, rec := newLiveResolver(regularSpecs(8, time.Second))
		got, err := resolver.ResolveRange(ctx, rec, sidecarBase.Add(time.Second), sidecarBase.Add(5*time.Second), MatchNearest)
		if err != nil {
			t.Fatal(err)
		}
		if got.End.Ordinal != 5 {
			t.Fatalf("end ordinal = %d, want 5", got.End.Ordinal)
		}
	})

	t.Run("latest sample cannot be clip endpoint", func(t *testing.T) {
		resolver, rec := newLiveResolver(regularSpecs(6, time.Second))
		_, err := resolver.ResolveRange(ctx, rec, sidecarBase, sidecarBase.Add(5*time.Second), MatchNearest)
		if !errors.Is(err, ErrClipIntervalNotCovered) {
			t.Fatalf("got %v, want ErrClipIntervalNotCovered", err)
		}
	})

	t.Run("sample after boundary is required", func(t *testing.T) {
		resolver, rec := newLiveResolver(regularSpecs(6, time.Second))
		_, err := resolver.ResolveRange(ctx, rec, sidecarBase, sidecarBase.Add(4600*time.Millisecond), MatchNearest)
		if !errors.Is(err, ErrClipIntervalNotCovered) {
			t.Fatalf("got %v, want ErrClipIntervalNotCovered", err)
		}
	})
}
