// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package storage persists recording metadata and the recorded media.
package storage

import (
	"encoding/base64"
	"errors"
	"os"
	"path/filepath"

	"github.com/google/uuid"
	"golang.org/x/sys/unix"
)

// openPrivateDir opens a directory that only the service user can access and
// takes the exclusive lock file lockName in it.
func openPrivateDir(directory, lockName string) (_ *os.Root, _ *os.File, result error) {
	absolute, err := filepath.Abs(directory)
	if err != nil || absolute == "/" {
		return nil, nil, errors.New("invalid recording storage directory")
	}
	if err := os.MkdirAll(absolute, 0o700); err != nil {
		return nil, nil, err
	}
	root, err := os.OpenRoot(absolute)
	if err != nil {
		return nil, nil, err
	}
	defer func() {
		if result != nil {
			result = errors.Join(result, root.Close())
		}
	}()
	directoryHandle, err := root.Open(".")
	if err != nil {
		return nil, nil, err
	}
	var stat unix.Stat_t
	statErr := unix.Fstat(int(directoryHandle.Fd()), &stat)
	if err := errors.Join(statErr, directoryHandle.Close()); err != nil {
		return nil, nil, err
	}
	if stat.Uid != uint32(os.Geteuid()) || stat.Mode&0o077 != 0 {
		return nil, nil, errors.New("SM_STORAGE_DIR must be private (0700) and owned by the service user")
	}
	lock, err := root.OpenFile(lockName, os.O_CREATE|os.O_RDWR|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil, nil, err
	}
	if err := unix.Flock(int(lock.Fd()), unix.LOCK_EX|unix.LOCK_NB); err != nil {
		return nil, nil, errors.Join(errors.New("recording storage is already in use by another instance"), lock.Close())
	}
	return root, lock, nil
}

func validRecordingID(recordingID string) bool {
	if len(recordingID) == base64.RawURLEncoding.EncodedLen(16) {
		decoded, err := base64.RawURLEncoding.Strict().DecodeString(recordingID)
		return err == nil && len(decoded) == 16
	}
	parsed, err := uuid.Parse(recordingID)
	return err == nil && parsed.String() == recordingID
}
