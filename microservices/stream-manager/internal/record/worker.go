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

	"github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/internal/model"
)

func (s *Service) writeMedia(j *job) (start, end time.Time, size int64, codec string, result error) {
	ctx, cancel := context.WithCancel(j.ctx)
	defer cancel()
	sidecar, err := s.media.OpenLiveSidecarWriter(ctx, j.id, j.record.RecordingPath)
	if err != nil {
		return start, end, 0, "", err
	}
	defer func() { result = errors.Join(result, sidecar.Close()) }()
	if err := writeLiveSidecarHeader(sidecar, j.record); err != nil {
		return start, end, 0, "", err
	}
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
		"-hide_banner", "-loglevel", "error", "-nostdin", "-y",
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
	var sidecarOrdinal int
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
		copied, copyErr := io.Copy(writer, slice)
		if err := errors.Join(copyErr, slice.Close()); err != nil {
			return start, end, 0, "", err
		}
		if copied <= 0 || slice.Slice.PTSEnd <= slice.Slice.PTSStart {
			return start, end, 0, "", errors.New("recording slice has invalid byte or PTS coverage")
		}
		if err := writeLiveSidecarSample(sidecar, sidecarOrdinal, slice.Slice); err != nil {
			return start, end, 0, "", err
		}
		sidecarOrdinal++
		if info, err := os.Stat(j.filename); err == nil && info.Size() > j.record.SizeBytes {
			s.mu.Lock()
			j.record.SizeBytes = info.Size()
			_, updateErr := s.metadata.UpdateMetadata(ctx, j.id, j.record)
			s.mu.Unlock()
			if updateErr != nil {
				return start, end, 0, "", updateErr
			}
		}
	}
	if start.IsZero() || !end.After(start) {
		return start, end, 0, "", errors.New("recording has no complete video slices")
	}
	s.mu.Lock()
	j.record.State = "finalizing"
	_, saveErr := s.metadata.UpdateMetadata(context.Background(), j.id, j.record)
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
	size, err = s.media.FinalizeLiveRecording(j.ctx, j.record.RecordingPath)
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
	return start, end, size, metadata.Streams[0].Codec, nil
}

func writeLiveSidecarHeader(writer io.Writer, recording model.Recording) error {
	return writeJSONLine(writer, map[string]any{
		"version": 2, "recording_id": recording.RecordingID,
		"media_path": recording.RecordingPath, "timescale": 90000,
	})
}

func writeLiveSidecarSample(writer io.Writer, ordinal int, sample model.BufferSlice) error {
	if ordinal < 0 || sample.StartTS.IsZero() || sample.PTSStart < 0 || sample.PTSEnd <= sample.PTSStart {
		return errors.New("recording slice has invalid sidecar timing")
	}
	pts := int64(sample.PTSStart)
	return writeJSONLine(writer, map[string]any{
		"ordinal": ordinal, "capture_ts": sample.StartTS.UTC().Format(time.RFC3339Nano),
		"pts": pts, "dts": pts, "duration": int64(sample.PTSEnd - sample.PTSStart),
		"offset": 0, "length": 0, "keyframe": true,
	})
}

func writeJSONLine(writer io.Writer, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	for len(data) > 0 {
		written, err := writer.Write(data)
		if err != nil {
			return err
		}
		if written == 0 {
			return io.ErrShortWrite
		}
		data = data[written:]
	}
	return nil
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
