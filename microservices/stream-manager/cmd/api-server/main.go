// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/retrieve"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

const (
	readHeaderTimeout = 10 * time.Second
	readTimeout       = 30 * time.Second
	writeTimeout      = 60 * time.Second
	idleTimeout       = 120 * time.Second // for keep-alive connection
	shutdownGrace     = 7 * time.Second
)

// These variables get updated while building the app
var (
	Version     string = "v0.0.1"
	BuildDate   string = "NA"
	BuildNumber string = "NA"
)

func main() {
	if err := run(); err != nil {
		slog.Error("Irrecoverable Error. Shutting down stream manager.", "error", err)
		os.Exit(1)
	}
}

func run() (errResult error) {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	metadata, err := storage.OpenMetadataStore(cfg.StorageDir)
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, metadata.Close()) }()
	media, err := storage.OpenMediaStore(cfg.StorageDir, cfg.RecordingStorageBytes())
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, media.Close()) }()
	buffers, err := stream.NewService(cfg)
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, buffers.Close()) }()
	recordings, err := record.NewService(buffers, metadata, media, cfg.ConcurrentRecorders, cfg.RecordingRetentionPeriod())
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, recordings.Close()) }()
	retrievals, err := retrieve.NewService(metadata, media, cfg.DerivedMediaTTLPeriod())
	if err != nil {
		return err
	}
	server := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           api.NewRouter(buffers, recordings, retrievals, Version, BuildNumber, BuildDate),
		ReadHeaderTimeout: readHeaderTimeout,
		ReadTimeout:       readTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	serveErr := make(chan error, 1)
	go func() { serveErr <- server.ListenAndServe() }()
	slog.Info("Stream Manager listening", "addr", cfg.HTTPAddr)

	select {
	case err := <-serveErr:
		return fmt.Errorf("http server error: %w", err)
	case <-ctx.Done():
	}

	slog.Info("shutting down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownGrace)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("http server shutdown: %w", err)
	}
	if err := <-serveErr; !errors.Is(err, http.ErrServerClosed) {
		return fmt.Errorf("http server: %w", err)
	}
	return nil
}
