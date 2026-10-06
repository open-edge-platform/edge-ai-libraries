// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api

import (
	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/handler"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

// NewRouter builds the HTTP engine with the API mounted under /v1.
func NewRouter(buffers stream.Bufferer, recordings *record.Service) *gin.Engine {
	router := gin.New()
	// adding global middlewares
	router.Use(gin.Logger(), common.Recovery(), common.BodyLimit())
	v1 := router.Group("/v1")

	streams := handler.StreamHandler{Buffers: buffers}
	streamRoutesWithID := v1.Group("/streams/:stream-id", common.RequireID("stream-id", "stream_not_found", "stream not found"))

	v1.POST("/streams", streams.Create)
	v1.GET("/streams", streams.List)
	streamRoutesWithID.GET("", streams.Get)
	streamRoutesWithID.DELETE("", streams.Delete)

	// TODO: implement buffer resizing; PUT /streams/{stream-id}/buffer returns 501 until then.
	streamRoutesWithID.PUT("/buffer", streams.UpdateBuffer)

	records := handler.RecordHandler{Records: recordings}
	recordRoutesWithID := v1.Group("/records/:recording-id", common.RequireID("recording-id", "record_not_found", "record not found"))

	v1.POST("/records/start", records.Start)
	v1.POST("/records/stop", records.Stop)
	v1.GET("/records", records.List)
	recordRoutesWithID.GET("", records.Get)
	recordRoutesWithID.DELETE("", records.Delete)

	// Serving Swagger UI
	router.GET("/docs/v1/*any", handler.ServeSwaggerUI)

	return router
}
