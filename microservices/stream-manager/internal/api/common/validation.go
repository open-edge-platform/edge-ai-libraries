// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import (
	"errors"
	"fmt"
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
	maxSourceURILength = 2048
	defaultLimit       = 20
	maxLimit           = 100
	maxIDLength        = 128
)

var (
	idPattern       = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]*$`)
	recordingStates = map[string]bool{"recording": true, "finalizing": true, "ready": true, "failed": true}
)

func CheckID(name, id string) error {
	if id == "" {
		return fmt.Errorf("%s is required", name)
	}
	if len(id) > maxIDLength || !idPattern.MatchString(id) {
		return fmt.Errorf("%s must be 1-%d characters matching %s", name, maxIDLength, idPattern)
	}
	return nil
}

func ParseLimit(s string) (int, error) {
	if s == "" {
		return defaultLimit, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > maxLimit {
		return 0, fmt.Errorf("limit must be an integer between 1 and %d", maxLimit)
	}
	return n, nil
}

// ParseTimestamp accepts RFC 3339 UTC with a Z suffix and at most nine
// fractional digits, within the range of int64 nanoseconds since 1970.
func ParseTimestamp(name, s string) (time.Time, error) {
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

func CheckSourceURI(s string) error {
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

// CheckBufferLength validates a length in whole seconds against the
// configured bounds.
func CheckBufferLength(seconds int) error {
	minSeconds, maxSeconds := int(config.MinBufferLength/time.Second), int(config.MaxBufferLength/time.Second)
	if seconds < minSeconds || seconds > maxSeconds {
		return fmt.Errorf("buffer_length must be between %d and %d seconds", minSeconds, maxSeconds)
	}
	return nil
}

// ParseRecordingFilter reads the GET /records query, returning the
// error_code and reason when it is invalid.
func ParseRecordingFilter(c *gin.Context) (model.RecordingFilter, string, error) {
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
		if err := CheckID(name, id); err != nil {
			return f, "invalid_request", err
		}
	}
	for name, dst := range map[string]*time.Time{"start_ts": &f.StartTS, "end_ts": &f.EndTS, "expiry_ts": &f.ExpiryTS} {
		s := c.Query(name)
		if s == "" {
			continue
		}
		t, err := ParseTimestamp(name, s)
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
	limit, err := ParseLimit(c.Query("limit"))
	if err != nil {
		return f, "invalid_request", err
	}
	f.Limit = limit
	return f, "", nil
}
