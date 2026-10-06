// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package stream handles stream attachment and related operations.
package stream

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"golang.org/x/sys/unix"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

// AttachmentConflict identifies the existing attachment without exposing its source.
type AttachmentConflict struct {
	StreamID string
}

func (e *AttachmentConflict) Error() string {
	return fmt.Sprintf("sensor is already attached as %s", e.StreamID)
}

func (*AttachmentConflict) Unwrap() error { return ErrStreamExists }

// Service owns stream ingestion and only the directories it creates.
type Service struct {
	mu        sync.RWMutex
	root      *os.Root
	cfg       config.Config
	ffmpeg    string
	streams   map[string]*attachedStream
	sensors   map[string]string
	wg        sync.WaitGroup
	closed    bool
	closeOnce sync.Once
	closeErr  error
	ingest    func(context.Context, string, string, *RollingBuffer, func(bool), func(), time.Duration) error
}

type attachedStream struct {
	mu          sync.Mutex
	id          string
	sensor      string
	directory   string
	created     time.Time
	state       string
	synced      bool
	arrivals    []time.Time
	dropped     int64
	buffer      *RollingBuffer
	cancel      context.CancelFunc
	done        chan struct{}
	closeErr    error
	statsErrors chan error
}

var _ Bufferer = (*Service)(nil)

func NewService(cfg config.Config) (*Service, error) {
	if !filepath.IsAbs(cfg.BufferDir) || filepath.Clean(cfg.BufferDir) == "/" {
		return nil, errors.New("SM_BUFFER_DIR must be an absolute private tmpfs directory")
	}
	executable, err := exec.LookPath("ffmpeg")
	if err != nil {
		return nil, fmt.Errorf("FFmpeg is required for buffering: %w", err)
	}
	if err := os.MkdirAll(cfg.BufferDir, 0o700); err != nil {
		return nil, fmt.Errorf("create buffer root: %w", err)
	}
	root, err := os.OpenRoot(cfg.BufferDir)
	if err != nil {
		return nil, err
	}
	if err := validateBufferRoot(root); err != nil {
		return nil, errors.Join(err, root.Close())
	}
	return &Service{
		root: root, cfg: cfg, ffmpeg: executable, ingest: runIngest,
		streams: make(map[string]*attachedStream), sensors: make(map[string]string),
	}, nil
}

func validateBufferRoot(root *os.Root) (result error) {
	f, err := root.Open(".")
	if err != nil {
		return err
	}
	defer func() { result = errors.Join(result, f.Close()) }()
	var fs unix.Statfs_t
	if err := unix.Fstatfs(int(f.Fd()), &fs); err != nil {
		return err
	}
	if fs.Type != unix.TMPFS_MAGIC {
		return errors.New("SM_BUFFER_DIR must be on tmpfs")
	}
	var stat unix.Stat_t
	if err := unix.Fstat(int(f.Fd()), &stat); err != nil {
		return err
	}
	if stat.Uid != uint32(os.Geteuid()) || stat.Mode&0o077 != 0 {
		return errors.New("SM_BUFFER_DIR must be owned by the service user with private permissions (0700)")
	}
	return nil
}

// CreateBuffer attaches a source; a zero bufferLength uses the configured default.
func (s *Service) CreateBuffer(ctx context.Context, sourceURI, sensorID string, bufferLength time.Duration) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	if bufferLength == 0 {
		bufferLength = s.cfg.BufferLength
	} else if bufferLength < config.MinBufferLength || bufferLength > config.MaxBufferLength {
		return "", ErrInvalidRequest
	}
	// HTTP validation applies the identifier contract; this also protects callers
	// inside the service from turning an identifier into a filesystem path.
	if sensorID == "" || len(sensorID) > 128 || !filepath.IsLocal(sensorID) ||
		filepath.Base(sensorID) != sensorID || strings.ContainsAny(sensorID, "\\\x00") {
		return "", ErrInvalidRequest
	}
	u, err := url.Parse(sourceURI)
	if err != nil || len(sourceURI) > 2048 || u.Host == "" || u.User != nil ||
		(u.Scheme != "rtsp" && u.Scheme != "rtsps") {
		return "", ErrUnsupportedSource
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return "", ErrBufferClosed
	}
	if existing := s.sensors[sensorID]; existing != "" {
		return "", &AttachmentConflict{StreamID: existing}
	}
	id, err := uuid.NewRandom()
	if err != nil {
		return "", err
	}
	streamID := "str-" + id.String()
	directory := sensorID + "-" + streamID
	if err := s.root.Mkdir(directory, 0o700); err != nil {
		return "", fmt.Errorf("create stream buffer: %w", err)
	}
	buffer, err := newRollingBuffer(filepath.Join(s.root.Name(), directory), bufferLength)
	if err != nil {
		return "", errors.Join(err, s.root.Remove(directory))
	}
	workerCtx, cancel := context.WithCancel(context.Background())
	entry := &attachedStream{
		id: streamID, sensor: sensorID, directory: directory, created: time.Now().UTC(),
		state: "connecting", buffer: buffer, cancel: cancel, done: make(chan struct{}),
		statsErrors: make(chan error, 1),
	}
	s.streams[streamID], s.sensors[sensorID] = entry, streamID
	s.wg.Go(func() { s.run(workerCtx, entry, sourceURI) })
	return streamID, nil
}

func (s *Service) run(ctx context.Context, entry *attachedStream, source string) {
	defer close(entry.done)
	ingestCtx, stopIngest := context.WithCancel(ctx)
	defer stopIngest()
	finished := make(chan error, 1)
	go func() {
		finished <- s.ingest(ingestCtx, s.ffmpeg, source, entry.buffer, entry.frame, func() {
			entry.mu.Lock()
			if entry.state != "failed" {
				entry.state, entry.synced = "buffering", true
			}
			entry.mu.Unlock()
		}, ingestTimeout)
	}()
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			if finished != nil {
				<-finished
			}
			entry.closeErr = errors.Join(entry.buffer.Close(), s.root.RemoveAll(entry.directory))
			return
		case err := <-finished:
			finished = nil
			if ctx.Err() == nil {
				if err == nil {
					err = ErrSourceFailed
				}
				entry.fail(err)
			}
		case err := <-entry.statsErrors:
			stopIngest()
			entry.fail(err)
		case now := <-ticker.C:
			if err := entry.buffer.expire(now); err != nil {
				stopIngest()
				entry.fail(err)
			}
		}
	}
}

func (e *attachedStream) fail(err error) {
	e.mu.Lock()
	wasFailed := e.state == "failed"
	e.state = "failed"
	e.mu.Unlock()
	e.buffer.fail(err)
	if !wasFailed {
		log.Printf("stream %s failed: %v", e.id, err)
	}
}

func (e *attachedStream) frame(dropped bool) {
	now := time.Now()
	e.mu.Lock()
	defer e.mu.Unlock()
	if dropped {
		e.dropped++
		return
	}
	e.pruneArrivals(now)
	if len(e.arrivals) >= 8192 {
		e.dropped++
		select {
		case e.statsErrors <- errors.New("source exceeds the bounded frame-rate tracking window"):
		default:
		}
		return
	}
	e.arrivals = append(e.arrivals, now)
}

func (e *attachedStream) pruneArrivals(now time.Time) {
	cutoff := now.Add(-time.Second)
	n := 0
	for n < len(e.arrivals) && !e.arrivals[n].After(cutoff) {
		n++
	}
	copy(e.arrivals, e.arrivals[n:])
	e.arrivals = e.arrivals[:len(e.arrivals)-n]
}

func (e *attachedStream) snapshot() (model.StreamBuffer, error) {
	result := e.buffer.snapshot()
	held, err := e.buffer.diskUsage()
	if err != nil {
		return result, err
	}
	result.BufferStat.HeldBytes = held
	e.mu.Lock()
	defer e.mu.Unlock()
	e.pruneArrivals(time.Now())
	result.StreamID, result.SensorID, result.CreationTS = e.id, e.sensor, e.created
	result.State, result.SyncConfidence = e.state, model.SyncUnverified
	if e.synced {
		result.SyncConfidence = model.SyncNTPSynced
	}
	result.FrameStat.Framerate = float64(len(e.arrivals))
	result.FrameStat.DroppedFrames = e.dropped
	return result, nil
}

func (s *Service) GetStream(ctx context.Context, streamID string) (model.StreamBuffer, error) {
	if err := ctx.Err(); err != nil {
		return model.StreamBuffer{}, err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	entry := s.streams[streamID]
	if entry == nil {
		return model.StreamBuffer{}, ErrStreamNotFound
	}
	return entry.snapshot()
}

func (s *Service) ListStreams(ctx context.Context) ([]model.StreamBuffer, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]model.StreamBuffer, 0, len(s.streams))
	for _, entry := range s.streams {
		info, err := entry.snapshot()
		if err != nil {
			return nil, err
		}
		result = append(result, info)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].StreamID < result[j].StreamID })
	return result, nil
}

func (s *Service) GetBuffer(ctx context.Context, streamID string, start, end time.Time) ([]model.BufferSlice, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	entry := s.streams[streamID]
	if entry == nil {
		return nil, ErrStreamNotFound
	}
	return entry.buffer.Get(start, end)
}

func (s *Service) AcquireBuffer(ctx context.Context, streamID string, start, end time.Time) (*BufferLease, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	entry := s.streams[streamID]
	if entry == nil {
		return nil, ErrStreamNotFound
	}
	return entry.buffer.Acquire(ctx, start, end)
}

// ResizeBuffer is not implemented yet; the length is fixed when the stream is created.
// TODO: implement resizing for PUT /streams/{stream-id}/buffer.
func (s *Service) ResizeBuffer(context.Context, string, int) (model.StreamBuffer, error) {
	return model.StreamBuffer{}, ErrNotImplemented
}

func (s *Service) RemoveBuffer(ctx context.Context, streamID string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	s.mu.Lock()
	entry := s.streams[streamID]
	if entry == nil {
		s.mu.Unlock()
		return ErrStreamNotFound
	}
	if entry.buffer.hasReaders() {
		s.mu.Unlock()
		return ErrActiveReaders
	}
	delete(s.streams, streamID)
	delete(s.sensors, entry.sensor)
	entry.cancel()
	s.mu.Unlock()
	<-entry.done
	return entry.closeErr
}

func (s *Service) Close() error {
	s.closeOnce.Do(func() {
		s.mu.Lock()
		s.closed = true
		entries := make([]*attachedStream, 0, len(s.streams))
		for _, entry := range s.streams {
			entries = append(entries, entry)
			entry.cancel()
		}
		clear(s.streams)
		clear(s.sensors)
		s.mu.Unlock()
		s.wg.Wait()
		for _, entry := range entries {
			s.closeErr = errors.Join(s.closeErr, entry.closeErr)
		}
		s.closeErr = errors.Join(s.closeErr, s.root.Close())
	})
	return s.closeErr
}

// Bufferer creates, reads and removes the buffers of attached streams.
type Bufferer interface {
	CreateBuffer(ctx context.Context, sourceURI string, sensorID string, bufferLength time.Duration) (string, error)
	GetBuffer(ctx context.Context, streamID string, startTS time.Time, endTS time.Time) ([]model.BufferSlice, error)
	AcquireBuffer(ctx context.Context, streamID string, startTS time.Time, endTS time.Time) (*BufferLease, error)
	ResizeBuffer(ctx context.Context, streamID string, bufferLength int) (model.StreamBuffer, error)
	RemoveBuffer(ctx context.Context, streamID string) error
	GetStream(ctx context.Context, streamID string) (model.StreamBuffer, error)
	ListStreams(ctx context.Context) ([]model.StreamBuffer, error)
}

var (
	ErrStreamNotFound     = errors.New("stream not found")
	ErrStreamExists       = errors.New("sensor is already attached")
	ErrUnsupportedSource  = errors.New("only RTSP or RTSPS H.264/H.265 video is supported")
	ErrInvalidRequest     = errors.New("invalid buffer request")
	ErrActiveReaders      = errors.New("buffer has active readers")
	ErrHistoryUnavailable = errors.New("requested history is not in the buffer")
	ErrSliceExpired       = errors.New("buffer slice exceeded its retention grace period")
	ErrBufferClosed       = errors.New("buffer is closed")
	ErrLeaseClosed        = errors.New("buffer lease is closed")
	ErrSourceFailed       = errors.New("stream ingestion failed")
	ErrNotImplemented     = errors.New("not implemented")
)
