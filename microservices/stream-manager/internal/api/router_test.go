// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/record"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/retrieve"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

func TestStreamRoutes(t *testing.T) {
	gin.SetMode(gin.TestMode)
	root, err := os.MkdirTemp("/dev/shm", "stream-manager-api-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(root); err != nil {
			t.Error(err)
		}
	})
	service, err := stream.NewService(config.Config{BufferLength: 45 * time.Second, BufferDir: root})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := service.Close(); err != nil {
			t.Error(err)
		}
	})
	storageDir := filepath.Join(root, "recordings")
	metadata, err := storage.OpenMetadataStore(storageDir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := metadata.Close(); err != nil {
			t.Error(err)
		}
	})
	media, err := storage.OpenMediaStore(storageDir, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := media.Close(); err != nil {
			t.Error(err)
		}
	})
	recordings, err := record.NewService(service, metadata, media, 64, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := recordings.Close(); err != nil {
			t.Error(err)
		}
	})
	retrievals, err := retrieve.NewService(metadata, media, 15*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	router := api.NewRouter(service, recordings, retrievals, "v0.0.1-test", "NA", "NA")
	request := func(method, path, body string, status int) *httptest.ResponseRecorder {
		t.Helper()
		recorder := httptest.NewRecorder()
		router.ServeHTTP(recorder, httptest.NewRequest(method, path, strings.NewReader(body)))
		if recorder.Code != status {
			t.Fatalf("%s %s: got %d, want %d: %s", method, path, recorder.Code, status, recorder.Body)
		}
		return recorder
	}
	created := request("POST", "/v1/streams", `{"sensor_id":"camera","source_uri":"rtsp://127.0.0.1:1/unavailable?token=secret"}`, 201)
	var result struct {
		StreamID string `json:"stream_id"`
		Buffer   struct {
			Capacity int `json:"capacity"`
		} `json:"buffer"`
	}
	if err := json.Unmarshal(created.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	path := "/v1/streams/" + result.StreamID
	if result.StreamID == "" || created.Header().Get("Location") != path || result.Buffer.Capacity != 45 ||
		strings.Contains(created.Body.String(), "secret") ||
		strings.Contains(created.Body.String(), "127.0.0.1") {
		t.Fatalf("unexpected creation response: %s", created.Body)
	}
	request("POST", "/v1/streams", `{"sensor_id":"camera","source_uri":"rtsp://127.0.0.1:1/unavailable?token=secret"}`, 409)
	substream := request("POST", "/v1/streams", `{"sensor_id":"camera","source_uri":"rtsp://127.0.0.1:1/substream"}`, 201)
	request("DELETE", substream.Header().Get("Location"), "", 200)
	sized := request("POST", "/v1/streams", `{"sensor_id":"sized","source_uri":"rtsp://127.0.0.1:1/unavailable","buffer_length":60}`, 201)
	var sizedResult struct {
		StreamID string `json:"stream_id"`
		Buffer   struct {
			Capacity int `json:"capacity"`
		} `json:"buffer"`
	}
	if err := json.Unmarshal(sized.Body.Bytes(), &sizedResult); err != nil || sizedResult.Buffer.Capacity != 60 {
		t.Fatalf("buffer_length was not applied: %s %v", sized.Body, err)
	}
	request("DELETE", "/v1/streams/"+sizedResult.StreamID, "", 200)
	request("GET", path, "", 200)
	request("GET", "/v1/streams?limit=0&cursor=ignored", "", 200)
	resized := request("PUT", path+"/buffer", `{"buffer_length":60}`, 200)
	var resizedResult struct {
		Buffer struct {
			Capacity int `json:"capacity"`
		} `json:"buffer"`
	}
	if err := json.Unmarshal(resized.Body.Bytes(), &resizedResult); err != nil || resizedResult.Buffer.Capacity != 60 {
		t.Fatalf("buffer was not resized: %s %v", resized.Body, err)
	}
	for _, tc := range []struct {
		method, path, body, code string
		status                   int
	}{
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"rtsp://host/live","source_kind":"uri_source"}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"rtsp://host/live","buffer_length":4}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"rtsp://host/live","buffer_length":301}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"rtsp://host/live","buffer_length":"30"}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"rtsp://host/live","buffer_length":30.5}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"x","source_uri":"http://host/live"}`, "unsupported_media", 415},
		{"POST", "/v1/streams", `{}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{} {}`, "invalid_request", 400},
		{"POST", "/v1/streams", `{"sensor_id":"` + strings.Repeat("a", 1<<20) + `"}`, "invalid_request", 400},
		{"GET", "/v1/streams/.bad", "", "stream_not_found", 404},
		{"GET", "/v1/streams/unknown", "", "stream_not_found", 404},
		{"PUT", "/v1/streams/.bad/buffer", "invalid JSON", "stream_not_found", 404},
		{"PUT", path + "/buffer", `{}`, "invalid_request", 400},
		{"PUT", path + "/buffer", `{"buffer_length":4}`, "invalid_request", 400},
		{"PUT", path + "/buffer", `{"buffer_length":301}`, "invalid_request", 400},
		{"PUT", "/v1/streams/unknown/buffer", `{"buffer_length":60}`, "stream_not_found", 404},
		{"POST", "/v1/records/start", `{"start_ts":"2026-01-01T00:00:00Z"}`, "invalid_selector", 400},
		{"POST", "/v1/records/start", `{"stream_id":".bad","start_ts":"2026-01-01T00:00:00Z"}`, "invalid_selector", 400},
		{"POST", "/v1/records/start", `{"stream_ids":["a"],"start_ts":"2026-01-01T00:00:00Z"}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","sensor_ids":["a"],"start_ts":"2026-01-01T00:00:00Z"}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"invalid"}`, "invalid_timestamp", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","duration":0}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","duration":-1}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","duration":1e300}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","duration":1e-12}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","pre_event_duration":-1}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","pre_event_duration":301}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"a","start_ts":"2026-01-01T00:00:00Z","pre_event_duration":1e-12}`, "invalid_request", 400},
		{"POST", "/v1/records/start", `{"stream_id":"missing","start_ts":"2026-01-01T00:00:00Z"}`, "stream_not_found", 404},
		{"POST", "/v1/records/start", `{"stream_id":"` + result.StreamID + `","start_ts":"2026-01-01T00:00:00Z"}`, "history_unavailable", 409},
		{"POST", "/v1/records/stop", `{}`, "invalid_request", 400},
		{"GET", "/v1/records?limit=0", "", "invalid_request", 400},
		{"GET", "/v1/records/.bad", "", "recording_not_found", 404},
	} {
		response := request(tc.method, tc.path, tc.body, tc.status)
		var failure struct {
			Status int    `json:"status"`
			Code   string `json:"error_code"`
			Detail string `json:"error_detail"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &failure); err != nil ||
			failure.Status != tc.status || failure.Code != tc.code || failure.Detail == "" {
			t.Fatalf("invalid error envelope: %s %v", response.Body, err)
		}
	}
	request("DELETE", path, "", 200)
	request("GET", path, "", 404)
	request("DELETE", path, "", 404)
	const retryBody = `{"sensor_id":"retry-camera","source_uri":"rtsp://127.0.0.1:1/unreachable"}`
	firstAttempt := request("POST", "/v1/streams", retryBody, 201)
	var firstStream struct {
		StreamID string `json:"stream_id"`
	}
	if err := json.Unmarshal(firstAttempt.Body.Bytes(), &firstStream); err != nil || firstStream.StreamID == "" {
		t.Fatalf("invalid initial attach response: %s %v", firstAttempt.Body, err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for {
		info, err := service.GetStream(t.Context(), firstStream.StreamID)
		if err != nil {
			t.Fatal(err)
		}
		if info.State == "failed" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("unreachable source did not fail, state %q", info.State)
		}
		time.Sleep(25 * time.Millisecond)
	}
	retry := request("POST", "/v1/streams", retryBody, 201)
	var retryStream struct {
		StreamID string `json:"stream_id"`
	}
	if err := json.Unmarshal(retry.Body.Bytes(), &retryStream); err != nil ||
		retryStream.StreamID == "" || retryStream.StreamID == firstStream.StreamID {
		t.Fatalf("retry did not create a new stream: %s %v", retry.Body, err)
	}
	request("DELETE", "/v1/streams/"+firstStream.StreamID, "", 200)
	request("DELETE", "/v1/streams/"+retryStream.StreamID, "", 200)
	empty := request("GET", "/v1/streams", "", 200)
	if empty.Body.String() != `{"items":[],"next_cursor":null}` {
		t.Fatalf("empty stream list: %s", empty.Body)
	}
	if response := request("GET", "/health", "", http.StatusNotFound); response.Body.String() != "404 page not found" {
		t.Fatal("unknown route behavior changed")
	}
	status := request("GET", "/v1/status", "", 200)
	var statusResult struct {
		Status      string `json:"status"`
		Version     string `json:"version"`
		BuildNumber string `json:"build_number"`
		BuildDate   string `json:"build_date"`
	}
	if err := json.Unmarshal(status.Body.Bytes(), &statusResult); err != nil ||
		statusResult.Status != "ok" || statusResult.Version != "v0.0.1-test" ||
		statusResult.BuildNumber != "NA" || statusResult.BuildDate != "NA" {
		t.Fatalf("unexpected status response: %s %v", status.Body, err)
	}
}
