// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package config

import (
	"os"
	"testing"
)

// withEnv sets env vars for the duration of the test and restores whatever
// was there before, including unsetting keys that were not previously set.
func withEnv(t *testing.T, kv map[string]string) {
	t.Helper()
	for k, v := range kv {
		prev, had := os.LookupEnv(k)
		if err := os.Setenv(k, v); err != nil {
			t.Fatalf("setenv %s: %v", k, err)
		}
		t.Cleanup(func() {
			if had {
				os.Setenv(k, prev)
			} else {
				os.Unsetenv(k)
			}
		})
	}
}

func clearAllStreamManagerEnv(t *testing.T) {
	t.Helper()
	for _, e := range os.Environ() {
		for i, c := range e {
			if c == '=' {
				key := e[:i]
				if len(key) > 15 && key[:15] == "STREAM_MANAGER_" {
					prev := e[i+1:]
					os.Unsetenv(key)
					t.Cleanup(func() { os.Setenv(key, prev) })
				}
				break
			}
		}
	}
}

func TestLoadDefaultsToFilesystemBackend(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_FS_ROOT":            "/var/lib/stream-manager/media",
		"STREAM_MANAGER_PUBLIC_BASE_URL":    "http://localhost:18080",
		"STREAM_MANAGER_MEDIA_TOKEN_SECRET": "secret",
	})

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.StorageBackend != StorageBackendFilesystem {
		t.Fatalf("got backend %q, want %q", cfg.StorageBackend, StorageBackendFilesystem)
	}
	if cfg.SQLitePath != "/var/lib/stream-manager/stream-manager.db" {
		t.Fatalf("got SQLitePath %q", cfg.SQLitePath)
	}
}

func TestLoadDefaultFilesystemBackendRequiresSettings(t *testing.T) {
	clearAllStreamManagerEnv(t)
	if _, err := Load(); err == nil {
		t.Fatal("expected error when default filesystem settings are missing")
	}
}

func TestLoadRequiresS3EndpointForS3Backend(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{"STREAM_MANAGER_STORAGE_BACKEND": StorageBackendS3})
	if _, err := Load(); err == nil {
		t.Fatal("expected error when S3 endpoint is missing")
	}
}

func TestLoadFilesystemBackendRequiresSettings(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{"STREAM_MANAGER_STORAGE_BACKEND": "filesystem"})
	if _, err := Load(); err == nil {
		t.Fatal("expected error when filesystem settings are missing")
	}

	withEnv(t, map[string]string{
		"STREAM_MANAGER_STORAGE_BACKEND":    "filesystem",
		"STREAM_MANAGER_FS_ROOT":            "/var/lib/stream-manager",
		"STREAM_MANAGER_PUBLIC_BASE_URL":    "http://host:18080",
		"STREAM_MANAGER_MEDIA_TOKEN_SECRET": "s3cr3t",
	})
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.StorageBackend != StorageBackendFilesystem {
		t.Fatalf("got backend %q, want %q", cfg.StorageBackend, StorageBackendFilesystem)
	}
	if cfg.FSRoot != "/var/lib/stream-manager" {
		t.Fatalf("got FSRoot %q", cfg.FSRoot)
	}
	if cfg.PublicBaseURL != "http://host:18080" {
		t.Fatalf("got PublicBaseURL %q", cfg.PublicBaseURL)
	}
	if cfg.MediaTokenSecret != "s3cr3t" {
		t.Fatalf("got MediaTokenSecret %q", cfg.MediaTokenSecret)
	}
	if cfg.FSMaxStageBytes != DefaultFSMaxStageBytes {
		t.Fatalf("got FSMaxStageBytes %d, want default %d", cfg.FSMaxStageBytes, DefaultFSMaxStageBytes)
	}
}

func TestLoadRejectsRelativeDatabasePath(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_STORAGE_BACKEND": "s3",
		"STREAM_MANAGER_S3_ENDPOINT":     "http://localhost:8333",
		"STREAM_MANAGER_SQLITE_PATH":     "data/stream-manager.db",
	})
	if _, err := Load(); err == nil {
		t.Fatal("expected error for relative SQLite path")
	}
}

func TestLoadRejectsRelativeFilesystemRoot(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_STORAGE_BACKEND":    "filesystem",
		"STREAM_MANAGER_FS_ROOT":            "data/media",
		"STREAM_MANAGER_PUBLIC_BASE_URL":    "http://host:18080",
		"STREAM_MANAGER_MEDIA_TOKEN_SECRET": "secret",
	})
	if _, err := Load(); err == nil {
		t.Fatal("expected error for relative filesystem root")
	}
}

func TestLoadRejectsUnknownBackend(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{"STREAM_MANAGER_STORAGE_BACKEND": "nfs"})
	if _, err := Load(); err == nil {
		t.Fatal("expected error for unknown backend")
	}
}

func TestLoadParsesFSMaxStageBytes(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_STORAGE_BACKEND":    "filesystem",
		"STREAM_MANAGER_FS_ROOT":            "/var/lib/stream-manager",
		"STREAM_MANAGER_PUBLIC_BASE_URL":    "http://host:18080",
		"STREAM_MANAGER_MEDIA_TOKEN_SECRET": "s3cr3t",
		"STREAM_MANAGER_FS_MAX_STAGE_BYTES": "1000",
	})
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.FSMaxStageBytes != 1000 {
		t.Fatalf("got FSMaxStageBytes %d, want 1000", cfg.FSMaxStageBytes)
	}
}

func TestLoadRejectsInvalidFSMaxStageBytes(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_STORAGE_BACKEND":    "s3",
		"STREAM_MANAGER_S3_ENDPOINT":        "http://localhost:8333",
		"STREAM_MANAGER_FS_MAX_STAGE_BYTES": "not-a-number",
	})
	if _, err := Load(); err == nil {
		t.Fatal("expected error for non-numeric FS_MAX_STAGE_BYTES")
	}
}

func TestBestEffortTimestampsRequireExplicitDevelopmentOptIn(t *testing.T) {
	clearAllStreamManagerEnv(t)
	withEnv(t, map[string]string{
		"STREAM_MANAGER_FS_ROOT":            "/var/lib/stream-manager/media",
		"STREAM_MANAGER_PUBLIC_BASE_URL":    "http://localhost:18080",
		"STREAM_MANAGER_MEDIA_TOKEN_SECRET": "secret",
	})
	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.AllowBestEffortTimestamps {
		t.Fatal("best-effort timestamps must be disabled by default")
	}

	withEnv(t, map[string]string{"STREAM_MANAGER_DEV_BEST_EFFORT_TIMESTAMPS": "true"})
	cfg, err = Load()
	if err != nil {
		t.Fatal(err)
	}
	if !cfg.AllowBestEffortTimestamps {
		t.Fatal("explicit development opt-in was ignored")
	}
}
