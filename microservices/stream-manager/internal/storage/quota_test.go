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
	"testing"

	"github.com/google/uuid"
)

func prepareTestMedia(t *testing.T, media *MediaStore) (filename, uri string) {
	t.Helper()
	id := uuid.New()
	filename, uri, err := media.PrepareMedia(context.Background(), base64.RawURLEncoding.EncodeToString(id[:]))
	if err != nil {
		t.Fatal(err)
	}
	return filename, uri
}

func writeDerived(content string) func(string) error {
	return func(path string) error { return os.WriteFile(path, []byte(content), 0o600) }
}

func TestMediaQuota(t *testing.T) {
	ctx := context.Background()
	dir := filepath.Join(t.TempDir(), "storage")
	media, err := OpenMediaStore(dir, 10)
	if err != nil {
		t.Fatal(err)
	}
	filename, uri := prepareTestMedia(t, media)

	if err := media.ReserveMedia(ctx, uri, 0); err != nil {
		t.Fatalf("empty store reported full: %v", err)
	}
	if err := media.ReserveMedia(ctx, uri, 6); err != nil {
		t.Fatal(err)
	}
	if err := media.ReserveMedia(ctx, uri, 5); !errors.Is(err, ErrStorageFull) {
		t.Fatalf("reservation past the limit: %v", err)
	}
	if err := os.WriteFile(filename, []byte("1234"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := media.PutMedia(ctx, uri); err != nil {
		t.Fatal(err)
	}
	if got := media.UsedBytes(); got != 4 {
		t.Fatalf("used after PutMedia = %d, want the file size 4", got)
	}

	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", writeDerived("1234567")); !errors.Is(err, ErrStorageFull) {
		t.Fatalf("derived file past the limit: %v", err)
	}
	if entries, _ := os.ReadDir(filepath.Join(filepath.Dir(filename), derivedDir)); len(entries) != 0 {
		t.Fatalf("rejected derived file left %d entries", len(entries))
	}
	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", writeDerived("123456")); err != nil {
		t.Fatal(err)
	}
	if err := media.ReserveMedia(ctx, uri, 0); !errors.Is(err, ErrStorageFull) {
		t.Fatalf("full store accepted a recording: %v", err)
	}
	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", writeDerived("123")); err != nil {
		t.Fatalf("smaller replacement in a full store: %v", err)
	}
	if got := media.UsedBytes(); got != 7 {
		t.Fatalf("used after replacement = %d, want 7", got)
	}

	other, otherURI := prepareTestMedia(t, media)
	if err := os.WriteFile(other, []byte("12"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := media.PutMedia(ctx, otherURI); err != nil {
		t.Fatal(err)
	}
	if err := media.Close(); err != nil {
		t.Fatal(err)
	}

	media, err = OpenMediaStore(dir, 10)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	if got := media.UsedBytes(); got != 9 {
		t.Fatalf("used after reopen = %d, want 9", got)
	}
	if err := media.DeleteMedia(ctx, uri); err != nil {
		t.Fatal(err)
	}
	if got := media.UsedBytes(); got != 2 {
		t.Fatalf("used after delete = %d, want 2", got)
	}
}

func TestReopenRemovesLeftoverDerivedTemp(t *testing.T) {
	ctx := context.Background()
	dir := filepath.Join(t.TempDir(), "storage")
	media, err := OpenMediaStore(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	filename, uri := prepareTestMedia(t, media)
	if _, _, err := media.PutDerived(ctx, uri, "frame-1.png", writeDerived("123")); err != nil {
		t.Fatal(err)
	}
	leftover := filepath.Join(filepath.Dir(filename), derivedDir, tempDerivedPrefix+"crashed.png")
	if err := os.WriteFile(leftover, []byte("12345"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := media.Close(); err != nil {
		t.Fatal(err)
	}

	media, err = OpenMediaStore(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	if _, err := os.Stat(leftover); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("leftover temporary file kept: %v", err)
	}
	if got := media.UsedBytes(); got != 3 {
		t.Fatalf("used after reopen = %d, want only the derived frame 3", got)
	}
	file, err := media.OpenDerived(ctx, uri, "frame-1.png")
	if err != nil {
		t.Fatalf("saved derived frame removed: %v", err)
	}
	_ = file.Close()
}

func TestMediaWithoutQuota(t *testing.T) {
	media, err := OpenMediaStore(filepath.Join(t.TempDir(), "storage"), 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	_, uri := prepareTestMedia(t, media)
	if err := media.ReserveMedia(context.Background(), uri, 1<<40); err != nil {
		t.Fatalf("unlimited store rejected a reservation: %v", err)
	}
}

func TestMediaLease(t *testing.T) {
	ctx := context.Background()
	media, err := OpenMediaStore(filepath.Join(t.TempDir(), "storage"), 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = media.Close() })
	filename, uri := prepareTestMedia(t, media)
	if err := os.WriteFile(filename, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}

	first, err := media.AcquireMedia(ctx, uri)
	if err != nil {
		t.Fatal(err)
	}
	second, err := media.AcquireMedia(ctx, uri)
	if err != nil {
		t.Fatal(err)
	}
	first()
	first()
	if err := media.DeleteMedia(ctx, uri); !errors.Is(err, ErrMediaBusy) {
		t.Fatalf("delete with one lease left: %v", err)
	}
	second()
	if err := media.DeleteMedia(ctx, uri); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filename); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("media kept: %v", err)
	}
	if _, err := media.AcquireMedia(ctx, uri); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("lease on deleted media: %v", err)
	}
}
