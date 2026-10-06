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
	r := gin.New()
	// adding global middlewares
	r.Use(gin.Logger(), common.Recovery(), common.BodyLimit())
	v1 := r.Group("/v1")

	streams := handler.StreamHandler{Buffers: buffers}
	v1.POST("/streams", streams.Create)
	v1.GET("/streams", streams.List)
	stream := v1.Group("/streams/:stream-id", common.RequireID("stream-id", "stream_not_found", "stream not found"))
	stream.GET("", streams.Get)
	stream.DELETE("", streams.Delete)
	// TODO: implement buffer resizing; PUT /streams/{stream-id}/buffer returns 501 until then.
	stream.PUT("/buffer", streams.UpdateBuffer)

	records := handler.RecordHandler{Records: recordings}
	v1.POST("/records/start", records.Start)
	v1.POST("/records/stop", records.Stop)
	v1.GET("/records", records.List)
	record := v1.Group("/records/:recording-id", common.RequireID("recording-id", "record_not_found", "record not found"))
	record.GET("", records.Get)
	record.DELETE("", records.Delete)

	// Serving Swagger UI
	r.GET("/docs/v1/*any", handler.ServeSwaggerUI)

	return r
}
