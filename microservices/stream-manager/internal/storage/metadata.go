// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

// ErrRecordingNotFound reports that no recording row exists for the
// requested identifier.
var ErrRecordingNotFound = errors.New("recording not found")

var ErrInvalidRecordingFilter = errors.New("invalid recording filter or cursor")

// RecordingMetadataStore is the production metadata seam for recordings: one
// row per recording_id, with state constrained to
// recording | finalizing | ready | failed. Retrieval only reads a recording
// by ID and requires state == "ready" before resolving media; it never
// queries or mutates the underlying table directly.
type RecordingMetadataStore interface {
	// GetByID returns the recording's metadata, or ErrRecordingNotFound if
	// no recording with that ID exists. It does not filter by state;
	// callers decide which states are retrievable.
	GetByID(ctx context.Context, recordingID string) (model.Recording, error)
	// Exists reports whether a recording row is present, without
	// materialising the whole row.
	Exists(ctx context.Context, recordingID string) (bool, error)
}

// RecordingLifecycleStore is the optional write/list capability used by the
// stream recorder. Retrieval continues to depend only on RecordingMetadataStore.
type RecordingLifecycleStore interface {
	RecordingMetadataStore
	CreateBatch(ctx context.Context, recordings []model.Recording) ([]model.Recording, error)
	GetMetadataByRecordingID(ctx context.Context, recordingID string) (model.Recording, error)
	UpdateMetadata(ctx context.Context, recordingID string, recording model.Recording) (model.Recording, error)
	ListMetadata(ctx context.Context, filter model.RecordingFilter) ([]model.Recording, string, error)
	DeleteMetadata(ctx context.Context, recordingID string) error
}
