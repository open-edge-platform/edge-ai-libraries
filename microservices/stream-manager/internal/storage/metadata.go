// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/glebarez/sqlite"
	"golang.org/x/sys/unix"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

// MetadataHandler saves, reads, lists, updates and deletes recording metadata.
type MetadataHandler interface {
	CreateMetadata(ctx context.Context, metadata model.Recording) (model.Recording, error)
	GetMetadataByRecordingID(ctx context.Context, recordingID string) (model.Recording, error)
	ListMetadata(ctx context.Context, recordingFilter model.RecordingFilter) ([]model.Recording, string, error)
	UpdateMetadata(ctx context.Context, recordingID string, metadata model.Recording) (model.Recording, error)
	DeleteMetadata(ctx context.Context, recordingID string) error
}

var (
	ErrNotFound      = errors.New("record not found")
	ErrInvalidFilter = errors.New("invalid recording filter or cursor")
)

const recordingsSchema = `
CREATE TABLE IF NOT EXISTS recordings (
	recording_id TEXT PRIMARY KEY,
	sensor_id TEXT NOT NULL,
	stream_id TEXT,
	start_ts INTEGER NOT NULL,
	end_ts INTEGER CHECK (end_ts IS NULL OR end_ts > start_ts),
	recording_path TEXT NOT NULL,
	codec TEXT,
	state TEXT NOT NULL CHECK (state IN ('recording','finalizing','ready','failed')),
	size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
	metadata TEXT NOT NULL DEFAULT '{}',
	creation_ts INTEGER NOT NULL,
	expiry_ts INTEGER,
	error_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_recordings_sensor_stream ON recordings(sensor_id, stream_id);
`

// slogWriter adapts gorm's logger.Writer interface to log/slog. GORM only
// calls Printf for warn-level-and-above diagnostics (per the configured
// logger.Config.LogLevel), so these are reported at warning severity.
type slogWriter struct{}

func (slogWriter) Printf(format string, args ...any) {
	slog.Warn(fmt.Sprintf(format, args...))
}

const databaseName = "stream-manager.db"

// MetadataStore keeps recording metadata in a SQLite database inside the storage directory.
type MetadataStore struct {
	db        *gorm.DB
	sql       *sql.DB
	lock      *os.File
	closeOnce sync.Once
	closeErr  error
}

var (
	_ MetadataHandler = (*MetadataStore)(nil)
	_ io.Closer       = (*MetadataStore)(nil)
)

func OpenMetadataStore(directory string) (_ *MetadataStore, result error) {
	root, lock, err := openPrivateDir(directory, ".metadata.lock")
	if err != nil {
		return nil, err
	}
	s := &MetadataStore{lock: lock}
	defer func() {
		if result != nil {
			result = errors.Join(result, s.Close())
		}
	}()
	databasePath, err := createDatabaseFile(root)
	if err := errors.Join(err, root.Close()); err != nil {
		return nil, err
	}
	dsn := (&url.URL{Scheme: "file", Path: databasePath}).String()
	dsn += "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(1)"
	db, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{
		Logger: logger.New(slogWriter{}, logger.Config{
			LogLevel: logger.Warn, ParameterizedQueries: true, IgnoreRecordNotFoundError: true,
			SlowThreshold: time.Second,
		}),
	})
	if err != nil {
		return nil, fmt.Errorf("open recording database: %w", err)
	}
	s.db = db
	s.sql, err = db.DB()
	if err != nil {
		return nil, err
	}
	s.sql.SetMaxOpenConns(1)
	if err := db.Transaction(func(tx *gorm.DB) error { return tx.Exec(recordingsSchema).Error }); err != nil {
		return nil, fmt.Errorf("initialize recordings schema: %w", err)
	}
	return s, nil
}

// createDatabaseFile creates the private database file in root and returns its absolute path.
func createDatabaseFile(root *os.Root) (string, error) {
	file, err := root.OpenFile(databaseName, os.O_CREATE|os.O_RDWR|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return "", err
	}
	return filepath.Join(root.Name(), databaseName), file.Close()
}

func (s *MetadataStore) createBatch(ctx context.Context, records []model.Recording) ([]model.Recording, error) {
	if len(records) == 0 {
		return nil, errors.New("no recordings to create")
	}
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		return tx.Create(&records).Error
	})
	return records, err
}

func (s *MetadataStore) CreateMetadata(ctx context.Context, metadata model.Recording) (model.Recording, error) {
	records, err := s.createBatch(ctx, []model.Recording{metadata})
	if err != nil {
		return model.Recording{}, err
	}
	return records[0], nil
}

func (s *MetadataStore) GetMetadataByRecordingID(ctx context.Context, id string) (model.Recording, error) {
	var rec model.Recording
	err := s.db.WithContext(ctx).Where("recording_id = ?", id).First(&rec).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		err = ErrNotFound
	}
	return rec, err
}

func (s *MetadataStore) UpdateMetadata(ctx context.Context, id string, rec model.Recording) (model.Recording, error) {
	rec.RecordingID = id
	result := s.db.WithContext(ctx).Model(&model.Recording{}).Where("recording_id = ?", id).Select("*").Updates(&rec)
	if result.Error != nil {
		return model.Recording{}, result.Error
	}
	if result.RowsAffected == 0 {
		return model.Recording{}, ErrNotFound
	}
	return rec, nil
}

func (s *MetadataStore) DeleteMetadata(ctx context.Context, id string) error {
	result := s.db.WithContext(ctx).Where("recording_id = ?", id).Delete(&model.Recording{})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *MetadataStore) ListMetadata(ctx context.Context, filter model.RecordingFilter) ([]model.Recording, string, error) {
	limit := filter.Limit
	if limit == 0 {
		limit = 20
	}
	if limit < 1 || limit > 100 {
		return nil, "", ErrInvalidFilter
	}
	query := s.db.WithContext(ctx).Model(&model.Recording{})
	if filter.SensorID != "" {
		query = query.Where("sensor_id = ?", filter.SensorID)
	}
	if filter.StreamID != "" {
		query = query.Where("stream_id = ?", filter.StreamID)
	}
	if filter.State != "" {
		query = query.Where("state = ?", filter.State)
	}
	if !filter.StartTS.IsZero() {
		query = query.Where("start_ts >= ?", filter.StartTS.UnixNano())
	}
	if !filter.EndTS.IsZero() {
		query = query.Where("end_ts <= ?", filter.EndTS.UnixNano())
	}
	if !filter.ExpiryTS.IsZero() {
		query = query.Where("expiry_ts <= ?", filter.ExpiryTS.UnixNano())
	}
	for key, value := range filter.Metadata {
		switch value.(type) {
		case nil:
			query = query.Where("EXISTS (SELECT 1 FROM json_each(recordings.metadata) WHERE key = ? AND type = 'null')", key)
		case string, bool, int, int64, float64:
			query = query.Where("EXISTS (SELECT 1 FROM json_each(recordings.metadata) WHERE key = ? AND value = ?)", key, value)
		default:
			return nil, "", ErrInvalidFilter
		}
	}
	if filter.Cursor != "" {
		if len(filter.Cursor) > 256 {
			return nil, "", ErrInvalidFilter
		}
		decoded, err := base64.RawURLEncoding.DecodeString(filter.Cursor)
		if err != nil {
			return nil, "", ErrInvalidFilter
		}
		timestamp, id, ok := strings.Cut(string(decoded), "\n")
		ns, err := strconv.ParseInt(timestamp, 10, 64)
		if !ok || err != nil || !validRecordingID(id) {
			return nil, "", ErrInvalidFilter
		}
		query = query.Where("(creation_ts < ? OR (creation_ts = ? AND recording_id > ?))", ns, ns, id)
	}
	var records []model.Recording
	if err := query.Order("creation_ts DESC, recording_id ASC").Limit(limit + 1).Find(&records).Error; err != nil {
		return nil, "", err
	}
	next := ""
	if len(records) > limit {
		records = records[:limit]
		last := records[len(records)-1]
		next = base64.RawURLEncoding.EncodeToString([]byte(strconv.FormatInt(last.CreationTS.UnixNano(), 10) + "\n" + last.RecordingID))
	}
	return records, next, nil
}

func (s *MetadataStore) Close() error {
	s.closeOnce.Do(func() {
		if s.sql != nil {
			s.closeErr = errors.Join(s.closeErr, s.sql.Close())
		}
		s.closeErr = errors.Join(s.closeErr, s.lock.Close())
	})
	return s.closeErr
}
