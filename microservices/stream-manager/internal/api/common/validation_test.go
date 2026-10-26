// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package common

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestCheckIDAcceptsBase64URLPrefix(t *testing.T) {
	for _, value := range []string{"_RClKSovSHSUbIf_hlnCIw", "-RClKSovSHSUbIf_hlnCIw", "str-_RClKSovSHSUbIf_hlnCIw"} {
		if err := CheckID("recording-id", value); err != nil {
			t.Fatalf("rejected resource ID %q: %v", value, err)
		}
	}
	for _, value := range []string{"_sensor", "-sensor", ".sensor"} {
		if err := CheckID("sensor_id", value); err == nil {
			t.Fatalf("accepted invalid sensor ID %q", value)
		}
	}
}

func TestParseRecordingFilterReportsAllErrors(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name, query, code, detail string
	}{
		{"valid", "sensor_id=cam&start_ts=2026-01-01T00:00:00Z&limit=5", "", ""},
		{
			"timestamps only", "start_ts=bad&end_ts=bad", "invalid_timestamp",
			"start_ts must be an RFC 3339 UTC timestamp ending in Z with at most 9 fractional digits\n" +
				"end_ts must be an RFC 3339 UTC timestamp ending in Z with at most 9 fractional digits",
		},
		{
			"reversed window", "start_ts=2026-01-02T00:00:00Z&end_ts=2026-01-01T00:00:00Z", "invalid_timestamp",
			"end_ts must be later than start_ts",
		},
		{
			"mixed", "stream_id=.bad&state=done&limit=0&expiry_ts=bad", "invalid_request",
			"stream_id must be 1-128 characters matching ^[A-Za-z0-9_-][A-Za-z0-9._:-]*$\n" +
				"state must be one of recording, finalizing, ready, failed\n" +
				"limit must be an integer between 1 and 100\n" +
				"expiry_ts must be an RFC 3339 UTC timestamp ending in Z with at most 9 fractional digits",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			c.Request = httptest.NewRequest(http.MethodGet, "/v1/records?"+tc.query, nil)
			_, code, err := ParseRecordingFilter(c)
			detail := ""
			if err != nil {
				detail = err.Error()
			}
			if code != tc.code || detail != tc.detail {
				t.Fatalf("got code %q detail %q, want %q %q", code, detail, tc.code, tc.detail)
			}
		})
	}
}
