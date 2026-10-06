// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

const (
	readHeaderTimeout = 10 * time.Second
	readTimeout       = 30 * time.Second
	writeTimeout      = 60 * time.Second
	idleTimeout       = 120 * time.Second
	shutdownGrace     = 7 * time.Second
)

func main() {
	if err := run(); err != nil {
		log.Fatal(err)
	}
}

func run() (errResult error) {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	store, err := storage.Open(cfg.StorageDir)
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, store.Close()) }()
	if err := store.RecoverInterrupted(context.Background()); err != nil {
		return err
	}
	buffers, err := stream.NewService(cfg)
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, buffers.Close()) }()
	recordings, err := record.NewService(buffers, store, cfg.ConcurrentRecorders)
	if err != nil {
		return err
	}
	defer func() { errResult = errors.Join(errResult, recordings.Close()) }()
	server := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           api.NewRouter(buffers, recordings),
		ReadHeaderTimeout: readHeaderTimeout,
		ReadTimeout:       readTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	serveErr := make(chan error, 1)
	go func() { serveErr <- server.ListenAndServe() }()
	log.Printf("Stream Manager listening on %s", cfg.HTTPAddr)

	select {
	case err := <-serveErr:
		return fmt.Errorf("http server error: %w", err)
	case <-ctx.Done():
	}

	log.Print("shutting down")
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
