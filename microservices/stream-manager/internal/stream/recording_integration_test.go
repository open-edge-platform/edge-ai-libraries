// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/config"
)

type recordingWire struct {
	ID    string     `json:"recording_id"`
	State string     `json:"state"`
	Start time.Time  `json:"start_ts"`
	End   *time.Time `json:"end_ts"`
	Size  *int64     `json:"size_bytes"`
	Error *string    `json:"error_detail"`
}

var integrationRace bool

// startTestApp runs the application with HOME pointing at home, so its
// default recording storage lives inside the test's directory. The app's
// listen address is passed via a temporary config.json pointed at by
// SM_CONFIG_FILE, since that address is only known once a free port has
// been reserved here; both the env var and the file are removed once the
// test is done.
func startTestApp(t *testing.T, executable, home string) (string, func()) {
	t.Helper()
	reservation, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := reservation.Addr().String()
	if err := reservation.Close(); err != nil {
		t.Fatal(err)
	}

	configFile, err := os.CreateTemp("", "stream-manager-test-config-*.json")
	if err != nil {
		t.Fatal(err)
	}
	configPath := configFile.Name()
	body, err := json.Marshal(map[string]string{"HTTPAddr": address})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := configFile.Write(body); err != nil {
		t.Fatal(err)
	}
	if err := configFile.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.Setenv("SM_CONFIG_FILE", configPath); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Unsetenv("SM_CONFIG_FILE"); err != nil {
			t.Error(err)
		}
		if err := os.Remove(configPath); err != nil && !os.IsNotExist(err) {
			t.Error(err)
		}
	})

	logName := filepath.Join(t.TempDir(), "server.log")
	logFile, err := os.Create(logName)
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(executable)
	cmd.Env = append(os.Environ(), "GIN_MODE=release", "HOME="+home)
	cmd.Stdout, cmd.Stderr = logFile, logFile
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	var waitErr error
	go func() { waitErr = cmd.Wait(); close(done) }()
	var once sync.Once
	stop := func() {
		once.Do(func() {
			if err := cmd.Process.Signal(syscall.SIGTERM); err != nil && !errors.Is(err, os.ErrProcessDone) {
				t.Error(err)
			}
			select {
			case <-done:
			case <-time.After(15 * time.Second):
				if err := cmd.Process.Kill(); err != nil {
					t.Error(err)
				}
				<-done
				t.Error("application did not shut down in time")
			}
			if err := logFile.Close(); err != nil {
				t.Error(err)
			}
			if waitErr != nil || t.Failed() {
				data, err := os.ReadFile(logName)
				if err != nil {
					t.Error(err)
				}
				t.Logf("application exit %v:\n%s", waitErr, data)
			}
			if waitErr != nil {
				t.Error(waitErr)
			}
		})
	}
	t.Cleanup(stop)
	baseURL := "http://" + address + "/v1"
	client := &http.Client{Timeout: time.Second}
	deadline := time.Now().Add(10 * time.Second)
	for {
		select {
		case <-done:
			stop()
			t.Fatal("application exited during startup")
		default:
		}
		response, err := client.Get(baseURL + "/streams")
		if err == nil {
			status := response.StatusCode
			if err := response.Body.Close(); err != nil {
				t.Fatal(err)
			}
			if status == http.StatusOK {
				break
			}
		}
		if time.Now().After(deadline) {
			t.Fatal("application did not become responsive")
		}
		time.Sleep(25 * time.Millisecond)
	}
	return baseURL, stop
}

func TestRecordingEndToEnd(t *testing.T) {
	if testing.Short() {
		t.Skip("real API, SQLite and FFmpeg recording integration")
	}
	executable := filepath.Join(t.TempDir(), "stream-manager")
	args := []string{"build", "-o", executable}
	cgo := "0"
	if integrationRace {
		args = append(args, "-race")
		cgo = "1"
	}
	args = append(args, "../../cmd/api-server")
	build := exec.Command("go", args...)
	build.Env = append(os.Environ(), "CGO_ENABLED="+cgo)
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build application: %v\n%s", err, output)
	}
	source, _, stopSource := testPublisherWithStop(t, "h264", true, time.Now().UTC().Truncate(time.Second))
	home := t.TempDir()
	storageDir := filepath.Join(home, ".local", "share", "stream-manager")
	baseURL, stopApp := startTestApp(t, executable, home)
	client := &http.Client{Timeout: 10 * time.Second}
	request := func(method, path string, body any, want ...int) ([]byte, int) {
		t.Helper()
		var data []byte
		if body != nil {
			var err error
			data, err = json.Marshal(body)
			if err != nil {
				t.Fatal(err)
			}
		}
		req, err := http.NewRequest(method, baseURL+path, bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("Content-Type", "application/json")
		response, err := client.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		data, err = io.ReadAll(response.Body)
		closeErr := response.Body.Close()
		if err := errors.Join(err, closeErr); err != nil {
			t.Fatal(err)
		}
		for _, status := range want {
			if response.StatusCode == status {
				return data, status
			}
		}
		t.Fatalf("%s %s: %d, expected %v: %s", method, path, response.StatusCode, want, data)
		return nil, 0
	}
	decode := func(data []byte, dst any) {
		t.Helper()
		if err := json.Unmarshal(data, dst); err != nil {
			t.Fatal(err)
		}
	}
	data, _ := request("POST", "/streams", map[string]any{"sensor_id": "camera", "source_uri": source, "buffer_length": 8}, 201)
	var attached struct {
		ID     string `json:"stream_id"`
		State  string `json:"state"`
		Buffer struct {
			Oldest *time.Time `json:"oldest_ts"`
			Newest *time.Time `json:"newest_ts"`
		} `json:"buffer"`
	}
	decode(data, &attached)
	streamPath := "/streams/" + attached.ID
	deadline := time.Now().Add(20 * time.Second)
	for attached.Buffer.Oldest == nil || attached.Buffer.Newest == nil ||
		attached.Buffer.Newest.Sub(*attached.Buffer.Oldest) < 2*time.Second {
		if attached.State == "failed" || time.Now().After(deadline) {
			t.Fatalf("source did not buffer: %+v", attached)
		}
		time.Sleep(50 * time.Millisecond)
		data, _ = request("GET", streamPath, nil, 200)
		decode(data, &attached)
	}
	event := attached.Buffer.Newest.Add(-500 * time.Millisecond)
	start := func(body map[string]any) recordingWire {
		t.Helper()
		data, _ := request("POST", "/records/start", body, 201)
		var response struct {
			Recordings []recordingWire `json:"recordings"`
		}
		decode(data, &response)
		if len(response.Recordings) != 1 || response.Recordings[0].State != "recording" {
			t.Fatalf("invalid acceptance response: %s", data)
		}
		if _, err := uuid.Parse(response.Recordings[0].ID); err != nil {
			t.Fatal(err)
		}
		return response.Recordings[0]
	}
	fixed := start(map[string]any{
		"stream_id": attached.ID, "start_ts": event, "duration": 0.2,
		"pre_event_duration": 0.25, "metadata": map[string]string{"case": "fixed"},
	})
	open := start(map[string]any{
		"stream_id": attached.ID, "start_ts": event, "metadata": map[string]string{"case": "open"},
	})
	request("DELETE", "/records/"+open.ID, nil, 409)
	request("DELETE", streamPath, nil, 409)
	request("POST", "/records/start", map[string]any{
		"stream_id": "missing", "start_ts": event,
	}, 404)
	request("POST", "/records/start", map[string]any{
		"stream_id": attached.ID, "start_ts": attached.Buffer.Oldest.Add(-time.Second),
	}, 409)
	data, _ = request("GET", "/records", nil, 200)
	var page struct {
		Items []recordingWire `json:"items"`
		Next  *string         `json:"next_cursor"`
	}
	decode(data, &page)
	if len(page.Items) != 2 {
		t.Fatalf("rejected requests left records: %s", data)
	}
	data, _ = request("POST", "/records/stop", map[string]string{"recording_id": open.ID}, 202)
	var stopped recordingWire
	decode(data, &stopped)
	data, repeatedStatus := request("POST", "/records/stop", map[string]string{"recording_id": open.ID}, 200, 202)
	var repeated recordingWire
	decode(data, &repeated)
	if repeatedStatus == 202 && (stopped.End == nil || repeated.End == nil || !stopped.End.Equal(*repeated.End)) {
		t.Fatal("repeated stop moved the fixed stop target")
	}
	for _, accepted := range []recordingWire{fixed, open} {
		deadline := time.Now().Add(20 * time.Second)
		var ready recordingWire
		for {
			data, _ = request("GET", "/records/"+accepted.ID, nil, 200)
			decode(data, &ready)
			if ready.State == "ready" {
				break
			}
			if ready.State == "failed" || time.Now().After(deadline) {
				t.Fatalf("recording failed: %s", data)
			}
			time.Sleep(50 * time.Millisecond)
		}
		if ready.End == nil || !ready.End.After(ready.Start) || ready.Size == nil || *ready.Size <= 0 ||
			strings.Contains(string(data), `"codec"`) || strings.Contains(string(data), `"recording_path"`) {
			t.Fatalf("invalid ready response: %s", data)
		}
		if accepted.ID == fixed.ID && (ready.Start.After(event.Add(-250*time.Millisecond)) ||
			ready.End.Before(event.Add(200*time.Millisecond))) {
			t.Fatal("actual GOP bounds do not cover the requested recording window")
		}
		filename := filepath.Join(storageDir, accepted.ID, "media.ts")
		info, err := os.Stat(filename)
		if err != nil || info.Size() != *ready.Size {
			t.Fatalf("recording file/metadata mismatch: %v", err)
		}
		if output, err := exec.Command("ffmpeg", "-v", "error", "-xerror", "-i", filename, "-f", "null", "-").CombinedOutput(); err != nil {
			t.Fatalf("recording cannot decode: %v\n%s", err, output)
		}
		frameData, err := exec.Command("ffprobe", "-v", "error", "-select_streams", "v:0",
			"-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "json", filename).Output()
		if err != nil {
			t.Fatal(err)
		}
		var counts struct {
			Streams []struct {
				Count string `json:"nb_read_frames"`
			} `json:"streams"`
		}
		decode(frameData, &counts)
		if len(counts.Streams) != 1 {
			t.Fatalf("unexpected frame-count result: %s", frameData)
		}
		frames, err := strconv.Atoi(counts.Streams[0].Count)
		wantFrames := int(math.Round(ready.End.Sub(ready.Start).Seconds() * 10))
		if err != nil || frames != wantFrames {
			t.Fatalf("stored window lost/duplicated frames: %d, want %d: %v", frames, wantFrames, err)
		}
	}
	data, _ = request("GET", "/records?metadata[case]=fixed&limit=1", nil, 200)
	decode(data, &page)
	if len(page.Items) != 1 || page.Items[0].ID != fixed.ID {
		t.Fatalf("metadata filter: %s", data)
	}
	data, _ = request("GET", "/records?limit=1", nil, 200)
	decode(data, &page)
	if page.Next == nil {
		t.Fatal("recording pagination omitted its next cursor")
	}
	firstID := page.Items[0].ID
	data, _ = request("GET", "/records?limit=1&cursor="+url.QueryEscape(*page.Next), nil, 200)
	decode(data, &page)
	if len(page.Items) != 1 || page.Items[0].ID == firstID || page.Next != nil {
		t.Fatalf("recording cursor pagination: %s", data)
	}
	request("DELETE", "/records/"+fixed.ID, nil, 200)
	request("GET", "/records/"+fixed.ID, nil, 404)
	request("DELETE", "/records/"+fixed.ID, nil, 404)
	if _, err := os.Stat(filepath.Join(storageDir, fixed.ID)); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("record deletion left media behind")
	}
	data, _ = request("GET", streamPath, nil, 200)
	decode(data, &attached)
	liveEvent := attached.Buffer.Newest.Add(-250 * time.Millisecond)
	liveIDs := make([]string, 0, config.ConcurrentRecorders)
	for range config.ConcurrentRecorders {
		rec := start(map[string]any{"stream_id": attached.ID, "start_ts": liveEvent})
		liveIDs = append(liveIDs, rec.ID)
	}
	request("POST", "/records/start", map[string]any{
		"stream_id": attached.ID, "start_ts": liveEvent,
	}, 429)
	stopSource()
	for _, id := range liveIDs {
		deadline := time.Now().Add(15 * time.Second)
		for {
			data, _ = request("GET", "/records/"+id, nil, 200)
			var failed recordingWire
			decode(data, &failed)
			if failed.State == "failed" {
				if failed.Error == nil || strings.Contains(*failed.Error, "shutdown") {
					t.Fatalf("source failure was not reported accurately: %s", data)
				}
				break
			}
			if time.Now().After(deadline) {
				t.Fatalf("disconnected source left a recording running: %s", data)
			}
			time.Sleep(50 * time.Millisecond)
		}
		if _, err := os.Stat(filepath.Join(storageDir, id)); !errors.Is(err, os.ErrNotExist) {
			t.Fatal("failed recording media was not cleaned up")
		}
	}
	request("DELETE", streamPath, nil, 200)
	stopApp()
	baseURL, _ = startTestApp(t, executable, home)
	data, _ = request("GET", "/records/"+open.ID, nil, 200)
	var persisted recordingWire
	decode(data, &persisted)
	if persisted.State != "ready" {
		t.Fatalf("ready recording did not survive restart: %s", data)
	}
	t.Log("fixed/open recordings, stop, admission, filters, pagination, deletion and restart passed")
}
