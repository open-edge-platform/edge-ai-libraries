// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"errors"
	"fmt"
	"path"
	"strings"
	"time"
)

// Object key layout. Every object this service reads or writes is addressed
// with one of these logical keys, relative to the store's configured prefix:
//
//	recordings/{recording_id}/media.mp4
//	recordings/{recording_id}/sidecar.json
//	derived/{recording_id}/frames/...
//	derived/{recording_id}/clips/...
const (
	recordingsRoot = "recordings"
	derivedRoot    = "derived"

	recordingMediaObject       = "media.mp4"
	recordingSidecarObject     = "sidecar.json"
	recordingLiveMediaObject   = "media.ts"
	recordingLiveSidecarObject = "sidecar.jsonl"

	derivedFramesSegment = "frames"
	derivedClipsSegment  = "clips"
)

var (
	// ErrInvalidIdentifier reports an identifier that cannot be safely
	// embedded in an object key (empty, separator-bearing, or traversing).
	ErrInvalidIdentifier = errors.New("invalid object identifier")
	// ErrInvalidObjectKey reports a key that escapes the configured
	// prefix, names another bucket, or is not a relative store key.
	ErrInvalidObjectKey = errors.New("invalid object key")
)

// ValidateIdentifier checks that id can be embedded verbatim in an object
// key. Identifiers come from request paths and persisted metadata, so they
// are treated as untrusted and must be a single, non-traversing path
// segment.
func ValidateIdentifier(kind, id string) error {
	switch {
	case strings.TrimSpace(id) == "":
		return fmt.Errorf("%w: %s is empty", ErrInvalidIdentifier, kind)
	case id != strings.TrimSpace(id):
		return fmt.Errorf("%w: %s %q has surrounding whitespace", ErrInvalidIdentifier, kind, id)
	case strings.ContainsAny(id, "/\\"):
		return fmt.Errorf("%w: %s %q contains a path separator", ErrInvalidIdentifier, kind, id)
	case id == "." || id == "..":
		return fmt.Errorf("%w: %s %q is a traversal segment", ErrInvalidIdentifier, kind, id)
	case strings.ContainsRune(id, 0):
		return fmt.Errorf("%w: %s contains a NUL byte", ErrInvalidIdentifier, kind)
	}
	return nil
}

// ValidateObjectKey checks that key is a relative, non-traversing store key.
// Absolute paths, URI forms (which could redirect reads or writes at another
// endpoint), and bucket-qualified keys are rejected so a key can never
// escape the store's configured prefix.
func ValidateObjectKey(key string) error {
	switch {
	case strings.TrimSpace(key) == "":
		return fmt.Errorf("%w: key is empty", ErrInvalidObjectKey)
	case strings.HasPrefix(key, "/"):
		return fmt.Errorf("%w: key %q is absolute", ErrInvalidObjectKey, key)
	case strings.Contains(key, "://"):
		return fmt.Errorf("%w: key %q is a URI", ErrInvalidObjectKey, key)
	case strings.HasPrefix(key, "s3:"):
		return fmt.Errorf("%w: key %q names a bucket", ErrInvalidObjectKey, key)
	case strings.ContainsRune(key, 0):
		return fmt.Errorf("%w: key contains a NUL byte", ErrInvalidObjectKey)
	case strings.Contains(key, `\`):
		return fmt.Errorf("%w: key %q contains a backslash", ErrInvalidObjectKey, key)
	}

	if cleaned := path.Clean(key); cleaned != key {
		return fmt.Errorf("%w: key %q is not in canonical form", ErrInvalidObjectKey, key)
	}
	for _, segment := range strings.Split(key, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return fmt.Errorf("%w: key %q contains an empty or traversal segment", ErrInvalidObjectKey, key)
		}
	}

	root, _, ok := strings.Cut(key, "/")
	if !ok || (root != recordingsRoot && root != derivedRoot) {
		return fmt.Errorf("%w: key %q is outside the managed layout", ErrInvalidObjectKey, key)
	}
	return nil
}

// RecordingMediaKey returns the source recording key for recordingID.
func RecordingMediaKey(recordingID string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	return path.Join(recordingsRoot, recordingID, recordingMediaObject), nil
}

// RecordingSidecarKey returns the sidecar key for recordingID.
func RecordingSidecarKey(recordingID string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	return path.Join(recordingsRoot, recordingID, recordingSidecarObject), nil
}

// RecordingLiveMediaKey returns the MPEG-TS source key for a live recording.
func RecordingLiveMediaKey(recordingID string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	return path.Join(recordingsRoot, recordingID, recordingLiveMediaObject), nil
}

// RecordingLiveSidecarKey returns the append-only JSONL sidecar key for a
// live recording.
func RecordingLiveSidecarKey(recordingID string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	return path.Join(recordingsRoot, recordingID, recordingLiveSidecarObject), nil
}

// RecordingSidecarKeyForPath resolves the sidecar key corresponding to a
// recording path stored in metadata. It accepts only known recording paths
// inside that recording's own directory.
func RecordingSidecarKeyForPath(recordingID, recordingPath string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	if err := ValidateObjectKey(recordingPath); err != nil {
		return "", err
	}
	if path.Dir(recordingPath) != path.Join(recordingsRoot, recordingID) {
		return "", fmt.Errorf("%w: recording path %q does not belong to %q", ErrInvalidObjectKey, recordingPath, recordingID)
	}

	switch path.Ext(recordingPath) {
	case ".mp4":
		return RecordingSidecarKey(recordingID)
	case ".ts":
		if path.Base(recordingPath) != recordingLiveMediaObject {
			break
		}
		return RecordingLiveSidecarKey(recordingID)
	}
	return "", fmt.Errorf("%w: unsupported recording path %q", ErrInvalidObjectKey, recordingPath)
}

// DerivedFrameKey returns a deterministic key for an extracted frame. The
// key is derived solely from the recording, the resolved capture timestamp,
// and the output format, so an identical request maps to the object a
// previous request already published.
func DerivedFrameKey(recordingID string, resolvedTS time.Time, format string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	if err := ValidateIdentifier("format", format); err != nil {
		return "", err
	}
	name := fmt.Sprintf("%s.%s", timestampSegment(resolvedTS), format)
	return path.Join(derivedRoot, recordingID, derivedFramesSegment, name), nil
}

// DerivedClipKey returns a deterministic key for an extracted clip, derived
// from the recording, both resolved boundary timestamps, and the output
// format.
func DerivedClipKey(recordingID string, resolvedStartTS, resolvedEndTS time.Time, format string) (string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return "", err
	}
	if err := ValidateIdentifier("format", format); err != nil {
		return "", err
	}
	name := fmt.Sprintf("%s_%s.%s", timestampSegment(resolvedStartTS), timestampSegment(resolvedEndTS), format)
	return path.Join(derivedRoot, recordingID, derivedClipsSegment, name), nil
}

// RecordingObjectPrefixes returns every logical prefix owned by a single
// recording, so source and derived objects can be removed together.
func RecordingObjectPrefixes(recordingID string) ([]string, error) {
	if err := ValidateIdentifier("recording_id", recordingID); err != nil {
		return nil, err
	}
	return []string{
		path.Join(recordingsRoot, recordingID) + "/",
		path.Join(derivedRoot, recordingID) + "/",
	}, nil
}

// timestampSegment renders an instant as a key segment. Colons are legal in
// S3 keys but awkward in URLs and shells, so the RFC3339Nano form is
// flattened to a compact, collision-free encoding that keeps nanosecond
// precision.
func timestampSegment(ts time.Time) string {
	utc := ts.UTC()
	return fmt.Sprintf("%s-%09d", utc.Format("20060102T150405"), utc.Nanosecond())
}
