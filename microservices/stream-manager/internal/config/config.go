// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package config loads service configuration from the environment.
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

const (
	DefaultBufferLength     = 30 * time.Second
	MaxBufferLength         = 300 * time.Second
	DefaultRecordingStorage = 10240 // in MB
	MinRecordingStorage     = 5120  // in MB
)

type Config struct {
	HTTPAddr         string // Override using SM_HTTP_ADDR (default ":8080")
	BufferLength     time.Duration
	BufferDir        string
	StorageDir       string
	RecordingStorage int // Override using SM_RECORDING_STORAGE (default 10240MB)
}

// Load reads the configuration from the environment.
func Load() (Config, error) {
	cfg := Config{
		HTTPAddr: ":8080", BufferLength: DefaultBufferLength, BufferDir: "/dev/shm/stream-manager",
		StorageDir: "./files", RecordingStorage: DefaultRecordingStorage,
	}
	if v := os.Getenv("SM_HTTP_ADDR"); v != "" {
		cfg.HTTPAddr = v
	}
	if v := os.Getenv("SM_RECORDING_STORAGE"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < MinRecordingStorage {
			return Config{}, fmt.Errorf("SM_RECORDING_STORAGE must be an integer greater than or equal to %d", MinRecordingStorage)
		}
		cfg.RecordingStorage = n
	}
	return cfg, nil
}
