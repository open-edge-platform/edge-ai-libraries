// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func testStores(t *testing.T) (*MetadataStore, *MediaStore, string) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "records")
	metadata, err := OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := metadata.Close(); err != nil {
			t.Error(err)
		}
	})
	media, err := OpenMediaStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := media.Close(); err != nil {
			t.Error(err)
		}
	})
	return metadata, media, dir
}

func testRecording(t *testing.T, media *MediaStore) model.Recording {
	t.Helper()
	id := uuid.NewString()
	_, uri, err := media.PrepareMedia(context.Background(), id)
	if err != nil {
		t.Fatal(err)
	}
	return model.Recording{
		RecordingID: id, SensorID: "camera", RecordingPath: uri,
		StartTS:    time.Date(2026, 1, 1, 0, 0, 0, 123456789, time.UTC),
		CreationTS: time.Date(2026, 1, 1, 0, 1, 0, 987654321, time.UTC),
		State:      "recording", Metadata: map[string]any{"label": "door", "a.b": "literal"},
	}
}

func TestSchemaSerializationAndReopen(t *testing.T) {
	metadata, media, dir := testStores(t)
	ctx := context.Background()
	rec := testRecording(t, media)
	created, err := metadata.CreateMetadata(ctx, rec)
	if err != nil {
		t.Fatal(err)
	}
	got, err := metadata.GetMetadataByRecordingID(ctx, created.RecordingID)
	if err != nil || !got.StartTS.Equal(rec.StartTS) || !got.CreationTS.Equal(rec.CreationTS) ||
		got.EndTS != nil || got.Codec != nil || got.SizeBytes != nil || got.ErrorDetail != nil {
		t.Fatalf("nanosecond/NULL round trip: %+v %v", got, err)
	}
	var stored int64
	if err := metadata.db.Raw("SELECT start_ts FROM recordings WHERE recording_id = ?", rec.RecordingID).Scan(&stored).Error; err != nil ||
		stored != rec.StartTS.UnixNano() {
		t.Fatalf("timestamp is not INTEGER nanoseconds: %d %v", stored, err)
	}
	var indexes []struct{ Name string }
	if err := metadata.db.Raw("PRAGMA index_list('recordings')").Scan(&indexes).Error; err != nil {
		t.Fatal(err)
	}
	found := false
	for _, index := range indexes {
		found = found || index.Name == "idx_recordings_sensor_stream"
	}
	if !found {
		t.Fatal("agreed sensor/stream index is missing")
	}
	if _, err := OpenMetadataStore(dir); err == nil {
		t.Fatal("second instance acquired the same metadata storage")
	}
	if err := metadata.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := reopened.Close(); err != nil {
			t.Error(err)
		}
	}()
	got, err = reopened.GetMetadataByRecordingID(ctx, rec.RecordingID)
	if err != nil || !got.StartTS.Equal(rec.StartTS) {
		t.Fatalf("migration was not idempotent: %+v %v", got, err)
	}
}

func TestBatchRollbackFiltersAndPagination(t *testing.T) {
	metadata, media, _ := testStores(t)
	ctx := context.Background()
	first, second := testRecording(t, media), testRecording(t, media)
	second.SensorID = "other-camera"
	end := second.StartTS.Add(time.Second)
	second.EndTS = &end
	if _, err := metadata.createBatch(ctx, []model.Recording{first, second}); err != nil {
		t.Fatal(err)
	}
	bad := testRecording(t, media)
	bad.State = "unsupported"
	valid := testRecording(t, media)
	if _, err := metadata.createBatch(ctx, []model.Recording{valid, bad}); err == nil {
		t.Fatal("CHECK constraint was not enforced")
	}
	if _, err := metadata.GetMetadataByRecordingID(ctx, valid.RecordingID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("failed batch partially committed: %v", err)
	}
	page, cursor, err := metadata.ListMetadata(ctx, model.RecordingFilter{Limit: 1})
	if err != nil || len(page) != 1 || cursor == "" {
		t.Fatalf("first page: %+v %q %v", page, cursor, err)
	}
	next, last, err := metadata.ListMetadata(ctx, model.RecordingFilter{Limit: 1, Cursor: cursor})
	if err != nil || len(next) != 1 || next[0].RecordingID == page[0].RecordingID || last != "" {
		t.Fatalf("second page: %+v %q %v", next, last, err)
	}
	for _, filter := range []model.RecordingFilter{
		{SensorID: "camera", Metadata: map[string]any{"a.b": "literal"}},
		{StartTS: end},
	} {
		got, _, err := metadata.ListMetadata(ctx, filter)
		if err != nil || len(got) != 1 || got[0].RecordingID != first.RecordingID {
			t.Fatalf("AND/overlap filter: %+v %v", got, err)
		}
	}
	got, _, err := metadata.ListMetadata(ctx, model.RecordingFilter{Metadata: map[string]any{"label' OR 1=1 --": "door"}})
	if err != nil || len(got) != 0 {
		t.Fatalf("metadata key escaped its bound parameter: %+v %v", got, err)
	}
	if _, _, err := metadata.ListMetadata(ctx, model.RecordingFilter{Cursor: "malformed"}); !errors.Is(err, ErrInvalidFilter) {
		t.Fatalf("invalid cursor: %v", err)
	}
}

// TestMediaDurabilityDeletionAndRecovery exercises the same storage mechanics
// the old combined store's RecoverInterrupted relied on; recovery itself is
// now record.Service's responsibility and is covered in that package.
func TestMediaDurabilityDeletionAndRecovery(t *testing.T) {
	metadata, media, dir := testStores(t)
	ctx := context.Background()
	rec := testRecording(t, media)
	filename, err := media.relativeMedia(rec.RecordingPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := media.root.WriteFile(filename, []byte("unfinished media"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := media.PutMedia(ctx, rec.RecordingPath); err != nil {
		t.Fatal(err)
	}
	if _, err := metadata.CreateMetadata(ctx, rec); err != nil {
		t.Fatal(err)
	}
	// Simulate what record.Service's restart recovery does: mark the
	// interrupted recording failed, then delete its media.
	rec.State, rec.ErrorDetail = "failed", ptr("recording interrupted by service restart")
	if _, err := metadata.UpdateMetadata(ctx, rec.RecordingID, rec); err != nil {
		t.Fatal(err)
	}
	if err := media.DeleteMedia(ctx, rec.RecordingPath); err != nil {
		t.Fatal(err)
	}
	failed, err := metadata.GetMetadataByRecordingID(ctx, rec.RecordingID)
	if err != nil || failed.State != "failed" || failed.ErrorDetail == nil {
		t.Fatalf("restart claimed successful recording: %+v %v", failed, err)
	}
	if _, err := media.OpenMedia(ctx, rec.RecordingPath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("interrupted media remains: %v", err)
	}
	if err := media.DeleteMedia(ctx, rec.RecordingPath); err != nil {
		t.Fatalf("retry cleanup is not idempotent: %v", err)
	}
	if err := metadata.DeleteMetadata(ctx, rec.RecordingID); err != nil {
		t.Fatal(err)
	}
	if err := metadata.DeleteMetadata(ctx, rec.RecordingID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("duplicate deletion: %v", err)
	}
	for _, uri := range []string{"file:///etc/passwd", "file://host/remote", "file://" + filepath.Join(dir, databaseName)} {
		if _, err := media.OpenMedia(ctx, uri); err == nil {
			t.Fatalf("unsafe URI accepted: %s", uri)
		}
	}
}

func ptr[T any](v T) *T { return &v }
