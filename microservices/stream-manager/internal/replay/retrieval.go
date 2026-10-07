// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package replay resolves and serves frame/clip media for previously
// recorded streams: it maps a requested wall-clock timestamp (or range) to
// media-clock positions via a recording's sidecar index, extracts the
// derived media, and stores/presigns the result.
package replay

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// Media types and content types this service can produce.
const (
	MediaTypeFrame = "frame"
	MediaTypeClip  = "clip"

	contentTypeJPEG = "image/jpeg"
	contentTypePNG  = "image/png"
	contentTypeMP4  = "video/mp4"
)

// Default derived-object and presigned-URL lifetimes, used when the caller
// does not configure them.
const (
	defaultDerivedTTL    = 15 * time.Minute
	defaultPresignExpiry = 5 * time.Minute
)

var (
	ErrRecordingNotReady      = errors.New("recording not ready")
	ErrUnsupportedFrameFormat = errors.New("unsupported frame format")
	ErrUnsupportedClipFormat  = errors.New("unsupported clip format")
	ErrUnsupportedMatchMode   = errors.New("unsupported match mode")
	ErrInvalidClipRange       = errors.New("invalid clip range")
	// ErrMediaUnavailable wraps any failure talking to the object store
	// (reading the recording, writing derived output, or presigning a
	// URL) so handlers can map it to a 503 without leaking the underlying
	// storage error text to callers.
	ErrMediaUnavailable = errors.New("media storage unavailable")
	// ErrRecordingTooLarge reports that a live recording's source media
	// exceeds the configured full-file staging limit. Extraction refuses
	// to start rather than risk exhausting local disk staging an
	// unbounded live recording.
	ErrRecordingTooLarge = errors.New("recording too large to stage")
	// ErrRecordingSizeUnknown reports a live recording without positive size
	// metadata, which cannot be safely checked against the staging limit.
	ErrRecordingSizeUnknown = errors.New("recording size is unknown")
)

// Options configures a RetrievalService. Zero values fall back to package
// defaults, so callers only set what they care about.
type Options struct {
	// DerivedTTL is the retention hint attached to published derived
	// objects.
	DerivedTTL time.Duration
	// PresignExpiry is how long an issued media URL stays valid.
	PresignExpiry time.Duration
	// Extractor overrides the default ffmpeg-backed media extractor.
	Extractor Extractor
	// Resolver overrides the default JSON-sidecar timestamp resolver.
	Resolver TimestampResolver
	// MaxStageBytes bounds full-file staging of a live recording's source
	// media ahead of extraction. Zero disables the check.
	MaxStageBytes int64
}

// RetrievalService resolves and prepares frame/clip media result payloads.
type RetrievalService struct {
	metadata      storage.RecordingMetadataStore
	media         storage.MediaStore
	resolver      TimestampResolver
	extractor     Extractor
	derivedTTL    time.Duration
	presignExpiry time.Duration
	maxStageBytes int64
}

// NewRetrievalService wires the retrieval dependencies, defaulting to a
// JSON-sidecar timestamp resolver and an ffmpeg-backed media extractor.
func NewRetrievalService(metadata storage.RecordingMetadataStore, media storage.MediaStore, opts Options) *RetrievalService {
	if opts.Extractor == nil {
		opts.Extractor = NewFFmpegExtractor()
	}
	if opts.Resolver == nil {
		opts.Resolver = NewJSONSidecarResolver(media)
	}
	if opts.DerivedTTL <= 0 {
		opts.DerivedTTL = defaultDerivedTTL
	}
	if opts.PresignExpiry <= 0 {
		opts.PresignExpiry = defaultPresignExpiry
	}

	return &RetrievalService{
		metadata:      metadata,
		media:         media,
		resolver:      opts.Resolver,
		extractor:     opts.Extractor,
		derivedTTL:    opts.DerivedTTL,
		presignExpiry: opts.PresignExpiry,
		maxStageBytes: opts.MaxStageBytes,
	}
}

// GetFrame resolves a requested wall-clock instant to a single still image.
func (s *RetrievalService) GetFrame(ctx context.Context, req model.FrameRequest) (model.MediaResult, error) {
	recording, err := s.readyRecording(ctx, req.RecordingID)
	if err != nil {
		return model.MediaResult{}, err
	}

	format, err := normalizeFrameFormat(req.Format)
	if err != nil {
		return model.MediaResult{}, err
	}
	matchMode, err := normalizeMatchMode(req.Match)
	if err != nil {
		return model.MediaResult{}, err
	}

	requested := req.StartTS.UTC()
	sample, err := s.resolver.ResolveFrame(ctx, recording, requested, matchMode)
	if err != nil {
		return model.MediaResult{}, err
	}

	// The key is derived from the resolved capture timestamp rather than
	// the requested one, so every request that lands on the same sample
	// reuses one object instead of re-extracting identical bytes.
	key, err := storage.DerivedFrameKey(recording.RecordingID, sample.CaptureTS, format)
	if err != nil {
		return model.MediaResult{}, err
	}
	contentType := frameContentType(format)

	extract := func(ctx context.Context) ([]byte, error) {
		return s.withRecording(ctx, recording, func(media io.Reader) ([]byte, error) {
			return s.extractor.ExtractFrame(ctx, media, sample.MediaTimeSeconds, format)
		})
	}
	url, expiryTS, err := s.publishDerived(ctx, key, contentType, extract)
	if err != nil {
		return model.MediaResult{}, err
	}

	return model.MediaResult{
		RecordingID:      recording.RecordingID,
		SensorID:         recording.SensorID,
		MediaType:        MediaTypeFrame,
		ContentType:      contentType,
		RequestedStartTS: requested,
		StartTS:          sample.CaptureTS,
		ExactMatch:       sample.CaptureTS.Equal(requested),
		URL:              url,
		ExpiryTS:         expiryTS,
		DerivedKey:       key,
	}, nil
}

// GetClip resolves a requested wall-clock interval to a trimmed sub-clip.
func (s *RetrievalService) GetClip(ctx context.Context, req model.ClipRequest) (model.MediaResult, error) {
	recording, err := s.readyRecording(ctx, req.RecordingID)
	if err != nil {
		return model.MediaResult{}, err
	}

	start := req.StartTS.UTC()
	end, err := clipEnd(start, req)
	if err != nil {
		return model.MediaResult{}, err
	}

	format, err := normalizeClipFormat(req.Format)
	if err != nil {
		return model.MediaResult{}, err
	}

	resolved, err := s.resolver.ResolveRange(ctx, recording, start, end, MatchNearest)
	if err != nil {
		return model.MediaResult{}, err
	}

	key, err := storage.DerivedClipKey(recording.RecordingID, resolved.Start.CaptureTS, resolved.End.CaptureTS, format)
	if err != nil {
		return model.MediaResult{}, err
	}

	extract := func(ctx context.Context) ([]byte, error) {
		return s.withRecording(ctx, recording, func(media io.Reader) ([]byte, error) {
			return s.extractor.ExtractClip(ctx, media, resolved.Start.MediaTimeSeconds, resolved.End.MediaTimeSeconds, format)
		})
	}
	url, expiryTS, err := s.publishDerived(ctx, key, contentTypeMP4, extract)
	if err != nil {
		return model.MediaResult{}, err
	}

	requestedEnd := end
	resolvedEnd := resolved.End.CaptureTS
	return model.MediaResult{
		RecordingID:      recording.RecordingID,
		SensorID:         recording.SensorID,
		MediaType:        MediaTypeClip,
		ContentType:      contentTypeMP4,
		RequestedStartTS: start,
		RequestedEndTS:   &requestedEnd,
		StartTS:          resolved.Start.CaptureTS,
		EndTS:            &resolvedEnd,
		ExactMatch:       resolved.Start.CaptureTS.Equal(start) && resolvedEnd.Equal(end),
		URL:              url,
		ExpiryTS:         expiryTS,
		DerivedKey:       key,
	}, nil
}

// readyRecording loads a recording and confirms it is in a state whose media
// is servable: either finalized (state == ready, end_ts set) or still being
// written (state == recording, end_ts unset). See model.Recording.IsServable.
func (s *RetrievalService) readyRecording(ctx context.Context, recordingID string) (model.Recording, error) {
	recording, err := s.metadata.GetByID(ctx, recordingID)
	if err != nil {
		return model.Recording{}, err
	}
	if !recording.IsServable() {
		return model.Recording{}, fmt.Errorf("%w: state is %q", ErrRecordingNotReady, recording.State)
	}
	return recording, nil
}

// publishDerived returns a URL for the derived object at key, extracting and
// uploading it only when it is not already published. Derived output is a
// pure function of the recording, the resolved timestamps, and the format,
// so a cached object is always equivalent to a freshly extracted one.
func (s *RetrievalService) publishDerived(ctx context.Context, key, contentType string, extract func(context.Context) ([]byte, error)) (string, time.Time, error) {
	exists, err := s.media.DerivedExists(ctx, key)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("%w: %v", ErrMediaUnavailable, err)
	}

	if !exists {
		data, err := extract(ctx)
		if err != nil {
			return "", time.Time{}, err
		}
		if err := s.media.PutDerived(ctx, key, bytes.NewReader(data), contentType, s.derivedTTL); err != nil {
			return "", time.Time{}, fmt.Errorf("%w: %v", ErrMediaUnavailable, err)
		}
	}

	url, expiryTS, err := s.media.PresignDerived(ctx, key, s.presignExpiry)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("%w: %v", ErrMediaUnavailable, err)
	}
	return url, expiryTS, nil
}

// withRecording opens the source recording, hands the stream to an
// extraction callback, and closes it afterwards, keeping the open/close
// pairing in one place. Before opening a live recording's source, it checks
// the recording's reported size against maxStageBytes: extraction stages
// the entire source into a temporary file, and an unbounded live recording
// could otherwise exhaust local disk. Finalized recordings are not subject
// to this check.
func (s *RetrievalService) withRecording(ctx context.Context, recording model.Recording, fn func(io.Reader) ([]byte, error)) ([]byte, error) {
	if recording.IsLive() && s.maxStageBytes > 0 {
		if recording.SizeBytes <= 0 {
			return nil, fmt.Errorf("%w: live recording %s has size %d", ErrRecordingSizeUnknown, recording.RecordingID, recording.SizeBytes)
		}
		if recording.SizeBytes > s.maxStageBytes {
			return nil, fmt.Errorf("%w: recording is %d bytes, limit is %d bytes", ErrRecordingTooLarge, recording.SizeBytes, s.maxStageBytes)
		}
	}

	reader, err := s.media.OpenRecording(ctx, recording.RecordingPath)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrMediaUnavailable, err)
	}
	defer reader.Close()
	return fn(reader)
}

// clipEnd derives the requested clip end from exactly one of an explicit end
// timestamp or a duration. Supplying both or neither is ambiguous and is
// rejected here as well as at the HTTP boundary.
func clipEnd(start time.Time, req model.ClipRequest) (time.Time, error) {
	hasEnd := req.EndTS != nil
	hasDuration := req.ClipDuration != nil

	switch {
	case hasEnd && hasDuration:
		return time.Time{}, fmt.Errorf("%w: provide exactly one of an end timestamp or a duration", ErrInvalidClipRange)
	case !hasEnd && !hasDuration:
		return time.Time{}, fmt.Errorf("%w: an end timestamp or a duration is required", ErrInvalidClipRange)
	}

	end := start
	if hasEnd {
		end = req.EndTS.UTC()
	} else {
		duration := *req.ClipDuration
		if duration <= 0 {
			return time.Time{}, fmt.Errorf("%w: duration must be greater than zero", ErrInvalidClipRange)
		}
		end = start.Add(time.Duration(duration * float64(time.Second)))
	}

	if !end.After(start) {
		return time.Time{}, fmt.Errorf("%w: end must be after start", ErrInvalidClipRange)
	}
	return end, nil
}

func frameContentType(format string) string {
	if format == "png" {
		return contentTypePNG
	}
	return contentTypeJPEG
}

// FrameContentType returns the MIME type a frame request in the given
// format will produce, or ErrUnsupportedFrameFormat. It applies the same
// normalization GetFrame does, so callers can negotiate the response before
// any extraction work is performed.
func FrameContentType(format string) (string, error) {
	normalized, err := normalizeFrameFormat(format)
	if err != nil {
		return "", err
	}
	return frameContentType(normalized), nil
}

// ClipContentType returns the MIME type a clip request in the given format
// will produce, or ErrUnsupportedClipFormat.
func ClipContentType(format string) (string, error) {
	if _, err := normalizeClipFormat(format); err != nil {
		return "", err
	}
	return contentTypeMP4, nil
}

func normalizeFrameFormat(format string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(format)) {
	case "", "jpg", "jpeg":
		return "jpeg", nil
	case "png":
		return "png", nil
	default:
		return "", fmt.Errorf("%w: %q", ErrUnsupportedFrameFormat, format)
	}
}

func normalizeClipFormat(format string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(format)) {
	case "", "mp4":
		return "mp4", nil
	default:
		return "", fmt.Errorf("%w: %q", ErrUnsupportedClipFormat, format)
	}
}

func normalizeMatchMode(mode string) (MatchMode, error) {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "", "nearest":
		return MatchNearest, nil
	case "exact":
		return MatchExact, nil
	default:
		return "", fmt.Errorf("%w: %q", ErrUnsupportedMatchMode, mode)
	}
}
