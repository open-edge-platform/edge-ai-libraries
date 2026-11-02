// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func testBuffer(t *testing.T, length int) *RollingBuffer {
	t.Helper()
	b, err := newRollingBuffer(t.TempDir(), time.Duration(length)*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := b.Close(); err != nil {
			t.Error(err)
		}
	})
	return b
}

func addTestSlice(t *testing.T, b *RollingBuffer, seq int, start, closedAt time.Time) model.BufferSlice {
	t.Helper()
	path := filepath.Join(b.root.Name(), sliceName(seq))
	if err := os.WriteFile(path, fmt.Appendf([]byte{}, "slice-%d", seq), 0o600); err != nil {
		t.Fatal(err)
	}
	s := model.BufferSlice{
		SeqNo: seq, StartTS: start, EndTS: start.Add(time.Second), Path: path,
		PTSStart: (seq - 1) * 90000, PTSEnd: seq * 90000,
	}
	if err := b.addSlice(s, closedAt); err != nil {
		t.Fatal(err)
	}
	return s
}

func requireLease(t *testing.T, b *RollingBuffer, start, end time.Time) *BufferLease {
	t.Helper()
	lease, err := b.Acquire(context.Background(), start, end)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := lease.Close(); err != nil {
			t.Error(err)
		}
	})
	return lease
}

func readSlice(t *testing.T, lease *BufferLease, seq int) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	reader, err := lease.Next(ctx)
	if err != nil {
		t.Fatal(err)
	}
	data, err := io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != fmt.Sprintf("slice-%d", seq) || reader.Slice.SeqNo != seq {
		t.Fatalf("unexpected slice: %s, %+v", data, reader.Slice)
	}
	if err := reader.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestRollingBufferReserveReadAndFollow(t *testing.T) {
	b := testBuffer(t, 30)
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	closed := time.Now()
	first := addTestSlice(t, b, 1, start, closed)
	second := addTestSlice(t, b, 2, first.EndTS, closed)
	lease := requireLease(t, b, start.Add(500*time.Millisecond), second.EndTS.Add(time.Second))
	other := requireLease(t, b, start, second.EndTS)
	snapshot := b.snapshot()
	if snapshot.Slices[0].RefCount != 2 || snapshot.Slices[1].RefCount != 2 ||
		snapshot.BufferStat.HeldBytes != 14 {
		t.Fatalf("unexpected snapshot: %+v", snapshot)
	}
	snapshot.Slices[0].SeqNo = 999
	if b.snapshot().Slices[0].SeqNo != 1 {
		t.Fatal("snapshot aliases buffer metadata")
	}
	readSlice(t, lease, 1)
	readSlice(t, lease, 2)
	if err := other.Close(); err != nil {
		t.Fatal(err)
	}
	if b.snapshot().Slices[0].RefCount != 0 {
		t.Fatal("released references remain")
	}
	addTestSlice(t, b, 3, second.EndTS, closed)
	readSlice(t, lease, 3)
	if _, err := lease.Next(context.Background()); !errors.Is(err, io.EOF) {
		t.Fatalf("completed lease: %v", err)
	}
	if lease.Err() != nil || b.hasReaders() {
		t.Fatal("completed lease retained readers or failed")
	}
}

func TestRollingBufferGraceClosesOpenReaders(t *testing.T) {
	b := testBuffer(t, 10)
	closed := time.Now()
	first := addTestSlice(t, b, 1, time.Unix(100, 0).UTC(), closed)
	lease := requireLease(t, b, first.StartTS, time.Time{})
	reader, err := lease.Next(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	file := reader.file
	for _, elapsed := range []time.Duration{10 * time.Second, 10*time.Second + readerGrace - time.Nanosecond} {
		if err := b.expire(closed.Add(elapsed)); err != nil {
			t.Fatal(err)
		}
		if len(b.snapshot().Slices) != 1 || lease.Err() != nil {
			t.Fatal("referenced slice expired before its hard deadline")
		}
	}
	if err := b.expire(closed.Add(10*time.Second + readerGrace)); err != nil {
		t.Fatal(err)
	}
	if !errors.Is(lease.Err(), ErrSliceExpired) {
		t.Fatalf("lease expiry: %v", lease.Err())
	}
	if _, err := reader.Read(make([]byte, 1)); !errors.Is(err, ErrSliceExpired) {
		t.Fatalf("open reader was not revoked: %v", err)
	}
	if _, err := file.Stat(); !errors.Is(err, os.ErrClosed) {
		t.Fatalf("owned descriptor is still open: %v", err)
	}
	if _, err := os.Stat(first.Path); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("expired file remains: %v", err)
	}
	if len(b.snapshot().Slices) != 0 || b.hasReaders() {
		t.Fatal("expired metadata or references remain")
	}
	if _, err := lease.Next(context.Background()); !errors.Is(err, ErrSliceExpired) {
		t.Fatalf("expiry was not delivered to the worker: %v", err)
	}
}

func TestRollingBufferExpiryUsesArrivalNotNTP(t *testing.T) {
	for _, year := range []int{1971, 2200} {
		t.Run(fmt.Sprint(year), func(t *testing.T) {
			b := testBuffer(t, 5)
			closed := time.Now()
			addTestSlice(t, b, 1, time.Date(year, 1, 1, 0, 0, 0, 0, time.UTC), closed)
			if err := b.expire(closed.Add(5*time.Second - time.Nanosecond)); err != nil {
				t.Fatal(err)
			}
			if len(b.snapshot().Slices) != 1 {
				t.Fatal("slice expired based on source wall clock")
			}
			if err := b.expire(closed.Add(5 * time.Second)); err != nil {
				t.Fatal(err)
			}
			if len(b.snapshot().Slices) != 0 {
				t.Fatal("unreferenced slice survived normal expiry")
			}
		})
	}
}

func TestRollingBufferLateReaderDoesNotResetGrace(t *testing.T) {
	b := testBuffer(t, 1)
	closed := time.Now()
	s := addTestSlice(t, b, 1, time.Unix(100, 0).UTC(), closed)
	first := requireLease(t, b, s.StartTS, s.EndTS)
	if err := b.expire(closed.Add(50 * time.Second)); err != nil {
		t.Fatal(err)
	}
	second := requireLease(t, b, s.StartTS, s.EndTS)
	if err := first.Close(); err != nil {
		t.Fatal(err)
	}
	if err := b.expire(closed.Add(time.Second + readerGrace)); err != nil {
		t.Fatal(err)
	}
	if !errors.Is(second.Err(), ErrSliceExpired) {
		t.Fatal("a later acquisition extended the slice's deadline")
	}
}

func TestRollingBufferCancellationAndFailure(t *testing.T) {
	b := testBuffer(t, 30)
	start := time.Unix(100, 0).UTC()
	ctx, cancel := context.WithCancel(context.Background())
	lease, err := b.Acquire(ctx, start, time.Time{})
	if err != nil {
		t.Fatal(err)
	}
	cancel()
	if _, err := lease.Next(context.Background()); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation did not wake a waiting reader: %v", err)
	}
	if b.hasReaders() {
		t.Fatal("cancelled lease kept references")
	}
	s := addTestSlice(t, b, 1, start, time.Now())
	historical := requireLease(t, b, s.StartTS, s.EndTS)
	live := requireLease(t, b, s.StartTS, time.Time{})
	b.fail(ErrSourceFailed)
	readSlice(t, historical, 1)
	if _, err := historical.Next(context.Background()); !errors.Is(err, io.EOF) {
		t.Fatalf("completed historical range was lost: %v", err)
	}
	if _, err := live.Next(context.Background()); !errors.Is(err, ErrSourceFailed) {
		t.Fatalf("live reader did not fail: %v", err)
	}
}

func TestRollingBufferRejectsGapsAndUnsafePaths(t *testing.T) {
	b := testBuffer(t, 10)
	closed := time.Now()
	start := time.Unix(100, 0).UTC()
	first := addTestSlice(t, b, 1, start, closed)
	second := addTestSlice(t, b, 2, first.EndTS, closed)
	addTestSlice(t, b, 3, second.EndTS, closed.Add(5*time.Second))
	lease := requireLease(t, b, first.StartTS, first.EndTS)
	if err := b.expire(closed.Add(10 * time.Second)); err != nil {
		t.Fatal(err)
	}
	if _, err := b.Get(start, start.Add(3*time.Second)); !errors.Is(err, ErrHistoryUnavailable) {
		t.Fatalf("gap was not rejected: %v", err)
	}
	if err := lease.Close(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{"../outside.ts", filepath.Join(b.root.Name(), "different.ts")} {
		err := b.addSlice(model.BufferSlice{
			SeqNo: 4, StartTS: start.Add(3 * time.Second), EndTS: start.Add(4 * time.Second),
			PTSStart: 270000, PTSEnd: 360000, Path: path,
		}, closed)
		if !errors.Is(err, ErrInvalidRequest) {
			t.Fatalf("unsafe path was accepted: %v", err)
		}
	}
}

func TestRollingBufferResize(t *testing.T) {
	b := testBuffer(t, 10)
	now := time.Now()
	start := time.Unix(100, 0).UTC()
	oldest := addTestSlice(t, b, 1, start, now.Add(-9*time.Second))
	newest := addTestSlice(t, b, 2, oldest.EndTS, now.Add(-1*time.Second))

	// Growing keeps every existing slice untouched.
	if err := b.resize(20 * time.Second); err != nil {
		t.Fatal(err)
	}
	if snap := b.snapshot(); len(snap.Slices) != 2 || snap.BufferStat.Capacity != 20 {
		t.Fatalf("grow altered slices: %+v", snap)
	}

	// Requesting the same length is a no-op.
	if err := b.resize(20 * time.Second); err != nil {
		t.Fatal(err)
	}
	if snap := b.snapshot(); len(snap.Slices) != 2 {
		t.Fatalf("no-op altered slices: %+v", snap)
	}

	// Shrinking discards slices that no longer fit the smaller window.
	if err := b.resize(2 * time.Second); err != nil {
		t.Fatal(err)
	}
	snap := b.snapshot()
	if len(snap.Slices) != 1 || snap.Slices[0].SeqNo != newest.SeqNo || snap.BufferStat.Capacity != 2 {
		t.Fatalf("shrink did not discard the oldest slice: %+v", snap)
	}
	if _, err := os.Stat(filepath.Join(b.root.Name(), sliceName(oldest.SeqNo))); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("discarded slice file was not removed: %v", err)
	}

	if err := b.Close(); err != nil {
		t.Fatal(err)
	}
	if err := b.resize(5 * time.Second); !errors.Is(err, ErrBufferClosed) {
		t.Fatalf("resize on closed buffer: %v", err)
	}
}

func TestLeaseEndAndTerminalNotification(t *testing.T) {
	b := testBuffer(t, 30)
	start := time.Unix(100, 0).UTC()
	for seq := 1; seq <= 3; seq++ {
		addTestSlice(t, b, seq, start.Add(time.Duration(seq-1)*time.Second), time.Now())
	}
	lease := requireLease(t, b, start.Add(250*time.Millisecond), time.Time{})
	if !lease.StartTime().Equal(start) {
		t.Fatal("lease did not expose the enclosing starting keyframe")
	}
	end := start.Add(1500 * time.Millisecond)
	if err := lease.SetEnd(end); err != nil {
		t.Fatal(err)
	}
	if err := lease.SetEnd(end.Add(time.Second)); !errors.Is(err, ErrInvalidRequest) {
		t.Fatalf("fixed end was changed: %v", err)
	}
	if b.snapshot().Slices[2].RefCount != 0 {
		t.Fatal("fixing the end retained later slices")
	}
	readSlice(t, lease, 1)
	readSlice(t, lease, 2)
	if _, err := lease.Next(context.Background()); !errors.Is(err, io.EOF) {
		t.Fatal(err)
	}
	select {
	case <-lease.Done():
	default:
		t.Fatal("completed lease did not notify its worker")
	}
	if lease.Err() != nil || b.hasReaders() {
		t.Fatal("completed fixed lease retained references")
	}
}

func TestRollingBufferConcurrentReaders(t *testing.T) {
	b := testBuffer(t, 30)
	start := time.Unix(100, 0).UTC()
	addTestSlice(t, b, 1, start, time.Now())
	var wg sync.WaitGroup
	for range 20 {
		wg.Go(func() {
			for range 10 {
				lease, err := b.Acquire(context.Background(), start, start.Add(time.Second))
				if err != nil {
					t.Error(err)
					return
				}
				reader, err := lease.Next(context.Background())
				if err != nil {
					t.Error(err)
					return
				}
				if _, err := io.Copy(io.Discard, reader); err != nil {
					t.Error(err)
				}
				if err := reader.Close(); err != nil {
					t.Error(err)
				}
				if err := lease.Close(); err != nil {
					t.Error(err)
				}
				b.snapshot()
			}
		})
	}
	wg.Wait()
	if b.hasReaders() || b.snapshot().Slices[0].RefCount != 0 {
		t.Fatal("concurrent readers leaked references")
	}
}
