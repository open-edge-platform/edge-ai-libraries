// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

const (
	maxSourceURILength  = 2048
	defaultLimit        = 20
	maxLimit            = 100
	maxIDLength         = 128
	maxSelectors        = 32
	maxPreEventDuration = 300
)

var (
	idPattern       = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]*$`)
	recordingStates = map[string]bool{"recording": true, "finalizing": true, "ready": true, "failed": true}
)

func writeError(c *gin.Context, status int, code, detail string) {
	c.AbortWithStatusJSON(status, model.ErrorResponse{Status: status, ErrorCode: code, ErrorDetails: detail})
}

func writeInternalError(c *gin.Context) {
	writeError(c, http.StatusInternalServerError, "internal_error", "internal error")
}

// decodeJSON reads exactly one JSON object and refuses unknown fields.
func decodeJSON(c *gin.Context, dst any) error {
	dec := json.NewDecoder(c.Request.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return jsonError(err)
	}
	if dec.Decode(&struct{}{}) != io.EOF {
		return errors.New("request body must contain a single JSON object")
	}
	return nil
}

func jsonError(err error) error {
	var typeErr *json.UnmarshalTypeError
	var maxErr *http.MaxBytesError
	switch {
	case errors.As(err, &typeErr) && typeErr.Field != "":
		return fmt.Errorf("%s has the wrong type", typeErr.Field)
	case errors.As(err, &maxErr):
		return fmt.Errorf("request body must be at most %d bytes", maxErr.Limit)
	case strings.HasPrefix(err.Error(), "json: unknown field "):
		return fmt.Errorf("unknown field %s", strings.TrimPrefix(err.Error(), "json: unknown field "))
	case errors.Is(err, io.EOF):
		return errors.New("request body is required")
	default:
		return errors.New("request body is not valid JSON")
	}
}

func checkID(name, id string) error {
	if id == "" {
		return fmt.Errorf("%s is required", name)
	}
	if len(id) > maxIDLength || !idPattern.MatchString(id) {
		return fmt.Errorf("%s must be 1-%d characters matching %s", name, maxIDLength, idPattern)
	}
	return nil
}

func parseLimit(s string) (int, error) {
	if s == "" {
		return defaultLimit, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > maxLimit {
		return 0, fmt.Errorf("limit must be an integer between 1 and %d", maxLimit)
	}
	return n, nil
}

// parseTimestamp accepts RFC 3339 UTC with a Z suffix and at most nine
// fractional digits, within the range of int64 nanoseconds since 1970.
func parseLifecycleTimestamp(name, s string) (time.Time, error) {
	invalid := fmt.Errorf("%s must be an RFC 3339 UTC timestamp ending in Z with at most 9 fractional digits", name)
	if !strings.HasSuffix(s, "Z") {
		return time.Time{}, invalid
	}
	// time.Parse silently truncates digits beyond the ninth.
	if i := strings.IndexByte(s, '.'); i >= 0 && len(s)-i-2 > 9 {
		return time.Time{}, invalid
	}
	t, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		return time.Time{}, invalid
	}
	if !time.Unix(0, t.UnixNano()).Equal(t) {
		return time.Time{}, fmt.Errorf("%s is out of range", name)
	}
	return t.UTC(), nil
}

func (r streamCreateRequest) validate() error {
	if err := checkID("sensor_id", r.SensorID); err != nil {
		return err
	}
	if r.SourceKind != nil && *r.SourceKind != "uri_source" {
		return errors.New("source_kind must be uri_source")
	}
	return checkSourceURI(r.SourceURI)
}

func checkSourceURI(s string) error {
	if s == "" {
		return errors.New("source_uri is required")
	}
	if len(s) > maxSourceURILength {
		return fmt.Errorf("source_uri must be at most %d characters", maxSourceURILength)
	}
	u, err := url.Parse(s)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return errors.New("source_uri must be an absolute URI")
	}
	if u.User != nil {
		return errors.New("source_uri must not contain credentials")
	}
	return nil
}

func (r bufferUpdateRequest) validate() error {
	if r.BufferLength == nil {
		return errors.New("buffer_length is required")
	}
	return checkBufferLength(*r.BufferLength)
}

func checkBufferLength(n int) error {
	if time.Duration(n)*time.Second < config.MinBufferLength || time.Duration(n)*time.Second > config.MaxBufferLength {
		return fmt.Errorf("buffer_length must be between %d and %d seconds", int(config.MinBufferLength/time.Second), int(config.MaxBufferLength/time.Second))
	}
	return nil
}

// validate checks the request and returns the parsed start_ts, or the
// error_code and reason for rejecting it.
func (r *recordStartRequest) validate(now time.Time) (time.Time, string, error) {
	if err := checkSelectors(r.StreamIDs, r.SensorIDs); err != nil {
		return time.Time{}, "invalid_selector", err
	}
	if r.StartTS == nil {
		return time.Time{}, "invalid_request", errors.New("start_ts is required")
	}
	startTS, err := parseLifecycleTimestamp("start_ts", *r.StartTS)
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

func checkSelectors(streamIDs, sensorIDs []string) error {
	name, ids := "stream_ids", streamIDs
	switch {
	case streamIDs != nil && sensorIDs != nil:
		return errors.New("provide either stream_ids or sensor_ids, not both")
	case streamIDs == nil && sensorIDs == nil:
		return errors.New("provide stream_ids or sensor_ids")
	case sensorIDs != nil:
		name, ids = "sensor_ids", sensorIDs
	}
	if len(ids) < 1 || len(ids) > maxSelectors {
		return fmt.Errorf("%s must hold 1-%d IDs", name, maxSelectors)
	}
	seen := make(map[string]bool, len(ids))
	for _, id := range ids {
		if err := checkID(name, id); err != nil {
			return err
		}
		if seen[id] {
			return fmt.Errorf("%s must not repeat an ID", name)
		}
		seen[id] = true
	}
	return nil
}

func (r recordStopRequest) validate() error {
	return checkID("recording_id", r.RecordingID)
}

// parseRecordingFilter reads the GET /records query, returning the
// error_code and reason when it is invalid.
func parseRecordingFilter(c *gin.Context) (model.RecordingFilter, string, error) {
	f := model.RecordingFilter{
		SensorID: c.Query("sensor_id"),
		StreamID: c.Query("stream_id"),
		State:    c.Query("state"),
		Cursor:   c.Query("cursor"),
	}
	for name, id := range map[string]string{"sensor_id": f.SensorID, "stream_id": f.StreamID} {
		if id == "" {
			continue
		}
		if err := checkID(name, id); err != nil {
			return f, "invalid_request", err
		}
	}
	for name, dst := range map[string]*time.Time{"start_ts": &f.StartTS, "end_ts": &f.EndTS, "expiry_ts": &f.ExpiryTS} {
		s := c.Query(name)
		if s == "" {
			continue
		}
		t, err := parseLifecycleTimestamp(name, s)
		if err != nil {
			return f, "invalid_timestamp", err
		}
		*dst = t
	}
	if !f.StartTS.IsZero() && !f.EndTS.IsZero() && !f.EndTS.After(f.StartTS) {
		return f, "invalid_timestamp", errors.New("end_ts must be later than start_ts")
	}
	if f.State != "" && !recordingStates[f.State] {
		return f, "invalid_request", errors.New("state must be one of recording, finalizing, ready, failed")
	}
	if md := c.QueryMap("metadata"); len(md) > 0 {
		f.Metadata = make(map[string]any, len(md))
		for k, v := range md {
			f.Metadata[k] = v
		}
	}
	limit, err := parseLimit(c.Query("limit"))
	if err != nil {
		return f, "invalid_request", err
	}
	f.Limit = limit
	return f, "", nil
}
