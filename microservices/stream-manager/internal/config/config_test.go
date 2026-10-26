// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package config

import (
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

// chdir switches the working directory for the duration of the test, since
// Load reads DefaultConfigFile ("config.json") relative to the process's CWD.
func chdir(t *testing.T, dir string) {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(wd); err != nil {
			t.Fatal(err)
		}
	})
}

func TestLoadDefaults(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("SM_DATA_DIR", "")
	// No config.json in this directory, so Load must fall back to defaults.
	chdir(t, t.TempDir())

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	want := Config{
		HTTPAddr: DefaultHTTPAddr, BufferLength: DefaultBufferLength, BufferDir: DefaultBufferDir,
		StorageDir:           filepath.Join(home, ".local/share/stream-manager"),
		ConcurrentRecorders:  ConcurrentRecorders,
		RecordingStorageSize: DefaultStorageSize,
		DerivedMediaTTL:      DefaultDerivedTTL,
	}
	if cfg != want {
		t.Fatalf("defaults: got %+v, want %+v", cfg, want)
	}
}

func TestLoadDataDirOverride(t *testing.T) {
	t.Setenv("SM_DATA_DIR", "/srv/stream-manager-data")
	chdir(t, t.TempDir())

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.StorageDir != "/srv/stream-manager-data" {
		t.Fatalf("StorageDir = %q, want override from SM_DATA_DIR", cfg.StorageDir)
	}
}

func TestLoadConfigFileEnvOverride(t *testing.T) {
	t.Setenv("SM_DATA_DIR", "")
	// Put a config.json in the CWD that must be ignored in favor of the one
	// named by SM_CONFIG_FILE, which can live anywhere on disk.
	cwd := t.TempDir()
	chdir(t, cwd)
	if err := os.WriteFile(filepath.Join(cwd, DefaultConfigFile), []byte(`{"HTTPAddr": "127.0.0.1:1"}`), 0o600); err != nil {
		t.Fatal(err)
	}

	elsewhere := t.TempDir()
	configPath := filepath.Join(elsewhere, "custom-config.json")
	if err := os.WriteFile(configPath, []byte(`{"HTTPAddr": "127.0.0.1:2"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("SM_CONFIG_FILE", configPath)

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.HTTPAddr != "127.0.0.1:2" {
		t.Fatalf("HTTPAddr = %q, want the file named by SM_CONFIG_FILE to be used", cfg.HTTPAddr)
	}
}

func TestLoadFromConfigFile(t *testing.T) {
	t.Setenv("SM_DATA_DIR", "")
	dir := t.TempDir()
	chdir(t, dir)

	const body = `{
		"HTTPAddr": "127.0.0.1:9000",
		"BufferLength": 60,
		"StorageDir": "/srv/sm-storage",
		"ConcurrentRecorders": 4,
		"RecordingStorageSize": 6000
	}`
	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	want := Config{
		HTTPAddr: "127.0.0.1:9000", BufferLength: 60 * time.Second, BufferDir: DefaultBufferDir,
		StorageDir: "/srv/sm-storage", ConcurrentRecorders: 4, RecordingStorageSize: 6000, DerivedMediaTTL: DefaultDerivedTTL,
	}
	if cfg != want {
		t.Fatalf("config file load: got %+v, want %+v", cfg, want)
	}
}

func TestLoadDataDirOverridesConfigFile(t *testing.T) {
	dir := t.TempDir()
	chdir(t, dir)

	const body = `{"StorageDir": "/srv/sm-storage"}`
	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("SM_DATA_DIR", "/override/data")

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.StorageDir != "/override/data" {
		t.Fatalf("StorageDir = %q, want SM_DATA_DIR to win over config.json", cfg.StorageDir)
	}
}

func TestLoadHTTPAddrOverridesConfigFile(t *testing.T) {
	dir := t.TempDir()
	chdir(t, dir)

	const body = `{"HTTPAddr": "127.0.0.1:9000"}`
	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("SM_HTTP_ADDR", ":8080")

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.HTTPAddr != ":8080" {
		t.Fatalf("HTTPAddr = %q, want SM_HTTP_ADDR to win over config.json", cfg.HTTPAddr)
	}
}

func TestLoadInvalidBufferLength(t *testing.T) {
	dir := t.TempDir()
	chdir(t, dir)

	for _, seconds := range []int64{1, 301} {
		body := `{"BufferLength": ` + strconv.FormatInt(seconds, 10) + `}`
		if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := Load(); err == nil {
			t.Fatalf("accepted out-of-range BufferLength %d seconds", seconds)
		}
	}
}

func TestLoadIgnoresBufferDirOverride(t *testing.T) {
	dir := t.TempDir()
	chdir(t, dir)

	const body = `{"BufferDir": "/tmp/should-be-ignored"}`
	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.BufferDir != DefaultBufferDir {
		t.Fatalf("BufferDir = %q, want it to stay internally determined as %q", cfg.BufferDir, DefaultBufferDir)
	}
}

func TestExpandHome(t *testing.T) {
	t.Setenv("HOME", "/home/example")
	for in, want := range map[string]string{
		"~/data":   "/home/example/data",
		"/srv/sm":  "/srv/sm",
		"relative": "relative",
		"~other":   "~other",
	} {
		if got, err := expandHome(in); err != nil || got != want {
			t.Fatalf("expandHome(%q) = %q, %v; want %q", in, got, err, want)
		}
	}
	t.Setenv("HOME", "relative-home")
	if _, err := expandHome("~/data"); err == nil {
		t.Fatal("accepted a relative home directory")
	}
}

func TestLoadRecordingStorageLimits(t *testing.T) {
	dir := t.TempDir()
	chdir(t, dir)

	for _, body := range []string{
		`{"RecordingStorageSize": 5119}`,
		`{"RecordingStorageSize": ` + strconv.Itoa(MaxStorageSize+1) + `}`,
		`{"RecordingStorageSize": 9007199254740993}`,
		`{"RecordingRetention": -1}`,
		`{"RecordingRetention": ` + strconv.Itoa(MaxRetentionHours+1) + `}`,
		`{"DerivedMediaTTL": 0}`,
		`{"DerivedMediaTTL": -2}`,
		`{"DerivedMediaTTL": ` + strconv.Itoa(MaxDerivedTTL+1) + `}`,
	} {
		if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := Load(); err == nil {
			t.Fatalf("accepted %s", body)
		}
	}

	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(`{"DerivedMediaTTL": -1}`), 0o600); err != nil {
		t.Fatal(err)
	}
	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DerivedMediaTTL != -1 || cfg.DerivedMediaTTLPeriod() != 0 {
		t.Fatalf("disabled derived TTL: got %d and %v, want -1 and 0", cfg.DerivedMediaTTL, cfg.DerivedMediaTTLPeriod())
	}

	const body = `{"RecordingStorageSize": 6000, "RecordingRetention": 48, "DerivedMediaTTL": 60}`
	if err := os.WriteFile(filepath.Join(dir, DefaultConfigFile), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	cfg, err = Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.RecordingStorageBytes() != 6000<<20 || cfg.RecordingRetentionPeriod() != 48*time.Hour ||
		cfg.DerivedMediaTTLPeriod() != time.Hour {
		t.Fatalf("got %d bytes, %v retention, %v derived TTL",
			cfg.RecordingStorageBytes(), cfg.RecordingRetentionPeriod(), cfg.DerivedMediaTTLPeriod())
	}
}
