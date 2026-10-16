// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"context"
	"errors"
	"log/slog"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
)

// replayWriteTimeout replaces the server write timeout on replay requests
const replayWriteTimeout = 15 * time.Minute

// ReplayHandler is initialized with the instance of Replay's new
// service which also implements Replayer interface
type ReplayHandler struct {
	Replays replay.Replayer
}

// handles /frame and /frame/url endpoints
func (h ReplayHandler) Frame(c *gin.Context)    { h.frame(c, false) }
func (h ReplayHandler) FrameURL(c *gin.Context) { h.frame(c, true) }

// handles /clip and /clip/url endpoints
func (h ReplayHandler) Clip(c *gin.Context)    { h.clip(c, false) }
func (h ReplayHandler) ClipURL(c *gin.Context) { h.clip(c, true) }

func (h ReplayHandler) frame(c *gin.Context, linkOnly bool) {
	ts, err := common.ParseTimestamp("timestamp", c.Query("timestamp"))
	if err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_timestamp", err.Error())
		return
	}
	format := c.DefaultQuery("format", "jpeg")
	if format != "jpeg" && format != "png" {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "format must be jpeg or png")
		return
	}
	match := c.DefaultQuery("match", "nearest")
	if match != "nearest" && match != "exact" {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "match must be nearest or exact")
		return
	}
	asJSON, ok := negotiate(c, linkOnly, "image/"+format)
	if !ok {
		return
	}
	extendWriteDeadline(c)
	media, err := h.Replays.Frame(c.Request.Context(), c.Param("recording-id"), ts, format, match)
	if err != nil {
		writeReplayError(c, err, false)
		return
	}
	h.respond(c, media, asJSON)
}

func (h ReplayHandler) clip(c *gin.Context, linkOnly bool) {
	start, err := common.ParseTimestamp("start_ts", c.Query("start_ts"))
	if err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_timestamp", err.Error())
		return
	}
	duration, err := parseDuration(c.Query("duration"))
	if err != nil {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	if format := c.DefaultQuery("format", "mp4"); format != "mp4" {
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "format must be mp4")
		return
	}
	asJSON, ok := negotiate(c, linkOnly, "video/mp4")
	if !ok {
		return
	}
	extendWriteDeadline(c)
	media, err := h.Replays.Clip(c.Request.Context(), c.Param("recording-id"), start, duration, "mp4")
	if err != nil {
		writeReplayError(c, err, true)
		return
	}
	h.respond(c, media, asJSON)
}

// Media handles GET /media/{recording-id}/{file}, serving a frame or clip
// until its expiry_ts.
func (h ReplayHandler) Media(c *gin.Context) {
	extendWriteDeadline(c)
	name := c.Param("file")
	file, info, err := h.Replays.OpenMedia(c.Request.Context(), c.Param("recording-id"), name)
	if err != nil {
		writeReplayError(c, err, strings.HasPrefix(name, "clip-"))
		return
	}
	defer closeMedia(file)
	serveMedia(c, file, info)
}

// respond writes media as a MediaResult or as its bytes.
func (h ReplayHandler) respond(c *gin.Context, media replay.Media, asJSON bool) {
	c.Header("X-Frame-Timestamp", media.Result.StartTS.UTC().Format(time.RFC3339Nano))
	c.Header("X-Exact-Match", strconv.FormatBool(media.ExactMatch))
	if asJSON {
		media.Result.URL = "/v1/media/" + media.Result.RecordingID + "/" + media.Name
		c.Header("Cache-Control", "no-store")
		c.JSON(http.StatusOK, media.Result)
		return
	}
	file, info, err := h.Replays.OpenMedia(c.Request.Context(), media.Result.RecordingID, media.Name)
	if err != nil {
		writeReplayError(c, err, media.Result.MediaType == "clip")
		return
	}
	defer closeMedia(file)
	serveMedia(c, file, info)
}

// negotiate picks JSON or the binary type from the Accept header; an absent
// header gets JSON. It answers 406 itself when neither is acceptable.
func negotiate(c *gin.Context, linkOnly bool, binaryType string) (asJSON, ok bool) {
	offers := []string{gin.MIMEJSON}
	if !linkOnly {
		offers = append(offers, binaryType)
	}
	switch c.NegotiateFormat(offers...) {
	case gin.MIMEJSON:
		return true, true
	case binaryType:
		return false, !linkOnly
	default:
		common.WriteError(c, http.StatusNotAcceptable, "not_acceptable", "the Accept header allows none of the available media types")
		return false, false
	}
}

func parseDuration(s string) (time.Duration, error) {
	seconds, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsNaN(seconds) || seconds <= 0 || seconds > math.MaxInt64/float64(time.Second) {
		return 0, errors.New("duration must be a positive number of seconds")
	}
	duration := time.Duration(math.Round(seconds * float64(time.Second)))
	if duration <= 0 {
		return 0, errors.New("duration must be a positive number of seconds")
	}
	return duration, nil
}

func serveMedia(c *gin.Context, file *os.File, info replay.MediaFile) {
	maxAge := max(int64(time.Until(info.ExpiryTS)/time.Second), 0)
	c.Header("Content-Type", info.ContentType)
	c.Header("Cache-Control", "private, max-age="+strconv.FormatInt(maxAge, 10))
	c.Header("Expires", info.ExpiryTS.UTC().Format(http.TimeFormat))
	c.Header("X-Content-Type-Options", "nosniff")
	http.ServeContent(c.Writer, c.Request, "", time.Time{}, file)
}

func closeMedia(file *os.File) {
	if err := file.Close(); err != nil {
		slog.Warn("closing replay media failed", "error", err)
	}
}

// extendWriteDeadline lifts the server write timeout for this request.
func extendWriteDeadline(c *gin.Context) {
	err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Now().Add(replayWriteTimeout))
	if err != nil && !errors.Is(err, http.ErrNotSupported) {
		slog.Warn("extending replay write deadline failed", "error", err)
	}
}

func writeReplayError(c *gin.Context, err error, clip bool) {
	notFoundCode := "frame_not_found"
	if clip {
		notFoundCode = "clip_not_found"
	}
	switch {
	case errors.Is(err, replay.ErrNotFound):
		common.WriteError(c, http.StatusNotFound, "recording_not_found", "recording not found")
	case errors.Is(err, replay.ErrNotCovered):
		detail := "the requested time is not covered by the record"
		if clip {
			detail = "the requested interval is not covered by the record"
		}
		common.WriteError(c, http.StatusNotFound, notFoundCode, detail)
	case errors.Is(err, replay.ErrFrameNotFound):
		detail := "no frame sits at exactly the requested time"
		if clip {
			detail = "no clip is available for the requested interval"
		}
		common.WriteError(c, http.StatusNotFound, notFoundCode, detail)
	case errors.Is(err, replay.ErrMediaNotFound):
		common.WriteError(c, http.StatusNotFound, notFoundCode, "media not found or expired")
	case errors.Is(err, replay.ErrNotReady):
		common.WriteError(c, http.StatusConflict, "record_not_ready", "record is not ready")
	case errors.Is(err, replay.ErrBusy):
		common.WriteError(c, http.StatusTooManyRequests, "capacity_exhausted", "extraction capacity reached, retry later")
	case errors.Is(err, replay.ErrInvalidRequest):
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "invalid replay request")
	case errors.Is(err, context.Canceled):
		c.Abort()
	case errors.Is(err, replay.ErrExtraction):
		slog.Error("replay extraction failed", "recording_id", c.Param("recording-id"))
		slog.Debug("replay extraction failure detail", "recording_id", c.Param("recording-id"), "error", err)
		common.WriteError(c, http.StatusServiceUnavailable, "storage_unavailable", "media extraction failed")
	default:
		slog.Error("replay request failed", "recording_id", c.Param("recording-id"), "error", err)
		common.WriteInternalError(c)
	}
}
