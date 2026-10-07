// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Command api-server runs the Stream Manager HTTP API.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/logging"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/mediaaccess"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

// startupTimeout bounds the backend reachability checks so a wedged
// dependency surfaces as a failed start rather than a hung process.
const startupTimeout = 30 * time.Second

func main() {
	cfg, err := config.Load()
	if err != nil {
		// No logger exists yet; fall back to a plain text handler.
		slog.Error("load configuration", "error", err)
		os.Exit(1)
	}

	logger, err := logging.New(cfg.LogFormat, cfg.LogLevel)
	if err != nil {
		slog.Error("configure logging", "error", err)
		os.Exit(1)
	}
	slog.SetDefault(logger)
	fatal := func(msg string, err error) {
		logger.Error(msg, "error", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithTimeout(context.Background(), startupTimeout)
	defer cancel()

	metadataStore, err := storage.OpenSQLiteMetadataStore(ctx, cfg.SQLitePath)
	if err != nil {
		fatal("open metadata store", err)
	}
	defer metadataStore.Close()

	mediaStore, mediaSigner, err := buildMediaStore(ctx, cfg)
	if err != nil {
		fatal("configure media store", err)
	}

	// The media backend is provisioned by the deployment, not by this
	// service, so startup only confirms it is reachable.
	if err := mediaStore.Health(ctx); err != nil {
		fatal("media store not reachable", err)
	}
	if err := metadataStore.Health(ctx); err != nil {
		fatal("metadata store not reachable", err)
	}

	buffers, err := stream.NewService(cfg)
	if err != nil {
		fatal("configure stream buffers", err)
	}
	defer buffers.Close()

	var recordings *record.Service
	if cfg.StorageBackend == config.StorageBackendFilesystem {
		liveStore, ok := mediaStore.(storage.LiveRecordingLifecycleMediaStore)
		if !ok {
			fatal("configure recorder", errors.New("filesystem backend does not support live recording writes"))
		}
		recordings, err = record.NewService(buffers, metadataStore, liveStore, cfg.MaxActiveRecords, cfg.AllowBestEffortTimestamps)
		if err != nil {
			fatal("configure recorder", err)
		}
		if err := recordings.RecoverInterrupted(ctx); err != nil {
			fatal("recover interrupted recordings", err)
		}
		defer recordings.Close()
	}

	service := replay.NewRetrievalService(metadataStore, mediaStore, replay.Options{
		DerivedTTL:    cfg.DerivedTTL,
		PresignExpiry: cfg.PresignExpiry,
		MaxStageBytes: cfg.FSMaxStageBytes,
	})
	router := api.NewRouter(service, mediaStore, cfg.Version, logger, mediaSigner, buffers, recordings)

	logger.Info("listening",
		"service", "stream-manager",
		"version", cfg.Version,
		"storage_backend", cfg.StorageBackend,
		"s3_endpoint", cfg.S3Endpoint,
		"s3_bucket", cfg.S3Bucket,
		"s3_prefix", cfg.S3Prefix,
		"fs_root", cfg.FSRoot,
		"sqlite_path", cfg.SQLitePath,
		"port", cfg.Port,
	)
	if err := http.ListenAndServe(cfg.HTTPAddr, router); err != nil {
		fatal("server failed", err)
	}
}

// buildMediaStore selects and constructs the MediaStore implementation
// named by cfg.StorageBackend. It also builds the mediaaccess.Signer for
// GET /v1/media/{token}: required (and used by PresignDerived) for the
// filesystem backend, optional for S3 (which presigns directly against the
// object store by default).
func buildMediaStore(ctx context.Context, cfg config.Config) (storage.MediaStore, *mediaaccess.Signer, error) {
	var signer *mediaaccess.Signer
	if strings.TrimSpace(cfg.MediaTokenSecret) != "" {
		var err error
		signer, err = mediaaccess.NewSigner(cfg.MediaTokenSecret)
		if err != nil {
			return nil, nil, err
		}
	}

	switch cfg.StorageBackend {
	case config.StorageBackendFilesystem:
		store, err := storage.NewFileMediaStore(cfg.FSRoot, cfg.PublicBaseURL, signer)
		if err != nil {
			return nil, nil, err
		}
		return store, signer, nil
	case config.StorageBackendS3:
		store, err := storage.NewS3MediaStore(ctx, storage.S3Config{
			Endpoint:     cfg.S3Endpoint,
			Region:       cfg.S3Region,
			Bucket:       cfg.S3Bucket,
			Prefix:       cfg.S3Prefix,
			UsePathStyle: cfg.S3UsePathStyle,
			AccessKey:    cfg.S3AccessKey,
			SecretKey:    cfg.S3SecretKey,
			SessionToken: cfg.S3SessionToken,
		})
		if err != nil {
			return nil, nil, err
		}
		return store, signer, nil
	default:
		return nil, nil, fmt.Errorf("unsupported storage backend %q", cfg.StorageBackend)
	}
}
