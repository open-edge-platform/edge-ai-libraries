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

func TestExpiredRecordingCleanupIsDeferred(t *testing.T) {
	ctx := context.Background()
	metadata, media := openStores(t)
	rec, filename := seed(t, metadata, media, "ready")
	past := time.Now().Add(-time.Minute)
	rec.ExpiryTS = &past
	if _, err := metadata.UpdateMetadata(ctx, rec.RecordingID, rec); err != nil {
		t.Fatal(err)
	}

	if err := newTestService(t, metadata, media, 0).Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID); err != nil {
		t.Fatalf("record metadata was removed without the cleanup service: %v", err)
	}
	if _, err := os.Stat(filename); err != nil {
		t.Fatalf("recording media was removed without the cleanup service: %v", err)
	}
}
