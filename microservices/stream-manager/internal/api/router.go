// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api

import (
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/handler"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/logging"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/mediaaccess"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

// NewRouter creates the HTTP router used by the Stream Manager service,
// built on Gin. It returns http.Handler (gin.Engine satisfies it) so
// callers (production bootstrap and tests) don't need to depend on Gin
// directly. version is reported by GET /v1/version; logger receives one
// access-log line per request. mediaSigner may be nil, in which case
// GET /v1/media/{token} rejects every request; it is non-nil whenever
// STREAM_MANAGER_MEDIA_TOKEN_SECRET is configured, which is required for
// the filesystem storage backend and optional for S3.
func NewRouter(service *replay.RetrievalService, media storage.MediaStore, version string, logger *slog.Logger, mediaSigner *mediaaccess.Signer, buffers stream.Bufferer, recordings *record.Service) http.Handler {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(logging.Middleware(logger), logging.Recovery(), handler.BodyLimit())

	retrievalHandler := handler.NewRetrievalHandler(service, media)
	mediaHandler := handler.NewMediaHandler(media, mediaSigner)

	router.GET("/v1/health", handler.Health)
	router.GET("/v1/version", handler.Version(version))
	router.GET("/v1/replays/:recording_id/frame", retrievalHandler.GetFrame)
	router.GET("/v1/replays/:recording_id/frame/url", retrievalHandler.GetFrameURL)
	router.GET("/v1/replays/:recording_id/clip", retrievalHandler.GetClip)
	router.GET("/v1/replays/:recording_id/clip/url", retrievalHandler.GetClipURL)
	router.GET("/v1/media/:token", mediaHandler.GetMedia)

	streams := handler.StreamHandler{Buffers: buffers}
	router.POST("/v1/streams", streams.Create)
	router.GET("/v1/streams", streams.List)
	streamRoutes := router.Group("/v1/streams/:stream-id", handler.RequireID("stream-id", "stream_not_found", "stream not found"))
	streamRoutes.GET("", streams.Get)
	streamRoutes.DELETE("", streams.Delete)
	streamRoutes.PUT("/buffer", streams.UpdateBuffer)

	records := handler.RecordHandler{Records: recordings}
	router.POST("/v1/records/start", records.Start)
	router.POST("/v1/records/stop", records.Stop)
	router.GET("/v1/records", records.List)
	recordRoutes := router.Group("/v1/records/:recording-id", handler.RequireID("recording-id", "record_not_found", "record not found"))
	recordRoutes.GET("", records.Get)
	recordRoutes.DELETE("", records.Delete)

	router.GET("/docs/v1/*any", handler.ServeSwaggerUI)

	return router
}
