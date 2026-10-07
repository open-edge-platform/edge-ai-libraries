// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Extraction (this file) generates derived media assets (single frames and
// short clips) from a finalized recording.
package replay

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
)

// ErrExtractionFailed wraps any failure raised by the underlying media
// tooling (e.g. ffmpeg exiting non-zero, or being unable to parse the
// recording).
var ErrExtractionFailed = errors.New("media extraction failed")

// FrameExtractor produces a single still image at a given media-clock
// position (seconds from the start of the recording, as resolved by the
// sidecar) in the requested format ("jpeg" or "png").
type FrameExtractor interface {
	ExtractFrame(ctx context.Context, recording io.Reader, mediaTimeSeconds float64, format string) ([]byte, error)
}

// ClipExtractor produces a trimmed sub-clip covering [startSeconds,
// endSeconds) of the recording's media clock, in the requested format
// ("mp4").
type ClipExtractor interface {
	ExtractClip(ctx context.Context, recording io.Reader, startSeconds, endSeconds float64, format string) ([]byte, error)
}

// Extractor is the full extraction capability required by the retrieval
// layer. It is defined narrowly so alternative implementations (e.g. a
// GStreamer/DLStreamer-backed extractor) can be swapped in without touching
// callers.
type Extractor interface {
	FrameExtractor
	ClipExtractor
}

// FFmpegExtractor implements Extractor by shelling out to the ffmpeg binary.
// Recordings are object-store byte streams rather than local files, so each
// call stages the recording into a temporary file (ffmpeg needs a seekable
// input to seek accurately) and reads the produced output back into memory.
type FFmpegExtractor struct {
	binary string
}

// NewFFmpegExtractor returns an Extractor that invokes "ffmpeg" from PATH.
func NewFFmpegExtractor() *FFmpegExtractor {
	return NewFFmpegExtractorWithBinary("ffmpeg")
}

// NewFFmpegExtractorWithBinary returns an Extractor that invokes the given
// ffmpeg binary path, useful for tests or environments with a non-standard
// install location.
func NewFFmpegExtractorWithBinary(binary string) *FFmpegExtractor {
	return &FFmpegExtractor{binary: binary}
}

func (f *FFmpegExtractor) ExtractFrame(ctx context.Context, recording io.Reader, mediaTimeSeconds float64, format string) ([]byte, error) {
	workDir, err := os.MkdirTemp("", "stream-manager-frame-*")
	if err != nil {
		return nil, fmt.Errorf("%w: create work dir: %v", ErrExtractionFailed, err)
	}
	defer os.RemoveAll(workDir)

	inPath, err := stageInput(workDir, recording)
	if err != nil {
		return nil, err
	}

	ext := format
	codecArgs := []string{"-c:v", "mjpeg", "-q:v", "2"}
	if format == "png" {
		codecArgs = []string{"-c:v", "png"}
	}

	outPath := filepath.Join(workDir, "frame."+ext)
	args := append([]string{
		"-y",
		"-ss", fmt.Sprintf("%.6f", mediaTimeSeconds),
		"-i", inPath,
		"-frames:v", "1",
	}, append(codecArgs, outPath)...)

	if err := f.run(ctx, args); err != nil {
		return nil, err
	}

	data, err := os.ReadFile(outPath)
	if err != nil {
		return nil, fmt.Errorf("%w: read extracted frame: %v", ErrExtractionFailed, err)
	}
	return data, nil
}

func (f *FFmpegExtractor) ExtractClip(ctx context.Context, recording io.Reader, startSeconds, endSeconds float64, format string) ([]byte, error) {
	if endSeconds <= startSeconds {
		return nil, fmt.Errorf("%w: clip end (%.6f) must be after start (%.6f)", ErrExtractionFailed, endSeconds, startSeconds)
	}

	workDir, err := os.MkdirTemp("", "stream-manager-clip-*")
	if err != nil {
		return nil, fmt.Errorf("%w: create work dir: %v", ErrExtractionFailed, err)
	}
	defer os.RemoveAll(workDir)

	inPath, err := stageInput(workDir, recording)
	if err != nil {
		return nil, err
	}

	outPath := filepath.Join(workDir, "clip."+format)
	duration := endSeconds - startSeconds

	// Re-encoding (rather than stream copy) keeps the trim frame-accurate:
	// container copy would otherwise snap to the nearest preceding
	// keyframe and could include extra footage before the requested start.
	args := []string{
		"-y",
		"-ss", fmt.Sprintf("%.6f", startSeconds),
		"-i", inPath,
		"-t", fmt.Sprintf("%.6f", duration),
		"-c:v", "libx264", "-preset", "veryfast",
		"-c:a", "aac",
		"-movflags", "+faststart",
		outPath,
	}

	if err := f.run(ctx, args); err != nil {
		return nil, err
	}

	data, err := os.ReadFile(outPath)
	if err != nil {
		return nil, fmt.Errorf("%w: read extracted clip: %v", ErrExtractionFailed, err)
	}
	return data, nil
}

func (f *FFmpegExtractor) run(ctx context.Context, args []string) error {
	cmd := exec.CommandContext(ctx, f.binary, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%w: %s: %v: %s", ErrExtractionFailed, f.binary, err, stderr.String())
	}
	return nil
}

// stageInput copies recording bytes into a temporary file inside workDir so
// ffmpeg can seek on it directly; ffmpeg's own -ss seeking is unreliable
// against a non-seekable pipe.
func stageInput(workDir string, recording io.Reader) (string, error) {
	inPath := filepath.Join(workDir, "input")
	inFile, err := os.Create(inPath)
	if err != nil {
		return "", fmt.Errorf("%w: create input staging file: %v", ErrExtractionFailed, err)
	}
	defer inFile.Close()

	if _, err := io.Copy(inFile, recording); err != nil {
		return "", fmt.Errorf("%w: stage recording bytes: %v", ErrExtractionFailed, err)
	}
	return inPath, nil
}
