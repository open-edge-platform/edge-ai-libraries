// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type stubSigner struct {
	lastKey string
	err     error
}

func (s *stubSigner) Sign(key string, _ time.Time) (string, error) {
	if s.err != nil {
		return "", s.err
	}
	s.lastKey = key
	return "signed-" + strings.ReplaceAll(key, "/", "_"), nil
}

func newTestFileStore(t *testing.T) (*FileMediaStore, *stubSigner) {
	t.Helper()
	signer := &stubSigner{}
	store, err := NewFileMediaStore(t.TempDir(), "http://media.test", signer)
	if err != nil {
		t.Fatalf("NewFileMediaStore: %v", err)
	}
	return store, signer
}

func TestFileMediaStorePutOpenRoundTrip(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()

	key, err := store.PutRecording(ctx, "rec-001", bytes.NewReader([]byte("hello")), "video/mp4")
	if err != nil {
		t.Fatalf("PutRecording: %v", err)
	}

	reader, err := store.OpenRecording(ctx, key)
	if err != nil {
		t.Fatalf("OpenRecording: %v", err)
	}
	defer reader.Close()
	body, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if string(body) != "hello" {
		t.Fatalf("got %q", body)
	}
}

func TestFileMediaStoreOpensJSONLSidecarForLiveRecording(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()
	mediaKey, err := store.PutLiveRecording(ctx, "rec-live-1", strings.NewReader("mpeg-ts bytes"))
	if err != nil {
		t.Fatalf("PutLiveRecording: %v", err)
	}
	mediaReader, err := store.OpenRecording(ctx, mediaKey)
	if err != nil {
		t.Fatalf("OpenRecording: %v", err)
	}
	mediaBody, err := io.ReadAll(mediaReader)
	mediaReader.Close()
	if err != nil || string(mediaBody) != "mpeg-ts bytes" {
		t.Fatalf("read live media = %q, %v", mediaBody, err)
	}

	_, err = store.PutLiveSidecar(ctx, "rec-live-1", strings.NewReader("live sidecar"))
	if err != nil {
		t.Fatalf("PutLiveSidecar: %v", err)
	}

	reader, err := store.OpenSidecarForRecording(ctx, "rec-live-1", "recordings/rec-live-1/media.ts")
	if err != nil {
		t.Fatalf("OpenSidecarForRecording: %v", err)
	}
	defer reader.Close()
	body, err := io.ReadAll(reader)
	if err != nil || string(body) != "live sidecar" {
		t.Fatalf("read sidecar = %q, %v", body, err)
	}

	if _, err := store.OpenSidecarForRecording(ctx, "rec-live-1", "recordings/rec-other/media.ts"); !errors.Is(err, ErrInvalidObjectKey) {
		t.Fatalf("mismatched recording path error = %v, want ErrInvalidObjectKey", err)
	}
}

func TestFileMediaStoreLiveWriterUsesCanonicalPaths(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()
	filename, mediaKey, err := store.PrepareLiveRecording(ctx, "rec-writer-1")
	if err != nil {
		t.Fatalf("PrepareLiveRecording: %v", err)
	}
	if mediaKey != "recordings/rec-writer-1/media.ts" {
		t.Fatalf("media key = %q", mediaKey)
	}
	if err := os.WriteFile(filename, []byte("ts-data"), 0o600); err != nil {
		t.Fatalf("write media: %v", err)
	}
	sidecar, err := store.OpenLiveSidecarWriter(ctx, "rec-writer-1", mediaKey)
	if err != nil {
		t.Fatalf("OpenLiveSidecarWriter: %v", err)
	}
	if _, err := io.WriteString(sidecar, "jsonl-data\n"); err != nil {
		t.Fatalf("write sidecar: %v", err)
	}
	if err := sidecar.Close(); err != nil {
		t.Fatalf("close sidecar: %v", err)
	}
	if size, err := store.FinalizeLiveRecording(ctx, mediaKey); err != nil || size != int64(len("ts-data")) {
		t.Fatalf("FinalizeLiveRecording = %d, %v", size, err)
	}
	reader, err := store.OpenSidecarForRecording(ctx, "rec-writer-1", mediaKey)
	if err != nil {
		t.Fatalf("OpenSidecarForRecording: %v", err)
	}
	defer reader.Close()
	body, err := io.ReadAll(reader)
	if err != nil || string(body) != "jsonl-data\n" {
		t.Fatalf("sidecar body = %q, %v", body, err)
	}
}

func TestFileMediaStoreOpenMissingObject(t *testing.T) {
	store, _ := newTestFileStore(t)
	if _, err := store.OpenDerived(context.Background(), "derived/rec-001/frames/a.jpeg"); !errors.Is(err, ErrObjectNotFound) {
		t.Fatalf("got %v, want ErrObjectNotFound", err)
	}
}

func TestFileMediaStoreRejectsTraversal(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()

	cases := []string{
		"../escape",
		"recordings/../../escape",
		"/etc/passwd",
		"recordings/rec-001/../../../etc/passwd",
	}
	for _, key := range cases {
		if _, err := store.OpenDerived(ctx, key); err == nil {
			t.Fatalf("key %q: expected error, got nil", key)
		}
		if err := store.putObject(key, bytes.NewReader(nil)); err == nil {
			t.Fatalf("key %q: expected put error, got nil", key)
		}
	}
}

func TestFileMediaStorePutDerivedIsAtomic(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()
	key := "derived/rec-001/frames/x.jpeg"

	if err := store.PutDerived(ctx, key, bytes.NewReader([]byte("frame-bytes")), "image/jpeg", 0); err != nil {
		t.Fatalf("PutDerived: %v", err)
	}

	// No staging files should be left behind.
	dir := filepath.Join(store.root, "derived", "rec-001", "frames")
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	if len(entries) != 1 || entries[0].Name() != "x.jpeg" {
		t.Fatalf("unexpected directory contents: %v", entries)
	}

	exists, err := store.DerivedExists(ctx, key)
	if err != nil || !exists {
		t.Fatalf("DerivedExists: %v, %v", exists, err)
	}
}

func TestFileMediaStorePresignDerivedReturnsMediaURL(t *testing.T) {
	store, signer := newTestFileStore(t)
	url, expiry, err := store.PresignDerived(context.Background(), "derived/rec-001/frames/x.jpeg", time.Minute)
	if err != nil {
		t.Fatalf("PresignDerived: %v", err)
	}
	if !strings.HasPrefix(url, "http://media.test/v1/media/signed-") {
		t.Fatalf("got url %q", url)
	}
	if signer.lastKey != "derived/rec-001/frames/x.jpeg" {
		t.Fatalf("signer saw key %q", signer.lastKey)
	}
	if !expiry.After(time.Now()) {
		t.Fatalf("expiry %v not in the future", expiry)
	}
}

func TestFileMediaStorePresignDerivedRejectsBadKey(t *testing.T) {
	store, _ := newTestFileStore(t)
	if _, _, err := store.PresignDerived(context.Background(), "../escape", time.Minute); err == nil {
		t.Fatalf("expected error")
	}
}

func TestFileMediaStoreDeleteRecordingObjects(t *testing.T) {
	store, _ := newTestFileStore(t)
	ctx := context.Background()

	if _, err := store.PutRecording(ctx, "rec-001", bytes.NewReader([]byte("media")), ""); err != nil {
		t.Fatalf("PutRecording: %v", err)
	}
	if err := store.PutDerived(ctx, "derived/rec-001/frames/x.jpeg", bytes.NewReader([]byte("x")), "image/jpeg", 0); err != nil {
		t.Fatalf("PutDerived: %v", err)
	}

	if err := store.DeleteRecordingObjects(ctx, "rec-001"); err != nil {
		t.Fatalf("DeleteRecordingObjects: %v", err)
	}

	if _, err := os.Stat(filepath.Join(store.root, "recordings", "rec-001")); !os.IsNotExist(err) {
		t.Fatalf("recordings dir still present: %v", err)
	}
	if _, err := os.Stat(filepath.Join(store.root, "derived", "rec-001")); !os.IsNotExist(err) {
		t.Fatalf("derived dir still present: %v", err)
	}
}

func TestFileMediaStoreHealth(t *testing.T) {
	store, _ := newTestFileStore(t)
	if err := store.Health(context.Background()); err != nil {
		t.Fatalf("Health: %v", err)
	}
}

func TestFileMediaStoreHealthFailsWhenRootMissing(t *testing.T) {
	store, _ := newTestFileStore(t)
	if err := os.RemoveAll(store.root); err != nil {
		t.Fatalf("RemoveAll: %v", err)
	}
	if err := store.Health(context.Background()); err == nil {
		t.Fatalf("expected error when root is missing")
	}
}

func TestNewFileMediaStoreRequiresArgs(t *testing.T) {
	if _, err := NewFileMediaStore("", "http://x", &stubSigner{}); err == nil {
		t.Fatalf("expected error for empty root")
	}
	if _, err := NewFileMediaStore(t.TempDir(), "", &stubSigner{}); err == nil {
		t.Fatalf("expected error for empty public base URL")
	}
	if _, err := NewFileMediaStore(t.TempDir(), "http://x", nil); err == nil {
		t.Fatalf("expected error for nil signer")
	}
}

func TestInferredContentType(t *testing.T) {
	cases := map[string]string{
		"derived/rec/frames/x.jpeg": "image/jpeg",
		"derived/rec/frames/x.png":  "image/png",
		"derived/rec/clips/x.mp4":   "video/mp4",
		"derived/rec/clips/x.bin":   "application/octet-stream",
	}
	for key, want := range cases {
		if got := InferredDerivedContentType(key); got != want {
			t.Fatalf("key %q: got %q, want %q", key, got, want)
		}
	}
}
