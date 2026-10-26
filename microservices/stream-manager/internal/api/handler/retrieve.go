// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"context"
	"errors"
	"log/slog"
	"math"
	"mime"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/retrieve"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// retrieveWriteTimeout replaces the server write timeout on retrieve requests
const retrieveWriteTimeout = 15 * time.Minute

// RetrieveHandler is initialized with the instance of Retrieve's new
// service which also implements Retriever interface
type RetrieveHandler struct {
	Retrievals retrieve.Retriever
}

func (h RetrieveHandler) Frame(c *gin.Context) {
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
	offers := []string{gin.MIMEJSON, "image/jpeg", "image/png"}
	if _, explicit := c.GetQuery("format"); explicit {
		offers = []string{gin.MIMEJSON, "image/" + format}
	}
	selected, ok := negotiate(c, offers...)
	if !ok {
		return
	}
	asJSON := selected == gin.MIMEJSON
	if !asJSON {
		format = strings.TrimPrefix(selected, "image/")
	}
	extendWriteDeadline(c)
	media, err := h.Retrievals.Frame(c.Request.Context(), c.Param("recording-id"), ts, format, match)
	if err != nil {
		writeRetrieveError(c, err, false)
		return
	}
	h.respond(c, media, asJSON)
}

func (h RetrieveHandler) Clip(c *gin.Context) {
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
	selected, ok := negotiate(c, gin.MIMEJSON, "video/mp4")
	if !ok {
		return
	}
	extendWriteDeadline(c)
	media, err := h.Retrievals.Clip(c.Request.Context(), c.Param("recording-id"), start, duration, "mp4")
	if err != nil {
		writeRetrieveError(c, err, true)
		return
	}
	h.respond(c, media, selected == gin.MIMEJSON)
}

// Media handles GET /media/{recording-id}/{file}, serving a frame or clip
// until its expiry_ts.
func (h RetrieveHandler) Media(c *gin.Context) {
	extendWriteDeadline(c)
	name := c.Param("file")
	file, info, err := h.Retrievals.OpenMedia(c.Request.Context(), c.Param("recording-id"), name)
	if err != nil {
		writeRetrieveError(c, err, strings.HasPrefix(name, "clip-"))
		return
	}
	defer closeMedia(file)
	serveMedia(c, file, info)
}

// respond writes media as a MediaResult or as its bytes.
func (h RetrieveHandler) respond(c *gin.Context, media retrieve.Media, asJSON bool) {
	c.Header("X-Frame-Timestamp", media.Result.StartTS.UTC().Format(time.RFC3339Nano))
	c.Header("X-Exact-Match", strconv.FormatBool(media.ExactMatch))
	if asJSON {
		media.Result.URL = "/v1/media/" + media.Result.RecordingID + "/" + media.Name
		c.Header("Cache-Control", "no-store")
		c.JSON(http.StatusOK, media.Result)
		return
	}
	file, info, err := h.Retrievals.OpenMedia(c.Request.Context(), media.Result.RecordingID, media.Name)
	if err != nil {
		writeRetrieveError(c, err, media.Result.MediaType == "clip")
		return
	}
	defer closeMedia(file)
	serveMedia(c, file, info)
}

func negotiate(c *gin.Context, offers ...string) (string, bool) {
	c.Writer.Header().Add("Vary", "Accept")
	header := strings.Join(c.Request.Header.Values("Accept"), ",")
	if strings.TrimSpace(header) == "" {
		return offers[0], true
	}
	type mediaRange struct {
		kind    string
		quality float64
	}
	var ranges []mediaRange
	parts := strings.Split(header, ",")
	valid := len(header) <= 8192 && len(parts) <= 64
	for _, part := range parts {
		if !valid {
			break
		}
		kind, params, err := mime.ParseMediaType(strings.TrimSpace(part))
		quality := 1.0
		if q, exists := params["q"]; exists {
			quality, err = strconv.ParseFloat(q, 64)
		}
		if err != nil || math.IsNaN(quality) || math.IsInf(quality, 0) || quality < 0 || quality > 1 || len(params) > 1 ||
			(len(params) == 1 && params["q"] == "") {
			valid = false
			break
		}
		ranges = append(ranges, mediaRange{kind, quality})
	}
	best, bestQuality := "", 0.0
	if valid {
		for _, offer := range offers {
			specificity, quality := -1, 0.0
			for _, r := range ranges {
				level := -1
				switch {
				case r.kind == offer:
					level = 2
				case r.kind == strings.SplitN(offer, "/", 2)[0]+"/*":
					level = 1
				case r.kind == "*/*":
					level = 0
				}
				if level >= 0 && (level > specificity || (level == specificity && r.quality > quality)) {
					specificity, quality = level, r.quality
				}
			}
			if quality > bestQuality {
				best, bestQuality = offer, quality
			}
		}
	}
	if best != "" {
		return best, true
	}
	common.WriteError(c, http.StatusNotAcceptable, "not_acceptable", "the Accept header allows none of the available media types")
	return "", false
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

func serveMedia(c *gin.Context, file *os.File, info retrieve.MediaFile) {
	c.Header("Content-Type", info.ContentType)
	if info.ExpiryTS == nil {
		c.Header("Cache-Control", "private, no-cache")
	} else {
		maxAge := max(int64(time.Until(*info.ExpiryTS)/time.Second), 0)
		c.Header("Cache-Control", "private, max-age="+strconv.FormatInt(maxAge, 10))
		c.Header("Expires", info.ExpiryTS.UTC().Format(http.TimeFormat))
	}
	c.Header("X-Content-Type-Options", "nosniff")
	http.ServeContent(c.Writer, c.Request, "", time.Time{}, file)
}

func closeMedia(file *os.File) {
	if err := file.Close(); err != nil {
		slog.Warn("closing retrieve media failed", "error", err)
	}
}

// extendWriteDeadline lifts the server write timeout for this request.
func extendWriteDeadline(c *gin.Context) {
	err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Now().Add(retrieveWriteTimeout))
	if err != nil && !errors.Is(err, http.ErrNotSupported) {
		slog.Warn("extending retrieve write deadline failed", "error", err)
	}
}

func writeRetrieveError(c *gin.Context, err error, clip bool) {
	notFoundCode := "frame_not_found"
	if clip {
		notFoundCode = "clip_not_found"
	}
	switch {
	case errors.Is(err, retrieve.ErrNotFound):
		common.WriteError(c, http.StatusNotFound, "recording_not_found", "recording not found")
	case errors.Is(err, retrieve.ErrNotCovered):
		detail := "the requested time is not covered by the record"
		if clip {
			detail = "the requested interval is not covered by the record"
		}
		common.WriteError(c, http.StatusNotFound, notFoundCode, detail)
	case errors.Is(err, retrieve.ErrFrameNotFound):
		detail := "no frame sits at exactly the requested time"
		if clip {
			detail = "no clip is available for the requested interval"
		}
		common.WriteError(c, http.StatusNotFound, notFoundCode, detail)
	case errors.Is(err, retrieve.ErrBeyondSearchLimit):
		slog.Warn("retrieve search limit reached", "recording_id", c.Param("recording-id"),
			"search_limit", retrieve.SearchLimit, "clip", clip, "error", err)
		detail := "no decodable frame is available for the requested time"
		if clip {
			detail = "no clip is available for the requested interval"
		}
		common.WriteError(c, http.StatusNotFound, notFoundCode, detail)
	case errors.Is(err, retrieve.ErrMediaNotFound):
		common.WriteError(c, http.StatusNotFound, notFoundCode, "media not found or expired")
	case errors.Is(err, retrieve.ErrNotReady):
		common.WriteError(c, http.StatusConflict, "record_not_ready", "record is not ready")
	case errors.Is(err, retrieve.ErrBusy):
		common.WriteError(c, http.StatusTooManyRequests, "capacity_exhausted", "extraction capacity reached, retry later")
	case errors.Is(err, storage.ErrStorageFull):
		common.WriteError(c, http.StatusInsufficientStorage, "storage_full", "recording storage quota reached")
	case errors.Is(err, retrieve.ErrInvalidRequest):
		common.WriteError(c, http.StatusBadRequest, "invalid_request", "invalid retrieve request")
	case errors.Is(err, context.Canceled):
		c.Abort()
	case errors.Is(err, retrieve.ErrExtraction):
		slog.Error("retrieve extraction failed", "recording_id", c.Param("recording-id"))
		slog.Debug("retrieve extraction failure detail", "recording_id", c.Param("recording-id"), "error", err)
		common.WriteError(c, http.StatusServiceUnavailable, "storage_unavailable", "media extraction failed")
	default:
		slog.Error("retrieve request failed", "recording_id", c.Param("recording-id"), "error", err)
		common.WriteInternalError(c)
	}
}
