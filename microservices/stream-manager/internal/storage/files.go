// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/sys/unix"
)

// PrepareMedia reserves a private UUID directory. FFmpeg creates media.ts there.
func (s *Store) PrepareMedia(ctx context.Context, id string) (filename, uri string, err error) {
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

func (s *Store) relativeMedia(uri string) (string, error) {
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
func (s *Store) PutMedia(ctx context.Context, uri string) (string, error) {
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

func (s *Store) OpenMedia(ctx context.Context, uri string) (string, error) {
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

func (s *Store) DeleteMedia(ctx context.Context, uri string) error {
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
