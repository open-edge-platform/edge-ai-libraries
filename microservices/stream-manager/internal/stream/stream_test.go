// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func idleIngest(ctx context.Context, _, _ string, _ *RollingBuffer, _ func(bool), _ func(), _ time.Duration) error {
	<-ctx.Done()
	return ctx.Err()
}

func TestServiceLifecycleAndIsolation(t *testing.T) {
	s := testService(t, 30)
	s.ingest = idleIngest
	foreign := filepath.Join(s.root.Name(), "another-instance")
	if err := os.Mkdir(foreign, 0o700); err != nil {
		t.Fatal(err)
	}
	var successes atomic.Int32
	var wg sync.WaitGroup
	for range 16 {
		wg.Go(func() {
			_, err := s.CreateBuffer(context.Background(), "rtsp://camera.invalid/live", "camera", 0)
			if err == nil {
				successes.Add(1)
			} else if !errors.Is(err, ErrStreamExists) {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	if successes.Load() != 1 {
		t.Fatal("duplicate sensor attachments were admitted")
	}
	streams, err := s.ListStreams(context.Background())
	if err != nil || len(streams) != 1 {
		t.Fatalf("list: %+v %v", streams, err)
	}
	id := streams[0].StreamID
	if _, err := s.ResizeBuffer(context.Background(), id, 45); !errors.Is(err, ErrNotImplemented) {
		t.Fatalf("resize must report not implemented: %v", err)
	}
	lease, err := s.AcquireBuffer(context.Background(), id, time.Now(), time.Time{})
	if err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveBuffer(context.Background(), id); !errors.Is(err, ErrActiveReaders) {
		t.Fatalf("detach with live reader: %v", err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if !errors.Is(lease.Err(), ErrBufferClosed) {
		t.Fatalf("shutdown did not revoke readers: %v", lease.Err())
	}
	if _, err := os.Stat(foreign); err != nil {
		t.Fatalf("another instance's directory was removed: %v", err)
	}
	if _, err := os.Stat(filepath.Join(s.cfg.BufferDir, "camera-"+id)); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("owned buffer directory was not removed: %v", err)
	}
}

func TestServiceExpiresWhileIngestIsIdle(t *testing.T) {
	s := testService(t, 1)
	s.ingest = idleIngest
	id, err := s.CreateBuffer(context.Background(), "rtsp://camera.invalid/live", "camera", 0)
	if err != nil {
		t.Fatal(err)
	}
	entry := s.streams[id]
	slice := addTestSlice(t, entry.buffer, 1, time.Unix(100, 0).UTC(), time.Now())
	lease := requireLease(t, entry.buffer, slice.StartTS, time.Time{})
	entry.buffer.mu.Lock()
	entry.buffer.slices[0].closedAt = time.Now().Add(-time.Second - readerGrace)
	entry.buffer.mu.Unlock()
	deadline := time.After(2 * time.Second)
	for lease.Err() == nil {
		select {
		case <-deadline:
			t.Fatal("maintenance stopped when ingest was idle")
		case <-time.After(10 * time.Millisecond):
		}
	}
	if !errors.Is(lease.Err(), ErrSliceExpired) {
		t.Fatal(lease.Err())
	}
}

func TestServiceRejectsUnsafeSourcesAndPaths(t *testing.T) {
	s := testService(t, 30)
	s.ingest = idleIngest
	for _, sensor := range []string{"", "../escape", "/absolute", "a/b", `a\b`} {
		if _, err := s.CreateBuffer(context.Background(), "rtsp://camera.invalid/live", sensor, 0); !errors.Is(err, ErrInvalidRequest) {
			t.Fatalf("unsafe sensor %q: %v", sensor, err)
		}
	}
	for _, source := range []string{"file:///etc/passwd", "http://camera.invalid", "rtsp://", "not-a-uri"} {
		if _, err := s.CreateBuffer(context.Background(), source, "camera", 0); !errors.Is(err, ErrUnsupportedSource) {
			t.Fatalf("unsafe source %q: %v", source, err)
		}
	}
}

func TestServiceBufferLength(t *testing.T) {
	s := testService(t, 30)
	s.ingest = idleIngest
	for _, length := range []time.Duration{-time.Second, time.Second, 301 * time.Second} {
		if _, err := s.CreateBuffer(context.Background(), "rtsp://camera.invalid/live", "camera", length); !errors.Is(err, ErrInvalidRequest) {
			t.Fatalf("buffer length %v: %v", length, err)
		}
	}
	for sensor, want := range map[string]int{"default": 30, "explicit": 60} {
		length := time.Duration(0)
		if sensor == "explicit" {
			length = 60 * time.Second
		}
		id, err := s.CreateBuffer(context.Background(), "rtsp://camera.invalid/live", sensor, length)
		if err != nil {
			t.Fatal(err)
		}
		info, err := s.GetStream(context.Background(), id)
		if err != nil || info.BufferStat.Capacity != want {
			t.Fatalf("%s capacity: %+v %v", sensor, info.BufferStat, err)
		}
	}
}
