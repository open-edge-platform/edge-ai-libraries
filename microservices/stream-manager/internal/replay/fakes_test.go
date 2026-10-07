// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage/storagetest"
)

type fakeMediaStore = storagetest.MemoryMediaStore

func newFakeMediaStore() *fakeMediaStore { return storagetest.NewMemoryMediaStore() }

type fakeMetadataStore = storagetest.MemoryMetadataStore

func newFakeMetadataStore(recs ...model.Recording) *fakeMetadataStore {
	return storagetest.NewMemoryMetadataStore(recs...)
}

// fakeExtractor returns synthetic bytes stamped with the requested media
// positions so tests can confirm what was asked of it without ffmpeg.
type fakeExtractor struct {
	frameCalls int
	clipCalls  int
	err        error
	lastFrame  float64
	lastStart  float64
	lastEnd    float64
}

func (e *fakeExtractor) ExtractFrame(_ context.Context, recording io.Reader, mediaTimeSeconds float64, format string) ([]byte, error) {
	e.frameCalls++
	e.lastFrame = mediaTimeSeconds
	if e.err != nil {
		return nil, e.err
	}
	src, _ := io.ReadAll(recording)
	return []byte(fmt.Sprintf("frame:%s:%.3f:%s", format, mediaTimeSeconds, src)), nil
}

func (e *fakeExtractor) ExtractClip(_ context.Context, recording io.Reader, startSeconds, endSeconds float64, format string) ([]byte, error) {
	e.clipCalls++
	e.lastStart, e.lastEnd = startSeconds, endSeconds
	if e.err != nil {
		return nil, e.err
	}
	src, _ := io.ReadAll(recording)
	return []byte(fmt.Sprintf("clip:%s:%.3f-%.3f:%s", format, startSeconds, endSeconds, src)), nil
}

func readyRecording(id string) model.Recording {
	endTS := sidecarBase.Add(time.Hour)
	return model.Recording{
		RecordingID:   id,
		SensorID:      "sensor-01",
		Origin:        model.RecordingOriginLive,
		State:         model.RecordingStateReady,
		StartTS:       sidecarBase,
		EndTS:         &endTS,
		RecordingPath: "recordings/" + id + "/media.mp4",
		CreationTS:    sidecarBase,
		Metadata:      map[string]any{},
	}
}
