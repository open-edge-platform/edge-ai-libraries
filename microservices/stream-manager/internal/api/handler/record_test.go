// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

func TestRecordErrors(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cases := []struct {
		err    error
		status int
		code   string
	}{
		{storage.ErrStorageFull, http.StatusInsufficientStorage, "storage_full"},
		{record.ErrCapacity, http.StatusTooManyRequests, "capacity_exhausted"},
	}
	for _, tc := range cases {
		rec := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(rec)
		writeRecordError(c, tc.err)
		if rec.Code != tc.status || errorCode(t, rec) != tc.code {
			t.Fatalf("%v: got %d %s, want %d %s", tc.err, rec.Code, rec.Body, tc.status, tc.code)
		}
	}
}
