// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/replay"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

// Integration tests run the real stack (ffmpeg + S3 + SQLite) against the
// SeaweedFS started by compose.dev.yaml. They skip unless the endpoint is
// reachable, so `go test ./...` stays green on machines without the stack.
//
// Override the defaults with STREAM_MANAGER_TEST_S3_* when the compose stack
// is published on different ports.
func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

type integrationEnv struct {
	router http.Handler
	media  *storage.S3MediaStore
}

func newIntegrationEnv(t *testing.T) integrationEnv {
	t.Helper()
	if os.Getenv("STREAM_MANAGER_SKIP_INTEGRATION") != "" {
		t.Skip("STREAM_MANAGER_SKIP_INTEGRATION set")
	}
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg not on PATH")
	}

	endpoint := envOr("STREAM_MANAGER_TEST_S3_ENDPOINT", "http://localhost:8333")
	parsed, err := url.Parse(endpoint)
	if err != nil {
		t.Fatalf("parse endpoint: %v", err)
	}
	conn, err := net.DialTimeout("tcp", parsed.Host, 500*time.Millisecond)
	if err != nil {
		t.Skipf("S3 endpoint %s not reachable: %v", endpoint, err)
	}
	_ = conn.Close()

	// Corporate proxies must not intercept loopback S3 or presigned URLs.
	t.Setenv("NO_PROXY", "*")
	t.Setenv("no_proxy", "*")

	suffix := make([]byte, 4)
	if _, err := rand.Read(suffix); err != nil {
		t.Fatalf("random suffix: %v", err)
	}

	ctx := context.Background()
	media, err := storage.NewS3MediaStore(ctx, storage.S3Config{
		Endpoint:     endpoint,
		Region:       envOr("STREAM_MANAGER_TEST_S3_REGION", "us-east-1"),
		Bucket:       envOr("STREAM_MANAGER_TEST_S3_BUCKET", "stream-manager-test"),
		Prefix:       "it-" + hex.EncodeToString(suffix),
		UsePathStyle: true,
		AccessKey:    envOr("STREAM_MANAGER_TEST_S3_ACCESS_KEY", "streammanagerdev"),
		SecretKey:    envOr("STREAM_MANAGER_TEST_S3_SECRET_KEY", "streammanagerdev123"),
	})
	if err != nil {
		t.Fatalf("new S3 media store: %v", err)
	}
	if err := media.Health(ctx); err != nil {
		t.Skipf("S3 bucket not usable: %v", err)
	}

	metadata, err := storage.OpenSQLiteMetadataStore(ctx, filepath.Join(t.TempDir(), "meta.db"))
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	t.Cleanup(func() { _ = metadata.Close() })

	recording, sidecarJSON := loadAPIFixture(t)
	mediaPath := filepath.Join(t.TempDir(), "media.mp4")
	command := exec.CommandContext(ctx, "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
		"-i", "testsrc=duration=10:size=320x240:rate=2", "-c:v", "libx264", "-preset", "veryfast",
		"-pix_fmt", "yuv420p", "-movflags", "+faststart", mediaPath)
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("generate test media: %v: %s", err, output)
	}
	mediaBytes, err := os.ReadFile(mediaPath)
	if err != nil {
		t.Fatal(err)
	}
	key, err := media.PutRecording(ctx, recording.RecordingID, bytes.NewReader(mediaBytes), "video/mp4")
	if err != nil || key != recording.RecordingPath {
		t.Fatalf("put test recording: key=%q, err=%v", key, err)
	}
	if _, err := media.PutSidecar(ctx, recording.RecordingID, bytes.NewReader(sidecarJSON)); err != nil {
		t.Fatalf("put test sidecar: %v", err)
	}
	recording.SizeBytes = int64(len(mediaBytes))
	if err := metadata.Save(ctx, recording); err != nil {
		t.Fatalf("save test metadata: %v", err)
	}
	t.Cleanup(func() {
		if err := media.DeleteRecordingObjects(context.Background(), recording.RecordingID); err != nil {
			t.Logf("cleanup: %v", err)
		}
	})

	service := replay.NewRetrievalService(metadata, media, replay.Options{
		Extractor:     replay.NewFFmpegExtractor(),
		DerivedTTL:    time.Hour,
		PresignExpiry: 5 * time.Minute,
	})
	return integrationEnv{router: NewRouter(service, media, "test", slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, nil), media: media}
}

func (e integrationEnv) do(t *testing.T, path, accept string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	if accept != "" {
		req.Header.Set("Accept", accept)
	}
	rr := httptest.NewRecorder()
	e.router.ServeHTTP(rr, req)
	return rr
}

func fetchURL(t *testing.T, rawURL string) []byte {
	t.Helper()
	client := &http.Client{Timeout: 10 * time.Second, Transport: &http.Transport{Proxy: nil}}
	resp, err := client.Get(rawURL)
	if err != nil {
		t.Fatalf("GET presigned url: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("presigned url status %d: %s", resp.StatusCode, body)
	}
	return body
}

func TestIntegrationFrameEndpoints(t *testing.T) {
	env := newIntegrationEnv(t)
	ts := fixtureBase.Add(2500 * time.Millisecond)

	rr := env.do(t, framePath(ts, ""), "image/jpeg")
	if rr.Code != http.StatusOK {
		t.Fatalf("frame status %d: %s", rr.Code, rr.Body.String())
	}
	if !bytes.HasPrefix(rr.Body.Bytes(), jpegMagic) {
		t.Fatalf("frame body is not JPEG (%d bytes)", rr.Body.Len())
	}
	if got := rr.Header().Get("X-Exact-Match"); got != "true" {
		t.Fatalf("X-Exact-Match = %q", got)
	}

	rr = env.do(t, framePath(ts, "&format=png"), "image/png")
	if rr.Code != http.StatusOK || !bytes.HasPrefix(rr.Body.Bytes(), pngMagic) {
		t.Fatalf("png frame status %d, prefix %x", rr.Code, rr.Body.Bytes()[:min(4, rr.Body.Len())])
	}

	rr = env.do(t, "/v1/replays/rec-001/frame/url?timestamp="+url.QueryEscape(ts.Format(time.RFC3339Nano)), "image/jpeg")
	result := decodeResult(t, rr)
	if result.ContentType != "image/jpeg" || result.URL == "" {
		t.Fatalf("frame/url result = %+v", result)
	}
	if !bytes.HasPrefix(fetchURL(t, result.URL), jpegMagic) {
		t.Fatal("presigned frame is not JPEG")
	}

	key, err := storage.DerivedFrameKey(result.RecordingID, result.StartTS, "jpeg")
	if err != nil {
		t.Fatalf("derived key: %v", err)
	}
	exists, err := env.media.DerivedExists(context.Background(), key)
	if err != nil || !exists {
		t.Fatalf("derived frame %s missing: exists=%v err=%v", key, exists, err)
	}
}

func TestIntegrationClipEndpoints(t *testing.T) {
	env := newIntegrationEnv(t)
	start := fixtureBase.Add(1 * time.Second)

	rr := env.do(t, clipPath(start, "&duration_seconds=2"), "video/mp4")
	if rr.Code != http.StatusOK {
		t.Fatalf("clip status %d: %s", rr.Code, rr.Body.String())
	}
	if !bytes.Contains(rr.Body.Bytes()[:min(16, rr.Body.Len())], mp4Magic) {
		t.Fatalf("clip body is not MP4 (%d bytes)", rr.Body.Len())
	}

	end := start.Add(3 * time.Second)
	rr = env.do(t, "/v1/replays/rec-001/clip/url?timestamp_start="+url.QueryEscape(start.Format(time.RFC3339Nano))+
		"&timestamp_end="+url.QueryEscape(end.Format(time.RFC3339Nano)), "")
	result := decodeResult(t, rr)
	if result.ContentType != "video/mp4" || result.EndTS == nil || !result.EndTS.Equal(end) {
		t.Fatalf("clip/url result = %+v", result)
	}
	body := fetchURL(t, result.URL)
	if !bytes.Contains(body[:min(16, len(body))], mp4Magic) {
		t.Fatal("presigned clip is not MP4")
	}
}
