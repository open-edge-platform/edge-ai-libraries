// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"errors"
	"fmt"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// RetrievalHandler serves frame and clip retrieval endpoints.
type RetrievalHandler struct {
	service *replay.RetrievalService
	media   storage.MediaStore
}

func NewRetrievalHandler(service *replay.RetrievalService, media storage.MediaStore) *RetrievalHandler {
	return &RetrievalHandler{service: service, media: media}
}

// GetFrame serves a single frame, negotiating binary or JSON.
func (h *RetrievalHandler) GetFrame(c *gin.Context) {
	h.handleFrame(c, false)
}

// GetFrameURL always answers with a JSON MediaResult carrying a presigned
// URL, regardless of the Accept header.
func (h *RetrievalHandler) GetFrameURL(c *gin.Context) {
	h.handleFrame(c, true)
}

// GetClip serves a clip, negotiating binary or JSON.
func (h *RetrievalHandler) GetClip(c *gin.Context) {
	h.handleClip(c, false)
}

// GetClipURL always answers with a JSON MediaResult carrying a presigned
// URL, regardless of the Accept header.
func (h *RetrievalHandler) GetClipURL(c *gin.Context) {
	h.handleClip(c, true)
}

func (h *RetrievalHandler) handleFrame(c *gin.Context, forceJSON bool) {
	recordingID := c.Param("recording_id")
	if strings.TrimSpace(recordingID) == "" {
		h.writeError(c, http.StatusBadRequest, "invalid_request", "missing recording_id")
		return
	}

	startTS, err := parseTimestamp(c, "timestamp")
	if err != nil {
		h.writeError(c, http.StatusBadRequest, "invalid_timestamp", err.Error())
		return
	}

	format := c.Query("format")
	if !h.negotiate(c, forceJSON, format, replay.FrameContentType, acceptsFrameBinary, "accept header is incompatible with the requested frame format") {
		return
	}

	result, err := h.service.GetFrame(c.Request.Context(), model.FrameRequest{
		RecordingID: recordingID,
		StartTS:     startTS,
		Format:      format,
		Match:       c.Query("match"),
	})
	if err != nil {
		h.writeServiceError(c, err)
		return
	}

	h.respond(c, result, forceJSON, acceptsFrameBinary)
}

func (h *RetrievalHandler) handleClip(c *gin.Context, forceJSON bool) {
	recordingID := c.Param("recording_id")
	if strings.TrimSpace(recordingID) == "" {
		h.writeError(c, http.StatusBadRequest, "invalid_request", "missing recording_id")
		return
	}

	startTS, err := parseTimestamp(c, "timestamp_start")
	if err != nil {
		h.writeError(c, http.StatusBadRequest, "invalid_timestamp", err.Error())
		return
	}

	endValue, durationValue := c.Query("timestamp_end"), c.Query("duration_seconds")
	endProvided := endValue != ""
	durationProvided := durationValue != ""
	if endProvided == durationProvided {
		if endProvided {
			h.writeError(c, http.StatusBadRequest, "invalid_request", "provide exactly one of timestamp_end or duration_seconds")
		} else {
			h.writeError(c, http.StatusBadRequest, "invalid_request", "missing clip end boundary")
		}
		return
	}

	var endTS *time.Time
	if endProvided {
		parsed, err := time.Parse(time.RFC3339Nano, endValue)
		if err != nil {
			h.writeError(c, http.StatusBadRequest, "invalid_timestamp", "timestamp_end must be RFC3339Nano")
			return
		}
		utc := parsed.UTC()
		endTS = &utc
	}

	var clipDuration *float64
	if durationProvided {
		parsed, err := parseDurationSeconds(durationValue)
		if err != nil {
			h.writeError(c, http.StatusBadRequest, "invalid_duration", err.Error())
			return
		}
		clipDuration = &parsed
	}

	format := c.Query("format")
	if !h.negotiate(c, forceJSON, format, replay.ClipContentType, acceptsClipBinary, "accept header is incompatible with the requested clip format") {
		return
	}

	result, err := h.service.GetClip(c.Request.Context(), model.ClipRequest{
		RecordingID:  recordingID,
		StartTS:      startTS,
		EndTS:        endTS,
		ClipDuration: clipDuration,
		Format:       format,
	})
	if err != nil {
		h.writeServiceError(c, err)
		return
	}

	h.respond(c, result, forceJSON, acceptsClipBinary)
}

// negotiate checks the Accept header against the media type the request will
// produce before any storage or extraction work happens. It returns false
// after writing a 406 when the caller cannot accept either the binary media
// or the JSON descriptor. Unsupported formats are left for the service to
// report as 415 so the error precedence stays unchanged.
func (h *RetrievalHandler) negotiate(c *gin.Context, forceJSON bool, format string, contentTypeFor func(string) (string, error), acceptsBinary func(accept, contentType string) bool, incompatibleDetail string) bool {
	if forceJSON {
		return true
	}
	contentType, err := contentTypeFor(format)
	if err != nil {
		return true
	}
	accept := c.GetHeader("Accept")
	if acceptsBinary(accept, contentType) || acceptsJSON(accept) {
		return true
	}
	h.writeError(c, http.StatusNotAcceptable, "not_acceptable", incompatibleDetail)
	return false
}

// respond applies the shared content-negotiation rules: the dedicated /url
// routes always return JSON, and the binary routes return bytes only when
// the caller explicitly asked for a compatible media type. negotiate has
// already rejected callers that accept neither representation.
func (h *RetrievalHandler) respond(c *gin.Context, result model.MediaResult, forceJSON bool, acceptsBinary func(accept, contentType string) bool) {
	if !forceJSON && acceptsBinary(c.GetHeader("Accept"), result.ContentType) {
		h.writeBinary(c, result)
		return
	}
	writeMediaResult(c, result)
}

func parseTimestamp(c *gin.Context, key string) (time.Time, error) {
	value := c.Query(key)
	if value == "" {
		return time.Time{}, fmt.Errorf("missing %s parameter", key)
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("%s must be RFC3339Nano", key)
	}
	return parsed.UTC(), nil
}

func parseDurationSeconds(value string) (float64, error) {
	parsed, err := strconv.ParseFloat(strings.TrimSpace(value), 64)
	if err != nil {
		return 0, errors.New("duration_seconds must be a number")
	}
	if math.IsNaN(parsed) || math.IsInf(parsed, 0) {
		return 0, errors.New("duration_seconds must be finite")
	}
	if parsed <= 0 {
		return 0, errors.New("duration_seconds must be greater than zero")
	}
	return parsed, nil
}

// writeMediaResult writes a MediaResult (the JSON alternative to raw frame
// or clip bytes). Per the API contract this response is never cached, same
// as the binary alternative.
func writeMediaResult(c *gin.Context, result model.MediaResult) {
	c.Header("Cache-Control", "private, no-store")
	c.JSON(http.StatusOK, result)
}

func (h *RetrievalHandler) writeBinary(c *gin.Context, result model.MediaResult) {
	reader, err := h.media.OpenDerived(c.Request.Context(), result.DerivedKey)
	if err != nil {
		h.writeError(c, http.StatusServiceUnavailable, "storage_unavailable", "failed to read derived media")
		return
	}
	defer reader.Close()

	extraHeaders := map[string]string{
		"Cache-Control":     "private, no-store",
		"X-Frame-Timestamp": result.StartTS.UTC().Format(time.RFC3339Nano),
		"X-Exact-Match":     strconv.FormatBool(result.ExactMatch),
	}
	// Content length is unknown up front (OpenDerived only hands back a
	// stream), so pass -1 and let Gin/net/http fall back to chunked
	// transfer encoding.
	c.DataFromReader(http.StatusOK, -1, result.ContentType, reader, extraHeaders)
}

func acceptsJSON(accept string) bool {
	accept = strings.ToLower(accept)
	return accept == "" || strings.Contains(accept, "application/json") || strings.Contains(accept, "*/*")
}

func acceptsFrameBinary(accept, contentType string) bool {
	accept = strings.ToLower(accept)
	if acceptsJSON(accept) {
		return false
	}
	if !strings.Contains(accept, "image/") {
		return false
	}
	switch contentType {
	case "image/jpeg":
		return strings.Contains(accept, "image/jpeg") || strings.Contains(accept, "image/*")
	case "image/png":
		return strings.Contains(accept, "image/png") || strings.Contains(accept, "image/*")
	default:
		return false
	}
}

func acceptsClipBinary(accept, contentType string) bool {
	accept = strings.ToLower(accept)
	if acceptsJSON(accept) {
		return false
	}
	if contentType != "video/mp4" {
		return false
	}
	return strings.Contains(accept, "video/mp4") ||
		strings.Contains(accept, "video/*") ||
		strings.Contains(accept, "application/octet-stream")
}

func (h *RetrievalHandler) writeError(c *gin.Context, status int, code, details string) {
	c.JSON(status, model.ErrorResponse{Status: status, ErrorCode: code, ErrorDetails: details})
}

// writeServiceError maps a RetrievalService error to the HTTP status and
// error_code the API contract requires. error_details is always a short,
// generic phrase: it must never leak file paths, storage addresses,
// credentials, or media-tooling output, so lower-level error strings (e.g.
// from the extractor or object store) are intentionally not echoed back to
// the caller. The full error is attached to the Gin context so the access
// log records it.
func (h *RetrievalHandler) writeServiceError(c *gin.Context, err error) {
	_ = c.Error(err)
	switch {
	case errors.Is(err, storage.ErrRecordingNotFound):
		h.writeError(c, http.StatusNotFound, "recording_not_found", "recording not found")
	case errors.Is(err, storage.ErrInvalidIdentifier), errors.Is(err, storage.ErrInvalidObjectKey):
		h.writeError(c, http.StatusBadRequest, "invalid_request", "invalid recording identifier")
	case errors.Is(err, replay.ErrRecordingNotReady):
		h.writeError(c, http.StatusConflict, "recording_not_ready", "recording is not ready for retrieval")
	case errors.Is(err, replay.ErrUnsupportedFrameFormat):
		h.writeError(c, http.StatusUnsupportedMediaType, "unsupported_media", "unsupported frame format")
	case errors.Is(err, replay.ErrUnsupportedClipFormat):
		h.writeError(c, http.StatusUnsupportedMediaType, "unsupported_media", "unsupported clip format")
	case errors.Is(err, replay.ErrUnsupportedMatchMode):
		h.writeError(c, http.StatusBadRequest, "invalid_request", "unsupported match mode")
	case errors.Is(err, replay.ErrInvalidClipRange):
		h.writeError(c, http.StatusBadRequest, "invalid_request", "invalid clip range")
	case errors.Is(err, replay.ErrNoExactMatch):
		h.writeError(c, http.StatusNotFound, "frame_not_found", "no frame sits exactly at the requested timestamp")
	case errors.Is(err, replay.ErrTimestampOutOfCoverage):
		h.writeError(c, http.StatusNotFound, "timestamp_out_of_coverage", "requested timestamp falls outside the recording's stored coverage")
	case errors.Is(err, replay.ErrClipIntervalNotCovered):
		h.writeError(c, http.StatusNotFound, "interval_not_covered", "the requested clip interval is not fully covered by the recording")
	case errors.Is(err, replay.ErrSidecarUnavailable):
		h.writeError(c, http.StatusServiceUnavailable, "storage_unavailable", "media index is not available")
	case errors.Is(err, replay.ErrSidecarMalformed),
		errors.Is(err, replay.ErrSidecarUnsupported),
		errors.Is(err, replay.ErrSidecarEmpty),
		errors.Is(err, replay.ErrSidecarInvalidTimescale),
		errors.Is(err, replay.ErrSidecarInvalidSample),
		errors.Is(err, replay.ErrSidecarDuplicateSample),
		errors.Is(err, replay.ErrSidecarUnordered),
		errors.Is(err, replay.ErrSidecarMismatch):
		h.writeError(c, http.StatusUnprocessableEntity, "invalid_media_index", "the recording's media index is invalid")
	case errors.Is(err, replay.ErrMediaUnavailable):
		h.writeError(c, http.StatusServiceUnavailable, "storage_unavailable", "media storage is not available")
	case errors.Is(err, replay.ErrRecordingTooLarge):
		h.writeError(c, http.StatusRequestEntityTooLarge, "recording_too_large", "recording exceeds the maximum size this service can extract from")
	case errors.Is(err, replay.ErrRecordingSizeUnknown):
		h.writeError(c, http.StatusConflict, "recording_size_unknown", "recording size is unavailable for safe extraction")
	case errors.Is(err, replay.ErrExtractionFailed):
		h.writeError(c, http.StatusServiceUnavailable, "extraction_failed", "media extraction failed")
	default:
		h.writeError(c, http.StatusInternalServerError, "internal_error", "internal error")
	}
}
