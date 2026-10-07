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

// Default derived-object and presigned-URL lifetimes. Derived assets are
// reproducible from the source recording, so they are kept only long enough
// for a client to follow the URL it was handed.
const (
	DefaultDerivedTTL    = 15 * time.Minute
	DefaultPresignExpiry = 5 * time.Minute
)

// DefaultVersion is reported by GET /v1/version when STREAM_MANAGER_VERSION
// is not set. Deployments override it with the released tag.
const DefaultVersion = "0.1.0"

// Storage backend selectors for STREAM_MANAGER_STORAGE_BACKEND.
const (
	StorageBackendS3         = "s3"
	StorageBackendFilesystem = "filesystem"
)

// DefaultFSMaxStageBytes bounds how large a source recording may be before
// full-file staging (copying it whole into a temporary file ahead of
// extraction) is refused. It exists to keep a long live recording from
// exhausting local disk.
const DefaultFSMaxStageBytes int64 = 2 << 30 // 2 GiB

const (
	DefaultBufferLength     = 30 * time.Second
	MinBufferLength         = 1 * time.Second
	MaxBufferLength         = 300 * time.Second
	DefaultMaxActiveRecords = 32
)

// Config holds the settings needed to bootstrap the metadata and media
// backends.
type Config struct {
	// Version is the service version reported by GET /v1/version.
	Version string

	// LogLevel is debug, info, warn, or error. LogFormat is json or text.
	LogLevel  string
	LogFormat string

	// Port is the HTTP listen port for the API server.
	Port string

	// SQLitePath is the filesystem path to the SQLite metadata database.
	SQLitePath string

	// S3Endpoint is the S3 service base URL, e.g. "http://localhost:8333"
	// for a local SeaweedFS S3 gateway.
	S3Endpoint string
	// S3Region participates in request signing. SeaweedFS does not
	// interpret it, but it must match between client and gateway.
	S3Region string
	// S3Bucket is the single, pre-existing bucket holding recordings,
	// sidecars, and derived media. The service never creates it.
	S3Bucket string
	// S3Prefix confines every object to one key namespace inside the
	// bucket, so environments can share a bucket safely.
	S3Prefix string
	// S3UsePathStyle selects /{bucket}/{key} addressing. Required by
	// SeaweedFS's S3 gateway.
	S3UsePathStyle bool
	// S3AccessKey, S3SecretKey, and S3SessionToken authenticate against the
	// endpoint. When the key pair is absent, the AWS default credential
	// provider chain is used instead.
	S3AccessKey    string
	S3SecretKey    string
	S3SessionToken string

	// DerivedTTL is the retention hint applied to derived frame/clip
	// objects when they are published.
	DerivedTTL time.Duration
	// PresignExpiry is how long an issued media URL stays valid.
	PresignExpiry time.Duration

	// StorageBackend selects the MediaStore implementation: "s3" (default)
	// or "filesystem".
	StorageBackend string
	// FSRoot is the local directory backing the filesystem MediaStore.
	// Required when StorageBackend is "filesystem".
	FSRoot string
	// PublicBaseURL is this service's externally reachable base URL, used
	// to build GET /v1/media/{token} capability URLs. Required when
	// StorageBackend is "filesystem".
	PublicBaseURL string
	// MediaTokenSecret signs and verifies GET /v1/media/{token} capability
	// tokens. Required when StorageBackend is "filesystem"; optional (but
	// usable) when the backend is S3.
	MediaTokenSecret string
	// FSMaxStageBytes bounds full-file staging of a live source recording
	// ahead of extraction.
	FSMaxStageBytes int64

	// BufferLength is the rolling RTSP history window. BufferDir must be
	// private tmpfs; HTTPAddr is derived from Port for the unified server.
	BufferLength time.Duration
	BufferDir    string
	HTTPAddr     string

	// MaxActiveRecords bounds concurrent recording workers.
	MaxActiveRecords int

	// AllowBestEffortTimestamps enables a development-only wall-clock anchor
	// when RTCP/NTP mapping is unavailable. Production should leave it false.
	AllowBestEffortTimestamps bool
}

// Load reads configuration from environment variables. Filesystem storage is
// the default; S3 must be selected explicitly and requires an endpoint.
//
// Credentials are read from the environment only; they are never defaulted
// and never logged.
func Load() (Config, error) {
	usePathStyle, err := getEnvBool("STREAM_MANAGER_S3_USE_PATH_STYLE", true)
	if err != nil {
		return Config{}, err
	}
	derivedTTL, err := getEnvDuration("STREAM_MANAGER_DERIVED_TTL", DefaultDerivedTTL)
	if err != nil {
		return Config{}, err
	}
	presignExpiry, err := getEnvDuration("STREAM_MANAGER_PRESIGN_EXPIRY", DefaultPresignExpiry)
	if err != nil {
		return Config{}, err
	}
	fsMaxStageBytes, err := getEnvInt64("STREAM_MANAGER_FS_MAX_STAGE_BYTES", DefaultFSMaxStageBytes)
	if err != nil {
		return Config{}, err
	}
	bufferLength, err := getEnvDuration("STREAM_MANAGER_BUFFER_LENGTH", DefaultBufferLength)
	if err != nil {
		return Config{}, err
	}
	if bufferLength < MinBufferLength || bufferLength > MaxBufferLength {
		return Config{}, fmt.Errorf("STREAM_MANAGER_BUFFER_LENGTH must be between %s and %s", MinBufferLength, MaxBufferLength)
	}
	maxActiveRecords, err := getEnvPositiveInt("STREAM_MANAGER_MAX_ACTIVE_RECORDS", DefaultMaxActiveRecords)
	if err != nil {
		return Config{}, err
	}
	allowBestEffortTimestamps, err := getEnvBool("STREAM_MANAGER_DEV_BEST_EFFORT_TIMESTAMPS", false)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{
		Version:    getEnvDefault("STREAM_MANAGER_VERSION", DefaultVersion),
		LogLevel:   getEnvDefault("STREAM_MANAGER_LOG_LEVEL", "info"),
		LogFormat:  getEnvDefault("STREAM_MANAGER_LOG_FORMAT", "json"),
		Port:       getEnvDefault("STREAM_MANAGER_PORT", "18080"),
		SQLitePath: getEnvDefault("STREAM_MANAGER_SQLITE_PATH", "/var/lib/stream-manager/stream-manager.db"),

		S3Endpoint:     os.Getenv("STREAM_MANAGER_S3_ENDPOINT"),
		S3Region:       getEnvDefault("STREAM_MANAGER_S3_REGION", "us-east-1"),
		S3Bucket:       getEnvDefault("STREAM_MANAGER_S3_BUCKET", "stream-manager"),
		S3Prefix:       os.Getenv("STREAM_MANAGER_S3_PREFIX"),
		S3UsePathStyle: usePathStyle,
		S3AccessKey:    os.Getenv("STREAM_MANAGER_S3_ACCESS_KEY"),
		S3SecretKey:    os.Getenv("STREAM_MANAGER_S3_SECRET_KEY"),
		S3SessionToken: os.Getenv("STREAM_MANAGER_S3_SESSION_TOKEN"),

		DerivedTTL:    derivedTTL,
		PresignExpiry: presignExpiry,

		StorageBackend:            strings.ToLower(getEnvDefault("STREAM_MANAGER_STORAGE_BACKEND", StorageBackendFilesystem)),
		FSRoot:                    os.Getenv("STREAM_MANAGER_FS_ROOT"),
		PublicBaseURL:             strings.TrimRight(os.Getenv("STREAM_MANAGER_PUBLIC_BASE_URL"), "/"),
		MediaTokenSecret:          os.Getenv("STREAM_MANAGER_MEDIA_TOKEN_SECRET"),
		FSMaxStageBytes:           fsMaxStageBytes,
		BufferLength:              bufferLength,
		BufferDir:                 getEnvDefault("STREAM_MANAGER_BUFFER_DIR", "/dev/shm/stream-manager"),
		HTTPAddr:                  ":" + getEnvDefault("STREAM_MANAGER_PORT", "18080"),
		MaxActiveRecords:          maxActiveRecords,
		AllowBestEffortTimestamps: allowBestEffortTimestamps,
	}
	if !filepath.IsAbs(cfg.SQLitePath) {
		return Config{}, fmt.Errorf("STREAM_MANAGER_SQLITE_PATH must be an absolute path")
	}

	switch cfg.StorageBackend {
	case StorageBackendS3:
		if strings.TrimSpace(cfg.S3Endpoint) == "" {
			return Config{}, fmt.Errorf("STREAM_MANAGER_S3_ENDPOINT is required")
		}
	case StorageBackendFilesystem:
		if strings.TrimSpace(cfg.FSRoot) == "" {
			return Config{}, fmt.Errorf("STREAM_MANAGER_FS_ROOT is required when STREAM_MANAGER_STORAGE_BACKEND=filesystem")
		}
		if !filepath.IsAbs(cfg.FSRoot) {
			return Config{}, fmt.Errorf("STREAM_MANAGER_FS_ROOT must be an absolute path")
		}
		if strings.TrimSpace(cfg.PublicBaseURL) == "" {
			return Config{}, fmt.Errorf("STREAM_MANAGER_PUBLIC_BASE_URL is required when STREAM_MANAGER_STORAGE_BACKEND=filesystem")
		}
		if strings.TrimSpace(cfg.MediaTokenSecret) == "" {
			return Config{}, fmt.Errorf("STREAM_MANAGER_MEDIA_TOKEN_SECRET is required when STREAM_MANAGER_STORAGE_BACKEND=filesystem")
		}
	default:
		return Config{}, fmt.Errorf("STREAM_MANAGER_STORAGE_BACKEND must be %q or %q, got %q", StorageBackendS3, StorageBackendFilesystem, cfg.StorageBackend)
	}

	return cfg, nil
}

func getEnvDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvBool(key string, fallback bool) (bool, error) {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("%s must be a boolean: %w", key, err)
	}
	return parsed, nil
}

func getEnvInt64(key string, fallback int64) (int64, error) {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer: %w", key, err)
	}
	if parsed <= 0 {
		return 0, fmt.Errorf("%s must be greater than zero", key)
	}
	return parsed, nil
}

func getEnvPositiveInt(key string, fallback int) (int, error) {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", key)
	}
	return parsed, nil
}

func getEnvDuration(key string, fallback time.Duration) (time.Duration, error) {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback, nil
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil {
		return 0, fmt.Errorf("%s must be a Go duration (e.g. \"5m\"): %w", key, err)
	}
	if parsed <= 0 {
		return 0, fmt.Errorf("%s must be greater than zero", key)
	}
	return parsed, nil
}
