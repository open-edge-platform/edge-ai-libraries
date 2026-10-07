// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"context"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

var (
	ErrSidecarUnavailable     = errors.New("sidecar unavailable")
	ErrClipIntervalNotCovered = errors.New("requested clip interval is not fully covered by the sidecar")
)

// ResolvedRange is the pair of samples bounding a resolved clip interval.
type ResolvedRange struct {
	Start SidecarSample
	End   SidecarSample
}

// TimestampResolver resolves wall-clock timestamps to media samples using a
// recording's sidecar. It hides the JSON sidecar implementation so a future
// database/index service can replace it without touching retrieval logic.
//
// Both methods take the loaded recording rather than a bare identifier, so
// the resolver can confirm the sidecar it reads actually describes that
// recording's media before resolving anything against it.
type TimestampResolver interface {
	ResolveFrame(ctx context.Context, recording model.Recording, requested time.Time, match MatchMode) (SidecarSample, error)
	ResolveRange(ctx context.Context, recording model.Recording, startTS, endTS time.Time, match MatchMode) (ResolvedRange, error)
}

// JSONSidecarResolver is the initial TimestampResolver implementation,
// backed directly by a MediaStore's recording sidecars.
type JSONSidecarResolver struct {
	media storage.MediaStore
}

func NewJSONSidecarResolver(media storage.MediaStore) *JSONSidecarResolver {
	return &JSONSidecarResolver{media: media}
}

func (r *JSONSidecarResolver) loadSidecar(ctx context.Context, recording model.Recording) (*Sidecar, error) {
	var reader io.ReadCloser
	var err error
	if media, ok := r.media.(storage.RecordingSidecarMediaStore); ok {
		reader, err = media.OpenSidecarForRecording(ctx, recording.RecordingID, recording.RecordingPath)
	} else {
		reader, err = r.media.OpenSidecar(ctx, recording.RecordingID)
	}
	if err != nil {
		return nil, fmt.Errorf("%w: %s: %v", ErrSidecarUnavailable, recording.RecordingID, err)
	}
	defer reader.Close()

	sidecar, err := ParseSidecarAuto(reader)
	if err != nil {
		return nil, fmt.Errorf("sidecar for %s: %w", recording.RecordingID, err)
	}
	if err := sidecar.VerifyIdentity(recording.RecordingID, recording.RecordingPath); err != nil {
		return nil, err
	}
	if recording.Origin == model.RecordingOriginLive {
		firstPTS := sidecar.Samples[0].PTS
		for i := range sidecar.Samples {
			sidecar.Samples[i].MediaTimeSeconds = float64(sidecar.Samples[i].PTS-firstPTS) / float64(sidecar.Timescale)
		}
	}
	return sidecar, nil
}

func (r *JSONSidecarResolver) ResolveFrame(ctx context.Context, recording model.Recording, requested time.Time, match MatchMode) (SidecarSample, error) {
	sidecar, err := r.loadSidecar(ctx, recording)
	if err != nil {
		return SidecarSample{}, err
	}
	return sidecar.FindByCaptureTimestamp(requested, match)
}

// ResolveRange resolves both boundaries of a clip request independently and
// confirms the resolved interval is contiguous: every sample between the two
// resolved ordinals must be present, so a gap in coverage is reported rather
// than silently returning a shorter clip.
func (r *JSONSidecarResolver) ResolveRange(ctx context.Context, recording model.Recording, startTS, endTS time.Time, match MatchMode) (ResolvedRange, error) {
	sidecar, err := r.loadSidecar(ctx, recording)
	if err != nil {
		return ResolvedRange{}, err
	}

	startSample, err := sidecar.FindByCaptureTimestamp(startTS, match)
	if err != nil {
		return ResolvedRange{}, err
	}
	endSample, err := sidecar.FindByCaptureTimestamp(endTS, match)
	if err != nil {
		return ResolvedRange{}, err
	}

	if endSample.Ordinal <= startSample.Ordinal || endSample.MediaTimeSeconds <= startSample.MediaTimeSeconds {
		return ResolvedRange{}, fmt.Errorf("%w: the requested interval resolves to a single sample", ErrClipIntervalNotCovered)
	}

	if err := sidecar.verifyContiguous(startSample.Ordinal, endSample.Ordinal); err != nil {
		return ResolvedRange{}, err
	}
	if recording.IsLive() {
		endIndex := -1
		coverageContinues := false
		for i, sample := range sidecar.Samples {
			if sample.Ordinal == endSample.Ordinal {
				endIndex = i
			}
			if sample.CaptureTS.After(endTS) {
				coverageContinues = true
			}
		}
		if !coverageContinues || endIndex < 0 || endIndex+1 >= len(sidecar.Samples) {
			return ResolvedRange{}, fmt.Errorf("%w: live clip requires a complete sample after its end boundary", ErrClipIntervalNotCovered)
		}
		if sidecar.Samples[endIndex+1].Ordinal != endSample.Ordinal+1 {
			return ResolvedRange{}, fmt.Errorf("%w: missing lookahead sample after ordinal %d", ErrClipIntervalNotCovered, endSample.Ordinal)
		}
	}

	return ResolvedRange{Start: startSample, End: endSample}, nil
}
