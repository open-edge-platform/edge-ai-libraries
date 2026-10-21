// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import "time"

// MediaResult describes a clip or frame produced from a recording.
type MediaResult struct {
	RecordingID      string     `json:"recording_id"`
	SensorID         string     `json:"sensor_id"`
	MediaType        string     `json:"-"`
	ContentType      string     `json:"-"`
	RequestedStartTS time.Time  `json:"requested_start_ts"`
	RequestedEndTS   *time.Time `json:"requested_end_ts"`
	StartTS          time.Time  `json:"start_ts"`
	EndTS            *time.Time `json:"end_ts"`
	URL              string     `json:"url"`
	ExpiryTS         time.Time  `json:"expiry_ts"`
}
