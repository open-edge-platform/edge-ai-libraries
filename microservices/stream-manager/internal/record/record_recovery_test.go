// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package record

import (
	"context"
	"encoding/base64"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

func seed(t *testing.T, metadata *storage.MetadataStore, media *storage.MediaStore, state string) (model.Recording, string) {
	t.Helper()
	ctx := context.Background()
	recordingUUID := uuid.New()
	recordingID := base64.RawURLEncoding.EncodeToString(recordingUUID[:])
	filename, uri, err := media.PrepareMedia(ctx, recordingID)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filename, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := media.PutMedia(ctx, uri); err != nil {
		t.Fatal(err)
	}
	rec, err := metadata.CreateMetadata(ctx, model.Recording{
		RecordingID: recordingID, SensorID: "s", StartTS: time.Unix(1, 0), RecordingPath: uri,
		State: state, Metadata: map[string]any{}, CreationTS: time.Now(),
	})
	if err != nil {
		t.Fatal(err)
	}
	return rec, filename
}

func TestRecoverInterrupted(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "storage")
	metadata, err := storage.OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = metadata.Close() })
	media, err := storage.OpenMediaStore(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	type seeded struct {
		rec      model.Recording
		filename string
		want     string
	}
	var all []seeded
	for range 150 {
		rec, filename := seed(t, metadata, media, "recording")
		all = append(all, seeded{rec, filename, "failed"})
	}
	for range 3 {
		rec, filename := seed(t, metadata, media, "finalizing")
		all = append(all, seeded{rec, filename, "failed"})
	}
	rec, filename := seed(t, metadata, media, "ready")
	all = append(all, seeded{rec, filename, "ready"})

	newTestService(t, metadata, media, 0)
	for _, s := range all {
		got, err := metadata.GetMetadataByRecordingID(context.Background(), s.rec.RecordingID)
		if err != nil {
			t.Fatal(err)
		}
		if got.State != s.want {
			t.Fatalf("state = %s, want %s", got.State, s.want)
		}
		_, statErr := os.Stat(s.filename)
		if s.want == "failed" {
			if got.ErrorDetail == nil || *got.ErrorDetail != "recording interrupted by service restart" {
				t.Fatalf("detail = %v", got.ErrorDetail)
			}
			if !errors.Is(statErr, os.ErrNotExist) {
				t.Fatalf("media kept: %v", statErr)
			}
		} else if statErr != nil {
			t.Fatalf("ready media removed: %v", statErr)
		}
	}
}

type failingMedia struct{ *storage.MediaStore }

func (failingMedia) DeleteMedia(context.Context, string) error {
	return errors.New("disk gone")
}

type failingMetadata struct{ *storage.MetadataStore }

func (failingMetadata) DeleteMetadata(context.Context, string) error { return errors.New("db gone") }

func TestDeleteOrder(t *testing.T) {
	ctx := context.Background()
	dir := filepath.Join(t.TempDir(), "storage")
	metadata, err := storage.OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}

	t.Cleanup(func() { _ = metadata.Close() })
	media, err := storage.OpenMediaStore(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })

	rec, filename := seed(t, metadata, media, "ready")
	svc := &Service{metadata: metadata, media: failingMedia{media}}
	if err := svc.DeleteRecording(ctx, rec.RecordingID); err != nil {
		t.Fatalf("media failure: %v", err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("row kept after media failure: %v", err)
	}
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("failed media deletion removed media: %v", err)
	}
	svc.media = media
	if err := media.DeleteMedia(ctx, rec.RecordingPath); err != nil {
		t.Fatalf("manual retry after media failure: %v", err)
	}
	rec, filename = seed(t, metadata, media, "ready")
	release, err := media.AcquireMedia(ctx, rec.RecordingPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := svc.DeleteRecording(ctx, rec.RecordingID); err != nil {
		t.Fatalf("busy media: %v", err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("busy media metadata kept: %v", err)
	}
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("busy media removed: %v", err)
	}
	release()
	if err := media.DeleteMedia(ctx, rec.RecordingPath); err != nil {
		t.Fatalf("manual retry after media was busy: %v", err)
	}
	if _, err := os.Stat(filepath.Dir(filename)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("media kept after manual retry: %v", err)
	}

	rec, filename = seed(t, metadata, media, "ready")
	svc.metadata = failingMetadata{metadata}
	if err := svc.DeleteRecording(ctx, rec.RecordingID); !errors.Is(err, ErrCleanup) {
		t.Fatalf("metadata failure: %v", err)
	}
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("media removed before metadata: %v", err)
	}
	svc.metadata = metadata
	if err := svc.DeleteRecording(ctx, rec.RecordingID); err != nil {
		t.Fatalf("retry after metadata failure: %v", err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("row kept: %v", err)
	}

	rec, filename = seed(t, metadata, media, "failed")
	if err := svc.DeleteRecording(ctx, rec.RecordingID); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Dir(filename)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("media kept: %v", err)
	}
}
