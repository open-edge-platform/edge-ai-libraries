// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package model defines the domain types shared across the service.
package model

import (
	"context"
	"fmt"
	"reflect"
	"time"

	"gorm.io/gorm/schema"
)

// Recording is one row of the records table.
type Recording struct {
	RecordingID   string         `gorm:"column:recording_id;type:text;primaryKey"`
	SensorID      string         `gorm:"column:sensor_id;type:text;not null;index:idx_records_sensor_stream,priority:1"`
	StreamID      *string        `gorm:"column:stream_id;type:text;index:idx_records_sensor_stream,priority:2"`
	StartTS       time.Time      `gorm:"column:start_ts;type:integer;not null;serializer:unixnano"`
	EndTS         *time.Time     `gorm:"column:end_ts;type:integer;serializer:unixnano;check:end_ts IS NULL OR end_ts > start_ts"`
	RecordingPath string         `gorm:"column:recording_path;type:text;not null"`
	Codec         *string        `gorm:"column:codec;type:text"`
	State         string         `gorm:"column:state;type:text;not null;check:state IN ('recording','finalizing','ready','failed')"`
	SizeBytes     *int64         `gorm:"column:size_bytes;type:integer;check:size_bytes IS NULL OR size_bytes >= 0"`
	Metadata      map[string]any `gorm:"column:metadata;type:text;not null;default:'{}';serializer:json"`
	CreationTS    time.Time      `gorm:"column:creation_ts;type:integer;not null;serializer:unixnano"`
	ExpiryTS      *time.Time     `gorm:"column:expiry_ts;type:integer;serializer:unixnano"`
	ErrorDetail   *string        `gorm:"column:error_detail;type:text"`
}

// TableName keeps GORM from pluralising the table to "recordings".
func (Recording) TableName() string { return "records" }

// RecordingFilter selects recordings; zero-valued fields are not applied.
type RecordingFilter struct {
	SensorID string
	StreamID string
	StartTS  time.Time
	EndTS    time.Time
	ExpiryTS time.Time
	State    string
	Metadata map[string]any
	Cursor   string
	Limit    int
}

func init() {
	schema.RegisterSerializer("unixnano", unixNanoSerializer{})
}

// Bounds of int64 nanoseconds since 1970.
var (
	minUnixNano = time.Unix(0, -1<<63)
	maxUnixNano = time.Unix(0, 1<<63-1)
)

// unixNanoSerializer stores time.Time and *time.Time as INTEGER nanoseconds
// since 1970 in UTC; a nil *time.Time is stored as NULL.
type unixNanoSerializer struct{}

func (unixNanoSerializer) Scan(ctx context.Context, field *schema.Field, dst reflect.Value, dbValue any) error {
	switch v := dbValue.(type) {
	case nil:
		return field.Set(ctx, dst, nil)
	case int64:
		return field.Set(ctx, dst, time.Unix(0, v).UTC())
	default:
		return fmt.Errorf("unixnano: cannot scan %T into %s", dbValue, field.Name)
	}
}

func (unixNanoSerializer) Value(_ context.Context, field *schema.Field, _ reflect.Value, fieldValue any) (any, error) {
	var t time.Time
	switch v := fieldValue.(type) {
	case time.Time:
		t = v
	case *time.Time:
		if v == nil {
			return nil, nil
		}
		t = *v
	default:
		return nil, fmt.Errorf("unixnano: unsupported type %T for %s", fieldValue, field.Name)
	}
	if t.Before(minUnixNano) || t.After(maxUnixNano) {
		return nil, fmt.Errorf("unixnano: %s out of range for %s", t.Format(time.RFC3339Nano), field.Name)
	}
	return t.UnixNano(), nil
}
