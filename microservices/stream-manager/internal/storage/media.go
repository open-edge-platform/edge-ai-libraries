// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"crypto/rand"
	"errors"
	"io"
	"io/fs"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"golang.org/x/sys/unix"
)

// MediaHandler reserves, saves, opens and deletes recorded media and the
// frames and clips derived from it.
type MediaHandler interface {
	PrepareMedia(ctx context.Context, recordingID string) (filename, uri string, err error)
	PutMedia(ctx context.Context, uri string) (string, int64, error)
	OpenMedia(ctx context.Context, uri string) (string, error)
	DeleteMedia(ctx context.Context, uri string) error
	PutDerived(ctx context.Context, uri, name string, write func(path string) error) (string, time.Time, error)
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

var ErrEmptyMedia = errors.New("media is empty or invalid")

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

// PutMedia durably publishes an already-written file and returns its URI and
// size in bytes; readiness is recorded in the metadata.
func (s *MediaStore) PutMedia(ctx context.Context, uri string) (string, int64, error) {
	if err := ctx.Err(); err != nil {
		return "", 0, err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return "", 0, err
	}
	file, err := s.root.OpenFile(relative, os.O_RDONLY|unix.O_NOFOLLOW, 0)
	if err != nil {
		return "", 0, err
	}
	info, statErr := file.Stat()
	if statErr != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return "", 0, errors.Join(ErrEmptyMedia, statErr, file.Close())
	}
	if err := errors.Join(file.Sync(), file.Close()); err != nil {
		return "", 0, err
	}
	for _, name := range []string{filepath.Dir(relative), "."} {
		directory, err := s.root.Open(name)
		if err != nil {
			return "", 0, err
		}
		if err := errors.Join(directory.Sync(), directory.Close()); err != nil {
			return "", 0, err
		}
	}
	return uri, info.Size(), nil
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

// relativeDerived returns the directory, relative to the root, that holds the
// frames and clips cut from a recording. DeleteMedia removes it with the recording.
func (s *MediaStore) relativeDerived(uri string) (string, error) {
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return "", err
	}
	return filepath.Join(filepath.Dir(relative), derivedDir), nil
}

// PutDerived saves the frame or clip called name for a recording. write fills
// a private temporary file, which then replaces name atomically. It returns
// the absolute path and modification time of the saved file.
func (s *MediaStore) PutDerived(ctx context.Context, uri, name string,
	write func(path string) error,
) (_ string, _ time.Time, result error) {
	if err := ctx.Err(); err != nil {
		return "", time.Time{}, err
	}
	if !derivedName.MatchString(name) {
		return "", time.Time{}, errors.New("invalid derived media name")
	}
	dir, err := s.relativeDerived(uri)
	if err != nil {
		return "", time.Time{}, err
	}
	if err := s.root.Mkdir(dir, 0o700); err != nil && !errors.Is(err, fs.ErrExist) {
		return "", time.Time{}, err
	}
	tmp := filepath.Join(dir, ".tmp-"+rand.Text()+filepath.Ext(name))
	file, err := s.root.OpenFile(tmp, os.O_CREATE|os.O_EXCL|os.O_WRONLY|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return "", time.Time{}, err
	}
	defer func() {
		if result != nil {
			result = errors.Join(result, s.root.Remove(tmp))
		}
	}()
	if err := file.Close(); err != nil {
		return "", time.Time{}, err
	}
	if err := write(file.Name()); err != nil {
		return "", time.Time{}, err
	}
	info, err := s.root.Lstat(tmp)
	if err != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return "", time.Time{}, errors.Join(ErrEmptyMedia, err)
	}
	target := filepath.Join(dir, name)
	if err := s.root.Rename(tmp, target); err != nil {
		return "", time.Time{}, err
	}
	return filepath.Join(s.root.Name(), target), info.ModTime(), nil
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
	dir, err := s.relativeDerived(uri)
	if err != nil {
		return nil, err
	}
	file, err := s.root.OpenFile(filepath.Join(dir, name), os.O_RDONLY|unix.O_NOFOLLOW, 0)
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
