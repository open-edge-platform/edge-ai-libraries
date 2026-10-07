// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/logging"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage/storagetest"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/stream"
)

// Fixture rec-001 covers 2026-09-21T00:00:00Z .. 00:00:09.5Z at 500 ms.
var (
	fixtureBase = time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC)
	fixtureRoot = filepath.Join("..", "..", "testdata", "recordings")

	jpegMagic = []byte{0xFF, 0xD8, 0xFF}
	pngMagic  = []byte{0x89, 'P', 'N', 'G'}
	mp4Magic  = []byte("ftyp")
)

// stubExtractor emits bytes that carry the real container signatures so the
// HTTP layer can be tested for content negotiation and headers without
// invoking ffmpeg.
type stubExtractor struct{ calls int }

func (s *stubExtractor) ExtractFrame(_ context.Context, _ io.Reader, mediaTime float64, format string) ([]byte, error) {
	s.calls++
	magic := jpegMagic
	if format == "png" {
		magic = pngMagic
	}
	return append(append([]byte{}, magic...), []byte(fmt.Sprintf("@%.3f", mediaTime))...), nil
}

func (s *stubExtractor) ExtractClip(_ context.Context, _ io.Reader, start, end float64, _ string) ([]byte, error) {
	s.calls++
	out := []byte{0, 0, 0, 0x18}
	out = append(out, mp4Magic...)
	return append(out, []byte(fmt.Sprintf("isom@%.3f-%.3f", start, end))...), nil
}

type unitEnv struct {
	router    http.Handler
	media     *storagetest.MemoryMediaStore
	metadata  *storagetest.MemoryMetadataStore
	extractor *stubExtractor
	logs      *bytes.Buffer
}

func loadAPIFixture(t *testing.T) (model.Recording, []byte) {
	t.Helper()
	dir := filepath.Join(fixtureRoot, "rec-001")
	metadataJSON, err := os.ReadFile(filepath.Join(dir, "metadata.json"))
	if err != nil {
		t.Fatal(err)
	}
	var recording model.Recording
	if err := json.Unmarshal(metadataJSON, &recording); err != nil {
		t.Fatal(err)
	}
	sidecarJSON, err := os.ReadFile(filepath.Join(dir, "sidecar.json"))
	if err != nil {
		t.Fatal(err)
	}
	return recording, sidecarJSON
}

// newUnitEnv stages the committed rec-001 fixture (metadata + sidecar) into
// in-memory stores with a placeholder recording body, and wires the router
// with a stub extractor.
func newUnitEnv(t *testing.T) unitEnv {
	t.Helper()
	recording, sidecarJSON := loadAPIFixture(t)
	media := storagetest.NewMemoryMediaStore()
	metadata := storagetest.NewMemoryMetadataStore()
	ctx := context.Background()
	if _, err := media.PutRecording(ctx, recording.RecordingID, bytes.NewReader([]byte("not-a-real-mp4")), "video/mp4"); err != nil {
		t.Fatal(err)
	}
	if _, err := media.PutSidecar(ctx, recording.RecordingID, bytes.NewReader(sidecarJSON)); err != nil {
		t.Fatal(err)
	}
	if err := metadata.Save(ctx, recording); err != nil {
		t.Fatal(err)
	}

	extractor := &stubExtractor{}
	service := replay.NewRetrievalService(metadata, media, replay.Options{Extractor: extractor})
	logs := &bytes.Buffer{}
	logger := slog.New(slog.NewJSONHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	return unitEnv{router: NewRouter(service, media, testVersion, logger, nil, nil, nil), media: media, metadata: metadata, extractor: extractor, logs: logs}
}

func (e unitEnv) do(t *testing.T, path, accept string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	if accept != "" {
		req.Header.Set("Accept", accept)
	}
	rr := httptest.NewRecorder()
	e.router.ServeHTTP(rr, req)
	return rr
}

func framePath(ts time.Time, extra string) string {
	return "/v1/replays/rec-001/frame?timestamp=" + url.QueryEscape(ts.Format(time.RFC3339Nano)) + extra
}

func clipPath(start time.Time, extra string) string {
	return "/v1/replays/rec-001/clip?timestamp_start=" + url.QueryEscape(start.Format(time.RFC3339Nano)) + extra
}

func decodeError(t *testing.T, rr *httptest.ResponseRecorder, wantStatus int, wantCode string) {
	t.Helper()
	if rr.Code != wantStatus {
		t.Fatalf("status = %d, want %d (body %s)", rr.Code, wantStatus, rr.Body.String())
	}
	var errResp model.ErrorResponse
	if err := json.NewDecoder(rr.Body).Decode(&errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if errResp.ErrorCode != wantCode || errResp.Status != wantStatus {
		t.Fatalf("error = %+v, want code %q status %d", errResp, wantCode, wantStatus)
	}
}

func decodeResult(t *testing.T, rr *httptest.ResponseRecorder) model.MediaResult {
	t.Helper()
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, body %s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("Content-Type"); got != "application/json; charset=utf-8" {
		t.Fatalf("content-type = %q", got)
	}
	if got := rr.Header().Get("Cache-Control"); got != "private, no-store" {
		t.Fatalf("cache-control = %q", got)
	}
	var result model.MediaResult
	if err := json.NewDecoder(rr.Body).Decode(&result); err != nil {
		t.Fatalf("decode result: %v", err)
	}
	return result
}

const testVersion = "1.2.3-test"

func decodeJSON(t *testing.T, rr *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	return body
}

func TestHealth(t *testing.T) {
	env := newUnitEnv(t)
	rr := env.do(t, "/v1/health", "")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	if body := decodeJSON(t, rr); body["status"] != "ok" {
		t.Fatalf("body = %v", body)
	}
}

func TestHealthzRemoved(t *testing.T) {
	env := newUnitEnv(t)
	if rr := env.do(t, "/healthz", ""); rr.Code != http.StatusNotFound {
		t.Fatalf("/healthz status = %d, want 404", rr.Code)
	}
}

// lastLog returns the most recent access-log entry written by the router.
func (e unitEnv) lastLog(t *testing.T) map[string]any {
	t.Helper()
	lines := strings.Split(strings.TrimSpace(e.logs.String()), "\n")
	var entry map[string]any
	if err := json.Unmarshal([]byte(lines[len(lines)-1]), &entry); err != nil {
		t.Fatalf("decode log line %q: %v", lines[len(lines)-1], err)
	}
	return entry
}

func TestRequestIDGeneratedAndLogged(t *testing.T) {
	env := newUnitEnv(t)
	rr := env.do(t, "/v1/health", "")

	reqID := rr.Header().Get(logging.RequestIDHeader)
	if reqID == "" {
		t.Fatal("response is missing X-Request-ID")
	}
	entry := env.lastLog(t)
	if entry["msg"] != "request" || entry["request_id"] != reqID || entry["path"] != "/v1/health" || entry["status"] != float64(200) {
		t.Fatalf("log entry = %v", entry)
	}
	if entry["level"] != "INFO" {
		t.Fatalf("level = %v, want INFO for 2xx", entry["level"])
	}
}

func TestRequestIDFromClientIsHonoured(t *testing.T) {
	env := newUnitEnv(t)
	req := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	req.Header.Set(logging.RequestIDHeader, "upstream-abc")
	rr := httptest.NewRecorder()
	env.router.ServeHTTP(rr, req)

	if got := rr.Header().Get(logging.RequestIDHeader); got != "upstream-abc" {
		t.Fatalf("X-Request-ID = %q", got)
	}
	if entry := env.lastLog(t); entry["request_id"] != "upstream-abc" {
		t.Fatalf("log request_id = %v", entry["request_id"])
	}
}

func TestServiceErrorIsLoggedButNotLeaked(t *testing.T) {
	env := newUnitEnv(t)
	rr := env.do(t, "/v1/replays/missing-rec/frame/url?timestamp="+url.QueryEscape(fixtureBase.Format(time.RFC3339Nano)), "")
	decodeError(t, rr, http.StatusNotFound, "recording_not_found")

	entry := env.lastLog(t)
	errText, _ := entry["error"].(string)
	if !strings.Contains(errText, "missing-rec") {
		t.Fatalf("access log should carry the underlying error, got %v", entry)
	}
	if entry["level"] != "INFO" {
		t.Fatalf("4xx should log at INFO, got %v", entry["level"])
	}
}

func TestVersion(t *testing.T) {
	env := newUnitEnv(t)
	rr := env.do(t, "/v1/version", "")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	body := decodeJSON(t, rr)
	if body["version"] != testVersion || len(body) != 1 {
		t.Fatalf("body = %v, want {version: %q}", body, testVersion)
	}
}

func TestFrameBinaryExactMatch(t *testing.T) {
	env := newUnitEnv(t)
	ts := fixtureBase.Add(3 * time.Second)

	rr := env.do(t, framePath(ts, "&format=jpeg&match=exact"), "image/jpeg")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d body %s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("Content-Type"); got != "image/jpeg" {
		t.Fatalf("content-type = %q", got)
	}
	if got := rr.Header().Get("Cache-Control"); got != "private, no-store" {
		t.Fatalf("cache-control = %q", got)
	}
	if got := rr.Header().Get("X-Frame-Timestamp"); got != ts.Format(time.RFC3339Nano) {
		t.Fatalf("x-frame-timestamp = %q", got)
	}
	if got := rr.Header().Get("X-Exact-Match"); got != "true" {
		t.Fatalf("x-exact-match = %q", got)
	}
	if body := rr.Body.Bytes(); !bytes.HasPrefix(body, jpegMagic) || !bytes.HasSuffix(body, []byte("@3.000")) {
		t.Fatalf("body = %q", body)
	}
}

func TestFrameBinaryNearestAndPNG(t *testing.T) {
	env := newUnitEnv(t)
	requested := fixtureBase.Add(3200 * time.Millisecond)
	resolved := fixtureBase.Add(3 * time.Second)

	rr := env.do(t, framePath(requested, "&format=png"), "image/*")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d body %s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("Content-Type"); got != "image/png" {
		t.Fatalf("content-type = %q", got)
	}
	if got := rr.Header().Get("X-Frame-Timestamp"); got != resolved.Format(time.RFC3339Nano) {
		t.Fatalf("x-frame-timestamp = %q", got)
	}
	if got := rr.Header().Get("X-Exact-Match"); got != "false" {
		t.Fatalf("x-exact-match = %q", got)
	}
	if !bytes.HasPrefix(rr.Body.Bytes(), pngMagic) {
		t.Fatalf("body is not PNG: %q", rr.Body.Bytes())
	}
}

func TestFrameJSONWhenAcceptIsJSONOrAbsent(t *testing.T) {
	env := newUnitEnv(t)
	ts := fixtureBase.Add(3 * time.Second)

	for _, accept := range []string{"", "application/json", "*/*"} {
		result := decodeResult(t, env.do(t, framePath(ts, ""), accept))
		if result.MediaType != "frame" || result.ContentType != "image/jpeg" || !result.ExactMatch {
			t.Fatalf("accept %q: result %+v", accept, result)
		}
		if result.RecordingID != "rec-001" || result.SensorID != "sensor-01" {
			t.Fatalf("accept %q: identity %+v", accept, result)
		}
		if !result.StartTS.Equal(ts) || !result.RequestedStartTS.Equal(ts) || result.EndTS != nil {
			t.Fatalf("accept %q: timestamps %+v", accept, result)
		}
		if !strings.Contains(result.URL, "derived/rec-001/frames/") || result.ExpiryTS.Before(time.Now()) {
			t.Fatalf("accept %q: url/expiry %+v", accept, result)
		}
	}
}

func TestFrameURLRouteAlwaysReturnsJSON(t *testing.T) {
	env := newUnitEnv(t)
	ts := fixtureBase.Add(3 * time.Second)

	rr := env.do(t, "/v1/replays/rec-001/frame/url?timestamp="+url.QueryEscape(ts.Format(time.RFC3339Nano))+"&format=jpeg", "image/jpeg")
	result := decodeResult(t, rr)
	if result.MediaType != "frame" || result.URL == "" {
		t.Fatalf("result %+v", result)
	}

	raw := map[string]any{}
	rr = env.do(t, "/v1/replays/rec-001/frame/url?timestamp="+url.QueryEscape(ts.Format(time.RFC3339Nano)), "")
	if err := json.Unmarshal(rr.Body.Bytes(), &raw); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"recording_id", "sensor_id", "media_type", "content_type", "requested_start_ts", "start_ts", "exact_match", "url", "expiry_ts"} {
		if _, ok := raw[key]; !ok {
			t.Errorf("JSON missing %q: %v", key, raw)
		}
	}
	for _, legacy := range []string{"record_id", "expires_at", "derived_key", "DerivedKey"} {
		if _, ok := raw[legacy]; ok {
			t.Errorf("JSON leaks %q", legacy)
		}
	}
}

func TestFrameDerivedObjectIsReused(t *testing.T) {
	env := newUnitEnv(t)
	for _, offset := range []time.Duration{3 * time.Second, 3100 * time.Millisecond, 2800 * time.Millisecond} {
		if rr := env.do(t, framePath(fixtureBase.Add(offset), ""), "image/jpeg"); rr.Code != http.StatusOK {
			t.Fatalf("status = %d", rr.Code)
		}
	}
	if env.extractor.calls != 1 || len(env.media.PutCalls) != 1 {
		t.Fatalf("extractor calls = %d, puts = %d; want 1 and 1", env.extractor.calls, len(env.media.PutCalls))
	}
}

func TestFrameRejections(t *testing.T) {
	env := newUnitEnv(t)
	notReady, _ := env.metadata.GetByID(context.Background(), "rec-001")
	notReady.RecordingID = "rec-busy"
	notReady.State = model.RecordingStateFinalizing
	_ = env.metadata.Save(context.Background(), notReady)

	inCoverage := fixtureBase.Add(3 * time.Second)
	tsParam := url.QueryEscape(inCoverage.Format(time.RFC3339Nano))

	cases := []struct {
		name   string
		path   string
		accept string
		status int
		code   string
	}{
		{"missing timestamp", "/v1/replays/rec-001/frame", "", http.StatusBadRequest, "invalid_timestamp"},
		{"bad timestamp", "/v1/replays/rec-001/frame?timestamp=yesterday", "", http.StatusBadRequest, "invalid_timestamp"},
		{"unsupported format", framePath(inCoverage, "&format=gif"), "", http.StatusUnsupportedMediaType, "unsupported_media"},
		{"unsupported match", framePath(inCoverage, "&match=fuzzy"), "", http.StatusBadRequest, "invalid_request"},
		{"incompatible accept", framePath(inCoverage, ""), "video/mp4", http.StatusNotAcceptable, "not_acceptable"},
		{"png requested but jpeg accepted", framePath(inCoverage, "&format=png"), "image/jpeg", http.StatusNotAcceptable, "not_acceptable"},
		{"out of coverage", framePath(fixtureBase.Add(time.Hour), ""), "", http.StatusNotFound, "timestamp_out_of_coverage"},
		{"before coverage", framePath(fixtureBase.Add(-time.Second), ""), "", http.StatusNotFound, "timestamp_out_of_coverage"},
		{"exact miss", framePath(fixtureBase.Add(3250*time.Millisecond), "&match=exact"), "", http.StatusNotFound, "frame_not_found"},
		{"unknown recording", "/v1/replays/rec-404/frame?timestamp=" + tsParam, "", http.StatusNotFound, "recording_not_found"},
		{"not ready", "/v1/replays/rec-busy/frame?timestamp=" + tsParam, "", http.StatusConflict, "recording_not_ready"},
		{"invalid identifier", "/v1/replays/%20rec-001/frame?timestamp=" + tsParam, "", http.StatusBadRequest, "invalid_request"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			decodeError(t, env.do(t, tc.path, tc.accept), tc.status, tc.code)
		})
	}
	if env.extractor.calls != 0 {
		t.Fatalf("extractor invoked %d times on rejected requests", env.extractor.calls)
	}
}

func TestClipBinaryByDuration(t *testing.T) {
	env := newUnitEnv(t)
	start := fixtureBase.Add(2 * time.Second)

	rr := env.do(t, clipPath(start, "&duration_seconds=1.5&format=mp4"), "video/mp4")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d body %s", rr.Code, rr.Body.String())
	}
	if got := rr.Header().Get("Content-Type"); got != "video/mp4" {
		t.Fatalf("content-type = %q", got)
	}
	if got := rr.Header().Get("X-Frame-Timestamp"); got != start.Format(time.RFC3339Nano) {
		t.Fatalf("x-frame-timestamp = %q", got)
	}
	if got := rr.Header().Get("X-Exact-Match"); got != "true" {
		t.Fatalf("x-exact-match = %q", got)
	}
	body := rr.Body.Bytes()
	if len(body) < 8 || !bytes.Equal(body[4:8], mp4Magic) || !bytes.HasSuffix(body, []byte("@2.000-3.500")) {
		t.Fatalf("body = %q", body)
	}
}

func TestClipJSONByEndTimestampResolvesNearest(t *testing.T) {
	env := newUnitEnv(t)
	start := fixtureBase.Add(1900 * time.Millisecond)
	end := fixtureBase.Add(3600 * time.Millisecond)

	result := decodeResult(t, env.do(t, clipPath(start, "&timestamp_end="+url.QueryEscape(end.Format(time.RFC3339Nano))), "application/json"))
	if result.MediaType != "clip" || result.ContentType != "video/mp4" || result.ExactMatch {
		t.Fatalf("result %+v", result)
	}
	if !result.RequestedStartTS.Equal(start) || result.RequestedEndTS == nil || !result.RequestedEndTS.Equal(end) {
		t.Fatalf("requested bounds %+v", result)
	}
	if !result.StartTS.Equal(fixtureBase.Add(2*time.Second)) || result.EndTS == nil || !result.EndTS.Equal(fixtureBase.Add(3500*time.Millisecond)) {
		t.Fatalf("resolved bounds %+v", result)
	}
	if !strings.Contains(result.URL, "derived/rec-001/clips/") {
		t.Fatalf("url %q", result.URL)
	}
}

func TestClipURLRouteAlwaysReturnsJSON(t *testing.T) {
	env := newUnitEnv(t)
	start := fixtureBase.Add(2 * time.Second)
	rr := env.do(t, "/v1/replays/rec-001/clip/url?timestamp_start="+url.QueryEscape(start.Format(time.RFC3339Nano))+"&duration_seconds=2", "video/mp4")
	result := decodeResult(t, rr)
	if result.MediaType != "clip" || result.URL == "" {
		t.Fatalf("result %+v", result)
	}
}

func TestClipRejections(t *testing.T) {
	env := newUnitEnv(t)
	start := fixtureBase.Add(2 * time.Second)
	endParam := func(ts time.Time) string { return "&timestamp_end=" + url.QueryEscape(ts.Format(time.RFC3339Nano)) }

	cases := []struct {
		name   string
		path   string
		accept string
		status int
		code   string
	}{
		{"missing start", "/v1/replays/rec-001/clip?duration_seconds=1", "", http.StatusBadRequest, "invalid_timestamp"},
		{"missing boundary", clipPath(start, ""), "", http.StatusBadRequest, "invalid_request"},
		{"both boundaries", clipPath(start, endParam(start.Add(time.Second))+"&duration_seconds=1"), "", http.StatusBadRequest, "invalid_request"},
		{"bad end", clipPath(start, "&timestamp_end=soon"), "", http.StatusBadRequest, "invalid_timestamp"},
		{"non-numeric duration", clipPath(start, "&duration_seconds=abc"), "", http.StatusBadRequest, "invalid_duration"},
		{"zero duration", clipPath(start, "&duration_seconds=0"), "", http.StatusBadRequest, "invalid_duration"},
		{"negative duration", clipPath(start, "&duration_seconds=-2"), "", http.StatusBadRequest, "invalid_duration"},
		{"end before start", clipPath(start, endParam(start.Add(-time.Second))), "", http.StatusBadRequest, "invalid_request"},
		{"unsupported format", clipPath(start, "&duration_seconds=1&format=webm"), "", http.StatusUnsupportedMediaType, "unsupported_media"},
		{"incompatible accept", clipPath(start, "&duration_seconds=1"), "image/jpeg", http.StatusNotAcceptable, "not_acceptable"},
		{"end beyond coverage", clipPath(start, "&duration_seconds=3600"), "", http.StatusNotFound, "timestamp_out_of_coverage"},
		{"collapses to one sample", clipPath(start, "&duration_seconds=0.1"), "", http.StatusNotFound, "interval_not_covered"},
		{"unknown recording", "/v1/replays/rec-404/clip?timestamp_start=" + url.QueryEscape(start.Format(time.RFC3339Nano)) + "&duration_seconds=1", "", http.StatusNotFound, "recording_not_found"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			decodeError(t, env.do(t, tc.path, tc.accept), tc.status, tc.code)
		})
	}
	if env.extractor.calls != 0 {
		t.Fatalf("extractor invoked %d times on rejected requests", env.extractor.calls)
	}
}

func TestClipRejectsCoverageGap(t *testing.T) {
	env := newUnitEnv(t)

	// Drop ordinals 5 and 6 (2.5s, 3.0s) from the fixture sidecar so a clip
	// spanning them is reported as not covered rather than shortened.
	raw, _ := env.media.Get("recordings/rec-001/sidecar.json")
	var doc map[string]any
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	samples := doc["samples"].([]any)
	doc["samples"] = append(append([]any{}, samples[:5]...), samples[7:]...)
	gapped, _ := json.Marshal(doc)
	env.media.Set("recordings/rec-001/sidecar.json", gapped)

	decodeError(t, env.do(t, clipPath(fixtureBase.Add(2*time.Second), "&duration_seconds=2"), ""), http.StatusNotFound, "interval_not_covered")

	// Ranges on either side of the gap still resolve.
	if rr := env.do(t, clipPath(fixtureBase, "&duration_seconds=2"), ""); rr.Code != http.StatusOK {
		t.Fatalf("range before gap: %d %s", rr.Code, rr.Body.String())
	}
}

func TestLiveRecordingUnknownSizeReturnsConflict(t *testing.T) {
	recordingID := "rec-live-unknown"
	start := fixtureBase
	recordingPath := "recordings/" + recordingID + "/media.ts"
	recording := model.Recording{
		RecordingID:   recordingID,
		SensorID:      "sensor-live",
		Origin:        model.RecordingOriginLive,
		State:         model.RecordingStateRecording,
		StartTS:       start,
		RecordingPath: recordingPath,
		Container:     "mpegts",
		SizeBytes:     0,
		CreationTS:    start,
		Metadata:      map[string]any{},
	}
	media := storagetest.NewMemoryMediaStore()
	media.Set(recordingPath, []byte("mpeg-ts"))
	media.Set("recordings/"+recordingID+"/sidecar.jsonl", []byte(fmt.Sprintf(
		"{\"version\":2,\"recording_id\":%q,\"media_path\":%q,\"timescale\":90000}\n"+
			"{\"ordinal\":0,\"capture_ts\":%q,\"pts\":0,\"dts\":0,\"duration\":3000,\"offset\":0,\"length\":1880,\"keyframe\":true}\n"+
			"{\"ordinal\":1,\"capture_ts\":%q,\"pts\":3000,\"dts\":3000,\"duration\":3000,\"offset\":1880,\"length\":940,\"keyframe\":false}\n",
		recordingID, recordingPath, start.Format(time.RFC3339Nano), start.Add(time.Second).Format(time.RFC3339Nano),
	)))
	metadata := storagetest.NewMemoryMetadataStore(recording)
	extractor := &stubExtractor{}
	service := replay.NewRetrievalService(metadata, media, replay.Options{Extractor: extractor, MaxStageBytes: 1024})
	logs := &bytes.Buffer{}
	logger := slog.New(slog.NewJSONHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	router := NewRouter(service, media, testVersion, logger, nil, nil, nil)
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, httptest.NewRequest(http.MethodGet,
		"/v1/replays/"+recordingID+"/frame?timestamp="+url.QueryEscape(start.Format(time.RFC3339Nano)), nil))

	decodeError(t, rr, http.StatusConflict, "recording_size_unknown")
	if extractor.calls != 0 {
		t.Fatalf("extractor invoked %d times for unknown-size live recording", extractor.calls)
	}
}

type routerBufferer struct{}

func (routerBufferer) CreateBuffer(context.Context, string, string) (string, error) {
	return "str-test", nil
}
func (routerBufferer) GetBuffer(context.Context, string, time.Time, time.Time) ([]model.BufferSlice, error) {
	return nil, nil
}
func (routerBufferer) AcquireBuffer(context.Context, string, time.Time, time.Time) (*stream.BufferLease, error) {
	return nil, nil
}
func (routerBufferer) ResizeBuffer(context.Context, string, int) (model.StreamBuffer, error) {
	return model.StreamBuffer{}, nil
}
func (routerBufferer) RemoveBuffer(context.Context, string) error { return nil }
func (routerBufferer) GetStream(_ context.Context, id string) (model.StreamBuffer, error) {
	return model.StreamBuffer{StreamID: id, SensorID: "sensor-01", State: "buffering"}, nil
}
func (routerBufferer) ListStreams(context.Context) ([]model.StreamBuffer, error) {
	return []model.StreamBuffer{{StreamID: "str-test", SensorID: "sensor-01", State: "buffering"}}, nil
}

func TestLifecycleRoutesComposeWithRetrievalAndReportUnavailableRecorder(t *testing.T) {
	env := newUnitEnv(t)
	service := replay.NewRetrievalService(env.metadata, env.media, replay.Options{Extractor: env.extractor})
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	router := NewRouter(service, env.media, testVersion, logger, nil, routerBufferer{}, nil)

	streams := httptest.NewRecorder()
	router.ServeHTTP(streams, httptest.NewRequest(http.MethodGet, "/v1/streams", nil))
	if streams.Code != http.StatusOK {
		t.Fatalf("GET /v1/streams status %d: %s", streams.Code, streams.Body.String())
	}

	records := httptest.NewRecorder()
	router.ServeHTTP(records, httptest.NewRequest(http.MethodGet, "/v1/records", nil))
	decodeError(t, records, http.StatusServiceUnavailable, "storage_unavailable")

	frame := httptest.NewRecorder()
	router.ServeHTTP(frame, httptest.NewRequest(http.MethodGet, framePath(fixtureBase, ""), nil))
	if frame.Code != http.StatusOK {
		t.Fatalf("existing replay route status %d: %s", frame.Code, frame.Body.String())
	}
}

func TestSidecarProblemsAreReported(t *testing.T) {
	ts := fixtureBase.Add(3 * time.Second)
	valid, err := os.ReadFile(filepath.Join(fixtureRoot, "rec-001", "sidecar.json"))
	if err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name    string
		sidecar []byte
		status  int
		code    string
	}{
		{"missing", nil, http.StatusServiceUnavailable, "storage_unavailable"},
		{"malformed", []byte(`{"version":1,`), http.StatusUnprocessableEntity, "invalid_media_index"},
		{"unsupported version", bytes.Replace(valid, []byte(`"version": 1`), []byte(`"version": 2`), 1), http.StatusUnprocessableEntity, "invalid_media_index"},
		{"legacy record_id", bytes.Replace(valid, []byte(`"recording_id"`), []byte(`"record_id"`), 1), http.StatusUnprocessableEntity, "invalid_media_index"},
		{"names another recording", bytes.Replace(valid, []byte(`"recording_id": "rec-001"`), []byte(`"recording_id": "rec-002"`), 1), http.StatusUnprocessableEntity, "invalid_media_index"},
		{"names other media", bytes.Replace(valid, []byte(`"media_path": "recordings/rec-001/media.mp4"`), []byte(`"media_path": "recordings/rec-001/other.mp4"`), 1), http.StatusUnprocessableEntity, "invalid_media_index"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			env := newUnitEnv(t)
			if tc.sidecar == nil {
				env.media.Delete("recordings/rec-001/sidecar.json")
			} else {
				env.media.Set("recordings/rec-001/sidecar.json", tc.sidecar)
			}
			decodeError(t, env.do(t, framePath(ts, ""), ""), tc.status, tc.code)
			if env.extractor.calls != 0 {
				t.Fatal("extraction attempted against an invalid sidecar")
			}
		})
	}
}

func TestStorageFailuresMapTo503(t *testing.T) {
	ts := fixtureBase.Add(3 * time.Second)

	t.Run("recording missing", func(t *testing.T) {
		env := newUnitEnv(t)
		env.media.Delete("recordings/rec-001/media.mp4")
		decodeError(t, env.do(t, framePath(ts, ""), ""), http.StatusServiceUnavailable, "storage_unavailable")
	})
	t.Run("derived write fails", func(t *testing.T) {
		env := newUnitEnv(t)
		env.media.PutErr = fmt.Errorf("bucket read-only")
		decodeError(t, env.do(t, framePath(ts, ""), ""), http.StatusServiceUnavailable, "storage_unavailable")
	})
	t.Run("presign fails", func(t *testing.T) {
		env := newUnitEnv(t)
		env.media.PresignErr = fmt.Errorf("signer offline")
		decodeError(t, env.do(t, framePath(ts, ""), ""), http.StatusServiceUnavailable, "storage_unavailable")
	})
	t.Run("error body never echoes internals", func(t *testing.T) {
		env := newUnitEnv(t)
		env.media.PutErr = fmt.Errorf("secret-bucket-name AKIA1234")
		rr := env.do(t, framePath(ts, ""), "")
		if strings.Contains(rr.Body.String(), "secret-bucket-name") || strings.Contains(rr.Body.String(), "AKIA") {
			t.Fatalf("error body leaks storage detail: %s", rr.Body.String())
		}
	})
}

func TestLifecycleRoutesAreAlwaysRegistered(t *testing.T) {
	env := newUnitEnv(t)
	for _, path := range []string{"/v1/replays/rec-001", "/v1/replays/rec-001/media", "/v1/recordings"} {
		if rr := env.do(t, path, ""); rr.Code != http.StatusNotFound {
			t.Errorf("%s: status %d, want 404", path, rr.Code)
		}
	}
	for _, path := range []string{"/v1/streams", "/v1/records"} {
		decodeError(t, env.do(t, path, ""), http.StatusServiceUnavailable, "storage_unavailable")
	}
	req := httptest.NewRequest(http.MethodPost, framePath(fixtureBase.Add(3*time.Second), ""), nil)
	rr := httptest.NewRecorder()
	env.router.ServeHTTP(rr, req)
	if rr.Code != http.StatusNotFound && rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("POST frame: status %d", rr.Code)
	}
}
