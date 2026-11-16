// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package gpu

import (
	"bufio"
	"context"
	"errors"
	"io/fs"
	"os"
	"time"
)

// maxLineBytes bounds a single JSON line.
//
// qmassa keeps a rolling window of 40 samples, which is roughly 30 kB per GPU,
// so this leaves ample headroom for a many-GPU host while still refusing to
// allocate without limit if the stream is corrupt. bufio.Scanner would
// otherwise cap lines at 64 kB and fail on any host with more than one GPU.
const maxLineBytes = 8 << 20

// Backoff timings for a stream that is not producing data.
const (
	// defaultRetryDelay paces reopen attempts. Tests pass a shorter value to
	// followWithRetry so they assert behaviour instead of the wall clock.
	defaultRetryDelay = time.Second

	// maxFastRetries is how many times to retry quickly before assuming the
	// host simply has no Intel GPU.
	maxFastRetries = 5

	// idleDelay keeps the process alive but quiet once that conclusion is
	// reached. Exiting instead would make Telegraf respawn the plugin every
	// few seconds and fill its log.
	idleDelay = time.Hour
)

// Logf reports a notable transition, such as the stream disappearing.
type Logf func(format string, args ...any)

// Follow reads qmassa's JSON stream and calls onLine for every non-empty line,
// reopening the stream whenever the writer restarts.
//
// It returns only when ctx is cancelled: a missing or broken stream is a
// normal condition on a host without an Intel GPU and is retried rather than
// reported as an error.
func Follow(ctx context.Context, path string, onLine func([]byte), logf Logf) {
	followWithRetry(ctx, path, onLine, logf, defaultRetryDelay)
}

// followWithRetry is Follow with the reopen pause injected.
func followWithRetry(ctx context.Context, path string, onLine func([]byte), logf Logf, retryDelay time.Duration) {
	failures := 0
	warnedMissing := false
	announcedIdle := false

	for ctx.Err() == nil {
		err := readOnce(ctx, path, onLine)

		switch {
		case ctx.Err() != nil:
			return

		case err == nil:
			// The writer closed the stream cleanly; reopen it. This is the
			// normal path when qmassa is restarted.
			if warnedMissing {
				logf("qmassa stream %s is available again, resuming", path)
			}
			failures, warnedMissing, announcedIdle = 0, false, false

			// Reopening a FIFO blocks until a writer returns, but if the path
			// is a regular file it succeeds instantly and reaches EOF again,
			// so pausing here is what stops that becoming a busy loop.
			if !sleep(ctx, retryDelay) {
				return
			}
			continue

		case errors.Is(err, fs.ErrNotExist):
			failures++
			if !warnedMissing {
				logf("qmassa stream %s not found; is qmassa running and an Intel GPU present?", path)
				warnedMissing = true
			}

		default:
			failures++
			logf("reading qmassa stream %s: %v", path, err)
		}

		delay := retryDelay
		if failures >= maxFastRetries {
			if !announcedIdle {
				logf("qmassa stream %s still unavailable after %d attempts; retrying every %s from now on, silently",
					path, maxFastRetries, idleDelay)
				announcedIdle = true
			}
			delay = idleDelay
		}
		if !sleep(ctx, delay) {
			return
		}
	}
}

// readOnce opens the stream and consumes it until the writer closes it.
func readOnce(ctx context.Context, path string, onLine func([]byte)) error {
	file, err := open(ctx, path)
	if err != nil {
		return err
	}
	defer file.Close()

	// Closing the file unblocks a read that is waiting for more data, so
	// cancellation takes effect even mid-stream.
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			file.Close()
		case <-done:
		}
	}()

	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 0, 64*1024), maxLineBytes)

	for scanner.Scan() {
		if line := scanner.Bytes(); len(line) > 0 {
			onLine(line)
		}
	}

	if err := scanner.Err(); err != nil && ctx.Err() == nil {
		return err
	}
	return nil
}

// open opens the stream without blocking cancellation.
//
// Opening a FIFO for reading blocks until a writer arrives, which would
// otherwise make the process ignore SIGTERM until qmassa starts.
func open(ctx context.Context, path string) (*os.File, error) {
	type result struct {
		file *os.File
		err  error
	}
	// The channel is buffered so the goroutine can finish and be collected
	// even after cancellation.
	opened := make(chan result, 1)

	go func() {
		file, err := os.Open(path)
		opened <- result{file, err}
	}()

	select {
	case r := <-opened:
		return r.file, r.err
	case <-ctx.Done():
		// Hand the descriptor back to the OS if the open later succeeds.
		go func() {
			if r := <-opened; r.err == nil {
				r.file.Close()
			}
		}()
		return nil, ctx.Err()
	}
}

// sleep waits for d, reporting false if ctx was cancelled first.
func sleep(ctx context.Context, d time.Duration) bool {
	timer := time.NewTimer(d)
	defer timer.Stop()

	select {
	case <-timer.C:
		return true
	case <-ctx.Done():
		return false
	}
}
