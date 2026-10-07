// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"
)

// SidecarVersion is the only sidecar schema this service accepts. The format
// is frozen: a sidecar declaring any other version is rejected rather than
// interpreted on a best-effort basis, so a future schema change cannot be
// silently misread as version 1.
const SidecarVersion = 1

// MatchMode selects how a requested wall-clock timestamp is resolved against
// the sidecar samples.
type MatchMode string

const (
	MatchNearest MatchMode = "nearest"
	MatchExact   MatchMode = "exact"
)

var (
	ErrSidecarMalformed        = errors.New("sidecar is malformed")
	ErrSidecarUnsupported      = errors.New("unsupported sidecar version")
	ErrSidecarEmpty            = errors.New("sidecar contains no samples")
	ErrSidecarInvalidTimescale = errors.New("sidecar has a non-positive timescale")
	ErrSidecarInvalidSample    = errors.New("sidecar contains an invalid sample")
	ErrSidecarDuplicateSample  = errors.New("sidecar contains a duplicate sample")
	ErrSidecarUnordered        = errors.New("sidecar samples are not ordered consistently")
	ErrSidecarMismatch         = errors.New("sidecar does not match the recording it was loaded for")
	ErrNoExactMatch            = errors.New("no exact sample match for requested timestamp")
	ErrTimestampOutOfCoverage  = errors.New("requested timestamp falls outside the recording's stored coverage")
)

// SidecarSample is a single entry from the sidecar's sample list, with its
// media-clock position pre-computed from pts/timescale.
type SidecarSample struct {
	Ordinal          int
	CaptureTS        time.Time
	PTS              int64
	DTS              int64
	Duration         int64
	Offset           int64
	Length           int64
	Keyframe         bool
	MediaTimeSeconds float64
}

// Sidecar is the parsed, validated timestamp-to-media mapping for a
// recording. Samples are sorted by ordinal, which validation has confirmed
// agrees with both the capture clock and the media clock.
type Sidecar struct {
	Version     int
	RecordingID string
	MediaPath   string
	Timescale   int64
	Samples     []SidecarSample
}

type rawSidecarSample struct {
	Ordinal   int    `json:"ordinal"`
	CaptureTS string `json:"capture_ts"`
	PTS       int64  `json:"pts"`
	DTS       int64  `json:"dts"`
	Duration  int64  `json:"duration"`
	Offset    int64  `json:"offset"`
	Length    int64  `json:"length"`
	Keyframe  bool   `json:"keyframe"`
}

type rawSidecar struct {
	Version     int                `json:"version"`
	RecordingID string             `json:"recording_id"`
	MediaPath   string             `json:"media_path"`
	Timescale   int64              `json:"timescale"`
	Samples     []rawSidecarSample `json:"samples"`
}

// ParseSidecar decodes and validates sidecar JSON read from a MediaStore.
//
// Decoding is strict: unknown fields are rejected, so a sidecar written
// against a different schema fails loudly here instead of losing data
// silently. Capture timestamps (wall-clock, RFC3339Nano) and media
// timestamps (pts/timescale, position inside the recording) are distinct
// clocks and are never substituted for one another.
func ParseSidecar(r io.Reader) (*Sidecar, error) {
	decoder := json.NewDecoder(r)
	decoder.DisallowUnknownFields()

	var raw rawSidecar
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSidecarMalformed, err)
	}
	if err := decoder.Decode(new(json.RawMessage)); err != io.EOF {
		return nil, fmt.Errorf("%w: trailing content after the sidecar document", ErrSidecarMalformed)
	}

	if raw.Version != SidecarVersion {
		return nil, fmt.Errorf("%w: got %d, want %d", ErrSidecarUnsupported, raw.Version, SidecarVersion)
	}
	if len(raw.Samples) == 0 {
		return nil, ErrSidecarEmpty
	}
	if raw.Timescale <= 0 {
		return nil, fmt.Errorf("%w: %d", ErrSidecarInvalidTimescale, raw.Timescale)
	}
	if strings.TrimSpace(raw.RecordingID) == "" {
		return nil, fmt.Errorf("%w: recording_id is empty", ErrSidecarInvalidSample)
	}
	if strings.TrimSpace(raw.MediaPath) == "" {
		return nil, fmt.Errorf("%w: media_path is empty", ErrSidecarInvalidSample)
	}

	seenOrdinal := make(map[int]struct{}, len(raw.Samples))
	samples := make([]SidecarSample, 0, len(raw.Samples))

	for _, rs := range raw.Samples {
		sample, err := buildSample(rs, raw.Timescale)
		if err != nil {
			return nil, err
		}
		if _, dup := seenOrdinal[sample.Ordinal]; dup {
			return nil, fmt.Errorf("%w: ordinal %d appears more than once", ErrSidecarDuplicateSample, sample.Ordinal)
		}
		seenOrdinal[sample.Ordinal] = struct{}{}
		samples = append(samples, sample)
	}

	sort.Slice(samples, func(i, j int) bool { return samples[i].Ordinal < samples[j].Ordinal })

	if err := verifySampleOrdering(samples); err != nil {
		return nil, err
	}

	return &Sidecar{
		Version:     raw.Version,
		RecordingID: raw.RecordingID,
		MediaPath:   raw.MediaPath,
		Timescale:   raw.Timescale,
		Samples:     samples,
	}, nil
}

// buildSample validates one raw sample record and computes its media-clock
// position. It is shared by the version 1 (single JSON document) and
// version 2 (JSONL) parsers so a sample is validated identically regardless
// of which sidecar schema carried it.
func buildSample(rs rawSidecarSample, timescale int64) (SidecarSample, error) {
	if rs.Ordinal < 0 {
		return SidecarSample{}, fmt.Errorf("%w: ordinal %d is negative", ErrSidecarInvalidSample, rs.Ordinal)
	}
	if strings.TrimSpace(rs.CaptureTS) == "" {
		return SidecarSample{}, fmt.Errorf("%w: ordinal %d has an empty capture_ts", ErrSidecarInvalidSample, rs.Ordinal)
	}
	captureTS, err := time.Parse(time.RFC3339Nano, rs.CaptureTS)
	if err != nil {
		return SidecarSample{}, fmt.Errorf("%w: ordinal %d has invalid capture_ts %q: %v", ErrSidecarInvalidSample, rs.Ordinal, rs.CaptureTS, err)
	}
	if rs.PTS < 0 {
		return SidecarSample{}, fmt.Errorf("%w: ordinal %d has a negative pts", ErrSidecarInvalidSample, rs.Ordinal)
	}
	if rs.Offset < 0 || rs.Length < 0 || rs.Duration < 0 {
		return SidecarSample{}, fmt.Errorf("%w: ordinal %d has a negative offset, length, or duration", ErrSidecarInvalidSample, rs.Ordinal)
	}

	return SidecarSample{
		Ordinal:          rs.Ordinal,
		CaptureTS:        captureTS.UTC(),
		PTS:              rs.PTS,
		DTS:              rs.DTS,
		Duration:         rs.Duration,
		Offset:           rs.Offset,
		Length:           rs.Length,
		Keyframe:         rs.Keyframe,
		MediaTimeSeconds: float64(rs.PTS) / float64(timescale),
	}, nil
}

// verifySampleOrdering checks that both the capture clock and the media
// clock strictly advance across the ordinal sequence (samples must already
// be sorted by ordinal). If they disagree, a requested wall-clock instant
// could not be mapped to one unambiguous media position, so the sidecar is
// rejected rather than resolved.
func verifySampleOrdering(samples []SidecarSample) error {
	for i := 1; i < len(samples); i++ {
		prev, cur := samples[i-1], samples[i]
		if !cur.CaptureTS.After(prev.CaptureTS) {
			return fmt.Errorf("%w: capture_ts does not advance at ordinal %d", ErrSidecarUnordered, cur.Ordinal)
		}
		if cur.PTS <= prev.PTS {
			return fmt.Errorf("%w: pts does not advance at ordinal %d", ErrSidecarUnordered, cur.Ordinal)
		}
	}
	return nil
}

// rawSidecarJSONLHeader is the first line of a version 2 (JSONL) sidecar:
// one JSON object carrying the fields that describe the recording, as
// opposed to a single sample.
type rawSidecarJSONLHeader struct {
	Version     int    `json:"version"`
	RecordingID string `json:"recording_id"`
	MediaPath   string `json:"media_path"`
	Timescale   int64  `json:"timescale"`
}

// ParseSidecarJSONL decodes and validates a version 2 (append-only JSONL)
// sidecar: a header line followed by one JSON object per sample line. It is
// used for a live recording's sidecar, which is appended to while the
// recording is still being written.
//
// The parser tolerates exactly one failure mode a version 1 sidecar does
// not need to: the final line may be a partially written sample (the writer
// was interrupted mid-append). Any other malformed line — including a
// malformed header — fails the whole parse, the same as version 1.
func ParseSidecarJSONL(r io.Reader) (*Sidecar, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("%w: read sidecar: %v", ErrSidecarMalformed, err)
	}

	hasPartialFinalLine := len(data) > 0 && data[len(data)-1] != '\n'
	lines := strings.Split(string(data), "\n")
	for len(lines) > 0 && strings.TrimSpace(lines[len(lines)-1]) == "" {
		lines = lines[:len(lines)-1]
	}
	if len(lines) == 0 {
		return nil, ErrSidecarEmpty
	}

	var header rawSidecarJSONLHeader
	if err := strictUnmarshalLine(lines[0], &header); err != nil {
		return nil, fmt.Errorf("%w: header: %v", ErrSidecarMalformed, err)
	}
	if header.Version != 2 {
		return nil, fmt.Errorf("%w: got %d, want 2", ErrSidecarUnsupported, header.Version)
	}
	if header.Timescale <= 0 {
		return nil, fmt.Errorf("%w: %d", ErrSidecarInvalidTimescale, header.Timescale)
	}
	if strings.TrimSpace(header.RecordingID) == "" {
		return nil, fmt.Errorf("%w: recording_id is empty", ErrSidecarInvalidSample)
	}
	if strings.TrimSpace(header.MediaPath) == "" {
		return nil, fmt.Errorf("%w: media_path is empty", ErrSidecarInvalidSample)
	}

	sampleLines := lines[1:]
	if len(sampleLines) == 0 {
		return nil, ErrSidecarEmpty
	}

	seenOrdinal := make(map[int]struct{}, len(sampleLines))
	samples := make([]SidecarSample, 0, len(sampleLines))

	for i, line := range sampleLines {
		var rs rawSidecarSample
		if err := strictUnmarshalLine(line, &rs); err != nil {
			if i == len(sampleLines)-1 && hasPartialFinalLine && isUnexpectedJSONEOF(err) {
				// A partially written final line is the expected
				// shape of an in-progress live append; earlier
				// lines and complete malformed lines are never
				// tolerated this way.
				break
			}
			return nil, fmt.Errorf("%w: sample line %d: %v", ErrSidecarMalformed, i+2, err)
		}

		sample, err := buildSample(rs, header.Timescale)
		if err != nil {
			return nil, err
		}
		if _, dup := seenOrdinal[sample.Ordinal]; dup {
			return nil, fmt.Errorf("%w: ordinal %d appears more than once", ErrSidecarDuplicateSample, sample.Ordinal)
		}
		seenOrdinal[sample.Ordinal] = struct{}{}
		if len(samples) > 0 && sample.Ordinal <= samples[len(samples)-1].Ordinal {
			return nil, fmt.Errorf("%w: ordinal %d does not follow ordinal %d", ErrSidecarUnordered, sample.Ordinal, samples[len(samples)-1].Ordinal)
		}
		samples = append(samples, sample)
	}
	if len(samples) == 0 {
		return nil, ErrSidecarEmpty
	}

	if err := verifySampleOrdering(samples); err != nil {
		return nil, err
	}

	return &Sidecar{
		Version:     header.Version,
		RecordingID: header.RecordingID,
		MediaPath:   header.MediaPath,
		Timescale:   header.Timescale,
		Samples:     samples,
	}, nil
}

func isUnexpectedJSONEOF(err error) bool {
	if errors.Is(err, io.ErrUnexpectedEOF) {
		return true
	}
	var syntaxErr *json.SyntaxError
	return errors.As(err, &syntaxErr) && syntaxErr.Error() == "unexpected end of JSON input"
}

// strictUnmarshalLine decodes exactly one JSON object from line, rejecting
// unknown fields and any trailing content, matching ParseSidecar's
// strictness.
func strictUnmarshalLine(line string, v any) error {
	decoder := json.NewDecoder(strings.NewReader(line))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	if err := decoder.Decode(new(json.RawMessage)); err != io.EOF {
		return errors.New("trailing content after the JSON line")
	}
	return nil
}

// ParseSidecarAuto decodes a sidecar of either supported schema, choosing
// version 1 (single JSON document) or version 2 (JSONL) by sniffing the
// declared "version" field of the first JSON value in the stream. Finalized
// recordings publish version 1; live recordings publish version 2.
func ParseSidecarAuto(r io.Reader) (*Sidecar, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("%w: read sidecar: %v", ErrSidecarMalformed, err)
	}

	var probe struct {
		Version int `json:"version"`
	}
	// json.Decoder.Decode reads only the first top-level JSON value from
	// the stream, so this correctly identifies the schema whether the
	// document is a single (possibly pretty-printed) JSON object or the
	// header line of a JSONL stream.
	if err := json.NewDecoder(bytes.NewReader(data)).Decode(&probe); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSidecarMalformed, err)
	}

	switch probe.Version {
	case SidecarVersion:
		return ParseSidecar(bytes.NewReader(data))
	case 2:
		return ParseSidecarJSONL(bytes.NewReader(data))
	default:
		return nil, fmt.Errorf("%w: got %d", ErrSidecarUnsupported, probe.Version)
	}
}

// VerifyIdentity confirms the sidecar describes the recording it was loaded
// for. A sidecar that names another recording, or points at different media
// than the metadata does, would resolve timestamps against the wrong
// footage, so it is rejected before any extraction is attempted.
func (s *Sidecar) VerifyIdentity(recordingID, mediaPath string) error {
	if s.RecordingID != recordingID {
		return fmt.Errorf("%w: sidecar names recording %q, expected %q", ErrSidecarMismatch, s.RecordingID, recordingID)
	}
	if s.MediaPath != mediaPath {
		return fmt.Errorf("%w: sidecar names media %q, expected %q", ErrSidecarMismatch, s.MediaPath, mediaPath)
	}
	return nil
}

// Coverage returns the wall-clock interval the sidecar indexes.
func (s *Sidecar) Coverage() (startTS, endTS time.Time) {
	if len(s.Samples) == 0 {
		return time.Time{}, time.Time{}
	}
	return s.Samples[0].CaptureTS, s.Samples[len(s.Samples)-1].CaptureTS
}

// FindByCaptureTimestamp resolves a requested wall-clock time to a sample.
// For MatchExact, it returns ErrNoExactMatch unless a sample's capture
// timestamp is exactly equal to requested. For MatchNearest (the default),
// it selects the sample with the smallest absolute time difference,
// preferring the earlier capture timestamp on a tie.
//
// Both modes require the requested instant to fall inside the recording's
// stored coverage, so a gap is never papered over with footage from a
// different time.
func (s *Sidecar) FindByCaptureTimestamp(requested time.Time, match MatchMode) (SidecarSample, error) {
	if len(s.Samples) == 0 {
		return SidecarSample{}, ErrSidecarEmpty
	}

	target := requested.UTC()
	first, last := s.Coverage()
	if target.Before(first) || target.After(last) {
		return SidecarSample{}, fmt.Errorf("%w: %s", ErrTimestampOutOfCoverage, target.Format(time.RFC3339Nano))
	}

	if match == MatchExact {
		for _, sample := range s.Samples {
			if sample.CaptureTS.Equal(target) {
				return sample, nil
			}
		}
		return SidecarSample{}, fmt.Errorf("%w: %s", ErrNoExactMatch, target.Format(time.RFC3339Nano))
	}

	best := s.Samples[0]
	bestDiff := absDuration(best.CaptureTS.Sub(target))
	for _, sample := range s.Samples[1:] {
		diff := absDuration(sample.CaptureTS.Sub(target))
		if diff < bestDiff {
			best, bestDiff = sample, diff
		}
	}
	return best, nil
}

func absDuration(d time.Duration) time.Duration {
	if d < 0 {
		return -d
	}
	return d
}

// verifyContiguous checks that every sample ordinal between startOrdinal and
// endOrdinal (inclusive) is present in the sidecar with no gaps, so a clip
// request is rejected rather than silently returning less than was asked
// for.
func (s *Sidecar) verifyContiguous(startOrdinal, endOrdinal int) error {
	var previous *SidecarSample
	for i := range s.Samples {
		sample := s.Samples[i]
		if sample.Ordinal < startOrdinal || sample.Ordinal > endOrdinal {
			continue
		}
		if previous != nil && sample.Ordinal-previous.Ordinal != 1 {
			return fmt.Errorf("%w: missing sample between ordinal %d and %d", ErrClipIntervalNotCovered, previous.Ordinal, sample.Ordinal)
		}
		previous = &sample
	}
	return nil
}
