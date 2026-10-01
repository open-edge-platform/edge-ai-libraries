// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package replay handles the retrieval of recorded streams.
package replay

import (
	"context"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

// Replayer extracts clips and frames from recorded media.
type Replayer interface {
	ExtractClip(ctx context.Context, recordingID string, startTS time.Time, clipDuration int, format string) ([]byte, error)
	GetClipURL(ctx context.Context, recordingID string, startTS time.Time, clipDuration int, format string) (model.MediaResult, error)
	ExtractFrame(ctx context.Context, recordingID string, timestamp time.Time, format string, match string) ([]byte, error)
	GetFrameURL(ctx context.Context, recordingID string, timestamp time.Time, format string, match string) (model.MediaResult, error)
}
