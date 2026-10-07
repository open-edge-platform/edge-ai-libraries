// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package record

import (
	"bytes"
	"context"
	"io"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/mediaaccess"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

type idleBufferer struct{}

func (idleBufferer) CreateBuffer(context.Context, string, string) (string, error) {
	return "", nil
}
func (idleBufferer) GetBuffer(context.Context, string, time.Time, time.Time) ([]model.BufferSlice, error) {
	return nil, nil
}
func (idleBufferer) AcquireBuffer(context.Context, string, time.Time, time.Time) (*stream.BufferLease, error) {
	return nil, nil
}
func (idleBufferer) ResizeBuffer(context.Context, string, int) (model.StreamBuffer, error) {
	return model.StreamBuffer{}, nil
}
func (idleBufferer) RemoveBuffer(context.Context, string) error { return nil }
func (idleBufferer) GetStream(context.Context, string) (model.StreamBuffer, error) {
	return model.StreamBuffer{}, nil
}
func (idleBufferer) ListStreams(context.Context) ([]model.StreamBuffer, error) { return nil, nil }

func TestLiveSidecarWriterEmitsRetrievalCompatibleJSONL(t *testing.T) {
	recording := model.Recording{RecordingID: "rec-sidecar", RecordingPath: "recordings/rec-sidecar/media.ts"}
	var output bytes.Buffer
	if err := writeLiveSidecarHeader(&output, recording); err != nil {
		t.Fatal(err)
	}
	base := time.Date(2026, time.October, 4, 12, 0, 0, 0, time.UTC)
	for ordinal := 0; ordinal < 2; ordinal++ {
		sample := model.BufferSlice{
			StartTS:  base.Add(time.Duration(ordinal) * time.Second),
			PTSStart: ordinal * 90000, PTSEnd: (ordinal + 1) * 90000,
		}
		if err := writeLiveSidecarSample(&output, ordinal, sample); err != nil {
			t.Fatal(err)
		}
	}
	parsed, err := replay.ParseSidecarAuto(io.Reader(&output))
	if err != nil {
		t.Fatalf("ParseSidecarAuto: %v", err)
	}
	if parsed.Version != 2 || parsed.RecordingID != recording.RecordingID || len(parsed.Samples) != 2 {
		t.Fatalf("unexpected parsed sidecar: %+v", parsed)
	}
	if parsed.Samples[1].PTS != 90000 || parsed.Samples[1].MediaTimeSeconds != 1 || !parsed.Samples[1].CaptureTS.Equal(base.Add(time.Second)) {
		t.Fatalf("unexpected sample: %+v", parsed.Samples[1])
	}
}

func TestRecoverInterruptedUsesCanonicalMetadataAndMediaStores(t *testing.T) {
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg not on PATH")
	}
	if _, err := exec.LookPath("ffprobe"); err != nil {
		t.Skip("ffprobe not on PATH")
	}
	ctx := context.Background()
	metadata, err := storage.OpenSQLiteMetadataStore(ctx, t.TempDir()+"/metadata.db")
	if err != nil {
		t.Fatal(err)
	}
	defer metadata.Close()
	signer, err := mediaaccess.NewSigner("test-secret")
	if err != nil {
		t.Fatal(err)
	}
	media, err := storage.NewFileMediaStore(t.TempDir(), "http://media.test", signer)
	if err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"rec-stale-1", "rec-stale-2"} {
		path, err := media.PutLiveRecording(ctx, id, strings.NewReader("partial-ts"))
		if err != nil {
			t.Fatal(err)
		}
		if _, err := media.PutLiveSidecar(ctx, id, strings.NewReader("partial-jsonl")); err != nil {
			t.Fatal(err)
		}
		state := model.RecordingStateRecording
		var endTS *time.Time
		if id == "rec-stale-2" {
			state = model.RecordingStateFinalizing
			end := time.Now().UTC()
			endTS = &end
		}
		if err := metadata.Save(ctx, model.Recording{
			RecordingID: id, SensorID: "sensor-1", Origin: model.RecordingOriginLive,
			State: state, StartTS: time.Now().UTC().Add(-time.Second), EndTS: endTS,
			RecordingPath: path, Container: "mpegts", SizeBytes: 10,
			CreationTS: time.Now().UTC(), Metadata: map[string]any{},
		}); err != nil {
			t.Fatal(err)
		}
	}

	service, err := NewService(idleBufferer{}, metadata, media, 4, false)
	if err != nil {
		t.Fatal(err)
	}
	if err := service.RecoverInterrupted(ctx); err != nil {
		t.Fatalf("RecoverInterrupted: %v", err)
	}
	for _, id := range []string{"rec-stale-1", "rec-stale-2"} {
		recording, err := metadata.GetByID(ctx, id)
		if err != nil {
			t.Fatal(err)
		}
		if recording.State != model.RecordingStateFailed || recording.SizeBytes != 0 || recording.ErrorDetails == "" {
			t.Fatalf("stale recording %q not failed: %+v", id, recording)
		}
		if _, err := media.OpenRecording(ctx, recording.RecordingPath); err == nil {
			t.Fatalf("partial media for %q was not removed", id)
		}
	}
}
