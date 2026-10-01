// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import "time"

// SyncConfidence tells how far a stream's timestamps can be trusted.
type SyncConfidence string

const (
	SyncNTPSynced  SyncConfidence = "ntp_synced"
	SyncBestEffort SyncConfidence = "best_effort"
	SyncUnverified SyncConfidence = "unverified"
)

// StreamBuffer is the in-memory state of one attached stream's buffer.
type StreamBuffer struct {
	StreamID       string
	SensorID       string
	State          string
	SyncConfidence SyncConfidence
	Slices         []BufferSlice
	BufferStat     bufferStat
	FrameStat      frameStat
	CreationTS     time.Time
}

// BufferSlice is one MPEG-TS segment held in the buffer.
type BufferSlice struct {
	SeqNo      int
	StartTS    time.Time
	EndTS      time.Time
	Path       string
	PTSStart   int
	PTSEnd     int
	SizeBytes  int64
	KeyframeTS *time.Time
	RefCount   int
}

type bufferStat struct {
	HeldBytes int64
	Capacity  int
	OldestTS  time.Time
	NewestTS  time.Time
}

type frameStat struct {
	Framerate     float64
	DroppedFrames int64
}
