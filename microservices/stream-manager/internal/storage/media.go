// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"

	"golang.org/x/sys/unix"
)

// MediaHandler reserves, saves, opens and deletes recorded media and the
// frames and clips derived from it.
type MediaHandler interface {
	PrepareMedia(ctx context.Context, recordingID string) (filename, uri string, err error)
	PutMedia(ctx context.Context, uri string) (string, error)
	OpenMedia(ctx context.Context, uri string) (string, error)
	DeleteMedia(ctx context.Context, uri string) error
	DerivedDir(ctx context.Context, uri string) (string, error)
	OpenDerived(ctx context.Context, uri, name string) (*os.File, error)
}

// MediaStore keeps media files in one private UUID directory per recording.
type MediaStore struct {
	root      *os.Root
	lock      *os.File
	closeOnce sync.Once
	closeErr  error
}

var (
	_ MediaHandler = (*MediaStore)(nil)
	_ io.Closer    = (*MediaStore)(nil)
)

func OpenMediaStore(directory string) (*MediaStore, error) {
	root, lock, err := openPrivateDir(directory, ".media.lock")
	if err != nil {
		return nil, err
	}
	return &MediaStore{root: root, lock: lock}, nil
}

const derivedDir = "derived"

// Derived media names carry offsets in nanoseconds from the recording start.
var derivedName = regexp.MustCompile(`^(frame-[0-9]+\.(jpeg|png)|clip-[0-9]+-[0-9]+\.mp4)$`)

// PrepareMedia reserves a private UUID directory. FFmpeg creates media.ts there.
func (s *MediaStore) PrepareMedia(ctx context.Context, id string) (filename, uri string, err error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	if !validRecordingID(id) {
		return "", "", errors.New("invalid recording ID")
	}
	if err := s.root.Mkdir(id, 0o700); err != nil {
		return "", "", err
	}
	filename = filepath.Join(s.root.Name(), id, "media.ts")
	uri = (&url.URL{Scheme: "file", Path: filename}).String()
	return filename, uri, nil
}

func (s *MediaStore) relativeMedia(uri string) (string, error) {
	u, err := url.Parse(uri)
	if err != nil || u.Scheme != "file" || u.Host != "" || u.RawQuery != "" || u.Fragment != "" {
		return "", errors.New("invalid recording media URI")
	}
	relative, err := filepath.Rel(s.root.Name(), u.Path)
	if err != nil {
		return "", errors.New("invalid recording media location")
	}
	parts := strings.Split(filepath.ToSlash(relative), "/")
	if len(parts) != 2 || !validRecordingID(parts[0]) || parts[1] != "media.ts" {
		return "", errors.New("recording media is outside its UUID directory")
	}
	return relative, nil
}

// PutMedia durably publishes an already-written file; readiness is recorded in SQLite.
func (s *MediaStore) PutMedia(ctx context.Context, uri string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return "", err
	}
	file, err := s.root.OpenFile(relative, os.O_RDONLY|unix.O_NOFOLLOW, 0)
	if err != nil {
		return "", err
	}
	info, statErr := file.Stat()
	if statErr != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return "", errors.Join(errors.New("recording media is empty or invalid"), statErr, file.Close())
	}
	if err := errors.Join(file.Sync(), file.Close()); err != nil {
		return "", err
	}
	for _, name := range []string{filepath.Dir(relative), "."} {
		directory, err := s.root.Open(name)
		if err != nil {
			return "", err
		}
		if err := errors.Join(directory.Sync(), directory.Close()); err != nil {
			return "", err
		}
	}
	return uri, nil
}

func (s *MediaStore) OpenMedia(ctx context.Context, uri string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return "", err
	}
	info, err := s.root.Lstat(relative)
	if err != nil {
		return "", err
	}
	if !info.Mode().IsRegular() {
		return "", errors.New("recording media is not a regular file")
	}
	return filepath.Join(s.root.Name(), relative), nil
}

func (s *MediaStore) DeleteMedia(ctx context.Context, uri string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return err
	}
	if err := s.root.RemoveAll(filepath.Dir(relative)); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

// DerivedDir returns the directory holding frames and clips cut from a
// recording, creating it if needed. DeleteMedia removes it with the recording.
func (s *MediaStore) DerivedDir(ctx context.Context, uri string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return "", err
	}
	dir := filepath.Join(filepath.Dir(relative), derivedDir)
	if err := s.root.Mkdir(dir, 0o700); err != nil && !errors.Is(err, fs.ErrExist) {
		return "", err
	}
	return filepath.Join(s.root.Name(), dir), nil
}

// OpenDerived opens a frame or clip cut from a recording. Unknown names
// report fs.ErrNotExist.
func (s *MediaStore) OpenDerived(ctx context.Context, uri, name string) (*os.File, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if !derivedName.MatchString(name) {
		return nil, fs.ErrNotExist
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return nil, err
	}
	file, err := s.root.OpenFile(filepath.Join(filepath.Dir(relative), derivedDir, name), os.O_RDONLY|unix.O_NOFOLLOW, 0)
	if err != nil {
		return nil, err
	}
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		return nil, errors.Join(fs.ErrNotExist, err, file.Close())
	}
	return file, nil
}

func (s *MediaStore) Close() error {
	s.closeOnce.Do(func() {
		s.closeErr = errors.Join(s.lock.Close(), s.root.Close())
	})
	return s.closeErr
}
