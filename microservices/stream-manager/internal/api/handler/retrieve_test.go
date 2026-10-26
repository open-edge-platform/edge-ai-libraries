// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/api/common"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/retrieve"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

const testRecordingID = "1f0d3c1e-2b9a-4e43-9f0e-6a3c5b1d2e7f"

var retrieveStart = time.Date(2026, 6, 15, 14, 12, 0, 0, time.UTC)

// fakeRetriever serves one file for every request, or fails with err.
type fakeRetriever struct {
	dir      string
	err      error
	openErr  error
	exact    bool
	duration time.Duration
	calls    int
	noExpiry bool
}

func (f *fakeRetriever) media(kind, contentType, name string, start time.Time) (retrieve.Media, error) {
	f.calls++
	if f.err != nil {
		return retrieve.Media{}, f.err
	}
	path := filepath.Join(f.dir, name)
	if err := os.WriteFile(path, []byte(kind+" bytes"), 0o600); err != nil {
		return retrieve.Media{}, err
	}
	var expiry *time.Time
	if !f.noExpiry {
		expiration := time.Now().Add(10 * time.Minute)
		expiry = &expiration
	}
	return retrieve.Media{
		Result: model.MediaResult{
			RecordingID: testRecordingID, SensorID: "cam-1", MediaType: kind, ContentType: contentType,
			RequestedStartTS: start, StartTS: retrieveStart.Add(1500 * time.Millisecond), ExpiryTS: expiry,
		},
		Name: name, Path: path, ExactMatch: f.exact,
	}, nil
}

func (f *fakeRetriever) Frame(_ context.Context, _ string, ts time.Time, format, _ string) (retrieve.Media, error) {
	return f.media("frame", "image/"+format, "frame-1500000000."+format, ts)
}

func (f *fakeRetriever) Clip(_ context.Context, _ string, start time.Time, duration time.Duration, _ string) (retrieve.Media, error) {
	f.duration = duration
	return f.media("clip", "video/mp4", "clip-1500000000-3000000000.mp4", start)
}

func (f *fakeRetriever) OpenMedia(_ context.Context, _, name string) (*os.File, retrieve.MediaFile, error) {
	if f.err != nil {
		return nil, retrieve.MediaFile{}, f.err
	}
	if f.openErr != nil {
		return nil, retrieve.MediaFile{}, f.openErr
	}
	file, err := os.Open(filepath.Join(f.dir, filepath.Base(name)))
	if err != nil {
		return nil, retrieve.MediaFile{}, retrieve.ErrMediaNotFound
	}
	contentType := map[string]string{".jpeg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4"}[filepath.Ext(name)]
	var expiry *time.Time
	if !f.noExpiry {
		expiration := time.Now().Add(10 * time.Minute)
		expiry = &expiration
	}
	return file, retrieve.MediaFile{ContentType: contentType, ExpiryTS: expiry}, nil
}

func retrieveRouter(f *fakeRetriever) *gin.Engine {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	h := RetrieveHandler{Retrievals: f}
	requireID := common.RequireID("recording-id", "recording_not_found", "recording not found")
	group := router.Group("/v1/retrieve/:recording-id", requireID)
	group.GET("/frame", h.Frame)
	group.GET("/clip", h.Clip)
	router.GET("/v1/media/:recording-id/:file", requireID, h.Media)
	return router
}

func get(router http.Handler, target, accept string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodGet, target, nil)
	if accept != "" {
		req.Header.Set("Accept", accept)
	}
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	return rec
}

func errorCode(t *testing.T, rec *httptest.ResponseRecorder) string {
	t.Helper()
	var body common.StreamManError
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("error body %q: %v", rec.Body.String(), err)
	}
	if body.Status != rec.Code {
		t.Fatalf("body status %d differs from HTTP status %d", body.Status, rec.Code)
	}
	return body.ErrorCode
}

func TestRetrieveNegotiation(t *testing.T) {
	frame := "/v1/retrieve/" + testRecordingID + "/frame?timestamp=2026-06-15T14:12:01.5Z"
	clip := "/v1/retrieve/" + testRecordingID + "/clip?start_ts=2026-06-15T14:12:01.5Z&duration=1.5"
	cases := []struct {
		name, target, accept string
		status               int
		contentType          string
	}{
		{"frame default JSON", frame, "", http.StatusOK, "application/json"},
		{"frame any", frame, "*/*", http.StatusOK, "application/json"},
		{"frame JSON", frame, "application/json", http.StatusOK, "application/json"},
		{"frame jpeg", frame, "image/jpeg", http.StatusOK, "image/jpeg"},
		{"frame png from Accept", frame, "image/png", http.StatusOK, "image/png"},
		{"frame JSON png link", frame + "&format=png", "application/json", http.StatusOK, "application/json"},
		{"frame weighted png", frame, "application/json;q=0.2, image/png;q=0.9", http.StatusOK, "image/png"},
		{"frame zero image", frame, "image/jpeg;q=0, application/json;q=0.5", http.StatusOK, "application/json"},
		{"frame exclusion overrides wildcard", frame, "image/*;q=0, */*;q=1", http.StatusOK, "application/json"},
		{"frame all excluded", frame, "*/*;q=0", http.StatusNotAcceptable, ""},
		{"frame invalid quality", frame, "image/png;q=NaN", http.StatusNotAcceptable, ""},
		{"frame image wildcard", frame + "&format=png", "image/*", http.StatusOK, "image/png"},
		{"frame preferred image", frame, "image/jpeg, application/json;q=0.5", http.StatusOK, "image/jpeg"},
		{"frame wrong image type", frame + "&format=png", "image/jpeg", http.StatusNotAcceptable, ""},
		{"frame video", frame, "video/mp4", http.StatusNotAcceptable, ""},
		{"clip default JSON", clip, "", http.StatusOK, "application/json"},
		{"clip mp4", clip, "video/mp4", http.StatusOK, "video/mp4"},
		{"clip weighted mp4", clip, "application/json;q=0.5, video/mp4;q=1", http.StatusOK, "video/mp4"},
		{"clip exact exclusion", clip, "video/mp4;q=0, video/*;q=1", http.StatusNotAcceptable, ""},
		{"clip zero JSON", clip, "application/json;q=0, */*;q=0.5", http.StatusOK, "video/mp4"},
		{"clip image", clip, "image/jpeg", http.StatusNotAcceptable, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := &fakeRetriever{dir: t.TempDir()}
			rec := get(retrieveRouter(f), tc.target, tc.accept)
			if rec.Code != tc.status {
				t.Fatalf("status %d, want %d: %s", rec.Code, tc.status, rec.Body)
			}
			if rec.Header().Get("Vary") != "Accept" {
				t.Fatalf("missing Vary: Accept: %v", rec.Header())
			}
			if tc.status == http.StatusNotAcceptable {
				if code := errorCode(t, rec); code != "not_acceptable" || f.calls != 0 {
					t.Fatalf("code %q after %d extractions; want not_acceptable before extracting", code, f.calls)
				}
				return
			}
			if got := rec.Header().Get("Content-Type"); !strings.HasPrefix(got, tc.contentType) {
				t.Fatalf("Content-Type %q, want %q", got, tc.contentType)
			}
			if rec.Header().Get("X-Frame-Timestamp") != "2026-06-15T14:12:01.5Z" || rec.Header().Get("X-Exact-Match") != "false" {
				t.Fatalf("unexpected retrieve headers %v", rec.Header())
			}
			if tc.contentType == "application/json" {
				var fields map[string]json.RawMessage
				if err := json.Unmarshal(rec.Body.Bytes(), &fields); err != nil {
					t.Fatal(err)
				}
				for _, name := range []string{"media_type", "content_type"} {
					if _, exists := fields[name]; exists {
						t.Fatalf("JSON reply contains removed field %q: %s", name, rec.Body)
					}
				}
				var result model.MediaResult
				if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
					t.Fatal(err)
				}
				if rec.Header().Get("Cache-Control") != "no-store" || !strings.HasPrefix(result.URL, "/v1/media/"+testRecordingID+"/") {
					t.Fatalf("unexpected JSON reply %v %+v", rec.Header(), result)
				}
				if tc.name == "frame JSON png link" && !strings.HasSuffix(result.URL, ".png") {
					t.Fatalf("JSON link did not select PNG: %+v", result)
				}
				return
			}

			if !strings.HasPrefix(rec.Header().Get("Cache-Control"), "private, max-age=") || rec.Body.Len() == 0 {
				t.Fatalf("unexpected binary reply %v", rec.Header())
			}
		})
	}
}

func TestMediaRouteWithoutExpiry(t *testing.T) {
	f := &fakeRetriever{dir: t.TempDir(), noExpiry: true}
	router := retrieveRouter(f)
	response := get(router, "/v1/retrieve/"+testRecordingID+"/frame?timestamp=2026-06-15T14:12:01.5Z", "application/json")

	var result model.MediaResult
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.ExpiryTS != nil {
		t.Fatalf("expiry %v, want null", result.ExpiryTS)
	}

	media := get(router, result.URL, "")
	if media.Code != http.StatusOK || media.Header().Get("Cache-Control") != "private, no-cache" ||
		media.Header().Get("Expires") != "" {
		t.Fatalf("unexpected no-expiry media reply %d %v", media.Code, media.Header())
	}
}

func TestRetrieveRemovedURLRoutes(t *testing.T) {
	f := &fakeRetriever{dir: t.TempDir()}
	router := retrieveRouter(f)
	for _, endpoint := range []string{"frame", "clip"} {
		rec := get(router, "/v1/retrieve/"+testRecordingID+"/"+endpoint+"/url", "application/json")
		if rec.Code != http.StatusNotFound || f.calls != 0 {
			t.Fatalf("removed URL route returned %d after %d extractions", rec.Code, f.calls)
		}
	}
}

func TestRetrieveParameters(t *testing.T) {
	base := "/v1/retrieve/" + testRecordingID
	cases := []struct {
		name, target, code string
	}{
		{"missing timestamp", base + "/frame", "invalid_timestamp"},
		{"offset timestamp", base + "/frame?timestamp=2026-06-15T14:12:01%2B01:00", "invalid_timestamp"},
		{"bad format", base + "/frame?timestamp=2026-06-15T14:12:01Z&format=gif", "invalid_request"},
		{"bad match", base + "/frame?timestamp=2026-06-15T14:12:01Z&match=closest", "invalid_request"},
		{"missing start", base + "/clip?duration=1", "invalid_timestamp"},
		{"missing duration", base + "/clip?start_ts=2026-06-15T14:12:01Z", "invalid_request"},
		{"zero duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=0", "invalid_request"},
		{"negative duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=-1", "invalid_request"},
		{"NaN duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=NaN", "invalid_request"},
		{"infinite duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=Inf", "invalid_request"},
		{"huge duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1e300", "invalid_request"},
		{"sub-nanosecond duration", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1e-12", "invalid_request"},
		{"bad clip format", base + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1&format=mkv", "invalid_request"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := &fakeRetriever{dir: t.TempDir()}
			rec := get(retrieveRouter(f), tc.target, "")
			if rec.Code != http.StatusBadRequest || errorCode(t, rec) != tc.code || f.calls != 0 {
				t.Fatalf("got %d %s after %d extractions, want 400 %s", rec.Code, rec.Body, f.calls, tc.code)
			}
		})
	}

	f := &fakeRetriever{dir: t.TempDir()}
	if rec := get(retrieveRouter(f), base+"/clip?start_ts=2026-06-15T14:12:01Z&duration=2.25", ""); rec.Code != http.StatusOK || f.duration != 2250*time.Millisecond {
		t.Fatalf("duration parsed as %v (status %d)", f.duration, rec.Code)
	}
}

func TestRetrieveErrors(t *testing.T) {
	cases := []struct {
		err    error
		status int
		code   string
	}{
		{retrieve.ErrNotFound, http.StatusNotFound, "recording_not_found"},
		{retrieve.ErrNotCovered, http.StatusNotFound, "frame_not_found"},
		{retrieve.ErrFrameNotFound, http.StatusNotFound, "frame_not_found"},
		{fmt.Errorf("%w: no keyframe", retrieve.ErrBeyondSearchLimit), http.StatusNotFound, "frame_not_found"},
		{retrieve.ErrMediaNotFound, http.StatusNotFound, "frame_not_found"},
		{retrieve.ErrNotReady, http.StatusConflict, "record_not_ready"},
		{retrieve.ErrBusy, http.StatusTooManyRequests, "capacity_exhausted"},
		{retrieve.ErrInvalidRequest, http.StatusBadRequest, "invalid_request"},
		{storage.ErrStorageFull, http.StatusInsufficientStorage, "storage_full"},
		{fmt.Errorf("%w: FFmpeg: exit status 1: /secret/path", retrieve.ErrExtraction), http.StatusServiceUnavailable, "storage_unavailable"},
		{fmt.Errorf("disk on fire"), http.StatusInternalServerError, "internal_error"},
	}
	targets := []string{
		"/v1/retrieve/" + testRecordingID + "/frame?timestamp=2026-06-15T14:12:01Z",
		"/v1/retrieve/" + testRecordingID + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1",
		"/v1/retrieve/" + testRecordingID + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1",
		"/v1/media/" + testRecordingID + "/frame-1.jpeg",
		"/v1/media/" + testRecordingID + "/clip-1-2.mp4",
	}
	for _, tc := range cases {
		for _, target := range targets {
			t.Run(tc.code+" "+strings.Split(target, "?")[0], func(t *testing.T) {
				rec := get(retrieveRouter(&fakeRetriever{dir: t.TempDir(), err: tc.err}), target, "")
				code := tc.code
				if code == "frame_not_found" && strings.Contains(target, "/clip") {
					code = "clip_not_found"
				}
				if rec.Code != tc.status || errorCode(t, rec) != code {
					t.Fatalf("got %d %s, want %d %s", rec.Code, rec.Body, tc.status, code)
				}
				if tc.err == retrieve.ErrNotCovered {
					detail := "the requested time is not covered by the record"
					if code == "clip_not_found" {
						detail = "the requested interval is not covered by the record"
					}
					if !strings.Contains(rec.Body.String(), detail) {
						t.Fatalf("got %s, want detail %q", rec.Body, detail)
					}
				}
				if tc.err == retrieve.ErrFrameNotFound && code == "clip_not_found" &&
					strings.Contains(rec.Body.String(), "frame") {
					t.Fatalf("clip error mentions a frame: %s", rec.Body)
				}
				if errors.Is(tc.err, retrieve.ErrBeyondSearchLimit) {
					detail := "no decodable frame is available for the requested time"
					if code == "clip_not_found" {
						detail = "no clip is available for the requested interval"
					}
					if !strings.Contains(rec.Body.String(), detail) {
						t.Fatalf("got %s, want detail %q", rec.Body, detail)
					}
					for _, internal := range []string{"5 minutes", "search limit", "keyframe"} {
						if strings.Contains(rec.Body.String(), internal) {
							t.Fatalf("error body leaks search details: %s", rec.Body)
						}
					}
				}
				if strings.Contains(rec.Body.String(), "secret") || strings.Contains(rec.Body.String(), "FFmpeg") {
					t.Fatalf("error body leaks internals: %s", rec.Body)
				}
			})
		}
	}
}

func TestSearchLimitLoggedInternally(t *testing.T) {
	var output bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&output, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })

	target := "/v1/retrieve/" + testRecordingID + "/frame?timestamp=2026-06-15T14:12:01Z"
	response := get(retrieveRouter(&fakeRetriever{
		dir: t.TempDir(), err: fmt.Errorf("%w: no keyframe", retrieve.ErrBeyondSearchLimit),
	}), target, "")
	if response.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", response.Code)
	}
	var entry struct {
		Message     string        `json:"msg"`
		RecordingID string        `json:"recording_id"`
		SearchLimit time.Duration `json:"search_limit"`
		Error       string        `json:"error"`
	}
	if err := json.Unmarshal(output.Bytes(), &entry); err != nil {
		t.Fatal(err)
	}
	if entry.Message != "retrieve search limit reached" || entry.RecordingID != testRecordingID ||
		entry.SearchLimit != retrieve.SearchLimit || !strings.Contains(entry.Error, "no keyframe") {
		t.Fatalf("unexpected search-limit log: %s", output.String())
	}
}

func TestClipBinaryMediaError(t *testing.T) {
	f := &fakeRetriever{dir: t.TempDir(), openErr: retrieve.ErrMediaNotFound}
	target := "/v1/retrieve/" + testRecordingID + "/clip?start_ts=2026-06-15T14:12:01Z&duration=1"
	rec := get(retrieveRouter(f), target, "video/mp4")
	if rec.Code != http.StatusNotFound || errorCode(t, rec) != "clip_not_found" {
		t.Fatalf("got %d %s, want 404 clip_not_found", rec.Code, rec.Body)
	}
}

func TestMediaRoute(t *testing.T) {
	f := &fakeRetriever{dir: t.TempDir(), exact: true}
	router := retrieveRouter(f)
	rec := get(router, "/v1/retrieve/"+testRecordingID+"/clip?start_ts=2026-06-15T14:12:01.5Z&duration=1.5", "")
	if rec.Header().Get("X-Exact-Match") != "true" {
		t.Fatalf("X-Exact-Match %q, want true", rec.Header().Get("X-Exact-Match"))
	}
	var result model.MediaResult
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}

	media := get(router, result.URL, "")
	maxAge, err := strconv.Atoi(strings.TrimPrefix(media.Header().Get("Cache-Control"), "private, max-age="))
	if media.Code != http.StatusOK || media.Header().Get("Content-Type") != "video/mp4" || media.Body.String() != "clip bytes" ||
		err != nil || maxAge <= 0 || maxAge > 600 || media.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatalf("unexpected media reply %d %v %q", media.Code, media.Header(), media.Body)
	}

	ranged := httptest.NewRequest(http.MethodGet, result.URL, nil)
	ranged.Header.Set("Range", "bytes=0-3")
	partial := httptest.NewRecorder()
	router.ServeHTTP(partial, ranged)
	if partial.Code != http.StatusPartialContent || partial.Body.String() != "clip" {
		t.Fatalf("range request: %d %q", partial.Code, partial.Body)
	}

	for _, target := range []string{
		"/v1/media/" + testRecordingID + "/frame-9.jpeg",
		"/v1/media/not%20an%20id/frame-1.jpeg",
	} {
		rec := get(router, target, "")
		if rec.Code != http.StatusNotFound {
			t.Fatalf("%s: status %d, want 404", target, rec.Code)
		}
	}
}
