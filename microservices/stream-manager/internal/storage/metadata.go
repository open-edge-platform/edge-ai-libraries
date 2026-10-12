// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package storage persists record metadata and the recorded media bytes.
//
// Some disk or network cycles would be traded here.
package storage

import (
	"context"

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
