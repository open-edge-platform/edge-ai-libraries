// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"errors"
	"log"
	"net/http"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

type streamCreateRequest struct {
	SensorID     string `json:"sensor_id"`
	SourceURI    string `json:"source_uri"`
	BufferLength *int   `json:"buffer_length"`
}

type streamResponse struct {
	StreamID       string               `json:"stream_id"`
	SensorID       string               `json:"sensor_id"`
	State          string               `json:"state"`
	SyncConfidence model.SyncConfidence `json:"sync_confidence"`
	Buffer         bufferStatusResponse `json:"buffer"`
	Stats          streamStatsResponse  `json:"stats"`
	CreationTS     time.Time            `json:"creation_ts"`
}

type bufferStatusResponse struct {
	Capacity  int        `json:"capacity"`
	HeldBytes int64      `json:"held_bytes"`
	OldestTS  *time.Time `json:"oldest_ts"`
	NewestTS  *time.Time `json:"newest_ts"`
}

type streamStatsResponse struct {
	Framerate     float64 `json:"framerate"`
	DroppedFrames int64   `json:"dropped_frames"`
}

type streamPageResponse struct {
	Items      []streamResponse `json:"items"`
	NextCursor *string          `json:"next_cursor"`
}

type deletionResponse struct {
	Resource string `json:"resource"`
	ID       string `json:"id"`
	Deleted  bool   `json:"deleted"`
}

// StreamHandler serves the Stream Attachment APIs.
type StreamHandler struct {
	Buffers stream.Bufferer
}

// Create handles POST /streams.
func (h StreamHandler) Create(c *gin.Context) {
	var req streamCreateRequest
	if err := common.DecodeJSON(c, &req); err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	if err := req.validate(); err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	var bufferLength time.Duration
	if req.BufferLength != nil {
		bufferLength = time.Duration(*req.BufferLength) * time.Second
	}
	id, err := h.Buffers.CreateBuffer(c.Request.Context(), req.SourceURI, req.SensorID, bufferLength)
	if err != nil {
		writeStreamError(c, err)
		return
	}
	sb, err := h.Buffers.GetStream(c.Request.Context(), id)
	if err != nil {
		writeStreamError(c, err)
		return
	}
	c.Header("Location", "/v1/streams/"+sb.StreamID)
	c.JSON(http.StatusCreated, toStreamResponse(sb))
}

// List handles GET /streams.
func (h StreamHandler) List(c *gin.Context) {
	streams, err := h.Buffers.ListStreams(c.Request.Context())
	if err != nil {
		writeStreamError(c, err)
		return
	}
	page := streamPageResponse{Items: make([]streamResponse, 0, len(streams))}
	for _, sb := range streams {
		page.Items = append(page.Items, toStreamResponse(sb))
	}
	c.JSON(http.StatusOK, page)
}

// Get handles GET /streams/{stream-id}.
func (h StreamHandler) Get(c *gin.Context) {
	id := c.Param("stream-id")
	sb, err := h.Buffers.GetStream(c.Request.Context(), id)
	if err != nil {
		writeStreamError(c, err)
		return
	}
	c.JSON(http.StatusOK, toStreamResponse(sb))
}

// Delete handles DELETE /streams/{stream-id}.
func (h StreamHandler) Delete(c *gin.Context) {
	id := c.Param("stream-id")
	if err := h.Buffers.RemoveBuffer(c.Request.Context(), id); err != nil {
		writeStreamError(c, err)
		return
	}
	c.JSON(http.StatusOK, deletionResponse{Resource: "stream", ID: id, Deleted: true})
}

// UpdateBuffer handles PUT /streams/{stream-id}/buffer, which is not implemented yet.
func (StreamHandler) UpdateBuffer(c *gin.Context) {
	common.WriteError(c, http.StatusNotImplemented, "not_implemented", "resizing a stream buffer is not implemented yet")
}

func writeStreamError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, stream.ErrStreamNotFound):
		common.WriteError(c, http.StatusNotFound, "stream_not_found", "stream not found")
	case errors.Is(err, stream.ErrStreamExists):
		common.WriteError(c, http.StatusConflict, "stream_exists", err.Error())
	case errors.Is(err, stream.ErrActiveReaders):
		common.WriteError(c, http.StatusConflict, "active_dependency", "active readers still need this buffer")
	case errors.Is(err, stream.ErrUnsupportedSource):
		common.WriteError(c, http.StatusUnsupportedMediaType, "unsupported_media", stream.ErrUnsupportedSource.Error())
	case errors.Is(err, stream.ErrInvalidRequest):
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "invalid buffer request")
	case errors.Is(err, syscall.ENOSPC), errors.Is(err, syscall.EDQUOT):
		common.WriteError(c, http.StatusTooManyRequests, "capacity_exhausted", "not enough buffer storage")
	default:
		log.Printf("stream operation failed: %v", err)
		common.WriteInternalError(c)
	}
}

func toStreamResponse(sb model.StreamBuffer) streamResponse {
	return streamResponse{
		StreamID:       sb.StreamID,
		SensorID:       sb.SensorID,
		State:          sb.State,
		SyncConfidence: sb.SyncConfidence,
		Buffer:         toBufferStatusResponse(sb),
		Stats: streamStatsResponse{
			Framerate:     sb.FrameStat.Framerate,
			DroppedFrames: sb.FrameStat.DroppedFrames,
		},
		CreationTS: sb.CreationTS.UTC(),
	}
}

func toBufferStatusResponse(sb model.StreamBuffer) bufferStatusResponse {
	return bufferStatusResponse{
		Capacity:  sb.BufferStat.Capacity,
		HeldBytes: sb.BufferStat.HeldBytes,
		OldestTS:  optionalTime(sb.BufferStat.OldestTS),
		NewestTS:  optionalTime(sb.BufferStat.NewestTS),
	}
}

func optionalString(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func optionalTime(t time.Time) *time.Time {
	if t.IsZero() {
		return nil
	}
	u := t.UTC()
	return &u
}

func (r streamCreateRequest) validate() error {
	if err := common.CheckID("sensor_id", r.SensorID); err != nil {
		return err
	}
	if err := common.CheckSourceURI(r.SourceURI); err != nil {
		return err
	}
	if r.BufferLength != nil {
		return common.CheckBufferLength(*r.BufferLength)
	}
	return nil
}
