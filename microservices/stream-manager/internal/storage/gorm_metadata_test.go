// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func openTestMetadataStore(t *testing.T) *SQLiteMetadataStore {
	t.Helper()
	store, err := OpenSQLiteMetadataStore(context.Background(), filepath.Join(t.TempDir(), "recordings.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func sampleRecording() model.Recording {
	start := time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC)
	end := start.Add(9500 * time.Millisecond)
	expiry := start.Add(24 * time.Hour)
	return model.Recording{
		RecordingID:   "rec-001",
		SensorID:      "sensor-01",
		StreamID:      "stream-01",
		Origin:        model.RecordingOriginLive,
		State:         model.RecordingStateReady,
		StartTS:       start,
		EndTS:         &end,
		RecordingPath: "recordings/rec-001/media.mp4",
		Codec:         "h264",
		Container:     "mp4",
		SizeBytes:     1234,
		Metadata:      map[string]any{"fixture": "development", "fps": float64(2)},
		CreationTS:    end,
		ExpiryTS:      &expiry,
		ErrorDetails:  "",
	}
}

func TestSchemaUsesCanonicalColumnsAndWAL(t *testing.T) {
	store := openTestMetadataStore(t)

	var columns []string
	if err := store.db.Raw("SELECT name FROM pragma_table_info('recordings')").Scan(&columns).Error; err != nil {
		t.Fatalf("read table info: %v", err)
	}
	if !reflect.DeepEqual(columns, recordingColumns) {
		t.Fatalf("columns = %v, want %v", columns, recordingColumns)
	}
	for _, legacy := range []string{"record_id", "created_ns", "expires_ns", "error_detail"} {
		for _, col := range columns {
			if col == legacy {
				t.Fatalf("legacy column %q still present", legacy)
			}
		}
	}

	var journal string
	if err := store.db.Raw("PRAGMA journal_mode").Scan(&journal).Error; err != nil {
		t.Fatalf("read journal mode: %v", err)
	}
	if !strings.EqualFold(journal, "wal") {
		t.Fatalf("journal_mode = %q, want wal", journal)
	}
	if err := store.Health(context.Background()); err != nil {
		t.Fatalf("health: %v", err)
	}
}

func TestSaveGetRoundTripPreservesEveryField(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)
	want := sampleRecording()

	if err := store.Save(ctx, want); err != nil {
		t.Fatalf("save: %v", err)
	}
	got, err := store.GetByID(ctx, want.RecordingID)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("round trip mismatch:\n got %+v\nwant %+v", got, want)
	}

	exists, err := store.Exists(ctx, want.RecordingID)
	if err != nil || !exists {
		t.Fatalf("exists = %v, %v; want true", exists, err)
	}
}

func TestLifecycleMetadataCRUDAndCursorPagination(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)
	first := sampleRecording()
	first.RecordingID = "rec-live-001"
	first.State = model.RecordingStateRecording
	first.EndTS = nil
	first.RecordingPath = "recordings/rec-live-001/media.ts"
	first.Container = "mpegts"
	first.CreationTS = time.Date(2026, time.September, 21, 0, 0, 1, 0, time.UTC)
	second := first
	second.RecordingID = "rec-live-002"
	second.SensorID = "sensor-02"
	second.RecordingPath = "recordings/rec-live-002/media.ts"
	second.CreationTS = first.CreationTS.Add(time.Second)
	if _, err := store.CreateBatch(ctx, []model.Recording{first, second}); err != nil {
		t.Fatalf("CreateBatch: %v", err)
	}

	page, cursor, err := store.ListMetadata(ctx, model.RecordingFilter{Limit: 1, State: model.RecordingStateRecording})
	if err != nil {
		t.Fatalf("ListMetadata first page: %v", err)
	}
	if len(page) != 1 || page[0].RecordingID != second.RecordingID || cursor == "" {
		t.Fatalf("first page = %+v, cursor %q", page, cursor)
	}
	page, next, err := store.ListMetadata(ctx, model.RecordingFilter{Limit: 1, State: model.RecordingStateRecording, Cursor: cursor})
	if err != nil {
		t.Fatalf("ListMetadata second page: %v", err)
	}
	if len(page) != 1 || page[0].RecordingID != first.RecordingID || next != "" {
		t.Fatalf("second page = %+v, cursor %q", page, next)
	}

	first.State = model.RecordingStateReady
	end := first.StartTS.Add(time.Second)
	first.EndTS = &end
	if _, err := store.UpdateMetadata(ctx, first.RecordingID, first); err != nil {
		t.Fatalf("UpdateMetadata: %v", err)
	}
	got, err := store.GetMetadataByRecordingID(ctx, first.RecordingID)
	if err != nil || got.State != model.RecordingStateReady || got.EndTS == nil {
		t.Fatalf("GetMetadataByRecordingID = %+v, %v", got, err)
	}
	if err := store.DeleteMetadata(ctx, first.RecordingID); err != nil {
		t.Fatalf("DeleteMetadata: %v", err)
	}
}

func TestSaveUpsertsAndWritesZeroValuesExplicitly(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)

	first := sampleRecording()
	if err := store.Save(ctx, first); err != nil {
		t.Fatalf("save: %v", err)
	}

	// Clearing fields back to their zero values must be persisted, not
	// dropped as "unset" by the ORM.
	second := first
	second.State = model.RecordingStateFailed
	second.SizeBytes = 0
	second.Codec = ""
	second.StreamID = ""
	second.EndTS = nil
	second.ExpiryTS = nil
	second.Metadata = nil
	second.ErrorDetails = "muxer crashed"
	if err := store.Save(ctx, second); err != nil {
		t.Fatalf("upsert: %v", err)
	}

	got, err := store.GetByID(ctx, first.RecordingID)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if got.State != model.RecordingStateFailed || got.SizeBytes != 0 || got.Codec != "" || got.StreamID != "" {
		t.Fatalf("zero values not written: %+v", got)
	}
	if got.EndTS != nil || got.ExpiryTS != nil {
		t.Fatalf("nullable timestamps not cleared: %+v", got)
	}
	if got.ErrorDetails != "muxer crashed" {
		t.Fatalf("error_details = %q", got.ErrorDetails)
	}
	if got.Metadata == nil || len(got.Metadata) != 0 {
		t.Fatalf("nil metadata should read back as empty map, got %#v", got.Metadata)
	}

	var count int64
	if err := store.db.Raw("SELECT COUNT(*) FROM recordings").Scan(&count).Error; err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("upsert produced %d rows, want 1", count)
	}
}

func TestSaveDefaultsCreationTimestamp(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)

	rec := sampleRecording()
	rec.CreationTS = time.Time{}
	before := time.Now().UTC().Add(-time.Second)
	if err := store.Save(ctx, rec); err != nil {
		t.Fatalf("save: %v", err)
	}
	got, err := store.GetByID(ctx, rec.RecordingID)
	if err != nil {
		t.Fatal(err)
	}
	if got.CreationTS.Before(before) {
		t.Fatalf("creation_ts %v not defaulted to now", got.CreationTS)
	}
}

func TestGetByIDMapsNotFound(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)

	if _, err := store.GetByID(ctx, "missing"); !errors.Is(err, ErrRecordingNotFound) {
		t.Fatalf("GetByID(missing) = %v, want ErrRecordingNotFound", err)
	}
	exists, err := store.Exists(ctx, "missing")
	if err != nil || exists {
		t.Fatalf("Exists(missing) = %v, %v", exists, err)
	}
	if _, err := store.GetByID(ctx, "bad/id"); !errors.Is(err, ErrInvalidIdentifier) {
		t.Fatalf("GetByID(bad/id) = %v, want ErrInvalidIdentifier", err)
	}
}

func TestSchemaConstraintsAreEnforced(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)

	badState := sampleRecording()
	badState.State = "done"
	if err := store.Save(ctx, badState); err == nil {
		t.Fatal("invalid state accepted")
	}

	badOrigin := sampleRecording()
	badOrigin.Origin = "upload"
	if err := store.Save(ctx, badOrigin); err == nil {
		t.Fatal("invalid origin accepted")
	}

	badEnd := sampleRecording()
	before := badEnd.StartTS.Add(-time.Second)
	badEnd.EndTS = &before
	if err := store.Save(ctx, badEnd); err == nil {
		t.Fatal("end_ts before start_ts accepted")
	}

	negativeSize := sampleRecording()
	negativeSize.SizeBytes = -1
	if err := store.Save(ctx, negativeSize); err == nil {
		t.Fatal("negative size_bytes accepted")
	}
}

func TestTimestampsKeepNanosecondPrecision(t *testing.T) {
	ctx := context.Background()
	store := openTestMetadataStore(t)

	rec := sampleRecording()
	rec.StartTS = time.Date(2026, time.September, 21, 0, 0, 6, 123456789, time.FixedZone("IST", 19800))
	if err := store.Save(ctx, rec); err != nil {
		t.Fatal(err)
	}
	got, err := store.GetByID(ctx, rec.RecordingID)
	if err != nil {
		t.Fatal(err)
	}
	if !got.StartTS.Equal(rec.StartTS) || got.StartTS.Location() != time.UTC {
		t.Fatalf("start_ts = %v, want %v in UTC", got.StartTS, rec.StartTS)
	}
}
