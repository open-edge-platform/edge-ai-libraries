// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import "time"

// MediaResult describes a clip or frame produced from a recording.
type MediaResult struct {
	RecordingID      string
	SensorID         string
	MediaType        string
	ContentType      string
	RequestedStartTS time.Time
	RequestedEndTS   *time.Time
	StartTS          time.Time
	EndTS            *time.Time
	URL              string
	ExpiryTS         time.Time
}
