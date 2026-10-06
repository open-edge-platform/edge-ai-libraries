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
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

const readerGrace = time.Minute

// RollingBuffer owns closed slices and revocable readers, not an open FFmpeg slice.
type RollingBuffer struct {
	mu       sync.Mutex
	root     *os.Root
	capacity time.Duration
	slices   []*bufferSlice
	leases   map[*BufferLease]struct{}
	changed  chan struct{}
	lastSeq  int
	lastEnd  time.Time
	failure  error
	closed   bool
}

type bufferSlice struct {
	media    model.BufferSlice
	closedAt time.Time
	leases   map[*BufferLease]struct{}
}

// BufferLease reserves a time range. A zero end follows the live stream until Close.
// Callers must close each SliceReader and the lease, and check Err before using
// the completed result. Its acquisition context controls the lease's lifetime.
type BufferLease struct {
	buffer      *RollingBuffer
	start       time.Time
	end         time.Time
	coveredEnd  time.Time
	pending     []*bufferSlice
	refs        map[*bufferSlice]struct{}
	active      *SliceReader
	stopContext func() bool
	closed      bool
	err         error
	closeErr    error
	done        chan struct{}
	actualStart time.Time
}

// SliceReader is a buffer-owned file handle that becomes unreadable on revocation.
type SliceReader struct {
	Slice model.BufferSlice
	mu    sync.Mutex
	lease *BufferLease
	entry *bufferSlice
	file  *os.File
	err   error
}

func newRollingBuffer(directory string, length time.Duration) (*RollingBuffer, error) {
	root, err := os.OpenRoot(directory)
	if err != nil {
		return nil, fmt.Errorf("open buffer directory: %w", err)
	}
	return &RollingBuffer{
		root:     root,
		capacity: length,
		leases:   make(map[*BufferLease]struct{}),
		changed:  make(chan struct{}),
	}, nil
}

func sliceName(seq int) string {
	return fmt.Sprintf("S%04d.ts", seq)
}

func (b *RollingBuffer) signalLocked() {
	close(b.changed)
	b.changed = make(chan struct{})
}

func (s *bufferSlice) snapshot() model.BufferSlice {
	media := s.media
	media.RefCount = len(s.leases)
	if media.KeyframeTS != nil {
		t := *media.KeyframeTS
		media.KeyframeTS = &t
	}
	return media
}

func (b *RollingBuffer) addSlice(media model.BufferSlice, closedAt time.Time) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.closed {
		return ErrBufferClosed
	}
	if b.failure != nil {
		return b.failure
	}
	if media.SeqNo != b.lastSeq+1 || media.StartTS.IsZero() ||
		!media.EndTS.After(media.StartTS) || media.PTSEnd <= media.PTSStart ||
		(!b.lastEnd.IsZero() && !media.StartTS.Equal(b.lastEnd)) {
		return fmt.Errorf("%w: discontinuous slice timing or sequence", ErrSourceFailed)
	}
	name := sliceName(media.SeqNo)
	if media.Path != filepath.Join(b.root.Name(), name) {
		return fmt.Errorf("%w: invalid slice path", ErrInvalidRequest)
	}
	info, err := b.root.Lstat(name)
	if err != nil {
		return fmt.Errorf("stat closed slice: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() == 0 {
		return fmt.Errorf("%w: slice is not a nonempty regular file", ErrSourceFailed)
	}
	media.SizeBytes, media.RefCount = info.Size(), 0
	entry := &bufferSlice{media: media, closedAt: closedAt, leases: make(map[*BufferLease]struct{})}
	b.slices = append(b.slices, entry)
	b.lastSeq, b.lastEnd = media.SeqNo, media.EndTS
	for lease := range b.leases {
		if !media.EndTS.After(lease.start) ||
			(!lease.end.IsZero() && !media.StartTS.Before(lease.end)) {
			continue
		}
		if media.StartTS.After(lease.coveredEnd) {
			lease.finishLocked(ErrHistoryUnavailable)
			continue
		}
		lease.reserveLocked(entry)
	}
	b.signalLocked()
	return b.expireLocked(time.Now())
}

func (b *RollingBuffer) snapshot() model.StreamBuffer {
	b.mu.Lock()
	defer b.mu.Unlock()
	var result model.StreamBuffer
	result.BufferStat.Capacity = int(b.capacity / time.Second)
	result.Slices = make([]model.BufferSlice, 0, len(b.slices))
	for _, entry := range b.slices {
		result.Slices = append(result.Slices, entry.snapshot())
		result.BufferStat.HeldBytes += entry.media.SizeBytes
	}
	if len(b.slices) != 0 {
		result.BufferStat.OldestTS = b.slices[0].media.StartTS
		result.BufferStat.NewestTS = b.slices[len(b.slices)-1].media.EndTS
	}
	return result
}

func (b *RollingBuffer) selectLocked(start, end time.Time, follow bool) ([]*bufferSlice, error) {
	if b.closed {
		return nil, ErrBufferClosed
	}
	if start.IsZero() || (!end.IsZero() && !end.After(start)) {
		return nil, fmt.Errorf("%w: end must be after a nonzero start", ErrInvalidRequest)
	}
	target := end
	if target.IsZero() || (follow && target.After(b.lastEnd)) {
		target = b.lastEnd
	}
	if !follow && (target.IsZero() || target.After(b.lastEnd) || !target.After(start)) {
		return nil, ErrHistoryUnavailable
	}
	cursor := start
	var selected []*bufferSlice
	for _, entry := range b.slices {
		if !entry.media.EndTS.After(start) {
			continue
		}
		if !end.IsZero() && !entry.media.StartTS.Before(end) {
			break
		}
		if entry.media.StartTS.After(cursor) {
			return nil, ErrHistoryUnavailable
		}
		selected = append(selected, entry)
		cursor = entry.media.EndTS
	}
	if cursor.Before(target) {
		return nil, ErrHistoryUnavailable
	}
	if follow && b.failure != nil && (end.IsZero() || end.After(cursor)) {
		return nil, b.failure
	}
	return selected, nil
}

// Get returns metadata only; use Acquire when the files must remain readable.
func (b *RollingBuffer) Get(start, end time.Time) ([]model.BufferSlice, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	entries, err := b.selectLocked(start, end, false)
	if err != nil {
		return nil, err
	}
	result := make([]model.BufferSlice, 0, len(entries))
	for _, entry := range entries {
		result = append(result, entry.snapshot())
	}
	return result, nil
}

// Acquire selects history and subscribes to future slices in the same locked step.
func (b *RollingBuffer) Acquire(ctx context.Context, start, end time.Time) (*BufferLease, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if err := b.expireLocked(time.Now()); err != nil {
		return nil, err
	}
	entries, err := b.selectLocked(start, end, true)
	if err != nil {
		return nil, err
	}
	lease := &BufferLease{
		buffer: b, start: start, end: end, coveredEnd: start,
		refs: make(map[*bufferSlice]struct{}),
		done: make(chan struct{}), actualStart: b.lastEnd,
	}
	if len(entries) != 0 {
		lease.actualStart = entries[0].media.StartTS
	}
	for _, entry := range entries {
		lease.reserveLocked(entry)
	}
	b.leases[lease] = struct{}{}
	lease.stopContext = context.AfterFunc(ctx, func() {
		b.mu.Lock()
		defer b.mu.Unlock()
		lease.finishLocked(ctx.Err())
	})
	return lease, nil
}

func (l *BufferLease) reserveLocked(entry *bufferSlice) {
	entry.leases[l] = struct{}{}
	l.refs[entry] = struct{}{}
	l.pending = append(l.pending, entry)
	l.coveredEnd = entry.media.EndTS
}

// Next waits for a closed slice. Close the previous reader before calling it again.
func (l *BufferLease) Next(ctx context.Context) (*SliceReader, error) {
	b := l.buffer
	for {
		b.mu.Lock()
		if l.closed {
			err := l.err
			b.mu.Unlock()
			if err == nil {
				err = io.EOF
			}
			return nil, err
		}
		if err := ctx.Err(); err != nil {
			b.mu.Unlock()
			return nil, err
		}
		if l.active != nil {
			b.mu.Unlock()
			return nil, errors.New("close the current slice reader before requesting another")
		}
		if len(l.pending) != 0 {
			entry := l.pending[0]
			file, err := b.root.Open(sliceName(entry.media.SeqNo))
			if err != nil {
				err = fmt.Errorf("open reserved slice: %w", err)
				l.finishLocked(err)
				b.mu.Unlock()
				return nil, err
			}
			l.pending[0] = nil
			l.pending = l.pending[1:]
			reader := &SliceReader{Slice: entry.snapshot(), file: file, lease: l, entry: entry}
			l.active = reader
			b.mu.Unlock()
			return reader, nil
		}
		if !l.end.IsZero() && !l.coveredEnd.Before(l.end) {
			l.finishLocked(nil)
			b.mu.Unlock()
			return nil, io.EOF
		}
		if b.failure != nil {
			err := b.failure
			l.finishLocked(err)
			b.mu.Unlock()
			return nil, err
		}
		changed := b.changed
		b.mu.Unlock()
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-changed:
		}
	}
}

func (r *SliceReader) Read(p []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.err != nil {
		return 0, r.err
	}
	if r.file == nil {
		return 0, os.ErrClosed
	}
	return r.file.Read(p)
}

func (r *SliceReader) closeLocked(cause error) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if cause != nil {
		r.err = cause
	}
	if r.file != nil {
		err := r.file.Close()
		r.file = nil
		r.err = errors.Join(r.err, err)
		return err
	}
	return nil
}

// Close releases this slice's reference, including when Read reached EOF.
func (r *SliceReader) Close() error {
	b := r.lease.buffer
	b.mu.Lock()
	defer b.mu.Unlock()
	err := r.closeLocked(nil)
	r.mu.Lock()
	err = errors.Join(err, r.err)
	r.mu.Unlock()
	delete(r.entry.leases, r.lease)
	delete(r.lease.refs, r.entry)
	if r.lease.active == r {
		r.lease.active = nil
	}
	b.signalLocked()
	return err
}

func (l *BufferLease) finishLocked(cause error) {
	if l.closed {
		return
	}
	l.closed, l.err = true, cause
	close(l.done)
	if l.stopContext != nil {
		l.stopContext()
	}
	if l.active != nil {
		l.closeErr = l.active.closeLocked(cause)
		l.err = errors.Join(l.err, l.closeErr)
		l.active = nil
	}
	for entry := range l.refs {
		delete(entry.leases, l)
	}
	l.refs, l.pending = nil, nil
	delete(l.buffer.leases, l)
	l.buffer.signalLocked()
}

// Err reports revocation or a source failure, including after the last file read.
func (l *BufferLease) Err() error {
	l.buffer.mu.Lock()
	defer l.buffer.mu.Unlock()
	return l.err
}

func (l *BufferLease) Done() <-chan struct{} { return l.done }

func (l *BufferLease) StartTime() time.Time {
	l.buffer.mu.Lock()
	defer l.buffer.mu.Unlock()
	return l.actualStart
}

// SetEnd fixes an open lease's end; already-reserved later slices are released.
func (l *BufferLease) SetEnd(end time.Time) error {
	l.buffer.mu.Lock()
	defer l.buffer.mu.Unlock()
	if l.closed {
		return ErrLeaseClosed
	}
	if !end.After(l.start) || (!l.end.IsZero() && !end.Equal(l.end)) ||
		(l.active != nil && !l.active.entry.media.StartTS.Before(end)) {
		return ErrInvalidRequest
	}
	l.end = end
	kept := l.pending[:0]
	for _, entry := range l.pending {
		if entry.media.StartTS.Before(end) {
			kept = append(kept, entry)
		} else {
			delete(entry.leases, l)
			delete(l.refs, entry)
		}
	}
	clear(l.pending[len(kept):])
	l.pending = kept
	l.buffer.signalLocked()
	return nil
}

func (l *BufferLease) Close() error {
	l.buffer.mu.Lock()
	defer l.buffer.mu.Unlock()
	l.finishLocked(ErrLeaseClosed)
	return l.closeErr
}

func (b *RollingBuffer) expire(now time.Time) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.closed {
		return ErrBufferClosed
	}
	return b.expireLocked(now)
}

func (b *RollingBuffer) expireLocked(now time.Time) error {
	kept := b.slices[:0]
	var result error
	for _, entry := range b.slices {
		expires := entry.closedAt.Add(b.capacity)
		if now.Before(expires) || (len(entry.leases) != 0 && now.Before(expires.Add(readerGrace))) {
			kept = append(kept, entry)
			continue
		}
		for lease := range entry.leases {
			lease.finishLocked(ErrSliceExpired)
			result = errors.Join(result, lease.closeErr)
		}
		if err := b.root.Remove(sliceName(entry.media.SeqNo)); err != nil {
			result = errors.Join(result, fmt.Errorf("remove expired slice: %w", err))
			kept = append(kept, entry)
		}
	}
	clear(b.slices[len(kept):])
	b.slices = kept
	b.signalLocked()
	return result
}

func (b *RollingBuffer) fail(err error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.failure == nil {
		b.failure = err
	}
	for lease := range b.leases {
		if lease.end.IsZero() || lease.end.After(lease.coveredEnd) {
			lease.finishLocked(b.failure)
		}
	}
	b.signalLocked()
}

func (b *RollingBuffer) hasReaders() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.leases) != 0
}

func (b *RollingBuffer) Close() error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.closed {
		return nil
	}
	b.closed = true
	var result error
	for lease := range b.leases {
		lease.finishLocked(ErrBufferClosed)
		result = errors.Join(result, lease.closeErr)
	}
	for _, entry := range b.slices {
		result = errors.Join(result, b.root.Remove(sliceName(entry.media.SeqNo)))
	}
	b.slices = nil
	b.signalLocked()
	return errors.Join(result, b.root.Close())
}
