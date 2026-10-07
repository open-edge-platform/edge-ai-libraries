// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

type retrievalFixture struct {
	service   *RetrievalService
	media     *fakeMediaStore
	extractor *fakeExtractor
}

func newRetrievalFixture(t *testing.T, recs ...model.Recording) retrievalFixture {
	t.Helper()
	if len(recs) == 0 {
		recs = []model.Recording{readyRecording("rec-001")}
	}
	media := newFakeMediaStore()
	for _, r := range recs {
		media.Set(r.RecordingPath, []byte("source-"+r.RecordingID))
		media.Set("recordings/"+r.RecordingID+"/sidecar.json", []byte(sidecarJSON(t, sidecarDoc(r.RecordingID, r.RecordingPath, regularSpecs(21, 500*time.Millisecond)))))
	}
	extractor := &fakeExtractor{}
	service := NewRetrievalService(newFakeMetadataStore(recs...), media, Options{
		Extractor:     extractor,
		DerivedTTL:    time.Hour,
		PresignExpiry: 10 * time.Minute,
	})
	return retrievalFixture{service: service, media: media, extractor: extractor}
}

func readDerived(t *testing.T, media *fakeMediaStore, key string) string {
	t.Helper()
	rc, err := media.OpenDerived(context.Background(), key)
	if err != nil {
		t.Fatalf("open derived %s: %v", key, err)
	}
	defer rc.Close()
	body, _ := io.ReadAll(rc)
	return string(body)
}

func TestGetFrameExactAndNearest(t *testing.T) {
	ctx := context.Background()
	fx := newRetrievalFixture(t)

	exactTS := sidecarBase.Add(3 * time.Second)
	res, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: "rec-001", StartTS: exactTS, Format: "JPG", Match: "exact"})
	if err != nil {
		t.Fatal(err)
	}
	if res.MediaType != MediaTypeFrame || res.ContentType != "image/jpeg" || !res.ExactMatch {
		t.Fatalf("unexpected result %+v", res)
	}
	if !res.StartTS.Equal(exactTS) || !res.RequestedStartTS.Equal(exactTS) || res.EndTS != nil || res.RequestedEndTS != nil {
		t.Fatalf("timestamps wrong: %+v", res)
	}
	if res.SensorID != "sensor-01" || res.URL == "" || res.ExpiryTS.Before(time.Now().Add(9*time.Minute)) {
		t.Fatalf("result envelope wrong: %+v", res)
	}
	if res.DerivedKey != "derived/rec-001/frames/20260921T000003-000000000.jpeg" {
		t.Fatalf("derived key %q", res.DerivedKey)
	}
	if got := readDerived(t, fx.media, res.DerivedKey); got != "frame:jpeg:3.000:source-rec-001" {
		t.Fatalf("derived bytes %q", got)
	}
	if fx.media.ContentType(res.DerivedKey) != "image/jpeg" {
		t.Fatalf("derived content type %q", fx.media.ContentType(res.DerivedKey))
	}

	nearTS := sidecarBase.Add(3200 * time.Millisecond)
	res, err = fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: "rec-001", StartTS: nearTS, Format: "png"})
	if err != nil {
		t.Fatal(err)
	}
	if res.ExactMatch || !res.StartTS.Equal(exactTS) || !res.RequestedStartTS.Equal(nearTS) {
		t.Fatalf("nearest resolution wrong: %+v", res)
	}
	if res.ContentType != "image/png" || !strings.HasSuffix(res.DerivedKey, ".png") {
		t.Fatalf("png not honoured: %+v", res)
	}
}

func TestGetFrameReusesDerivedObject(t *testing.T) {
	ctx := context.Background()
	fx := newRetrievalFixture(t)

	for _, offset := range []time.Duration{3 * time.Second, 3100 * time.Millisecond, 2900 * time.Millisecond} {
		if _, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase.Add(offset)}); err != nil {
			t.Fatal(err)
		}
	}
	if fx.extractor.frameCalls != 1 {
		t.Fatalf("extractor called %d times, want 1 (cache reuse)", fx.extractor.frameCalls)
	}
	if len(fx.media.PutCalls) != 1 {
		t.Fatalf("derived put %d times, want 1", len(fx.media.PutCalls))
	}
}

func TestGetFrameValidation(t *testing.T) {
	ctx := context.Background()
	notReady := readyRecording("rec-busy")
	notReady.State = model.RecordingStateRecording
	fx := newRetrievalFixture(t, readyRecording("rec-001"), notReady)

	cases := []struct {
		name string
		req  model.FrameRequest
		want error
	}{
		{"missing recording", model.FrameRequest{RecordingID: "rec-404", StartTS: sidecarBase}, storage.ErrRecordingNotFound},
		{"invalid id", model.FrameRequest{RecordingID: "../x", StartTS: sidecarBase}, storage.ErrInvalidIdentifier},
		{"not ready", model.FrameRequest{RecordingID: "rec-busy", StartTS: sidecarBase}, ErrRecordingNotReady},
		{"bad format", model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase, Format: "gif"}, ErrUnsupportedFrameFormat},
		{"bad match", model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase, Match: "fuzzy"}, ErrUnsupportedMatchMode},
		{"out of coverage", model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase.Add(time.Hour)}, ErrTimestampOutOfCoverage},
		{"no exact", model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase.Add(250 * time.Millisecond), Match: "exact"}, ErrNoExactMatch},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := fx.service.GetFrame(ctx, tc.req)
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
		})
	}
	if fx.extractor.frameCalls != 0 {
		t.Fatalf("extractor invoked on rejected requests")
	}
}

func TestGetClipByDurationAndEnd(t *testing.T) {
	ctx := context.Background()
	fx := newRetrievalFixture(t)
	start := sidecarBase.Add(2 * time.Second)
	dur := 1.5

	res, err := fx.service.GetClip(ctx, model.ClipRequest{RecordingID: "rec-001", StartTS: start, ClipDuration: &dur})
	if err != nil {
		t.Fatal(err)
	}
	wantEnd := start.Add(1500 * time.Millisecond)
	if res.MediaType != MediaTypeClip || res.ContentType != "video/mp4" || !res.ExactMatch {
		t.Fatalf("unexpected result %+v", res)
	}
	if !res.StartTS.Equal(start) || res.EndTS == nil || !res.EndTS.Equal(wantEnd) {
		t.Fatalf("resolved bounds wrong: %+v", res)
	}
	if res.RequestedEndTS == nil || !res.RequestedEndTS.Equal(wantEnd) {
		t.Fatalf("requested end wrong: %+v", res)
	}
	if fx.extractor.lastStart != 2 || fx.extractor.lastEnd != 3.5 {
		t.Fatalf("extractor asked for %v-%v, want 2-3.5", fx.extractor.lastStart, fx.extractor.lastEnd)
	}
	if res.DerivedKey != "derived/rec-001/clips/20260921T000002-000000000_20260921T000003-500000000.mp4" {
		t.Fatalf("derived key %q", res.DerivedKey)
	}

	// The same interval expressed with an explicit end, slightly off the
	// sample grid, resolves to the same derived object.
	end := wantEnd.Add(100 * time.Millisecond)
	res2, err := fx.service.GetClip(ctx, model.ClipRequest{RecordingID: "rec-001", StartTS: start.Add(-100 * time.Millisecond), EndTS: &end, Format: "MP4"})
	if err != nil {
		t.Fatal(err)
	}
	if res2.DerivedKey != res.DerivedKey || res2.ExactMatch {
		t.Fatalf("nearest clip did not reuse derived object: %+v", res2)
	}
	if fx.extractor.clipCalls != 1 {
		t.Fatalf("extractor called %d times, want 1", fx.extractor.clipCalls)
	}
}

func TestGetClipValidation(t *testing.T) {
	ctx := context.Background()
	fx := newRetrievalFixture(t)
	start := sidecarBase.Add(2 * time.Second)
	pos, zero, neg := 1.0, 0.0, -1.0
	end := start.Add(time.Second)
	before := start.Add(-time.Second)
	far := start.Add(time.Hour)
	tiny := start.Add(100 * time.Millisecond)

	cases := []struct {
		name string
		req  model.ClipRequest
		want error
	}{
		{"neither boundary", model.ClipRequest{RecordingID: "rec-001", StartTS: start}, ErrInvalidClipRange},
		{"both boundaries", model.ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &end, ClipDuration: &pos}, ErrInvalidClipRange},
		{"zero duration", model.ClipRequest{RecordingID: "rec-001", StartTS: start, ClipDuration: &zero}, ErrInvalidClipRange},
		{"negative duration", model.ClipRequest{RecordingID: "rec-001", StartTS: start, ClipDuration: &neg}, ErrInvalidClipRange},
		{"end before start", model.ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &before}, ErrInvalidClipRange},
		{"bad format", model.ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &end, Format: "webm"}, ErrUnsupportedClipFormat},
		{"end out of coverage", model.ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &far}, ErrTimestampOutOfCoverage},
		{"collapses to one sample", model.ClipRequest{RecordingID: "rec-001", StartTS: start, EndTS: &tiny}, ErrClipIntervalNotCovered},
		{"missing recording", model.ClipRequest{RecordingID: "rec-404", StartTS: start, EndTS: &end}, storage.ErrRecordingNotFound},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := fx.service.GetClip(ctx, tc.req)
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
		})
	}
	if fx.extractor.clipCalls != 0 {
		t.Fatalf("extractor invoked on rejected requests")
	}
}

func TestStorageFailuresAreWrappedAsMediaUnavailable(t *testing.T) {
	ctx := context.Background()
	req := model.FrameRequest{RecordingID: "rec-001", StartTS: sidecarBase.Add(time.Second)}

	t.Run("source open fails", func(t *testing.T) {
		fx := newRetrievalFixture(t)
		fx.media.Delete("recordings/rec-001/media.mp4")
		if _, err := fx.service.GetFrame(ctx, req); !errors.Is(err, ErrMediaUnavailable) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("derived put fails", func(t *testing.T) {
		fx := newRetrievalFixture(t)
		fx.media.PutErr = errors.New("disk full")
		if _, err := fx.service.GetFrame(ctx, req); !errors.Is(err, ErrMediaUnavailable) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("presign fails", func(t *testing.T) {
		fx := newRetrievalFixture(t)
		fx.media.PresignErr = errors.New("signer down")
		if _, err := fx.service.GetFrame(ctx, req); !errors.Is(err, ErrMediaUnavailable) {
			t.Fatalf("got %v", err)
		}
	})
	t.Run("extraction fails is passed through", func(t *testing.T) {
		fx := newRetrievalFixture(t)
		fx.extractor.err = ErrExtractionFailed
		if _, err := fx.service.GetFrame(ctx, req); !errors.Is(err, ErrExtractionFailed) {
			t.Fatalf("got %v", err)
		}
		if len(fx.media.PutCalls) != 0 {
			t.Fatal("derived object written despite failed extraction")
		}
	})
}

func TestOptionsDefaultLifetimes(t *testing.T) {
	svc := NewRetrievalService(newFakeMetadataStore(), newFakeMediaStore(), Options{Extractor: &fakeExtractor{}})
	if svc.derivedTTL != defaultDerivedTTL || svc.presignExpiry != defaultPresignExpiry {
		t.Fatalf("defaults not applied: %v %v", svc.derivedTTL, svc.presignExpiry)
	}
	if svc.resolver == nil {
		t.Fatal("resolver not defaulted")
	}
}
