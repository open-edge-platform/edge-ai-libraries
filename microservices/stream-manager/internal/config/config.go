// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package config loads service configuration from the environment.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	DefaultHTTPAddr         = ":8080"
	DefaultBufferLength     = 30 * time.Second
	MaxBufferLength         = 300 * time.Second
	MinBufferLength         = 5 * time.Second
	DefaultRecordingStorage = 10240 // MegaBytes; ~10 GB
	MinRecordingStorage     = 5120  // MegaBytes; ~5 GB
	ConcurrentRecorders     = 10
)

type Config struct {
	HTTPAddr            string // Override using SM_HTTP_ADDR (default ":8080")
	BufferLength        time.Duration
	BufferDir           string
	StorageDir          string
	ConcurrentRecorders int
	RecordingStorage    int // Override using SM_RECORDING_STORAGE (default 10240 MB)
}

// Load reads the configuration from the environment.
func Load() (Config, error) {
	cfg := Config{
		HTTPAddr:            DefaultHTTPAddr,
		BufferLength:        DefaultBufferLength,
		BufferDir:           "/dev/shm/stream-manager",
		StorageDir:          "~/.local/share/stream-manager",
		ConcurrentRecorders: ConcurrentRecorders,
		RecordingStorage:    DefaultRecordingStorage,
	}
	if v := strings.TrimSpace(os.Getenv("SM_HTTP_ADDR")); v != "" {
		cfg.HTTPAddr = v
	}
	if v := strings.TrimSpace(os.Getenv("SM_RECORDING_STORAGE")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < MinRecordingStorage {
			return Config{}, fmt.Errorf("SM_RECORDING_STORAGE must be an integer greater than or equal to %d", MinRecordingStorage)
		}
		cfg.RecordingStorage = n
	}

	if storageDir, err := expandHome(cfg.StorageDir); err == nil {
		cfg.StorageDir = storageDir
	} else {
		return Config{}, err
	}

	return cfg, nil
}

// Resolve ~ in the any path either coming from const defined above or user supplied config.
func expandHome(path string) (string, error) {
	restOfThePath, ok := strings.CutPrefix(path, "~/")
	if !ok {
		return path, nil
	}
	if homeDir, err := os.UserHomeDir(); err == nil {
		if !filepath.IsAbs(homeDir) {
			return "", fmt.Errorf("home directory %q must be absolute", homeDir)
		}
		return filepath.Join(homeDir, restOfThePath), nil
	} else {
		return "", fmt.Errorf("resolve home directory for %s: %w", path, err)
	}
}
