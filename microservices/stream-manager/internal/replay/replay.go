// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package replay cuts frames and clips out of ready recordings.
//
// A recording starts on a keyframe at its start_ts and its slices are
// contiguous, so the wall time of any frame is start_ts plus the frame's PTS
// offset from the first frame. No index besides the media itself is needed.
package replay

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

const (
	maxConcurrentExtractions = 6
	// derivedTTL is how long a cut frame or clip is served; the recording's own
	// expiry_ts wins when it comes sooner.
	derivedTTL = 15 * time.Minute
	// exactTolerance is how far a frame may sit from the requested time and
	// still count as an exact match.
	exactTolerance = time.Millisecond
)

var (
	ErrInvalidRequest = errors.New("invalid replay request")
	ErrNotFound       = errors.New("recording not found")
	ErrNotReady       = errors.New("recording is not ready")
	ErrNotCovered     = errors.New("requested time is not covered by the recording")
	ErrFrameNotFound  = errors.New("no frame sits at the requested time")
	ErrMediaNotFound  = errors.New("media not found or expired")
	ErrBusy           = errors.New("extraction capacity reached")
	ErrExtraction     = errors.New("media extraction failed")
)

var contentTypes = map[string]string{"jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4"}

// Replayer cuts frames and clips from recordings and serves them until they expire.
type Replayer interface {
	Frame(ctx context.Context, recordingID string, timestamp time.Time, format, match string) (Media, error)
	Clip(ctx context.Context, recordingID string, startTS time.Time, duration time.Duration, format string) (Media, error)
	OpenMedia(ctx context.Context, recordingID, name string) (*os.File, MediaFile, error)
}

// Media is a cut frame or clip. Name is the file name under the recording's
// derived directory and Path its absolute location.
type Media struct {
	Result     model.MediaResult
	Name       string
	Path       string
	ExactMatch bool
}

// MediaFile describes an opened derived file.
type MediaFile struct {
	ContentType string
	ExpiryTS    time.Time
}

// Store is the subset of storage the replay service needs.
type Store interface {
	GetMetadataByRecordingID(ctx context.Context, id string) (model.Recording, error)
	OpenMedia(ctx context.Context, uri string) (string, error)
	DerivedDir(ctx context.Context, uri string) (string, error)
	OpenDerived(ctx context.Context, uri, name string) (*os.File, error)
}

// Service implements Replayer with FFmpeg and FFprobe.
type Service struct {
	store   Store
	ffmpeg  string
	ffprobe string
	slots   chan struct{}
	now     func() time.Time
}

var _ Replayer = (*Service)(nil)

func NewService(store Store) (*Service, error) {
	ffmpeg, err := exec.LookPath("ffmpeg")
	if err != nil {
		return nil, fmt.Errorf("find FFmpeg: %w", err)
	}
	ffprobe, err := exec.LookPath("ffprobe")
	if err != nil {
		return nil, fmt.Errorf("find FFprobe: %w", err)
	}
	return &Service{
		store: store, ffmpeg: ffmpeg, ffprobe: ffprobe,
		slots: make(chan struct{}, maxConcurrentExtractions), now: time.Now,
	}, nil
}

// Frame returns the frame nearest to timestamp, or the frame at exactly that
// time when match is "exact".
func (s *Service) Frame(ctx context.Context, id string, ts time.Time, format, match string) (Media, error) {
	contentType, ok := contentTypes[format]
	if !ok || format == "mp4" || (match != "nearest" && match != "exact") {
		return Media{}, ErrInvalidRequest
	}
	rec, err := s.readyRecording(ctx, id)
	if err != nil {
		return Media{}, err
	}
	if ts.Before(rec.StartTS) || !ts.Before(*rec.EndTS) {
		return Media{}, ErrNotCovered
	}
	release, err := s.acquire()
	if err != nil {
		return Media{}, err
	}
	defer release()
	tl, err := s.openTimeline(ctx, rec)
	if err != nil {
		return Media{}, err
	}
	frame, keyframe, err := tl.nearestFrame(ctx, ts)
	if err != nil {
		return Media{}, err
	}
	frameTS := tl.wall(frame.PTS)
	exact := absDuration(frameTS.Sub(ts)) <= exactTolerance
	if match == "exact" && !exact {
		return Media{}, ErrFrameNotFound
	}
	name := fmt.Sprintf("frame-%d.%s", frameTS.Sub(rec.StartTS).Nanoseconds(), format)
	path, mtime, err := s.derive(ctx, rec, tl, name, func(dst string) []string {
		codec := []string{"-c:v", "mjpeg", "-q:v", "2"}
		if format == "png" {
			codec = []string{"-c:v", "png"}
		}
		args := []string{"-copyts", "-ss", tl.preseek(keyframe.PTS), "-noaccurate_seek", "-i", tl.path,
			"-map", "0:v:0", "-vf", fmt.Sprintf("select='eq(pts\\,%d)'", frame.PTS), "-frames:v", "1"}
		args = append(args, codec...)
		return append(args, "-f", "image2", "-update", "1", dst)
	})
	if err != nil {
		return Media{}, err
	}
	return Media{
		Result: model.MediaResult{
			RecordingID: rec.RecordingID, SensorID: rec.SensorID, MediaType: "frame", ContentType: contentType,
			RequestedStartTS: ts.UTC(), StartTS: frameTS.UTC(), ExpiryTS: expiry(rec, mtime),
		},
		Name: name, Path: path, ExactMatch: exact,
	}, nil
}

// Clip returns the span [startTS, startTS+duration) as a stream copy. The
// clip begins on the keyframe at or before startTS, which is reported as its
// start_ts.
func (s *Service) Clip(ctx context.Context, id string, start time.Time, duration time.Duration, format string) (Media, error) {
	if format != "mp4" || duration <= 0 {
		return Media{}, ErrInvalidRequest
	}
	rec, err := s.readyRecording(ctx, id)
	if err != nil {
		return Media{}, err
	}
	end := start.Add(duration)
	if start.Before(rec.StartTS) || end.After(*rec.EndTS) || !end.After(start) {
		return Media{}, ErrNotCovered
	}
	release, err := s.acquire()
	if err != nil {
		return Media{}, err
	}
	defer release()
	tl, err := s.openTimeline(ctx, rec)
	if err != nil {
		return Media{}, err
	}
	keyframe, err := tl.keyframeAtOrBefore(ctx, start, nil)
	if err != nil {
		return Media{}, err
	}
	clipStart := tl.wall(keyframe.PTS)
	name := fmt.Sprintf("clip-%d-%d.mp4", clipStart.Sub(rec.StartTS).Nanoseconds(), end.Sub(rec.StartTS).Nanoseconds())
	path, mtime, err := s.derive(ctx, rec, tl, name, func(dst string) []string {
		seek, length := tl.cut(keyframe.PTS, end)
		return []string{"-ss", seek, "-i", tl.path, "-t", length, "-map", "0:v:0", "-c", "copy",
			"-movflags", "+faststart", "-f", "mp4", dst}
	})
	if err != nil {
		return Media{}, err
	}
	requestedEnd, clipEnd := end.UTC(), end.UTC()
	return Media{
		Result: model.MediaResult{
			RecordingID: rec.RecordingID, SensorID: rec.SensorID, MediaType: "clip", ContentType: contentTypes[format],
			RequestedStartTS: start.UTC(), RequestedEndTS: &requestedEnd,
			StartTS: clipStart.UTC(), EndTS: &clipEnd, ExpiryTS: expiry(rec, mtime),
		},
		Name: name, Path: path, ExactMatch: clipStart.Equal(start),
	}, nil
}

// OpenMedia opens a frame or clip cut earlier, unless it or its recording expired.
func (s *Service) OpenMedia(ctx context.Context, id, name string) (*os.File, MediaFile, error) {
	rec, err := s.recording(ctx, id)
	if err != nil {
		return nil, MediaFile{}, err
	}
	file, err := s.store.OpenDerived(ctx, rec.RecordingPath, name)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, MediaFile{}, ErrMediaNotFound
	}
	if err != nil {
		return nil, MediaFile{}, err
	}
	info, err := file.Stat()
	if err != nil {
		return nil, MediaFile{}, errors.Join(err, file.Close())
	}
	expiryTS := expiry(rec, info.ModTime())
	if !s.now().Before(expiryTS) {
		return nil, MediaFile{}, errors.Join(ErrMediaNotFound, file.Close())
	}
	contentType := contentTypes[filepath.Ext(name)[1:]]
	return file, MediaFile{ContentType: contentType, ExpiryTS: expiryTS}, nil
}

// recording returns a recording that has not expired.
func (s *Service) recording(ctx context.Context, id string) (model.Recording, error) {
	rec, err := s.store.GetMetadataByRecordingID(ctx, id)
	if errors.Is(err, storage.ErrNotFound) {
		return model.Recording{}, ErrNotFound
	}
	if err != nil {
		return model.Recording{}, err
	}
	if rec.ExpiryTS != nil && !s.now().Before(*rec.ExpiryTS) {
		return model.Recording{}, ErrNotFound
	}
	return rec, nil
}

func (s *Service) readyRecording(ctx context.Context, id string) (model.Recording, error) {
	rec, err := s.recording(ctx, id)
	if err != nil {
		return model.Recording{}, err
	}
	if rec.State != "ready" || rec.EndTS == nil {
		return model.Recording{}, ErrNotReady
	}
	return rec, nil
}

func (s *Service) acquire() (func(), error) {
	select {
	case s.slots <- struct{}{}:
		return func() { <-s.slots }, nil
	default:
		return nil, ErrBusy
	}
}

func (s *Service) openTimeline(ctx context.Context, rec model.Recording) (*timeline, error) {
	path, err := s.store.OpenMedia(ctx, rec.RecordingPath)
	if err != nil {
		return nil, err
	}
	return newTimeline(ctx, s.ffprobe, path, rec.StartTS)
}

// derive returns the cached file called name while its TTL holds, otherwise
// cuts it again with the FFmpeg arguments built for a destination path.
func (s *Service) derive(ctx context.Context, rec model.Recording, tl *timeline, name string, args func(dst string) []string) (string, time.Time, error) {
	dir, err := s.store.DerivedDir(ctx, rec.RecordingPath)
	if err != nil {
		return "", time.Time{}, err
	}
	path := filepath.Join(dir, name)
	if info, err := os.Lstat(path); err == nil && info.Mode().IsRegular() && s.now().Before(info.ModTime().Add(derivedTTL)) {
		return path, info.ModTime(), nil
	}
	tmp, err := os.CreateTemp(dir, ".tmp-*"+filepath.Ext(name))
	if err != nil {
		return "", time.Time{}, err
	}
	tmpName := tmp.Name()
	if err := tmp.Close(); err != nil {
		return "", time.Time{}, errors.Join(err, os.Remove(tmpName))
	}
	if err := runFFmpeg(ctx, s.ffmpeg, tl.path, ffmpegArgs(args(tmpName))...); err != nil {
		return "", time.Time{}, errors.Join(err, os.Remove(tmpName))
	}
	info, err := os.Stat(tmpName)
	if err != nil || info.Size() == 0 {
		return "", time.Time{}, errors.Join(ErrExtraction, err, os.Remove(tmpName))
	}
	if err := os.Rename(tmpName, path); err != nil {
		return "", time.Time{}, errors.Join(err, os.Remove(tmpName))
	}
	return path, info.ModTime(), nil
}

// ffmpegArgs prefixes the shared FFmpeg flags.
func ffmpegArgs(args []string) []string {
	return append([]string{"-hide_banner", "-loglevel", "error", "-nostdin", "-y"}, args...)
}

// expiry is the TTL of a derived file, capped by its recording's expiry_ts.
func expiry(rec model.Recording, mtime time.Time) time.Time {
	expiryTS := mtime.Add(derivedTTL)
	if rec.ExpiryTS != nil && rec.ExpiryTS.Before(expiryTS) {
		expiryTS = *rec.ExpiryTS
	}
	return expiryTS.UTC()
}

func absDuration(d time.Duration) time.Duration {
	if d < 0 {
		return -d
	}
	return d
}
