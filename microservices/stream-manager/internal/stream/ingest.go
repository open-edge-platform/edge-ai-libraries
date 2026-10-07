// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package stream

import (
	"bufio"
	"bytes"
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

const (
	ingestTimeout  = 30 * time.Second
	ffmpegStopWait = 3 * time.Second
)

func ffmpegArgs(source string) []string {
	return []string{
		"-hide_banner", "-loglevel", "error", "-nostdin", "-n",
		"-rtsp_transport", "tcp", "-allowed_media_types", "video", "-i", source,
		"-map", "0:v:0", "-an", "-c:v", "copy", "-copyts",
		// The relay's first keyframe is exactly PTS 0. FFmpeg may discard that
		// first PTS while deriving B-frame DTS; restore only this known value.
		"-bsf:v", "setts=pts=PTS*not(not(N)),dump_extra=freq=keyframe",
		"-avoid_negative_ts", "disabled", "-f", "segment",
		"-segment_format", "mpegts",
		"-segment_format_options", "mpegts_copyts=1:mpegts_flags=+resend_headers",
		"-segment_time", "0.000001", "-reset_timestamps", "0",
		"-segment_start_number", "1", "-segment_list_type", "csv",
		"-segment_list", "pipe:1", "S%04d.ts",
	}
}

func runIngest(ctx context.Context, executable, source string, buffer *RollingBuffer,
	onFrame func(bool), onSlice func(bool), allowBestEffort bool, timeout time.Duration,
) (result error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	startup := time.AfterFunc(timeout, cancel)
	defer startup.Stop()
	input, err := openRTSP(ctx, source, onFrame, allowBestEffort)
	if err != nil {
		return err
	}
	defer input.close()
	select {
	case <-ctx.Done():
		return fmt.Errorf("%w: no NTP/keyframe readiness within %s", ErrSourceFailed, timeout)
	case err := <-input.failures:
		return err
	case <-input.ready:
	}
	reader, writer, err := os.Pipe()
	if err != nil {
		return fmt.Errorf("open FFmpeg segment report pipe: %w", err)
	}
	defer func() { result = errors.Join(result, reader.Close()) }()
	cmd := exec.CommandContext(ctx, executable, ffmpegArgs(input.relay.url())...)
	cmd.Dir = buffer.root.Name()
	cmd.Stdout = writer
	var diagnostics boundedDiagnostics
	cmd.Stderr = &diagnostics
	cmd.Cancel = func() error { return cmd.Process.Signal(syscall.SIGTERM) }
	cmd.WaitDelay = ffmpegStopWait
	if err := cmd.Start(); err != nil {
		return errors.Join(fmt.Errorf("start FFmpeg: %w", err), writer.Close())
	}
	writerErr := writer.Close()
	waitDone := make(chan struct{})
	var waitErr error
	go func() {
		waitErr = cmd.Wait()
		close(waitDone)
	}()
	progress := make(chan struct{}, 1)
	parseDone := make(chan struct{})
	var parseErr error
	go func() {
		parseErr = readSegments(ctx, reader, input.keyframes, buffer, func() {
			onSlice(input.bestEffort.Load())
			select {
			case progress <- struct{}{}:
			default:
			}
		})
		close(parseDone)
	}()
	defer func() {
		cancel()
		<-waitDone
		<-parseDone
		result = errors.Join(result, buffer.removeUnindexed())
		if result != nil && len(diagnostics.data) != 0 {
			text := strings.ReplaceAll(string(diagnostics.data), input.relay.url(), "[relay]")
			text = strings.ReplaceAll(text, buffer.root.Name(), "[buffer]")
			result = fmt.Errorf("%w; FFmpeg: %s", result, text)
		}
	}()
	if writerErr != nil {
		return writerErr
	}

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("%w: ingest stopped or no NTP/keyframe progress within %s", ErrSourceFailed, timeout)
		case <-progress:
			startup.Reset(timeout)
		case err := <-input.failures:
			return err
		case <-waitDone:
			return fmt.Errorf("%w: FFmpeg exited: %v", ErrSourceFailed, waitErr)
		case <-parseDone:
			return fmt.Errorf("%w: FFmpeg segment reports stopped: %w", ErrSourceFailed, parseErr)
		}
	}
}

type boundedDiagnostics struct{ data []byte }

func (b *boundedDiagnostics) Write(p []byte) (int, error) {
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

func readSegments(ctx context.Context, reports io.Reader, keyframes <-chan keyframeTime,
	buffer *RollingBuffer, onSlice func(),
) error {
	nextKey := func() (keyframeTime, error) {
		select {
		case <-ctx.Done():
			return keyframeTime{}, ctx.Err()
		case key := <-keyframes:
			return key, nil
		}
	}
	var start keyframeTime
	seq := 1
	scanner := bufio.NewScanner(reports)
	scanner.Buffer(make([]byte, 1024), 4096)
	for scanner.Scan() {
		row, err := csv.NewReader(strings.NewReader(scanner.Text())).Read()
		if err != nil || len(row) != 3 || row[0] != sliceName(seq) {
			return errors.New("invalid FFmpeg segment report")
		}
		if seq == 1 {
			start, err = nextKey()
			if err != nil {
				return err
			}
		}
		end, err := nextKey()
		if err != nil {
			return err
		}
		reportStart, err := strconv.ParseFloat(row[1], 64)
		if err != nil || math.IsNaN(reportStart) || math.IsInf(reportStart, 0) ||
			math.Abs(reportStart-float64(start.pts)/videoClockRate) > 0.00002 {
			return fmt.Errorf("FFmpeg slice start %.6f does not match source PTS %.6f",
				reportStart, float64(start.pts)/videoClockRate)
		}
		reportEnd, err := strconv.ParseFloat(row[2], 64)
		if err != nil || math.IsNaN(reportEnd) || math.IsInf(reportEnd, 0) ||
			reportEnd <= reportStart ||
			math.Abs(reportEnd-float64(end.pts)/videoClockRate) > 0.00002 {
			return fmt.Errorf("FFmpeg slice end %.6f does not match next keyframe PTS %.6f",
				reportEnd, float64(end.pts)/videoClockRate)
		}
		// FFmpeg flushes the CSV before closing the media file. Opening the
		// following segment is the barrier that proves the previous one closed.
		if err := buffer.waitForNextSegment(ctx, seq+1); err != nil {
			return err
		}
		if err := buffer.addSlice(model.BufferSlice{
			SeqNo: seq, StartTS: start.ntp, EndTS: end.ntp,
			PTSStart: int(start.pts), PTSEnd: int(end.pts),
			Path: filepath.Join(buffer.root.Name(), row[0]),
		}, end.receivedAt); err != nil {
			return err
		}
		onSlice()
		start = end
		seq++
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("read FFmpeg segment reports: %w", err)
	}
	return io.EOF
}

func (b *RollingBuffer) waitForNextSegment(ctx context.Context, seq int) error {
	ticker := time.NewTicker(2 * time.Millisecond)
	defer ticker.Stop()
	for {
		info, err := b.root.Lstat(sliceName(seq))
		if err == nil {
			if !info.Mode().IsRegular() {
				return errors.New("FFmpeg created a nonregular slice")
			}
			return nil
		}
		if !errors.Is(err, os.ErrNotExist) {
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (b *RollingBuffer) diskUsage() (size int64, result error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	directory, err := b.root.Open(".")
	if err != nil {
		return 0, err
	}
	defer func() { result = errors.Join(result, directory.Close()) }()
	entries, err := directory.ReadDir(-1)
	if err != nil {
		return 0, err
	}
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "S") || !strings.HasSuffix(entry.Name(), ".ts") {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			return 0, err
		}
		if !info.Mode().IsRegular() {
			return 0, errors.New("buffer contains a nonregular slice")
		}
		size += info.Size()
	}
	return size, nil
}

func (b *RollingBuffer) removeUnindexed() (result error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	directory, err := b.root.Open(".")
	if err != nil {
		return err
	}
	defer func() { result = errors.Join(result, directory.Close()) }()
	entries, err := directory.ReadDir(-1)
	if err != nil {
		return err
	}
	indexed := make(map[string]bool, len(b.slices))
	for _, entry := range b.slices {
		indexed[sliceName(entry.media.SeqNo)] = true
	}
	for _, entry := range entries {
		name := entry.Name()
		if indexed[name] || !strings.HasPrefix(name, "S") || !strings.HasSuffix(name, ".ts") {
			continue
		}
		result = errors.Join(result, b.root.Remove(name))
	}
	return result
}
