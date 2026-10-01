// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package record

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
)

func (s *Service) writeMedia(j *job) (start, end time.Time, size int64, codec string, result error) {
	ctx, cancel := context.WithCancel(j.ctx)
	defer cancel()
	watchDone := make(chan struct{})
	go func() {
		defer close(watchDone)
		select {
		case <-j.lease.Done():
			if j.lease.Err() != nil {
				cancel()
			}
		case <-ctx.Done():
		}
	}()
	defer func() { cancel(); <-watchDone }()
	reader, writer, err := os.Pipe()
	if err != nil {
		return start, end, 0, "", err
	}
	cmd := exec.CommandContext(ctx, s.ffmpeg,
		"-hide_banner", "-loglevel", "error", "-nostdin", "-n",
		"-f", "mpegts", "-i", "pipe:0", "-map", "0:v:0", "-an", "-c:v", "copy",
		"-copyts", "-start_at_zero", "-mpegts_copyts", "1", "-f", "mpegts", j.filename)
	cmd.Stdin = reader
	var diagnostics limitedOutput
	cmd.Stderr = &diagnostics
	cmd.Cancel = func() error { return cmd.Process.Signal(syscall.SIGTERM) }
	cmd.WaitDelay = 3 * time.Second
	if err := cmd.Start(); err != nil {
		return start, end, 0, "", errors.Join(err, reader.Close(), writer.Close())
	}
	if err := reader.Close(); err != nil {
		cancel()
		return start, end, 0, "", errors.Join(err, writer.Close(), cmd.Wait())
	}
	waitDone := make(chan struct{})
	inputClosed := false
	var waitErr error
	go func() {
		waitErr = cmd.Wait()
		cancel()
		close(waitDone)
	}()
	defer func() {
		if result != nil {
			cancel()
		}
		if !inputClosed {
			result = errors.Join(result, writer.Close())
		}
		<-waitDone
		if waitErr != nil {
			text := strings.ReplaceAll(string(diagnostics.data), j.filename, "[recording]")
			result = errors.Join(result, fmt.Errorf("FFmpeg recording failed: %w: %s", waitErr, text))
		}
		result = errors.Join(result, j.lease.Err())
	}()
	for {
		nextCtx, stop := context.WithTimeout(ctx, 30*time.Second)
		slice, err := j.lease.Next(nextCtx)
		stop()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return start, end, 0, "", err
		}
		if start.IsZero() {
			start = slice.Slice.StartTS
		}
		end = slice.Slice.EndTS
		_, copyErr := io.Copy(writer, slice)
		if err := errors.Join(copyErr, slice.Close()); err != nil {
			return start, end, 0, "", err
		}
	}
	if start.IsZero() || !end.After(start) {
		return start, end, 0, "", errors.New("recording has no complete video slices")
	}
	s.mu.Lock()
	j.record.State = "finalizing"
	_, saveErr := s.store.UpdateMetadata(context.Background(), j.id, j.record)
	s.mu.Unlock()
	if saveErr != nil {
		return start, end, 0, "", saveErr
	}
	inputClosed = true
	if err := writer.Close(); err != nil {
		return start, end, 0, "", err
	}
	finalizeTimeout := time.AfterFunc(30*time.Second, cancel)
	<-waitDone
	finalizeTimeout.Stop()
	if waitErr != nil {
		return start, end, 0, "", waitErr
	}
	// FFmpeg exit cancels the pipe-reading context, not the recording's lifetime.
	if err := j.ctx.Err(); err != nil {
		return start, end, 0, "", err
	}
	if _, err := s.store.PutMedia(j.ctx, j.uri); err != nil {
		return start, end, 0, "", err
	}
	info, err := os.Stat(j.filename)
	if err != nil {
		return start, end, 0, "", err
	}
	probeCtx, stop := context.WithTimeout(j.ctx, 10*time.Second)
	defer stop()
	probe := exec.CommandContext(probeCtx, s.ffprobe, "-v", "error", "-select_streams", "v:0",
		"-show_entries", "stream=codec_name", "-of", "json", j.filename)
	var output limitedOutput
	probe.Stdout = &output
	probe.Stderr = io.Discard
	if err := probe.Run(); err != nil {
		return start, end, 0, "", fmt.Errorf("inspect recording codec: %w", err)
	}
	var metadata struct {
		Streams []struct {
			Codec string `json:"codec_name"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(output.data, &metadata); err != nil || len(metadata.Streams) != 1 {
		return start, end, 0, "", errors.New("recording does not contain exactly one video stream")
	}
	if metadata.Streams[0].Codec != "h264" && metadata.Streams[0].Codec != "hevc" {
		return start, end, 0, "", errors.New("recording codec is not supported")
	}
	return start, end, info.Size(), metadata.Streams[0].Codec, nil
}

type limitedOutput struct{ data []byte }

func (b *limitedOutput) Write(p []byte) (int, error) {
	const limit = 8192
	n := len(p)
	if n >= limit {
		b.data = bytes.Clone(p[n-limit:])
	} else {
		if len(b.data)+n > limit {
			b.data = b.data[len(b.data)+n-limit:]
		}
		b.data = append(b.data, p...)
	}
	return n, nil
}
