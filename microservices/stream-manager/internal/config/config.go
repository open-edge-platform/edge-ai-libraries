// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package config

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	DefaultConfigFile   = "config.json" // relative to the CWD; override via SM_CONFIG_FILE.
	DefaultHTTPAddr     = ":8080"       // override via config.json or SM_HTTP_ADDR if set.
	DefaultStorageDir   = "~/.local/share/stream-manager"
	DefaultBufferDir    = "/dev/shm/stream-manager"
	DefaultBufferLength = 30 * time.Second
	MaxBufferLength     = 300 * time.Second
	MinBufferLength     = 5 * time.Second
	DefaultStorageSize  = 10240 // MegaBytes; ~10 GB
	MinStorageSize      = 5120  // MegaBytes; ~5 GB
	ConcurrentRecorders = 10
)

type Config struct {
	HTTPAddr             string // Override via config.json or SM_HTTP_ADDR if set.
	BufferLength         time.Duration
	BufferDir            string
	StorageDir           string // Override via config.json or SM_DATA_DIR if set.
	ConcurrentRecorders  int
	RecordingStorageSize int
}

// Load reads the configuration from config.json (or the file named by SM_CONFIG_FILE),
// falling back to the default config for any unset field.
func Load() (Config, error) {
	cfg := Config{
		HTTPAddr:             DefaultHTTPAddr,
		BufferLength:         DefaultBufferLength,
		StorageDir:           DefaultStorageDir,
		ConcurrentRecorders:  ConcurrentRecorders,
		RecordingStorageSize: DefaultStorageSize,
	}

	// look for config file provided via env var
	configFile := DefaultConfigFile
	if v := strings.TrimSpace(os.Getenv("SM_CONFIG_FILE")); v != "" {
		if absConfigPath, err := expandHome(v); err == nil {
			configFile = absConfigPath
		} else {
			slog.Warn("User config file path is invalid. Continuing with default config file.", "path", v, "error", err)
		}
	}

	// proceed to read the config file if it exists
	if data, errFile := os.ReadFile(configFile); errFile == nil {
		if err := json.Unmarshal(data, &cfg); err != nil {
			slog.Warn("Invalid config file. Continuing with default config value.", "path", configFile, "error", err)
		} else if hasKey(data, "BufferLength") {
			// config.json expresses BufferLength in whole seconds, but time.Duration keeps ns.
			// once we confirm config.json had BufferLength we convert it to ns.
			cfg.BufferLength *= time.Second
		}
	} else {
		slog.Warn("Failed to read config file. Continuing with default config value.", "path", configFile, "error", errFile)
	}

	// override storage dir using env var if available
	if dataDir := strings.TrimSpace(os.Getenv("SM_DATA_DIR")); dataDir != "" {
		cfg.StorageDir = dataDir
	}

	// override http listen address using env var if available; this lets a
	// container fix its internal listen port regardless of a mounted config.json.
	if httpAddr := strings.TrimSpace(os.Getenv("SM_HTTP_ADDR")); httpAddr != "" {
		cfg.HTTPAddr = httpAddr
	}

	if cfg.BufferLength < MinBufferLength || cfg.BufferLength > MaxBufferLength {
		return Config{}, fmt.Errorf("buffer length can not be less than %v or greater than %v", MinBufferLength, MaxBufferLength)
	}

	if storageDir, err := expandHome(cfg.StorageDir); err == nil {
		cfg.StorageDir = storageDir
	} else {
		return Config{}, err
	}

	// this config is internally determined.
	cfg.BufferDir = DefaultBufferDir

	return cfg, nil
}

// hasKey verifies whether the top-level JSON object in data contains a given key.
func hasKey(data []byte, key string) bool {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return false
	}
	_, ok := raw[key]
	return ok
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
