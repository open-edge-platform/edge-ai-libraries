// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package retrieve

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/storage"
)

const (
	fixtureFPS    = 30
	fixtureFrames = 180
	fixtureGOP    = 45
	// sparseFixtureFrames is 6.5 minutes at 1 fps.
	sparseFixtureFrames = 390
	// testDerivedTTL differs from the 15-minute default to show the setting is used.
	testDerivedTTL = 7 * time.Minute
)

var (
	fixtureStart = time.Date(2026, 6, 15, 14, 12, 0, 0, time.UTC)
	fixtureEnd   = fixtureStart.Add(fixtureFrames * time.Second / fixtureFPS)
	fixtures     sync.Map
)

// fixture writes a 6 s, 30 fps H.264 MPEG-TS with a non-zero start time and
// passes it through the recorder's FFmpeg flags, as a recording's media.ts.
func fixture(t *testing.T, bFrames int) string {
	t.Helper()
	return cachedFixture(t, bFrames, fixtureFPS, fixtureFrames, fixtureGOP, bFrames)
}

// sparseFixture is a 1 fps fixture, longer than SearchLimit, whose only keyframe is its first frame.
func sparseFixture(t *testing.T) string {
	t.Helper()
	return cachedFixture(t, "sparse", 1, sparseFixtureFrames, 100000, 0)
}

func cachedFixture(t *testing.T, key any, fps, frames, gop, bFrames int) string {
	t.Helper()
	if path, ok := fixtures.Load(key); ok {
		return path.(string)
	}
	for _, tool := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(tool); err != nil {
			t.Skipf("%s not available", tool)
		}
	}
	dir, err := os.MkdirTemp("", "retrieve-fixture-")
	if err != nil {
		t.Fatal(err)
	}
	source, media := filepath.Join(dir, "source.ts"), filepath.Join(dir, "media.ts")
	run(t, "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
		fmt.Sprintf("testsrc2=size=160x120:rate=%d", fps), "-frames:v", strconv.Itoa(frames),
		"-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", strconv.Itoa(gop), "-keyint_min", strconv.Itoa(gop),
		"-sc_threshold", "0", "-bf", strconv.Itoa(bFrames), "-output_ts_offset", "1001.4", "-f", "mpegts", source)
	run(t, "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "mpegts", "-i", source, "-map", "0:v:0", "-an",
		"-c:v", "copy", "-copyts", "-start_at_zero", "-mpegts_copyts", "1", "-f", "mpegts", media)
	fixtures.Store(key, media)
	return media
}

func TestMain(m *testing.M) {
	code := m.Run()
	fixtures.Range(func(_, path any) bool {
		_ = os.RemoveAll(filepath.Dir(path.(string)))
		return true
	})
	os.Exit(code)
}

func run(t *testing.T, name string, args ...string) []byte {
	t.Helper()
	var stderr bytes.Buffer
	cmd := exec.Command(name, args...)
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("%s %v: %v: %s", name, args, err, stderr.String())
	}
	return out
}

type testEnv struct {
	svc           *Service
	metadataStore *storage.MetadataStore
	mediaStore    *storage.MediaStore
	media         string
}

func newEnv(t *testing.T, bFrames int) testEnv {
	t.Helper()
	media := fixture(t, bFrames)
	dir := filepath.Join(t.TempDir(), "storage")
	if err := os.Mkdir(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	metadataStore, err := storage.OpenMetadataStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = metadataStore.Close() })
	mediaStore, err := storage.OpenMediaStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = mediaStore.Close() })
	svc, err := NewService(metadataStore, mediaStore)
	if err != nil {
		t.Fatal(err)
	}
	return testEnv{svc: svc, metadataStore: metadataStore, mediaStore: mediaStore, media: media}
}

// addRecording stores a recording of the fixture, edited by opts.
func (e testEnv) addRecording(t *testing.T, opts ...func(*model.Recording)) model.Recording {
	t.Helper()
	recordingUUID := uuid.New()
	recordingID := base64.RawURLEncoding.EncodeToString(recordingUUID[:])
	filename, uri, err := e.mediaStore.PrepareMedia(context.Background(), recordingID)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(e.media)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filename, data, 0o600); err != nil {
		t.Fatal(err)
	}
	end, expiry := fixtureEnd, time.Now().Add(time.Hour)
	rec := model.Recording{
		RecordingID: recordingID, SensorID: "cam-1", StartTS: fixtureStart, EndTS: &end, RecordingPath: uri,
		State: "ready", CreationTS: time.Now(), ExpiryTS: &expiry, Metadata: map[string]any{},
	}
	for _, opt := range opts {
		opt(&rec)
	}
	if rec, err = e.metadataStore.CreateMetadata(context.Background(), rec); err != nil {
		t.Fatal(err)
	}
	return rec
}

// frameTS is the wall time of frame n of the fixture.
func frameTS(n int) time.Time {
	return fixtureStart.Add(time.Duration(int64(n) * int64(time.Second) / fixtureFPS))
}

// pixels decodes the first frame of a file to raw RGB and hashes it.
func pixels(t *testing.T, path string, filter string) string {
	t.Helper()
	args := []string{"-hide_banner", "-loglevel", "error", "-i", path}
	if filter != "" {
		args = append(args, "-vf", filter)
	}
	args = append(args, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
	sum := md5.Sum(run(t, "ffmpeg", args...))
	return hex.EncodeToString(sum[:])
}

func referenceFrame(t *testing.T, media string, n int) string {
	return pixels(t, media, fmt.Sprintf("select=eq(n\\,%d)", n))
}

func TestFrame(t *testing.T) {
	for _, bFrames := range []int{0, 2} {
		t.Run(fmt.Sprintf("bframes=%d", bFrames), func(t *testing.T) {
			env := newEnv(t, bFrames)
			rec := env.addRecording(t)
			cases := []struct {
				name   string
				ts     time.Time
				match  string
				format string
				want   int
				exact  bool
			}{
				{"first frame exact", frameTS(0), "exact", "png", 0, true},
				{"just after first frame", frameTS(0).Add(10 * time.Millisecond), "nearest", "png", 0, false},
				{"before keyframe", frameTS(44).Add(5 * time.Millisecond), "nearest", "png", 44, false},
				{"keyframe exact", frameTS(45), "exact", "png", 45, true},
				{"after keyframe", frameTS(46).Add(-5 * time.Millisecond), "nearest", "png", 46, false},
				{"mid GOP", frameTS(100), "exact", "png", 100, true},
				{"tie picks earlier", fixtureStart.Add(83333333), "nearest", "png", 2, false},
				{"last frame", frameTS(fixtureFrames - 1).Add(30 * time.Millisecond), "nearest", "png", fixtureFrames - 1, false},
				{"jpeg", frameTS(120), "nearest", "jpeg", 120, true},
			}
			for _, tc := range cases {
				t.Run(tc.name, func(t *testing.T) {
					media, err := env.svc.Frame(context.Background(), rec.RecordingID, tc.ts, tc.format, tc.match)
					if err != nil {
						t.Fatal(err)
					}
					if !media.Result.StartTS.Equal(frameTS(tc.want)) || media.ExactMatch != tc.exact {
						t.Fatalf("got frame at %v exact=%v, want %v exact=%v", media.Result.StartTS, media.ExactMatch, frameTS(tc.want), tc.exact)
					}
					if media.Result.MediaType != "frame" || media.Result.ContentType != "image/"+tc.format ||
						!media.Result.RequestedStartTS.Equal(tc.ts) || media.Result.EndTS != nil {
						t.Fatalf("unexpected result %+v", media.Result)
					}
					if tc.format == "png" {
						if got, want := pixels(t, media.Path, ""), referenceFrame(t, env.media, tc.want); got != want {
							t.Fatalf("frame pixels differ from frame %d", tc.want)
						}
					}
				})
			}
		})
	}
}

func TestFrameErrors(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	recording := env.addRecording(t, func(r *model.Recording) { r.State, r.EndTS = "recording", nil })
	expired := env.addRecording(t, func(r *model.Recording) { past := time.Now().Add(-time.Second); r.ExpiryTS = &past })
	cases := []struct {
		name   string
		id     string
		ts     time.Time
		format string
		match  string
		want   error
	}{
		{"before start", rec.RecordingID, fixtureStart.Add(-time.Nanosecond), "jpeg", "nearest", ErrNotCovered},
		{"at end", rec.RecordingID, fixtureEnd, "jpeg", "nearest", ErrNotCovered},
		{"exact missing", rec.RecordingID, frameTS(10).Add(5 * time.Millisecond), "jpeg", "exact", ErrFrameNotFound},
		{"not ready", recording.RecordingID, fixtureStart, "jpeg", "nearest", ErrNotReady},
		{"expired", expired.RecordingID, fixtureStart, "jpeg", "nearest", ErrNotFound},
		{"unknown", uuid.NewString(), fixtureStart, "jpeg", "nearest", ErrNotFound},
		{"bad format", rec.RecordingID, fixtureStart, "mp4", "nearest", ErrInvalidRequest},
		{"bad match", rec.RecordingID, fixtureStart, "jpeg", "closest", ErrInvalidRequest},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := env.svc.Frame(context.Background(), tc.id, tc.ts, tc.format, tc.match); !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
		})
	}
}

func TestBusy(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	for range maxConcurrentExtractions {
		env.svc.slots <- struct{}{}
	}
	if _, err := env.svc.Frame(context.Background(), rec.RecordingID, fixtureStart, "jpeg", "nearest"); !errors.Is(err, ErrBusy) {
		t.Fatalf("frame: got %v, want ErrBusy", err)
	}
	if _, err := env.svc.Clip(context.Background(), rec.RecordingID, fixtureStart, time.Second, "mp4"); !errors.Is(err, ErrBusy) {
		t.Fatalf("clip: got %v, want ErrBusy", err)
	}
	<-env.svc.slots
	if _, err := env.svc.Frame(context.Background(), rec.RecordingID, fixtureStart, "jpeg", "nearest"); err != nil {
		t.Fatalf("frame after a slot freed: %v", err)
	}
}

type probedClip struct {
	frames   int
	firstKey bool
}

func probeClip(t *testing.T, path string) probedClip {
	t.Helper()
	out := strings.TrimSpace(string(run(t, "ffprobe", "-v", "error", "-select_streams", "v:0",
		"-show_entries", "packet=flags", "-of", "csv=p=0", path)))
	lines := strings.Split(out, "\n")
	return probedClip{frames: len(lines), firstKey: strings.HasPrefix(lines[0], "K")}
}

func TestClip(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	cases := []struct {
		name      string
		start     time.Time
		duration  time.Duration
		wantStart int
		frames    int
		exact     bool
	}{
		// Frames 45..110 lie before start+duration.
		{"mid GOP starts on keyframe", frameTS(50).Add(time.Millisecond), 2 * time.Second, 45, 66, false},
		{"on keyframe", frameTS(90), time.Second, 90, 30, true},
		{"whole recording", fixtureStart, fixtureEnd.Sub(fixtureStart), 0, fixtureFrames, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			media, err := env.svc.Clip(context.Background(), rec.RecordingID, tc.start, tc.duration, "mp4")
			if err != nil {
				t.Fatal(err)
			}
			end := tc.start.Add(tc.duration)
			if !media.Result.StartTS.Equal(frameTS(tc.wantStart)) || media.ExactMatch != tc.exact ||
				media.Result.EndTS == nil || !media.Result.EndTS.Equal(end) ||
				media.Result.RequestedEndTS == nil || !media.Result.RequestedEndTS.Equal(end) ||
				media.Result.ContentType != "video/mp4" || media.Result.MediaType != "clip" {
				t.Fatalf("unexpected result %+v exact=%v", media.Result, media.ExactMatch)
			}
			got := probeClip(t, media.Path)
			if got.frames != tc.frames || !got.firstKey {
				t.Fatalf("clip has %d frames, first keyframe=%v; want %d frames from a keyframe", got.frames, got.firstKey, tc.frames)
			}
			if pixels(t, media.Path, "") != referenceFrame(t, env.media, tc.wantStart) {
				t.Fatalf("clip does not start with frame %d", tc.wantStart)
			}
		})
	}
	for _, tc := range []struct {
		name     string
		start    time.Time
		duration time.Duration
		want     error
	}{
		{"before start", fixtureStart.Add(-time.Millisecond), time.Second, ErrNotCovered},
		{"past end", frameTS(150), 2 * time.Second, ErrNotCovered},
		{"zero duration", fixtureStart, 0, ErrInvalidRequest},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := env.svc.Clip(context.Background(), rec.RecordingID, tc.start, tc.duration, "mp4"); !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
		})
	}
}

// TestSearchLimit shows that a frame or clip whose keyframe lies more than
// SearchLimit before it fails fast instead of reading from the recording start.
func TestSearchLimit(t *testing.T) {
	env := newEnvWithMedia(t, sparseFixture(t))
	rec := env.addRecording(t, func(r *model.Recording) {
		end := fixtureStart.Add(sparseFixtureFrames * time.Second)
		r.EndTS = &end
	})
	near, far := fixtureStart.Add(4*time.Minute+30*time.Second), fixtureStart.Add(5*time.Minute+30*time.Second)

	frame, err := env.svc.Frame(context.Background(), rec.RecordingID, near, "png", "exact")
	if err != nil || !frame.Result.StartTS.Equal(near) {
		t.Fatalf("frame within the limit: got %+v, %v", frame.Result, err)
	}
	if pixels(t, frame.Path, "") != referenceFrame(t, env.media, 270) {
		t.Fatal("frame within the limit has the wrong pixels")
	}
	clip, err := env.svc.Clip(context.Background(), rec.RecordingID, near, time.Second, "mp4")
	if err != nil || !clip.Result.StartTS.Equal(fixtureStart) {
		t.Fatalf("clip within the limit: got %+v, %v", clip.Result, err)
	}

	for _, match := range []string{"nearest", "exact"} {
		if _, err := env.svc.Frame(context.Background(), rec.RecordingID, far, "jpeg", match); !errors.Is(err, ErrBeyondSearchLimit) {
			t.Fatalf("frame %s beyond the limit: got %v, want ErrBeyondSearchLimit", match, err)
		}
	}
	if _, err := env.svc.Clip(context.Background(), rec.RecordingID, far, time.Second, "mp4"); !errors.Is(err, ErrBeyondSearchLimit) {
		t.Fatalf("clip beyond the limit: got %v, want ErrBeyondSearchLimit", err)
	}
}

func modTime(t *testing.T, path string) time.Time {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	return info.ModTime()
}

func TestDerivedTTL(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	ctx := context.Background()

	first, err := env.svc.Frame(ctx, rec.RecordingID, frameTS(30), "jpeg", "nearest")
	if err != nil {
		t.Fatal(err)
	}
	created := modTime(t, first.Path)
	if !first.Result.ExpiryTS.Equal(created.Add(derivedTTL)) {
		t.Fatalf("expiry %v, want mtime+%v = %v", first.Result.ExpiryTS, derivedTTL, created.Add(derivedTTL))
	}

	// A fresh file is reused as is.
	old := created.Add(-time.Minute)
	if err := os.Chtimes(first.Path, old, old); err != nil {
		t.Fatal(err)
	}
	again, err := env.svc.Frame(ctx, rec.RecordingID, frameTS(30), "jpeg", "nearest")
	if err != nil {
		t.Fatal(err)
	}
	if again.Path != first.Path || !modTime(t, again.Path).Equal(old) || !again.Result.ExpiryTS.Equal(old.Add(derivedTTL).UTC()) {
		t.Fatal("cached frame was not reused with its original TTL")
	}

	file, info, err := env.svc.OpenMedia(ctx, rec.RecordingID, first.Name)
	if err != nil {
		t.Fatal(err)
	}
	_ = file.Close()
	if info.ContentType != "image/jpeg" || !info.ExpiryTS.Equal(again.Result.ExpiryTS) {
		t.Fatalf("unexpected media info %+v", info)
	}

	// An expired file is refused, then cut again with a new TTL.
	stale := time.Now().Add(-derivedTTL - time.Second)
	if err := os.Chtimes(first.Path, stale, stale); err != nil {
		t.Fatal(err)
	}
	if _, _, err := env.svc.OpenMedia(ctx, rec.RecordingID, first.Name); !errors.Is(err, ErrMediaNotFound) {
		t.Fatalf("expired media: got %v, want ErrMediaNotFound", err)
	}
	renewed, err := env.svc.Frame(ctx, rec.RecordingID, frameTS(30), "jpeg", "nearest")
	if err != nil {
		t.Fatal(err)
	}
	if !modTime(t, renewed.Path).After(stale.Add(derivedTTL)) {
		t.Fatal("expired frame was not cut again")
	}

	// Unknown names, traversal and media.ts itself are not served.
	for _, name := range []string{"frame-1.jpeg", "../media.ts", "media.ts", "frame-1.gif", ".tmp-1.jpeg"} {
		if _, _, err := env.svc.OpenMedia(ctx, rec.RecordingID, name); !errors.Is(err, ErrMediaNotFound) {
			t.Fatalf("%q: got %v, want ErrMediaNotFound", name, err)
		}
	}
}

func TestDerivedTTLCappedByRecordingExpiry(t *testing.T) {
	env := newEnv(t, 0)
	soon := time.Now().Add(2 * time.Minute).UTC()
	rec := env.addRecording(t, func(r *model.Recording) { r.ExpiryTS = &soon })
	ctx := context.Background()

	media, err := env.svc.Clip(ctx, rec.RecordingID, fixtureStart, time.Second, "mp4")
	if err != nil {
		t.Fatal(err)
	}
	if !media.Result.ExpiryTS.Equal(soon) {
		t.Fatalf("expiry %v, want the recording's %v", media.Result.ExpiryTS, soon)
	}
	file, info, err := env.svc.OpenMedia(ctx, rec.RecordingID, media.Name)
	if err != nil {
		t.Fatal(err)
	}
	if body, _ := io.ReadAll(file); len(body) == 0 || info.ContentType != "video/mp4" || !info.ExpiryTS.Equal(soon) {
		t.Fatalf("unexpected media %+v (%d bytes)", info, len(body))
	}
	_ = file.Close()

	// Once the recording expires, its derived media goes with it even though
	// the clip's own TTL has 13 minutes left.
	env.svc.now = func() time.Time { return soon }
	if _, _, err := env.svc.OpenMedia(ctx, rec.RecordingID, media.Name); !errors.Is(err, ErrNotFound) {
		t.Fatalf("got %v, want ErrNotFound", err)
	}
	if _, err := env.svc.Clip(ctx, rec.RecordingID, fixtureStart, time.Second, "mp4"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("got %v, want ErrNotFound", err)
	}
}

func TestDeleteMediaRemovesDerived(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	media, err := env.svc.Frame(context.Background(), rec.RecordingID, fixtureStart, "jpeg", "nearest")
	if err != nil {
		t.Fatal(err)
	}
	if err := env.mediaStore.DeleteMedia(context.Background(), rec.RecordingPath); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Dir(media.Path)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("derived directory survived deletion: %v", err)
	}
}

func TestCancelledExtraction(t *testing.T) {
	env := newEnv(t, 0)
	rec := env.addRecording(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := env.svc.Clip(ctx, rec.RecordingID, fixtureStart, time.Second, "mp4"); !errors.Is(err, context.Canceled) {
		t.Fatalf("got %v, want context.Canceled", err)
	}
	entries, _ := os.ReadDir(filepath.Join(filepath.Dir(strings.TrimPrefix(rec.RecordingPath, "file://")), "derived"))
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".tmp-") {
			t.Fatalf("temporary file %s left behind", entry.Name())
		}
	}
}
