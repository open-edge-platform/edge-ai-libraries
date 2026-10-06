// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package record handles recording of attached streams.
package record

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math"
	"os/exec"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

// Recorder starts, stops and deletes recordings.
type Recorder interface {
	StartRecording(ctx context.Context, sensorID string, streamID string, startTS time.Time, endTS time.Time, preEventDuration int, metadata map[string]any) (model.Recording, error)
	StopRecording(ctx context.Context, recordingID string) error
	DeleteRecording(ctx context.Context, recordingID string) error
}

var (
	ErrInvalidRequest = errors.New("invalid recording request")
	ErrConflict       = errors.New("recording cannot be changed in its current state")
	ErrCapacity       = errors.New("recording capacity reached")
	ErrCleanup        = errors.New("recording storage cleanup failed")
)

// StartOptions describes one recording of a single attached stream.
// TODO: accept several stream IDs and admit their recordings atomically.
type StartOptions struct {
	StreamID string
	StartTS  time.Time
	Duration *time.Duration
	PreEvent time.Duration
	Metadata map[string]any
}

// Service owns recording workers; Store remains open until Close completes.
type Service struct {
	mu        sync.Mutex
	buffers   stream.Bufferer
	store     *storage.Store
	ffmpeg    string
	ffprobe   string
	max       int
	jobs      map[string]*job
	wg        sync.WaitGroup
	closed    bool
	closeOnce sync.Once
	closeErr  error
	now       func() time.Time
}

type job struct {
	record   model.Recording
	id       string
	uri      string
	lease    *stream.BufferLease
	filename string
	fixed    bool
	stopped  bool
	ctx      context.Context
	cancel   context.CancelFunc
	err      error
}

var _ Recorder = (*Service)(nil)

func NewService(buffers stream.Bufferer, store *storage.Store, concurrentRecordings int) (*Service, error) {
	if concurrentRecordings < 1 || concurrentRecordings > 1024 {
		return nil, ErrInvalidRequest
	}
	ffmpeg, err := exec.LookPath("ffmpeg")
	if err != nil {
		return nil, err
	}
	ffprobe, err := exec.LookPath("ffprobe")
	if err != nil {
		return nil, err
	}
	return &Service{
		buffers: buffers, store: store, ffmpeg: ffmpeg, ffprobe: ffprobe, max: concurrentRecordings,
		jobs: make(map[string]*job), now: time.Now,
	}, nil
}

func Seconds(value float64) (time.Duration, error) {
	ns := value * float64(time.Second)
	if math.IsNaN(ns) || math.IsInf(ns, 0) || ns < 0 || ns >= float64(math.MaxInt64) ||
		(value > 0 && ns < 1) {
		return 0, ErrInvalidRequest
	}
	return time.Duration(math.Round(ns)), nil
}

// Start admits a recording of one stream; the requested history must be buffered.
func (s *Service) Start(ctx context.Context, options StartOptions) (model.Recording, error) {
	if options.StreamID == "" || options.StartTS.IsZero() || options.StartTS.After(s.now()) ||
		options.PreEvent < 0 || options.PreEvent > 300*time.Second ||
		(options.Duration != nil && *options.Duration <= 0) {
		return model.Recording{}, ErrInvalidRequest
	}
	start := options.StartTS.Add(-options.PreEvent)
	end := time.Time{}
	if options.Duration != nil {
		end = options.StartTS.Add(*options.Duration)
	}
	if !time.Unix(0, start.UnixNano()).Equal(start) ||
		(!end.IsZero() && !time.Unix(0, end.UnixNano()).Equal(end)) {
		return model.Recording{}, ErrInvalidRequest
	}
	metadata := map[string]any{}
	if options.Metadata != nil {
		encoded, err := json.Marshal(options.Metadata)
		if err != nil {
			return model.Recording{}, ErrInvalidRequest
		}
		if err := json.Unmarshal(encoded, &metadata); err != nil {
			return model.Recording{}, err
		}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return model.Recording{}, ErrConflict
	}
	if len(s.jobs) >= s.max {
		return model.Recording{}, ErrCapacity
	}
	info, err := s.buffers.GetStream(ctx, options.StreamID)
	if err != nil {
		return model.Recording{}, err
	}
	if info.State != "buffering" || info.SyncConfidence != model.SyncNTPSynced ||
		info.BufferStat.OldestTS.IsZero() || start.Before(info.BufferStat.OldestTS) {
		return model.Recording{}, stream.ErrHistoryUnavailable
	}
	workerCtx, cancel := context.WithCancel(context.Background())
	lease, err := s.buffers.AcquireBuffer(workerCtx, info.StreamID, start, end)
	if err != nil {
		cancel()
		return model.Recording{}, err
	}
	j := &job{lease: lease, ctx: workerCtx, cancel: cancel, fixed: options.Duration != nil}
	rollback := func(cause error) error {
		cancel()
		cause = errors.Join(cause, lease.Close())
		if j.uri != "" {
			cause = errors.Join(cause, s.store.DeleteMedia(context.Background(), j.uri))
		}
		return cause
	}
	if lease.StartTime().IsZero() {
		return model.Recording{}, rollback(stream.ErrHistoryUnavailable)
	}
	recordID, err := uuid.NewRandom()
	if err != nil {
		return model.Recording{}, rollback(err)
	}
	filename, uri, err := s.store.PrepareMedia(ctx, recordID.String())
	if err != nil {
		return model.Recording{}, rollback(err)
	}
	j.id, j.uri, j.filename = recordID.String(), uri, filename
	streamID := info.StreamID
	j.record = model.Recording{
		RecordingID: j.id, SensorID: info.SensorID, StreamID: &streamID,
		StartTS: lease.StartTime(), RecordingPath: uri, State: "recording",
		Metadata: metadata, CreationTS: s.now().UTC(),
	}
	if !end.IsZero() {
		target := end.UTC()
		j.record.EndTS = &target
	}
	rec, err := s.store.CreateMetadata(ctx, j.record)
	if err != nil {
		return model.Recording{}, rollback(err)
	}
	j.record = rec
	s.jobs[rec.RecordingID] = j
	s.wg.Go(func() { s.run(j) })
	return rec, nil
}

// StartRecording implements Recorder for one stream; sensorID is ignored
// because recordings are selected by stream ID only.
func (s *Service) StartRecording(ctx context.Context, _ string, streamID string, start, end time.Time,
	preEventDuration int, metadata map[string]any,
) (model.Recording, error) {
	options := StartOptions{
		StreamID: streamID, StartTS: start, Metadata: metadata,
		PreEvent: time.Duration(preEventDuration) * time.Second,
	}
	if !end.IsZero() {
		duration := end.Sub(start)
		options.Duration = &duration
	}
	return s.Start(ctx, options)
}

func (s *Service) Stop(ctx context.Context, id string) (model.Recording, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec, err := s.store.GetMetadataByRecordingID(ctx, id)
	if err != nil {
		return rec, false, err
	}
	if rec.State == "ready" {
		return rec, false, nil
	}
	j := s.jobs[id]
	if j == nil || j.fixed || rec.State == "failed" {
		return rec, false, ErrConflict
	}
	if j.stopped {
		return rec, true, nil
	}
	target := s.now().UTC()
	if err := j.lease.SetEnd(target); err != nil {
		return rec, false, err
	}
	rec.State, rec.EndTS = "finalizing", &target
	rec, err = s.store.UpdateMetadata(ctx, id, rec)
	if err != nil {
		j.cancel()
		return rec, false, err
	}
	j.record, j.stopped = rec, true
	return rec, true, nil
}

func (s *Service) StopRecording(ctx context.Context, id string) error {
	_, _, err := s.Stop(ctx, id)
	return err
}

func (s *Service) Get(ctx context.Context, id string) (model.Recording, error) {
	return s.store.GetMetadataByRecordingID(ctx, id)
}

func (s *Service) List(ctx context.Context, filter model.RecordingFilter) ([]model.Recording, string, error) {
	return s.store.ListMetadata(ctx, filter)
}

func (s *Service) DeleteRecording(ctx context.Context, id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec, err := s.store.GetMetadataByRecordingID(ctx, id)
	if err != nil {
		return err
	}
	if rec.State == "recording" || rec.State == "finalizing" || s.jobs[id] != nil {
		return ErrConflict
	}
	if err := s.store.DeleteMedia(ctx, rec.RecordingPath); err != nil {
		return fmt.Errorf("%w: %w", ErrCleanup, err)
	}
	if err := s.store.DeleteMetadata(ctx, id); err != nil {
		return fmt.Errorf("%w: %w", ErrCleanup, err)
	}
	return nil
}

func (s *Service) run(j *job) {
	defer j.cancel()
	start, end, size, codec, err := s.writeMedia(j)
	err = errors.Join(err, j.lease.Close())
	s.mu.Lock()
	defer s.mu.Unlock()
	defer delete(s.jobs, j.record.RecordingID)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err == nil {
		j.record.StartTS, j.record.EndTS = start, &end
		j.record.State, j.record.SizeBytes, j.record.Codec = "ready", &size, &codec
		_, err = s.store.UpdateMetadata(ctx, j.record.RecordingID, j.record)
	}
	if err != nil {
		detail := "recording could not be completed"
		if errors.Is(err, stream.ErrSliceExpired) {
			detail = "a required buffer slice exceeded its retention grace period"
		} else if errors.Is(err, stream.ErrSourceFailed) {
			detail = "recording source became unavailable"
		} else if j.ctx.Err() != nil {
			detail = "recording interrupted before completion"
		}
		j.record.State, j.record.SizeBytes, j.record.ErrorDetail = "failed", nil, &detail
		_, saveErr := s.store.UpdateMetadata(ctx, j.record.RecordingID, j.record)
		cleanupErr := s.store.DeleteMedia(ctx, j.record.RecordingPath)
		j.err = errors.Join(saveErr, cleanupErr)
		s.closeErr = errors.Join(s.closeErr, j.err)
		log.Printf("recording %s failed: %v", j.record.RecordingID, errors.Join(err, j.err))
	}
}

func (s *Service) Close() error {
	s.closeOnce.Do(func() {
		s.mu.Lock()
		s.closed = true
		for _, j := range s.jobs {
			j.cancel()
		}
		s.mu.Unlock()
		s.wg.Wait()
	})
	return s.closeErr
}
