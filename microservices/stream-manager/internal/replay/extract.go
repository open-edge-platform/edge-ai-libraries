// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package replay

import (
	"bytes"
	"cmp"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"slices"
	"strconv"
	"strings"
	"time"
)

const (
	// preseekMargin starts reading slightly before a keyframe so that seeking
	// never lands after it; FFmpeg drops the frames before the keyframe.
	preseekMargin = 100 * time.Millisecond
	// nearestWindow is the first half-width searched around a frame request.
	nearestWindow = time.Second
	// SearchLimit is how far from the requested time a frame or keyframe is looked for.
	SearchLimit  = 5 * time.Minute
	probeTimeout = 30 * time.Second
	outputLimit  = 8192
)

// keyframeWindows are how far back a keyframe is looked for, widest last.
var keyframeWindows = []time.Duration{2 * time.Second, 10 * time.Second, time.Minute, SearchLimit}

// nearestWindows are the half-widths searched around a frame request, widest last.
var nearestWindows = []time.Duration{nearestWindow, 10 * nearestWindow, SearchLimit}

type packet struct {
	PTS int64
	Key bool
}

// timeline maps PTS in a recording to wall time: start_ts is the time of the
// first frame, a keyframe.
type timeline struct {
	ffprobe string
	path    string
	start   time.Time
	first   int64
	num     int64
	den     int64
}

func newTimeline(ctx context.Context, ffprobe, path string, start time.Time) (*timeline, error) {
	tl := &timeline{ffprobe: ffprobe, path: path, start: start}
	packets, timeBase, err := tl.probe(ctx, "%+#1")
	if err != nil {
		return nil, err
	}
	if len(packets) == 0 || !packets[0].Key {
		return nil, fmt.Errorf("%w: recording does not start on a keyframe", ErrExtraction)
	}
	num, den, ok := strings.Cut(timeBase, "/")
	tl.num, _ = strconv.ParseInt(num, 10, 64)
	tl.den, _ = strconv.ParseInt(den, 10, 64)
	if !ok || tl.num <= 0 || tl.den <= 0 {
		return nil, fmt.Errorf("%w: invalid time base %q", ErrExtraction, timeBase)
	}
	tl.first = packets[0].PTS
	return tl, nil
}

// offset converts a PTS to its distance from the first frame.
func (tl *timeline) offset(pts int64) time.Duration {
	d := pts - tl.first
	scaled := d/tl.den*tl.num*int64(time.Second) + d%tl.den*tl.num*int64(time.Second)/tl.den
	return time.Duration(scaled)
}

func (tl *timeline) wall(pts int64) time.Time { return tl.start.Add(tl.offset(pts)) }

// position is the absolute stream time, in seconds, of an offset from the first frame.
func (tl *timeline) position(offset time.Duration) float64 {
	return float64(tl.first)*float64(tl.num)/float64(tl.den) + offset.Seconds()
}

// window lists packets whose wall time falls roughly in [from, to], sorted by PTS.
func (tl *timeline) window(ctx context.Context, from, to time.Time) ([]packet, error) {
	interval := fmt.Sprintf("%%%.6f", tl.position(to.Sub(tl.start)))
	if from.After(tl.start) {
		interval = fmt.Sprintf("%.6f", tl.position(from.Sub(tl.start))) + interval
	}
	packets, _, err := tl.probe(ctx, interval)
	slices.SortFunc(packets, func(a, b packet) int { return cmp.Compare(a.PTS, b.PTS) })
	return packets, err
}

// nearestFrame finds the frame closest to ts, the earlier one on a tie, and
// the keyframe it decodes from.
func (tl *timeline) nearestFrame(ctx context.Context, ts time.Time) (packet, packet, error) {
	for i, half := range nearestWindows {
		packets, err := tl.window(ctx, ts.Add(-half), ts.Add(half))
		if err != nil {
			return packet{}, packet{}, err
		}
		best, found := packet{}, false
		for _, p := range packets {
			d := absDuration(tl.wall(p.PTS).Sub(ts))
			if !found || d < absDuration(tl.wall(best.PTS).Sub(ts)) {
				best, found = p, true
			}
		}
		// The window may begin a little late, so only trust a frame well inside
		// it; the widest window takes any frame.
		widest := i == len(nearestWindows)-1
		if !found || (!widest && absDuration(tl.wall(best.PTS).Sub(ts)) > half/2) {
			continue
		}
		keyframe, err := tl.keyframeAtOrBefore(ctx, tl.wall(best.PTS), packets)
		return best, keyframe, err
	}
	return packet{}, packet{}, fmt.Errorf("%w: no frame", ErrBeyondSearchLimit)
}

// keyframeAtOrBefore finds the last keyframe at or before ts, first among
// known packets, then in widening windows up to SearchLimit.
func (tl *timeline) keyframeAtOrBefore(ctx context.Context, ts time.Time, known []packet) (packet, error) {
	if keyframe, ok := tl.lastKeyframe(known, ts); ok {
		return keyframe, nil
	}
	for _, back := range keyframeWindows {
		packets, err := tl.window(ctx, ts.Add(-back), ts.Add(time.Millisecond))
		if err != nil {
			return packet{}, err
		}
		if keyframe, ok := tl.lastKeyframe(packets, ts); ok {
			return keyframe, nil
		}
	}
	return packet{}, fmt.Errorf("%w: no keyframe", ErrBeyondSearchLimit)
}

func (tl *timeline) lastKeyframe(packets []packet, ts time.Time) (packet, bool) {
	for _, p := range slices.Backward(packets) {
		if p.Key && !tl.wall(p.PTS).After(ts) {
			return p, true
		}
	}
	return packet{}, false
}

// preseek is the FFmpeg -ss value, relative to the first frame, a little
// before a keyframe.
func (tl *timeline) preseek(keyframe int64) string {
	return seconds(max(tl.offset(keyframe)-preseekMargin, 0))
}

// cut returns -ss and -t values that copy from a keyframe up to, but not including, end.
func (tl *timeline) cut(keyframe int64, end time.Time) (string, string) {
	seek := max(tl.offset(keyframe)-preseekMargin, 0)
	return seconds(seek), seconds(end.Sub(tl.start) - seek)
}

func seconds(d time.Duration) string { return strconv.FormatFloat(d.Seconds(), 'f', 6, 64) }

func (tl *timeline) probe(ctx context.Context, interval string) ([]packet, string, error) {
	ctx, cancel := context.WithTimeout(ctx, probeTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, tl.ffprobe, "-v", "error", "-select_streams", "v:0", "-read_intervals", interval,
		"-show_entries", "packet=pts,flags:stream=time_base", "-of", "json", tl.path)
	var stdout bytes.Buffer
	stderr := &limitedOutput{}
	cmd.Stdout, cmd.Stderr = &stdout, stderr
	if err := cmd.Run(); err != nil {
		return nil, "", failure(ctx, "FFprobe", tl.path, err, stderr)
	}
	var out struct {
		Packets []struct {
			PTS   *int64 `json:"pts"`
			Flags string `json:"flags"`
		} `json:"packets"`
		Streams []struct {
			TimeBase string `json:"time_base"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &out); err != nil || len(out.Streams) != 1 {
		return nil, "", fmt.Errorf("%w: unreadable FFprobe output", ErrExtraction)
	}
	packets := make([]packet, 0, len(out.Packets))
	for _, p := range out.Packets {
		if p.PTS != nil {
			packets = append(packets, packet{PTS: *p.PTS, Key: strings.HasPrefix(p.Flags, "K")})
		}
	}
	return packets, out.Streams[0].TimeBase, nil
}

// failure reports a failed FFmpeg or FFprobe run with its output, minus the
// recording path. A cancelled request is reported as such.
func failure(ctx context.Context, tool, path string, err error, stderr *limitedOutput) error {
	if ctxErr := ctx.Err(); ctxErr != nil && !errors.Is(ctxErr, context.DeadlineExceeded) {
		return ctxErr
	}
	text := strings.ReplaceAll(strings.TrimSpace(string(stderr.data)), path, "[recording]")
	return fmt.Errorf("%w: %s: %w: %s", ErrExtraction, tool, err, text)
}

func runFFmpeg(ctx context.Context, ffmpeg, path string, args ...string) error {
	cmd := exec.CommandContext(ctx, ffmpeg, args...)
	stderr := &limitedOutput{}
	cmd.Stderr = stderr
	if err := cmd.Run(); err != nil {
		return failure(ctx, "FFmpeg", path, err, stderr)
	}
	return nil
}

// limitedOutput keeps the last outputLimit bytes written to it.
type limitedOutput struct{ data []byte }

func (b *limitedOutput) Write(p []byte) (int, error) {
	b.data = append(b.data, p...)
	if len(b.data) > outputLimit {
		b.data = b.data[len(b.data)-outputLimit:]
	}
	return len(p), nil
}
