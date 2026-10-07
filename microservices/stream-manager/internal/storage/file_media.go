// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// DerivedURLSigner issues a capability URL that resolves to a derived
// object through GET /v1/media/{token}, without exposing the underlying
// filesystem path. internal/mediaaccess.Signer implements this.
type DerivedURLSigner interface {
	Sign(key string, expiresAt time.Time) (string, error)
}

// FileMediaStore is a MediaStore backed by a local filesystem directory.
// It lays objects out exactly like S3MediaStore's logical key space (see
// keys.go), rooted under a configured directory instead of a bucket:
//
//	<root>/recordings/{recording_id}/media.{ext}
//	<root>/recordings/{recording_id}/sidecar.{json,jsonl}
//	<root>/derived/{recording_id}/frames/...
//	<root>/derived/{recording_id}/clips/...
//
// Every logical key is validated with ValidateObjectKey before it is joined
// onto root, so a key can never resolve outside root regardless of what a
// caller (or corrupted metadata) supplies.
type FileMediaStore struct {
	root          string
	signer        DerivedURLSigner
	publicBaseURL string
}

var _ LiveRecordingLifecycleMediaStore = (*FileMediaStore)(nil)

// NewFileMediaStore builds a FileMediaStore rooted at root, issuing
// capability URLs of the form "{publicBaseURL}/v1/media/{token}" signed by
// signer. It creates root if it does not already exist.
func NewFileMediaStore(root, publicBaseURL string, signer DerivedURLSigner) (*FileMediaStore, error) {
	if strings.TrimSpace(root) == "" {
		return nil, errors.New("filesystem: root is required")
	}
	if strings.TrimSpace(publicBaseURL) == "" {
		return nil, errors.New("filesystem: public base URL is required")
	}
	if signer == nil {
		return nil, errors.New("filesystem: signer is required")
	}

	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("filesystem: resolve root %q: %w", root, err)
	}
	if err := os.MkdirAll(abs, 0o750); err != nil {
		return nil, fmt.Errorf("filesystem: create root %q: %w", abs, err)
	}

	return &FileMediaStore{
		root:          abs,
		signer:        signer,
		publicBaseURL: strings.TrimRight(publicBaseURL, "/"),
	}, nil
}

// resolvePath validates logicalKey and maps it to an absolute filesystem
// path under the store's root. It re-checks containment after joining as a
// defense-in-depth measure: ValidateObjectKey already rejects traversal
// segments, but a path escaping root would be a critical failure mode, so
// it is never trusted on a single check alone.
func (f *FileMediaStore) resolvePath(logicalKey string) (string, error) {
	if err := ValidateObjectKey(logicalKey); err != nil {
		return "", err
	}
	full := filepath.Join(f.root, filepath.FromSlash(logicalKey))
	rel, err := filepath.Rel(f.root, full)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("%w: key %q escapes the store root", ErrInvalidObjectKey, logicalKey)
	}
	return full, nil
}

func (f *FileMediaStore) OpenRecording(_ context.Context, recordingPath string) (io.ReadCloser, error) {
	return f.openObject(recordingPath)
}

func (f *FileMediaStore) OpenSidecar(_ context.Context, recordingID string) (io.ReadCloser, error) {
	key, err := RecordingSidecarKey(recordingID)
	if err != nil {
		return nil, err
	}
	return f.openObject(key)
}

func (f *FileMediaStore) OpenSidecarForRecording(_ context.Context, recordingID, recordingPath string) (io.ReadCloser, error) {
	key, err := RecordingSidecarKeyForPath(recordingID, recordingPath)
	if err != nil {
		return nil, err
	}
	return f.openObject(key)
}

func (f *FileMediaStore) OpenDerived(_ context.Context, key string) (io.ReadCloser, error) {
	return f.openObject(key)
}

func (f *FileMediaStore) openObject(logicalKey string) (io.ReadCloser, error) {
	path, err := f.resolvePath(logicalKey)
	if err != nil {
		return nil, err
	}
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("%w: %s", ErrObjectNotFound, logicalKey)
		}
		return nil, fmt.Errorf("open object %q: %w", logicalKey, err)
	}
	return file, nil
}

func (f *FileMediaStore) PutRecording(_ context.Context, recordingID string, media io.Reader, _ string) (string, error) {
	key, err := RecordingMediaKey(recordingID)
	if err != nil {
		return "", err
	}
	if err := f.putObject(key, media); err != nil {
		return "", err
	}
	return key, nil
}

func (f *FileMediaStore) PutSidecar(_ context.Context, recordingID string, sidecar io.Reader) (string, error) {
	key, err := RecordingSidecarKey(recordingID)
	if err != nil {
		return "", err
	}
	if err := f.putObject(key, sidecar); err != nil {
		return "", err
	}
	return key, nil
}

func (f *FileMediaStore) PutLiveRecording(_ context.Context, recordingID string, media io.Reader) (string, error) {
	key, err := RecordingLiveMediaKey(recordingID)
	if err != nil {
		return "", err
	}
	if err := f.putObject(key, media); err != nil {
		return "", err
	}
	return key, nil
}

func (f *FileMediaStore) PutLiveSidecar(_ context.Context, recordingID string, sidecar io.Reader) (string, error) {
	key, err := RecordingLiveSidecarKey(recordingID)
	if err != nil {
		return "", err
	}
	if err := f.putObject(key, sidecar); err != nil {
		return "", err
	}
	return key, nil
}

func (f *FileMediaStore) PrepareLiveRecording(ctx context.Context, recordingID string) (string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	key, err := RecordingLiveMediaKey(recordingID)
	if err != nil {
		return "", "", err
	}
	root, err := os.OpenRoot(f.root)
	if err != nil {
		return "", "", err
	}
	defer root.Close()
	relative := filepath.FromSlash(key)
	if err := root.MkdirAll(filepath.Dir(relative), 0o750); err != nil {
		return "", "", fmt.Errorf("create live recording directory: %w", err)
	}
	file, err := root.OpenFile(relative, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return "", "", fmt.Errorf("create live recording: %w", err)
	}
	if err := file.Close(); err != nil {
		_ = root.Remove(relative)
		return "", "", err
	}
	return filepath.Join(f.root, relative), key, nil
}

func (f *FileMediaStore) OpenLiveSidecarWriter(ctx context.Context, recordingID, recordingPath string) (io.WriteCloser, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	key, err := RecordingSidecarKeyForPath(recordingID, recordingPath)
	if err != nil {
		return nil, err
	}
	root, err := os.OpenRoot(f.root)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	relative := filepath.FromSlash(key)
	file, err := root.OpenFile(relative, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, fmt.Errorf("create live sidecar: %w", err)
	}
	return &syncingFileWriter{File: file}, nil
}

func (f *FileMediaStore) FinalizeLiveRecording(ctx context.Context, recordingPath string) (int64, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if err := ValidateObjectKey(recordingPath); err != nil {
		return 0, err
	}
	if filepath.Base(filepath.FromSlash(recordingPath)) != recordingLiveMediaObject {
		return 0, fmt.Errorf("%w: not a live media path", ErrInvalidObjectKey)
	}
	root, err := os.OpenRoot(f.root)
	if err != nil {
		return 0, err
	}
	defer root.Close()
	file, err := root.OpenFile(filepath.FromSlash(recordingPath), os.O_RDWR, 0)
	if err != nil {
		return 0, err
	}
	info, statErr := file.Stat()
	if statErr == nil && (!info.Mode().IsRegular() || info.Size() <= 0) {
		statErr = errors.New("live recording is empty or not a regular file")
	}
	if err := errors.Join(statErr, file.Sync(), file.Close()); err != nil {
		return 0, err
	}
	return info.Size(), nil
}

type syncingFileWriter struct {
	*os.File
}

func (w *syncingFileWriter) Close() error {
	return errors.Join(w.File.Sync(), w.File.Close())
}

func (f *FileMediaStore) PutDerived(_ context.Context, key string, media io.Reader, _ string, _ time.Duration) error {
	return f.putObject(key, media)
}

// putObject writes body to a temporary file alongside the destination and
// then atomically renames it into place, so a reader can never observe a
// partially written object at the final path.
func (f *FileMediaStore) putObject(logicalKey string, body io.Reader) error {
	path, err := f.resolvePath(logicalKey)
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return fmt.Errorf("put object %q: create directory: %w", logicalKey, err)
	}

	tmp, err := os.CreateTemp(dir, ".stage-*")
	if err != nil {
		return fmt.Errorf("put object %q: create staging file: %w", logicalKey, err)
	}
	tmpPath := tmp.Name()
	// Always attempt to remove the staging file; after a successful
	// rename it is already gone, so this is a no-op in the success path.
	defer os.Remove(tmpPath)

	if _, err := io.Copy(tmp, body); err != nil {
		tmp.Close()
		return fmt.Errorf("put object %q: write staging file: %w", logicalKey, err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("put object %q: close staging file: %w", logicalKey, err)
	}
	if err := os.Rename(tmpPath, path); err != nil {
		return fmt.Errorf("put object %q: publish: %w", logicalKey, err)
	}
	return nil
}

func (f *FileMediaStore) DerivedExists(_ context.Context, key string) (bool, error) {
	path, err := f.resolvePath(key)
	if err != nil {
		return false, err
	}
	if _, err := os.Stat(path); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return false, nil
		}
		return false, fmt.Errorf("stat object %q: %w", key, err)
	}
	return true, nil
}

// PresignDerived returns a GET /v1/media/{token} capability URL for key,
// signed to expire after expiresIn. The raw filesystem path is never
// embedded in the token or the URL.
func (f *FileMediaStore) PresignDerived(_ context.Context, key string, expiresIn time.Duration) (string, time.Time, error) {
	if err := ValidateObjectKey(key); err != nil {
		return "", time.Time{}, err
	}
	if expiresIn <= 0 {
		return "", time.Time{}, fmt.Errorf("presign object %q: expiry must be positive", key)
	}

	expiresAt := time.Now().UTC().Add(expiresIn)
	token, err := f.signer.Sign(key, expiresAt)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("presign object %q: %w", key, err)
	}
	return f.publicBaseURL + "/v1/media/" + token, expiresAt, nil
}

// DeleteRecordingObjects removes the recording, sidecar, and every derived
// object for recordingID by removing their directories outright.
func (f *FileMediaStore) DeleteRecordingObjects(_ context.Context, recordingID string) error {
	prefixes, err := RecordingObjectPrefixes(recordingID)
	if err != nil {
		return err
	}
	for _, logicalPrefix := range prefixes {
		dirKey := strings.TrimSuffix(logicalPrefix, "/")
		path, err := f.resolvePath(dirKey)
		if err != nil {
			return err
		}
		if err := os.RemoveAll(path); err != nil {
			return fmt.Errorf("delete objects under %q: %w", logicalPrefix, err)
		}
	}
	return nil
}

// Health confirms root exists and is writable by staging and removing a
// throwaway file inside it.
func (f *FileMediaStore) Health(_ context.Context) error {
	probe, err := os.CreateTemp(f.root, ".health-*")
	if err != nil {
		return fmt.Errorf("filesystem root %q not writable: %w", f.root, err)
	}
	path := probe.Name()
	probe.Close()
	if err := os.Remove(path); err != nil {
		return fmt.Errorf("filesystem root %q not writable: %w", f.root, err)
	}
	return nil
}

// InferredDerivedContentType returns a best-effort MIME type for a derived
// object key based on its file extension, for backends (like FileMediaStore)
// that do not separately persist the content type an object was published
// with.
func InferredDerivedContentType(key string) string {
	if ct := mime.TypeByExtension(filepath.Ext(key)); ct != "" {
		return ct
	}
	return "application/octet-stream"
}
