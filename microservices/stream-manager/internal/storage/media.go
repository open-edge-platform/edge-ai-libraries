// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package storage persists record metadata and the recorded media bytes..
package storage

import "context"

// MediaHandler saves, opens and deletes recorded media files.
type MediaHandler interface {
	PutMedia(ctx context.Context, recordingPath string) (string, error)
	OpenMedia(ctx context.Context, recordingPath string) (string, error)
	DeleteMedia(ctx context.Context, recordingPath string) error
}
