// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package storage holds the production persistence seams: object storage for
// recording, sidecar, and derived media, and a metadata store for recording
// rows.
package storage

import (
	"context"
	"io"
	"time"
)

// MediaStore is the production storage seam for recording, sidecar, and
// derived (frame/clip) media. Retrieval depends only on this interface: it
// never imports an object-store SDK, opens a local file directly, or
// constructs backend-specific paths itself. Concrete implementations own
// where bytes physically live and map logical keys (see keys.go) onto the
// backend's own addressing.
//
// Source objects (the recording and its sidecar) are immutable as far as
// retrieval is concerned: retrieval only ever opens them. The Put* source
// methods exist so development tooling can stage a fixture through the same
// adapter the service reads through; they are deliberately not a statement
// about how a future recording pipeline will publish media.
type MediaStore interface {
	// OpenRecording streams the finalized recording named by a recording's
	// recording_path. The caller is responsible for closing the reader.
	OpenRecording(ctx context.Context, recordingPath string) (io.ReadCloser, error)
	// OpenSidecar streams the recording's sidecar.json object. Retrieval
	// parses and validates the returned bytes; storage adapters must not
	// parse sidecar content themselves.
	OpenSidecar(ctx context.Context, recordingID string) (io.ReadCloser, error)
	// OpenDerived streams a previously published derived (frame/clip)
	// object by its store key.
	OpenDerived(ctx context.Context, key string) (io.ReadCloser, error)

	// PutRecording writes the source recording object for recordingID and
	// returns the key it was written to, which is what belongs in the
	// recording's recording_path.
	PutRecording(ctx context.Context, recordingID string, media io.Reader, contentType string) (string, error)
	// PutSidecar writes the source sidecar object for recordingID and
	// returns the key it was written to.
	PutSidecar(ctx context.Context, recordingID string, sidecar io.Reader) (string, error)

	// PutDerived publishes a derived object, replacing any existing object
	// at the same key. ttl is a hint for backends that expire derived
	// objects (e.g. object lifecycle rules); it is not a hard guarantee.
	PutDerived(ctx context.Context, key string, media io.Reader, contentType string, ttl time.Duration) error
	// DerivedExists reports whether a derived object is already published,
	// so callers can reuse cached output instead of re-extracting it.
	DerivedExists(ctx context.Context, key string) (bool, error)
	// PresignDerived issues a short-lived, backend-specific URL that
	// resolves directly to a derived object without exposing the
	// underlying recording or requiring the retrieval service to serve
	// bytes itself.
	PresignDerived(ctx context.Context, key string, expiresIn time.Duration) (string, time.Time, error)

	// DeleteRecordingObjects removes the recording, sidecar, and every
	// derived object associated with a recording together, so a delete can
	// never leave a partial or orphaned object behind.
	DeleteRecordingObjects(ctx context.Context, recordingID string) error
	// Health reports whether the backend is reachable and the configured
	// bucket is usable, for use in service readiness checks.
	Health(ctx context.Context) error
}

// RecordingSidecarMediaStore is an optional capability for stores whose
// sidecar key depends on the source format declared by recordingPath.
// Callers should fall back to MediaStore.OpenSidecar when it is not
// implemented, preserving compatibility with existing backends.
type RecordingSidecarMediaStore interface {
	OpenSidecarForRecording(ctx context.Context, recordingID, recordingPath string) (io.ReadCloser, error)
}

// LiveRecordingMediaStore is an optional capability for backends that publish
// live MPEG-TS recordings and append-only JSONL sidecars. It does not change
// the finalized PutRecording/PutSidecar behavior of existing MediaStore
// implementations.
type LiveRecordingMediaStore interface {
	PutLiveRecording(ctx context.Context, recordingID string, media io.Reader) (string, error)
	PutLiveSidecar(ctx context.Context, recordingID string, sidecar io.Reader) (string, error)
}

// LiveRecordingWriterStore is the filesystem capability used by an active
// recorder. Unlike PutLiveRecording, it creates a private in-progress TS
// file and an append-only JSONL writer at canonical logical keys.
type LiveRecordingWriterStore interface {
	PrepareLiveRecording(ctx context.Context, recordingID string) (filename, recordingPath string, err error)
	OpenLiveSidecarWriter(ctx context.Context, recordingID, recordingPath string) (io.WriteCloser, error)
	FinalizeLiveRecording(ctx context.Context, recordingPath string) (sizeBytes int64, err error)
}

// LiveRecordingLifecycleMediaStore combines retrieval storage with the
// optional filesystem writer required by the stream recorder.
type LiveRecordingLifecycleMediaStore interface {
	MediaStore
	LiveRecordingWriterStore
}
