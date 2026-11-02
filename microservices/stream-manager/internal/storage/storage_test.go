// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"encoding/base64"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestStoreLocks(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "storage")
	metadata, err := OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	media, err := OpenMediaStore(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := OpenMetadataStore(dir); err == nil {
		t.Fatal("second metadata store opened")
	}
	if _, err := OpenMediaStore(dir, 0); err == nil {
		t.Fatal("second media store opened")
	}
	if err := metadata.Close(); err != nil {
		t.Fatal(err)
	}
	if err := media.Close(); err != nil {
		t.Fatal(err)
	}
	if err := media.Close(); err != nil {
		t.Fatal("second close:", err)
	}
	reopened, err := OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	if err := reopened.Close(); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{".metadata.lock", ".media.lock", "stream-manager.db"} {
		info, err := os.Lstat(filepath.Join(dir, name))
		if err != nil || info.Mode().Perm() != 0o600 {
			t.Fatalf("%s: %v %v", name, info, err)
		}
	}
	shared := t.TempDir()
	if err := os.Chmod(shared, 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenMediaStore(shared, 0); err == nil {
		t.Fatal("non-private directory accepted")
	}
}

func TestValidRecordingID(t *testing.T) {
	for _, tc := range []struct {
		name, value string
		valid       bool
	}{
		{"short", "ABEiM0RVZneImaq7zN3u_w", true},
		{"leading underscore", "_BEiM0RVZneImaq7zN3u_w", true},
		{"legacy", "00112233-4455-6677-8899-aabbccddeeff", true},
		{"empty", "", false},
		{"too short", "ABEiM0RVZneImaq7zN3u_", false},
		{"padded", "ABEiM0RVZneImaq7zN3u_w==", false},
		{"invalid alphabet", "ABEiM0RVZneImaq7zN3u/w", false},
		{"noncanonical trailing bits", "ABEiM0RVZneImaq7zN3u_x", false},
		{"legacy uppercase", "00112233-4455-6677-8899-AABBCCDDEEFF", false},
		{"path traversal", "../recording", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := validRecordingID(tc.value); got != tc.valid {
				t.Fatalf("validRecordingID(%q) = %t, want %t", tc.value, got, tc.valid)
			}
		})
	}
}

func TestPutMediaAndDerived(t *testing.T) {
	ctx := context.Background()
	media, err := OpenMediaStore(filepath.Join(t.TempDir(), "storage"), 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	recordingUUID := uuid.MustParse("0b6f7a52-6f63-4e0e-9f0b-2d1d6c1f2a10")
	recordingID := base64.RawURLEncoding.EncodeToString(recordingUUID[:])
	filename, uri, err := media.PrepareMedia(ctx, recordingID)
	if err != nil {
		t.Fatal(err)
	}
	for _, invalidID := range []string{"../escape", "0b6f7a52-6f63-4e0e-9f0b-2d1d6c1f2a10/",
		strings.Repeat("a", 22), recordingID + "=", recordingID[:21]} {
		if _, _, err := media.PrepareMedia(ctx, invalidID); err == nil {
			t.Fatalf("invalid recording ID accepted: %q", invalidID)
		}
	}
	if _, _, err := media.PutMedia(ctx, uri); err == nil {
		t.Fatal("missing media published")
	}
	if err := os.WriteFile(filename, []byte("12345"), 0o600); err != nil {
		t.Fatal(err)
	}
	gotURI, size, err := media.PutMedia(ctx, uri)
	if err != nil || gotURI != uri || size != 5 {
		t.Fatalf("PutMedia = %q %d %v", gotURI, size, err)
	}
	derived := filepath.Join(filepath.Dir(filename), "derived")
	noTemp := func() {
		t.Helper()
		entries, _ := os.ReadDir(derived)
		for _, e := range entries {
			if e.Name()[0] == '.' {
				t.Fatalf("temp file left: %s", e.Name())
			}
		}
	}
	if _, _, err := media.PutDerived(ctx, uri, "../x.mp4", func(string) error { return nil }); err == nil {
		t.Fatal("bad name accepted")
	}
	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", func(string) error { return nil }); !errors.Is(err, ErrEmptyMedia) {
		t.Fatalf("empty output: %v", err)
	}
	noTemp()
	boom := errors.New("boom")
	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", func(string) error { return boom }); !errors.Is(err, boom) {
		t.Fatalf("write error: %v", err)
	}
	noTemp()
	if _, err := media.OpenDerived(ctx, uri, "frame-1.png"); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("failed write published: %v", err)
	}
	path, mtime, err := media.PutDerived(ctx, uri, "frame-1.png", func(p string) error {
		if filepath.Dir(p) != derived {
			t.Fatalf("temp outside derived dir: %s", p)
		}
		return os.WriteFile(p, []byte("png"), 0o600)
	})
	if err != nil || path != filepath.Join(derived, "frame-1.png") || mtime.IsZero() {
		t.Fatalf("PutDerived = %q %v %v", path, mtime, err)
	}
	noTemp()
	file, err := media.OpenDerived(ctx, uri, "frame-1.png")
	if err != nil || file.Name() != path {
		t.Fatalf("OpenDerived = %v %v", file, err)
	}
	_ = file.Close()
	if err := media.DeleteMedia(ctx, uri); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Dir(filename)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("recording dir kept: %v", err)
	}
}
