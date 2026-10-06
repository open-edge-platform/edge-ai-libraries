// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

const (
	maxPreEventDuration = 300
)

// recordingResponse is the API view of a recording.
type recordingResponse struct {
	RecordingID string         `json:"recording_id"`
	SensorID    string         `json:"sensor_id"`
	StreamID    *string        `json:"stream_id"`
	StartTS     time.Time      `json:"start_ts"`
	EndTS       *time.Time     `json:"end_ts"`
	State       string         `json:"state"`
	SizeBytes   *int64         `json:"size_bytes"`
	Metadata    map[string]any `json:"metadata"`
	CreationTS  time.Time      `json:"creation_ts"`
	ExpiryTS    *time.Time     `json:"expiry_ts"`
	ErrorDetail *string        `json:"error_detail"`
}

// recordStartRequest records one stream.
// TODO: accept multiple stream_ids in one request.
type recordStartRequest struct {
	StreamID         string         `json:"stream_id"`
	StartTS          *string        `json:"start_ts"`
	Duration         *float64       `json:"duration"`
	PreEventDuration *float64       `json:"pre_event_duration"`
	Metadata         map[string]any `json:"metadata"`
}

type recordStartResponse struct {
	Recordings []recordingResponse `json:"recordings"`
}

type recordStopRequest struct {
	RecordingID string `json:"recording_id"`
}

type recordingPageResponse struct {
	Items      []recordingResponse `json:"items"`
	NextCursor *string             `json:"next_cursor"`
}

// RecordHandler serves the Recording Storage APIs.
type RecordHandler struct {
	Records *record.Service
}

// Start handles POST /records/start.
func (h RecordHandler) Start(c *gin.Context) {
	var req recordStartRequest
	if err := common.DecodeJSON(c, &req); err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	startTS, code, err := req.validate(time.Now())
	if err != nil {
		common.WriteError(c, http.StatusBadRequest, code, err.Error())
		return
	}
	preEvent, err := record.Seconds(*req.PreEventDuration)
	if err != nil {
		writeRecordError(c, err)
		return
	}
	options := record.StartOptions{
		StreamID: req.StreamID, StartTS: startTS, PreEvent: preEvent, Metadata: req.Metadata,
	}
	if req.Duration != nil {
		duration, err := record.Seconds(*req.Duration)
		if err != nil {
			writeRecordError(c, err)
			return
		}
		options.Duration = &duration
	}
	rec, err := h.Records.Start(c.Request.Context(), options)
	if err != nil {
		writeRecordError(c, err)
		return
	}
	c.JSON(http.StatusCreated, recordStartResponse{Recordings: []recordingResponse{toRecordingResponse(rec)}})
}

// Stop handles POST /records/stop.
func (h RecordHandler) Stop(c *gin.Context) {
	var req recordStopRequest
	if err := common.DecodeJSON(c, &req); err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	if err := req.validate(); err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	rec, accepted, err := h.Records.Stop(c.Request.Context(), req.RecordingID)
	if err != nil {
		writeRecordError(c, err)
		return
	}
	status := http.StatusOK
	if accepted {
		status = http.StatusAccepted
	}
	c.JSON(status, toRecordingResponse(rec))
}

// List handles GET /records.
func (h RecordHandler) List(c *gin.Context) {
	filter, code, err := common.ParseRecordingFilter(c)
	if err != nil {
		common.WriteError(c, http.StatusBadRequest, code, err.Error())
		return
	}
	recs, next, err := h.Records.List(c.Request.Context(), filter)
	if err != nil {
		writeRecordError(c, err)
		return
	}
	page := recordingPageResponse{Items: make([]recordingResponse, 0, len(recs)), NextCursor: optionalString(next)}
	for _, rec := range recs {
		page.Items = append(page.Items, toRecordingResponse(rec))
	}
	c.JSON(http.StatusOK, page)
}

// Get handles GET /records/{recording-id}.
func (h RecordHandler) Get(c *gin.Context) {
	id := c.Param("recording-id")
	rec, err := h.Records.Get(c.Request.Context(), id)
	if err != nil {
		writeRecordError(c, err)
		return
	}
	c.JSON(http.StatusOK, toRecordingResponse(rec))
}

// Delete handles DELETE /records/{recording-id}.
func (h RecordHandler) Delete(c *gin.Context) {
	id := c.Param("recording-id")
	if err := h.Records.DeleteRecording(c.Request.Context(), id); err != nil {
		writeRecordError(c, err)
		return
	}
	c.JSON(http.StatusOK, deletionResponse{Resource: "recording", ID: id, Deleted: true})
}

func writeRecordError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, storage.ErrNotFound):
		common.WriteError(c, http.StatusNotFound, "record_not_found", "record not found")
	case errors.Is(err, stream.ErrStreamNotFound):
		common.WriteError(c, http.StatusNotFound, "stream_not_found", "stream is not attached")
	case errors.Is(err, stream.ErrHistoryUnavailable), errors.Is(err, stream.ErrSliceExpired):
		common.WriteError(c, http.StatusConflict, "history_unavailable", "requested history is not available")
	case errors.Is(err, record.ErrInvalidRequest), errors.Is(err, storage.ErrInvalidFilter):
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "invalid recording request or filter")
	case errors.Is(err, record.ErrConflict):
		common.WriteError(c, http.StatusConflict, "record_not_ready", "recording cannot be changed in its current state")
	case errors.Is(err, record.ErrCapacity):
		common.WriteError(c, http.StatusTooManyRequests, "capacity_exhausted", "recording capacity reached")
	case errors.Is(err, record.ErrCleanup):
		common.WriteError(c, http.StatusServiceUnavailable, "storage_unavailable", "recording cleanup failed; retry later")
	default:
		log.Printf("recording operation failed: %v", err)
		common.WriteInternalError(c)
	}
}

func toRecordingResponse(rec model.Recording) recordingResponse {
	md := rec.Metadata
	if md == nil {
		md = map[string]any{}
	}
	return recordingResponse{
		RecordingID: rec.RecordingID,
		SensorID:    rec.SensorID,
		StreamID:    rec.StreamID,
		StartTS:     rec.StartTS.UTC(),
		EndTS:       utcPtr(rec.EndTS),
		State:       rec.State,
		SizeBytes:   rec.SizeBytes,
		Metadata:    md,
		CreationTS:  rec.CreationTS.UTC(),
		ExpiryTS:    utcPtr(rec.ExpiryTS),
		ErrorDetail: rec.ErrorDetail,
	}
}

func utcPtr(t *time.Time) *time.Time {
	if t == nil {
		return nil
	}
	u := t.UTC()
	return &u
}

// validate checks the request and returns the parsed start_ts, or the
// error_code and reason for rejecting it.
func (r *recordStartRequest) validate(now time.Time) (time.Time, string, error) {
	if err := common.CheckID("stream_id", r.StreamID); err != nil {
		return time.Time{}, "invalid_selector", err
	}
	if r.StartTS == nil {
		return time.Time{}, "invalid_request", errors.New("start_ts is required")
	}
	startTS, err := common.ParseTimestamp("start_ts", *r.StartTS)
	if err != nil {
		return time.Time{}, "invalid_timestamp", err
	}
	if startTS.After(now) {
		return time.Time{}, "invalid_timestamp", errors.New("start_ts must not be in the future")
	}
	if r.Duration != nil && *r.Duration <= 0 {
		return time.Time{}, "invalid_request", errors.New("duration must be greater than 0")
	}
	if r.PreEventDuration == nil {
		r.PreEventDuration = new(float64)
	}
	if *r.PreEventDuration < 0 || *r.PreEventDuration > maxPreEventDuration {
		return time.Time{}, "invalid_request", fmt.Errorf("pre_event_duration must be between 0 and %d", maxPreEventDuration)
	}
	return startTS, "", nil
}

func (r recordStopRequest) validate() error {
	return common.CheckID("recording_id", r.RecordingID)
}
