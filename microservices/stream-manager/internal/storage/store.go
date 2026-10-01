// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"golang.org/x/sys/unix"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

var (
	ErrNotFound      = errors.New("record not found")
	ErrInvalidFilter = errors.New("invalid recording filter or cursor")
)

const recordsSchema = `
CREATE TABLE IF NOT EXISTS records (
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
CREATE INDEX IF NOT EXISTS idx_records_sensor_stream ON records(sensor_id, stream_id);`

// Store owns the SQLite connection and the private recording filesystem root.
type Store struct {
	db        *gorm.DB
	sql       *sql.DB
	root      *os.Root
	lock      *os.File
	closeOnce sync.Once
	closeErr  error
}

var _ MetadataHandler = (*Store)(nil)
var _ MediaHandler = (*Store)(nil)

func Open(directory string) (_ *Store, result error) {
	absolute, err := filepath.Abs(directory)
	if err != nil || absolute == "/" {
		return nil, errors.New("invalid recording storage directory")
	}
	if err := os.MkdirAll(absolute, 0o700); err != nil {
		return nil, err
	}
	root, err := os.OpenRoot(absolute)
	if err != nil {
		return nil, err
	}
	s := &Store{root: root}
	defer func() {
		if result != nil {
			result = errors.Join(result, s.Close())
		}
	}()
	directoryHandle, err := root.Open(".")
	if err != nil {
		return nil, err
	}
	var stat unix.Stat_t
	statErr := unix.Fstat(int(directoryHandle.Fd()), &stat)
	if err := errors.Join(statErr, directoryHandle.Close()); err != nil {
		return nil, err
	}
	if stat.Uid != uint32(os.Geteuid()) || stat.Mode&0o077 != 0 {
		return nil, errors.New("SM_STORAGE_DIR must be private (0700) and owned by the service user")
	}
	s.lock, err = root.OpenFile(".lock", os.O_CREATE|os.O_RDWR|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil, err
	}
	if err := unix.Flock(int(s.lock.Fd()), unix.LOCK_EX|unix.LOCK_NB); err != nil {
		return nil, errors.New("recording storage is already in use by another instance")
	}
	dbFile, err := root.OpenFile("stream-manager.db", os.O_CREATE|os.O_RDWR|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil, err
	}
	if err := dbFile.Close(); err != nil {
		return nil, err
	}
	dsn := (&url.URL{Scheme: "file", Path: filepath.Join(absolute, "stream-manager.db")}).String()
	dsn += "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(1)"
	db, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{
		Logger: logger.New(log.New(os.Stderr, "", log.LstdFlags), logger.Config{
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
	if err := db.Transaction(func(tx *gorm.DB) error { return tx.Exec(recordsSchema).Error }); err != nil {
		return nil, fmt.Errorf("initialize records schema: %w", err)
	}
	return s, nil
}

func (s *Store) CreateBatch(ctx context.Context, records []model.Recording) ([]model.Recording, error) {
	if len(records) == 0 {
		return nil, errors.New("no recordings to create")
	}
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		return tx.Create(&records).Error
	})
	return records, err
}

func (s *Store) CreateMetadata(ctx context.Context, metadata model.Recording) (model.Recording, error) {
	records, err := s.CreateBatch(ctx, []model.Recording{metadata})
	if err != nil {
		return model.Recording{}, err
	}
	return records[0], nil
}

func (s *Store) GetMetadataByRecordingID(ctx context.Context, id string) (model.Recording, error) {
	var rec model.Recording
	err := s.db.WithContext(ctx).Where("recording_id = ?", id).First(&rec).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		err = ErrNotFound
	}
	return rec, err
}

func (s *Store) UpdateMetadata(ctx context.Context, id string, rec model.Recording) (model.Recording, error) {
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

func (s *Store) DeleteMetadata(ctx context.Context, id string) error {
	result := s.db.WithContext(ctx).Where("recording_id = ?", id).Delete(&model.Recording{})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Store) ListMetadata(ctx context.Context, filter model.RecordingFilter) ([]model.Recording, string, error) {
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
		query = query.Where("(end_ts IS NULL OR end_ts > ?)", filter.StartTS.UnixNano())
	}
	if !filter.EndTS.IsZero() {
		query = query.Where("start_ts < ?", filter.EndTS.UnixNano())
	}
	if !filter.ExpiryTS.IsZero() {
		query = query.Where("expiry_ts <= ?", filter.ExpiryTS.UnixNano())
	}
	for key, value := range filter.Metadata {
		switch value.(type) {
		case nil:
			query = query.Where("EXISTS (SELECT 1 FROM json_each(records.metadata) WHERE key = ? AND type = 'null')", key)
		case string, bool, int, int64, float64:
			query = query.Where("EXISTS (SELECT 1 FROM json_each(records.metadata) WHERE key = ? AND value = ?)", key, value)
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

func (s *Store) RecoverInterrupted(ctx context.Context) error {
	var records []model.Recording
	if err := s.db.WithContext(ctx).Where("state IN ?", []string{"recording", "finalizing"}).Find(&records).Error; err != nil {
		return err
	}
	for _, rec := range records {
		detail := "recording interrupted by service restart"
		rec.State, rec.ErrorDetail = "failed", &detail
		if _, err := s.UpdateMetadata(ctx, rec.RecordingID, rec); err != nil {
			return err
		}
		if err := s.DeleteMedia(ctx, rec.RecordingPath); err != nil {
			return fmt.Errorf("clean interrupted recording %s: %w", rec.RecordingID, err)
		}
	}
	return nil
}

func validRecordingID(id string) bool {
	parsed, err := uuid.Parse(id)
	return err == nil && parsed.String() == id
}

func (s *Store) Close() error {
	s.closeOnce.Do(func() {
		if s.sql != nil {
			s.closeErr = errors.Join(s.closeErr, s.sql.Close())
		}
		if s.lock != nil {
			s.closeErr = errors.Join(s.closeErr, s.lock.Close())
		}
		s.closeErr = errors.Join(s.closeErr, s.root.Close())
	})
	return s.closeErr
}
