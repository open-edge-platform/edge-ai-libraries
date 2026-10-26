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

func (failingMedia) DeleteMedia(context.Context, string) error { return errors.New("disk gone") }

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
	svc.cleanupOrphanedMedia(ctx)
	if _, err := os.Stat(filepath.Dir(filename)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("orphan media kept after cleanup: %v", err)
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
	svc.cleanupOrphanedMedia(ctx)
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("busy media removed: %v", err)
	}
	release()
	svc.cleanupOrphanedMedia(ctx)
	if _, err := os.Stat(filepath.Dir(filename)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("released orphan media kept: %v", err)
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

type unreadableMetadata struct{ *storage.MetadataStore }

func (unreadableMetadata) GetMetadataByRecordingID(context.Context, string) (model.Recording, error) {
	return model.Recording{}, errors.New("db unavailable")
}

func TestCleanupOrphanedMedia(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	kept, keptFile := seed(t, metadata, media, "ready")
	orphan, orphanFile := seed(t, metadata, media, "ready")
	if _, _, err := media.PutDerived(ctx, orphan.RecordingPath, "frame-0.jpeg", func(path string) error {
		return os.WriteFile(path, []byte("frame"), 0o600)
	}); err != nil {
		t.Fatal(err)
	}
	if err := metadata.DeleteMetadata(ctx, orphan.RecordingID); err != nil {
		t.Fatal(err)
	}
	svc := &Service{metadata: unreadableMetadata{metadata}, media: media}
	if err := svc.cleanupOrphan(ctx, orphan.RecordingID, orphan.RecordingPath); err == nil {
		t.Fatal("metadata lookup failure was ignored")
	}
	if _, err := os.Stat(orphanFile); err != nil {
		t.Fatalf("media deleted after metadata lookup failure: %v", err)
	}
	svc.metadata = metadata
	svc.media = failingMedia{media}
	if err := svc.cleanupOrphan(ctx, orphan.RecordingID, orphan.RecordingPath); err == nil {
		t.Fatal("media deletion failure was ignored")
	}
	svc.media = media
	svc.jobs = map[string]*job{orphan.RecordingID: {}}
	svc.cleanupOrphanedMedia(ctx)
	if _, err := os.Stat(orphanFile); err != nil {
		t.Fatalf("active job media deleted: %v", err)
	}
	delete(svc.jobs, orphan.RecordingID)
	svc.cleanupOrphanedMedia(ctx)
	if _, err := os.Stat(filepath.Dir(orphanFile)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("orphan recording and derived media kept: %v", err)
	}
	if _, err := os.Stat(keptFile); err != nil {
		t.Fatalf("media with metadata removed: %v", err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, kept.RecordingID); err != nil {
		t.Fatal(err)
	}
	if media.UsedBytes() != 1 {
		t.Fatalf("used bytes = %d, want 1", media.UsedBytes())
	}
}

func TestStartupCleanupRemovesOrphans(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	rec, filename := seed(t, metadata, media, "ready")
	if err := metadata.DeleteMetadata(ctx, rec.RecordingID); err != nil {
		t.Fatal(err)
	}
	newTestService(t, metadata, media, 0)
	deadline := time.Now().Add(5 * time.Second)
	for {
		_, err := os.Stat(filepath.Dir(filename))
		if errors.Is(err, os.ErrNotExist) {
			return
		}
		if err != nil || time.Now().After(deadline) {
			t.Fatalf("startup cleanup kept orphan media: %v", err)
		}
		time.Sleep(10 * time.Millisecond)
	}
}
