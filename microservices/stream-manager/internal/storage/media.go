// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"crypto/rand"
	"errors"
	"io"
	"io/fs"
	"log/slog"
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
	ListMedia(ctx context.Context) (map[string]string, error)
	PrepareMedia(ctx context.Context, recordingID string) (filename, uri string, err error)
	PutMedia(ctx context.Context, uri string) (string, int64, error)
	OpenMedia(ctx context.Context, uri string) (string, error)
	DeleteMedia(ctx context.Context, uri string) error
	PutDerived(ctx context.Context, uri, name string, write func(path string) error) (string, time.Time, error)
	OpenDerived(ctx context.Context, uri, name string) (*os.File, error)
	ReserveMedia(ctx context.Context, uri string, size int64) error
	AcquireMedia(ctx context.Context, uri string) (release func(), err error)
}

// MediaStore keeps media files in one private UUID directory per recording.
// A positive limit caps the bytes that recording directories may hold.
type MediaStore struct {
	root      *os.Root
	lock      *os.File
	closeOnce sync.Once
	closeErr  error

	mu       sync.Mutex
	limit    int64
	used     int64
	usage    map[string]int64 // bytes charged to each recording directory
	readers  map[string]int   // active leases on each recording directory
	deleting map[string]bool
}

var (
	_ MediaHandler = (*MediaStore)(nil)
	_ io.Closer    = (*MediaStore)(nil)
)

// OpenMediaStore opens the media directory. limitBytes caps the stored
// recording bytes; zero or less means no limit.
func OpenMediaStore(directory string, limitBytes int64) (*MediaStore, error) {
	root, lock, err := openPrivateDir(directory, ".media.lock")
	if err != nil {
		return nil, err
	}
	s := &MediaStore{
		root: root, lock: lock, limit: limitBytes,
		usage: make(map[string]int64), readers: make(map[string]int), deleting: make(map[string]bool),
	}
	if err := s.loadUsage(); err != nil {
		return nil, errors.Join(err, s.Close())
	}
	return s, nil
}

const (
	derivedDir        = "derived"
	tempDerivedPrefix = ".tmp-"
)

var (
	ErrEmptyMedia  = errors.New("media is empty or invalid")
	ErrStorageFull = errors.New("recording storage quota reached")
	ErrMediaBusy   = errors.New("recording media is in use")
)

func (s *MediaStore) loadUsage() error {
	entries, err := fs.ReadDir(s.root.FS(), ".")
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if !entry.IsDir() || !validRecordingID(entry.Name()) {
			continue
		}
		s.removeTempDerived(entry.Name())
		size, err := s.dirSize(entry.Name())
		if err != nil {
			return err
		}
		s.usage[entry.Name()] = size
		s.used += size
	}
	return nil
}

// removeTempDerived deletes the temporary files that an interrupted frame or
// clip extraction left in a recording's derived directory.
func (s *MediaStore) removeTempDerived(dir string) {
	leftovers, err := fs.Glob(s.root.FS(), filepath.Join(dir, derivedDir, tempDerivedPrefix+"*"))
	if err != nil {
		slog.Warn("could not list leftover derived media", "directory", dir, "error", err)
		return
	}
	for _, leftover := range leftovers {
		if err := s.root.Remove(leftover); err != nil && !errors.Is(err, fs.ErrNotExist) {
			slog.Warn("could not delete leftover derived media", "file", leftover, "error", err)
		}
	}
}

func (s *MediaStore) dirSize(dir string) (int64, error) {
	var total int64
	err := fs.WalkDir(s.root.FS(), dir, func(_ string, entry fs.DirEntry, err error) error {
		if err != nil || !entry.Type().IsRegular() {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		total += info.Size()
		return nil
	})
	if errors.Is(err, fs.ErrNotExist) {
		return total, nil
	}
	return total, err
}

// chargeLocked adds delta bytes to dir; growth past the limit fails with ErrStorageFull.
func (s *MediaStore) chargeLocked(dir string, delta int64) error {
	if delta > 0 && s.limit > 0 && s.used+delta > s.limit {
		return ErrStorageFull
	}
	s.usage[dir] += delta
	s.used += delta
	return nil
}

// ReserveMedia charges size bytes to a recording before they are written.
// A zero size checks that the store still has free space.
func (s *MediaStore) ReserveMedia(ctx context.Context, uri string, size int64) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if size < 0 {
		return errors.New("invalid reservation size")
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if size == 0 && s.limit > 0 && s.used >= s.limit {
		return ErrStorageFull
	}
	return s.chargeLocked(filepath.Dir(relative), size)
}

// AcquireMedia keeps a recording's media from deletion until release is
// called. Missing or deleting media reports fs.ErrNotExist.
func (s *MediaStore) AcquireMedia(ctx context.Context, uri string) (func(), error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	relative, err := s.relativeMedia(uri)
	if err != nil {
		return nil, err
	}
	dir := filepath.Dir(relative)
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.deleting[dir] {
		return nil, fs.ErrNotExist
	}
	if _, err := s.root.Lstat(dir); err != nil {
		return nil, err
	}
	s.readers[dir]++
	var once sync.Once
	return func() {
		once.Do(func() {
			s.mu.Lock()
			defer s.mu.Unlock()
			if s.readers[dir]--; s.readers[dir] == 0 {
				delete(s.readers, dir)
			}
		})
	}, nil
}

// UsedBytes returns the bytes charged to all recordings.
func (s *MediaStore) UsedBytes() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.used
}

// Derived media names carry offsets in nanoseconds from the recording start.
var derivedName = regexp.MustCompile(`^(frame-[0-9]+\.(jpeg|png)|clip-[0-9]+-[0-9]+\.mp4)$`)

// ListMedia maps recording IDs to their media URIs, including orphaned directories.
func (s *MediaStore) ListMedia(ctx context.Context) (map[string]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	entries, err := fs.ReadDir(s.root.FS(), ".")
	if err != nil {
		return nil, err
	}
	media := make(map[string]string)
	for _, entry := range entries {
		if !entry.IsDir() || !validRecordingID(entry.Name()) {
			continue
		}
		path := filepath.Join(s.root.Name(), entry.Name(), "media.ts")
		media[entry.Name()] = (&url.URL{Scheme: "file", Path: path}).String()
	}
	return media, nil
}

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
	s.mu.Lock()
	dir := filepath.Dir(relative)
	s.used += info.Size() - s.usage[dir]
	s.usage[dir] = info.Size()
	s.mu.Unlock()
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
	dir := filepath.Dir(relative)
	s.mu.Lock()
	if s.readers[dir] > 0 || s.deleting[dir] {
		s.mu.Unlock()
		return ErrMediaBusy
	}
	s.deleting[dir] = true
	s.mu.Unlock()
	removeErr := s.root.RemoveAll(dir)
	if errors.Is(removeErr, os.ErrNotExist) {
		removeErr = nil
	}
	remaining, sizeErr := s.dirSize(dir)
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.deleting, dir)
	if sizeErr != nil {
		return errors.Join(removeErr, sizeErr)
	}
	s.used += remaining - s.usage[dir]
	if remaining == 0 {
		delete(s.usage, dir)
	} else {
		s.usage[dir] = remaining
	}
	return removeErr
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
	tmp := filepath.Join(dir, tempDerivedPrefix+rand.Text()+filepath.Ext(name))
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
	if err := s.replaceDerived(tmp, target, info.Size()); err != nil {
		return "", time.Time{}, err
	}
	return filepath.Join(s.root.Name(), target), info.ModTime(), nil
}

// replaceDerived moves tmp to target when the quota allows the size change.
func (s *MediaStore) replaceDerived(tmp, target string, size int64) error {
	recordingDir := filepath.Dir(filepath.Dir(target))
	s.mu.Lock()
	defer s.mu.Unlock()
	var replaced int64
	if old, err := s.root.Lstat(target); err == nil && old.Mode().IsRegular() {
		replaced = old.Size()
	}
	if err := s.chargeLocked(recordingDir, size-replaced); err != nil {
		return err
	}
	if err := s.root.Rename(tmp, target); err != nil {
		s.usage[recordingDir] -= size - replaced
		s.used -= size - replaced
		return err
	}
	return nil
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
