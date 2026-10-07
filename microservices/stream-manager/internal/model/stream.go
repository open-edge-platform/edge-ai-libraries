// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package model

import "time"

// SyncConfidence describes the quality of a live stream's wall-clock mapping.
type SyncConfidence string

const (
	SyncNTPSynced  SyncConfidence = "ntp_synced"
	SyncBestEffort SyncConfidence = "best_effort"
	SyncUnverified SyncConfidence = "unverified"
)

// StreamBuffer is the in-memory state of one attached stream buffer.
type StreamBuffer struct {
	StreamID       string
	SensorID       string
	State          string
	SyncConfidence SyncConfidence
	Slices         []BufferSlice
	BufferStat     BufferStat
	FrameStat      FrameStat
	CreationTS     time.Time
}

// BufferSlice describes one complete MPEG-TS segment in the rolling buffer.
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

type BufferStat struct {
	HeldBytes int64
	Capacity  int
	OldestTS  time.Time
	NewestTS  time.Time
}

type FrameStat struct {
	Framerate     float64
	DroppedFrames int64
}
