// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import "time"

// Recording states. Retrieval only serves media for RecordingStateReady.
const (
	RecordingStateRecording  = "recording"
	RecordingStateFinalizing = "finalizing"
	RecordingStateReady      = "ready"
	RecordingStateFailed     = "failed"
)

// Recording origins.
const (
	RecordingOriginLive   = "live"
	RecordingOriginImport = "import"
)

// Recording is the canonical metadata for a recording. Wall-clock instants
// are carried as time.Time throughout the domain and API; the Unix-nanosecond
// representation exists only inside the persistence layer.
type Recording struct {
	RecordingID   string         `json:"recording_id"`
	SensorID      string         `json:"sensor_id"`
	StreamID      string         `json:"stream_id,omitempty"`
	Origin        string         `json:"origin"`
	State         string         `json:"state"`
	StartTS       time.Time      `json:"start_ts"`
	EndTS         *time.Time     `json:"end_ts,omitempty"`
	RecordingPath string         `json:"recording_path"`
	Codec         string         `json:"codec,omitempty"`
	Container     string         `json:"container,omitempty"`
	SizeBytes     int64          `json:"size_bytes,omitempty"`
	Metadata      map[string]any `json:"metadata"`
	CreationTS    time.Time      `json:"creation_ts"`
	ExpiryTS      *time.Time     `json:"expiry_ts,omitempty"`
	ErrorDetails  string         `json:"error_details,omitempty"`
}

// RecordingFilter selects recording rows for the records API. Zero-valued
// fields are not applied; Cursor is an opaque pagination token.
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

// IsReady reports whether the recording is in a state retrieval can serve.
func (r Recording) IsReady() bool {
	return r.State == RecordingStateReady
}

// IsLive reports whether the recording is actively being written. There is
// no dedicated "live" column: a recording is live precisely when it is still
// in state "recording" and has not yet been assigned an end_ts.
func (r Recording) IsLive() bool {
	return r.State == RecordingStateRecording && r.EndTS == nil
}

// IsServable reports whether retrieval can resolve and extract media for
// this recording, covering both a finalized recording and one still being
// written. It rejects the states that indicate an in-progress producer
// operation (finalizing) or a permanently unusable one (failed), and it
// rejects any state/end_ts combination that the producer contract forbids
// (a finalized recording with no end_ts, or a live recording that already
// has one).
func (r Recording) IsServable() bool {
	switch r.State {
	case RecordingStateReady:
		return r.EndTS != nil
	case RecordingStateRecording:
		return r.EndTS == nil
	default:
		return false
	}
}

// FrameRequest describes a single-frame retrieval request. Fields are
// populated by hand from the request context rather than via framework
// struct-tag binding, so no form:/uri:/binding: tags are used here.
type FrameRequest struct {
	RecordingID string
	StartTS     time.Time
	Format      string
	Match       string
}

// ClipRequest describes a clip retrieval request. Exactly one of EndTS or
// ClipDuration is supplied by the caller; the handler rejects the request
// before it reaches the retrieval service otherwise.
type ClipRequest struct {
	RecordingID  string
	StartTS      time.Time
	EndTS        *time.Time
	ClipDuration *float64
	Format       string
}

// MediaResult is returned for both frame and clip retrieval.
type MediaResult struct {
	RecordingID      string     `json:"recording_id"`
	SensorID         string     `json:"sensor_id"`
	MediaType        string     `json:"media_type"`
	ContentType      string     `json:"content_type"`
	RequestedStartTS time.Time  `json:"requested_start_ts"`
	RequestedEndTS   *time.Time `json:"requested_end_ts,omitempty"`
	StartTS          time.Time  `json:"start_ts"`
	EndTS            *time.Time `json:"end_ts,omitempty"`
	ExactMatch       bool       `json:"exact_match"`
	URL              string     `json:"url"`
	ExpiryTS         time.Time  `json:"expiry_ts"`
	DerivedKey       string     `json:"-"`
}

// ErrorResponse is returned on validation and retrieval errors.
type ErrorResponse struct {
	Status       int    `json:"status"`
	ErrorCode    string `json:"error_code"`
	ErrorDetails string `json:"error_details"`
}
