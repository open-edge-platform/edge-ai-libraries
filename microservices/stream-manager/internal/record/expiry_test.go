// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package record

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

func openStores(t *testing.T) (*storage.MetadataStore, *storage.MediaStore) {
	t.Helper()
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
	return metadata, media
}

// newTestService starts a recording service that is closed when the test ends.
func newTestService(t *testing.T, metadata storage.MetadataHandler, media storage.MediaHandler,
	retention time.Duration,
) *Service {
	t.Helper()
	svc, err := NewService(nil, metadata, media, 1, retention)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = svc.Close() })
	return svc
}

func seedExpiring(t *testing.T, metadata *storage.MetadataStore, media *storage.MediaStore,
	expiry *time.Time,
) (model.Recording, string) {
	t.Helper()
	rec, filename := seed(t, metadata, media, "ready")
	rec.ExpiryTS = expiry
	rec, err := metadata.UpdateMetadata(context.Background(), rec.RecordingID, rec)
	if err != nil {
		t.Fatal(err)
	}
	return rec, filename
}

func TestExpireRecordings(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	past, future := time.Now().Add(-time.Minute), time.Now().Add(time.Hour)
	var expired []model.Recording
	for range recoveryBatchSize + 5 {
		rec, _ := seedExpiring(t, metadata, media, &past)
		expired = append(expired, rec)
	}
	kept, keptFile := seedExpiring(t, metadata, media, &future)
	forever, foreverFile := seedExpiring(t, metadata, media, nil)

	failing := newTestService(t, metadata, failingMedia{media}, 0)
	failing.expireRecordings(ctx)
	if err := failing.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, expired[0].RecordingID); err != nil {
		t.Fatalf("metadata deleted although media deletion failed: %v", err)
	}

	// Retention 0 must still delete rows that an earlier retention setting expired.
	newTestService(t, metadata, media, 0)
	deadline := time.Now().Add(5 * time.Second)
	for _, rec := range expired {
		for {
			_, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID)
			if errors.Is(err, storage.ErrNotFound) {
				break
			}
			if time.Now().After(deadline) {
				t.Fatalf("expired recording kept: %v", err)
			}
			time.Sleep(10 * time.Millisecond)
		}
	}
	if media.UsedBytes() != 2 {
		t.Fatalf("used = %d, want only the two kept recordings", media.UsedBytes())
	}
	for _, rec := range []model.Recording{kept, forever} {
		if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); err != nil {
			t.Fatalf("unexpired recording deleted: %v", err)
		}
	}
	for _, filename := range []string{keptFile, foreverFile} {
		if _, err := os.Stat(filename); err != nil {
			t.Fatalf("unexpired media deleted: %v", err)
		}
	}
}

func TestRetentionSetsExpiry(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	rec, _ := seed(t, metadata, media, "recording")
	if err := newTestService(t, metadata, media, time.Hour).Close(); err != nil {
		t.Fatal(err)
	}
	got, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID)
	if err != nil {
		t.Fatal(err)
	}
	if got.State != "failed" || got.ExpiryTS == nil || time.Until(*got.ExpiryTS) <= 59*time.Minute {
		t.Fatalf("interrupted recording: state %s, expiry %v", got.State, got.ExpiryTS)
	}
	if _, err := NewService(nil, metadata, media, 1, -time.Hour); !errors.Is(err, ErrInvalidRequest) {
		t.Fatalf("negative retention accepted: %v", err)
	}
}

func TestExpireSkipsMediaInUse(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	past := time.Now().Add(-time.Minute)
	rec, filename := seedExpiring(t, metadata, media, &past)
	release, err := media.AcquireMedia(ctx, rec.RecordingPath)
	if err != nil {
		t.Fatal(err)
	}
	svc := newTestService(t, metadata, media, 0)
	if err := svc.expire(ctx, rec); err != nil {
		t.Fatalf("busy media must be skipped quietly: %v", err)
	}
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("media in use deleted: %v", err)
	}
	release()
	if err := svc.expire(ctx, rec); err != nil {
		t.Fatal(err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("expired recording kept: %v", err)
	}
}
