// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

type streamBufferStub struct{ info model.StreamBuffer }

func (streamBufferStub) CreateBuffer(context.Context, string, string, time.Duration) (string, error) {
	return "", nil
}

func (streamBufferStub) GetBuffer(context.Context, string, time.Time, time.Time) ([]model.BufferSlice, error) {
	return nil, nil
}

func (streamBufferStub) AcquireBuffer(context.Context, string, time.Time, time.Time) (*stream.BufferLease, error) {
	return nil, nil
}

func (streamBufferStub) ResizeBuffer(context.Context, string, int) (model.StreamBuffer, error) {
	return model.StreamBuffer{}, nil
}

func (streamBufferStub) RemoveBuffer(context.Context, string) error { return nil }

func (s streamBufferStub) GetStream(context.Context, string) (model.StreamBuffer, error) {
	return s.info, nil
}

func (streamBufferStub) ListStreams(context.Context) ([]model.StreamBuffer, error) { return nil, nil }

func TestGetFailedStreamNTPReadinessError(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name       string
		info       model.StreamBuffer
		wantStatus int
		wantCode   string
	}{
		{
			name: "unverified after readiness timeout",
			info: model.StreamBuffer{
				State: "failed", SyncConfidence: model.SyncUnverified, IngestFailure: stream.ErrNotNTPSynced,
			},
			wantStatus: http.StatusUnprocessableEntity,
			wantCode:   "not_ntp_synced",
		},
		{
			name: "best effort after readiness timeout",
			info: model.StreamBuffer{
				State: "failed", SyncConfidence: model.SyncBestEffort, IngestFailure: stream.ErrNotNTPSynced,
			},
			wantStatus: http.StatusUnprocessableEntity,
			wantCode:   "not_ntp_synced",
		},
		{
			name: "unverified after another failure",
			info: model.StreamBuffer{
				State: "failed", SyncConfidence: model.SyncUnverified, IngestFailure: stream.ErrSourceFailed,
			},
			wantStatus: http.StatusOK,
		},
		{
			name: "unverified while connecting",
			info: model.StreamBuffer{
				State: "connecting", SyncConfidence: model.SyncUnverified,
			},
			wantStatus: http.StatusOK,
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(recorder)
			c.Params = gin.Params{{Key: "stream-id", Value: "stream-1"}}
			c.Request = httptest.NewRequest(http.MethodGet, "/v1/streams/stream-1", nil)
			StreamHandler{Buffers: streamBufferStub{info: tc.info}}.Get(c)
			if recorder.Code != tc.wantStatus {
				t.Fatalf("got status %d, want %d: %s", recorder.Code, tc.wantStatus, recorder.Body)
			}
			if tc.wantCode != "" && errorCode(t, recorder) != tc.wantCode {
				t.Fatalf("got response %s, want error code %q", recorder.Body, tc.wantCode)
			}
		})
	}
}
