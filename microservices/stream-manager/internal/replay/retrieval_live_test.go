// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func liveRecording(id string, sizeBytes int64) model.Recording {
	return model.Recording{
		RecordingID:   id,
		SensorID:      "sensor-01",
		Origin:        model.RecordingOriginLive,
		State:         model.RecordingStateRecording,
		StartTS:       sidecarBase,
		EndTS:         nil,
		RecordingPath: "recordings/" + id + "/media.ts",
		Container:     "mpegts",
		SizeBytes:     sizeBytes,
		CreationTS:    sidecarBase,
		Metadata:      map[string]any{},
	}
}

// newLiveFixture wires a fixture around a single live (state=recording,
// end_ts=nil) recording whose sidecar is version 2 JSONL, matching how a
// producer publishes an in-progress MPEG-TS recording.
func newLiveFixture(t *testing.T, rec model.Recording, maxStageBytes int64) retrievalFixture {
	t.Helper()
	media := newFakeMediaStore()
	media.Set(rec.RecordingPath, []byte("source-"+rec.RecordingID))
	media.Set("recordings/"+rec.RecordingID+"/sidecar.jsonl", []byte(jsonlDoc(t, rec.RecordingID, rec.RecordingPath, regularSpecs(21, 500*time.Millisecond))))

	extractor := &fakeExtractor{}
	service := NewRetrievalService(newFakeMetadataStore(rec), media, Options{
		Extractor:     extractor,
		DerivedTTL:    time.Hour,
		PresignExpiry: 10 * time.Minute,
		MaxStageBytes: maxStageBytes,
	})
	return retrievalFixture{service: service, media: media, extractor: extractor}
}

func TestGetFrameServesLiveRecordingWithJSONLSidecar(t *testing.T) {
	ctx := context.Background()
	rec := liveRecording("rec-live-1", 1024)
	fx := newLiveFixture(t, rec, 0)

	exactTS := sidecarBase.Add(3 * time.Second)
	res, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: exactTS, Match: "exact"})
	if err != nil {
		t.Fatalf("GetFrame: %v", err)
	}
	if !res.ExactMatch || !res.StartTS.Equal(exactTS) {
		t.Fatalf("unexpected result %+v", res)
	}
}

func TestGetLiveMPEGTSRecordingProducesMP4Clip(t *testing.T) {
	ffmpeg, err := exec.LookPath("ffmpeg")
	if err != nil {
		t.Skip("ffmpeg not on PATH")
	}

	sourcePath := filepath.Join(t.TempDir(), "source.ts")
	command := exec.Command(ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10", "-t", "3", "-c:v", "mpeg2video", "-f", "mpegts", sourcePath)
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("generate MPEG-TS source: %v: %s", err, output)
	}
	source, err := os.ReadFile(sourcePath)
	if err != nil {
		t.Fatalf("read MPEG-TS source: %v", err)
	}

	rec := liveRecording("rec-live-ts-clip", int64(len(source)))
	media := newFakeMediaStore()
	media.Set(rec.RecordingPath, source)
	media.Set("recordings/"+rec.RecordingID+"/sidecar.jsonl", []byte(jsonlDoc(t, rec.RecordingID, rec.RecordingPath, regularSpecs(5, 500*time.Millisecond))))
	service := NewRetrievalService(newFakeMetadataStore(rec), media, Options{
		Extractor:     NewFFmpegExtractorWithBinary(ffmpeg),
		MaxStageBytes: int64(len(source)),
	})
	end := sidecarBase.Add(1500 * time.Millisecond)
	result, err := service.GetClip(context.Background(), model.ClipRequest{
		RecordingID: rec.RecordingID,
		StartTS:     sidecarBase.Add(500 * time.Millisecond),
		EndTS:       &end,
		Format:      "mp4",
	})
	if err != nil {
		t.Fatalf("GetClip from MPEG-TS: %v", err)
	}
	if result.ContentType != contentTypeMP4 {
		t.Fatalf("content type = %q, want %q", result.ContentType, contentTypeMP4)
	}
	clip, ok := media.Get(result.DerivedKey)
	if !ok {
		t.Fatalf("derived clip %q was not published", result.DerivedKey)
	}
	if len(clip) < 8 || !bytes.Equal(clip[4:8], []byte("ftyp")) {
		t.Fatalf("derived clip is not MP4: %x", clip[:min(16, len(clip))])
	}
}

func TestFinalizingAndFailedRecordingsAreNotServable(t *testing.T) {
	ctx := context.Background()
	for _, state := range []string{model.RecordingStateFinalizing, model.RecordingStateFailed} {
		rec := liveRecording("rec-x", 0)
		rec.State = state
		fx := newLiveFixture(t, rec, 0)

		_, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: sidecarBase, Match: "exact"})
		if !errors.Is(err, ErrRecordingNotReady) {
			t.Fatalf("state %q: got %v, want ErrRecordingNotReady", state, err)
		}
	}
}

func TestLiveRecordingExceedingMaxStageBytesIsRejected(t *testing.T) {
	ctx := context.Background()
	rec := liveRecording("rec-live-big", 10_000)
	fx := newLiveFixture(t, rec, 1_000)

	_, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: sidecarBase.Add(3 * time.Second), Match: "exact"})
	if !errors.Is(err, ErrRecordingTooLarge) {
		t.Fatalf("got %v, want ErrRecordingTooLarge", err)
	}
	if fx.extractor.frameCalls != 0 {
		t.Fatalf("extractor must not run once the size limit is exceeded, got %d calls", fx.extractor.frameCalls)
	}
}

func TestLiveRecordingWithUnknownSizeIsRejectedBeforeExtraction(t *testing.T) {
	ctx := context.Background()
	for _, sizeBytes := range []int64{0, -1} {
		rec := liveRecording("rec-live-unknown", sizeBytes)
		fx := newLiveFixture(t, rec, 1_000)

		_, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: sidecarBase.Add(3 * time.Second), Match: "exact"})
		if !errors.Is(err, ErrRecordingSizeUnknown) {
			t.Errorf("size %d: got %v, want ErrRecordingSizeUnknown", sizeBytes, err)
		}
		if fx.extractor.frameCalls != 0 {
			t.Errorf("size %d: extractor called %d times", sizeBytes, fx.extractor.frameCalls)
		}
	}
}

func TestLiveRecordingWithinMaxStageBytesIsServed(t *testing.T) {
	ctx := context.Background()
	rec := liveRecording("rec-live-small", 500)
	fx := newLiveFixture(t, rec, 1_000)

	if _, err := fx.service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: sidecarBase.Add(3 * time.Second), Match: "exact"}); err != nil {
		t.Fatalf("GetFrame: %v", err)
	}
}

// TestFinalizedRecordingIsNeverSizeLimited confirms the staging size limit
// applies only to a live recording, matching the Phase 1 plan: a finalized
// recording's size is not re-checked against MaxStageBytes.
func TestFinalizedRecordingIsNeverSizeLimited(t *testing.T) {
	ctx := context.Background()
	rec := readyRecording("rec-001")
	rec.SizeBytes = 10_000
	media := newFakeMediaStore()
	media.Set(rec.RecordingPath, []byte("source-"+rec.RecordingID))
	media.Set("recordings/"+rec.RecordingID+"/sidecar.json", []byte(sidecarJSON(t, sidecarDoc(rec.RecordingID, rec.RecordingPath, regularSpecs(21, 500*time.Millisecond)))))
	extractor := &fakeExtractor{}
	service := NewRetrievalService(newFakeMetadataStore(rec), media, Options{Extractor: extractor, MaxStageBytes: 1_000})

	if _, err := service.GetFrame(ctx, model.FrameRequest{RecordingID: rec.RecordingID, StartTS: sidecarBase.Add(3 * time.Second), Match: "exact"}); err != nil {
		t.Fatalf("GetFrame: %v", err)
	}
}
