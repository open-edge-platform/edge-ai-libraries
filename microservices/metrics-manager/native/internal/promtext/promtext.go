// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package promtext parses the Prometheus text exposition format.
//
// The TUI reads telemetry from the same endpoint that the service's own
// /metrics/stream already polls, so what it renders is by construction the
// same data the REST interface serves rather than a second collection path
// that could drift from it.
//
// Only the subset of the format that Telegraf's prometheus_client output
// actually produces is supported: HELP/TYPE comments, an optional label set
// and an optional millisecond timestamp. Exemplars, native histograms and the
// OpenMetrics extensions are not emitted by that output and are rejected
// rather than half-understood.
package promtext

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
)

// maxLineBytes caps a single exposition line. Telegraf's longest realistic
// line is a few hundred bytes, so this is generous, but it has to be bounded:
// the reader consumes a network response and an unbounded bufio.Scanner token
// would let a malformed or hostile endpoint drive allocation.
const maxLineBytes = 1 << 20

// MaxSamples caps how many samples a single parse will accumulate. The same
// reasoning applies as for maxLineBytes -- the number of lines is attacker
// controlled even when the body size is capped, because lines can be short.
const MaxSamples = 1 << 16

// ErrTooManySamples reports that the payload exceeded MaxSamples. It is
// returned rather than silently truncating so a caller cannot mistake a
// clipped snapshot for a complete one.
var ErrTooManySamples = errors.New("promtext: too many samples")

// Sample is one exposed time series at one point in time.
type Sample struct {
	// Name is the metric name, for example "cpu_usage_idle".
	Name string

	// Labels holds the label set. It is nil when the series carries none,
	// which keeps the common case allocation-free.
	Labels map[string]string

	// Value is the sample value. It may be NaN or an infinity: Prometheus
	// uses those to mean "collected but unavailable", and discarding them
	// here would hide that distinction from the display layer.
	Value float64

	// TimestampMS is the exposition timestamp in milliseconds since the Unix
	// epoch, or zero when the line carried none. Telegraf normally omits it,
	// in which case scrape time applies.
	TimestampMS int64
}

// Parse reads an exposition body and returns every sample in it.
//
// The caller is responsible for bounding r -- typically with an
// io.LimitReader around the HTTP response body -- because Parse cannot know
// what payload size is reasonable for a given deployment.
func Parse(r io.Reader) ([]Sample, error) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), maxLineBytes)

	var samples []Sample
	lineNo := 0
	for scanner.Scan() {
		lineNo++

		line := strings.TrimSpace(scanner.Text())
		// Blank lines are legal padding and '#' introduces HELP and TYPE
		// metadata, which carries no sample.
		if line == "" || line[0] == '#' {
			continue
		}

		sample, err := parseLine(line)
		if err != nil {
			return nil, fmt.Errorf("line %d: %w", lineNo, err)
		}

		if len(samples) >= MaxSamples {
			return nil, ErrTooManySamples
		}
		samples = append(samples, sample)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("promtext: read: %w", err)
	}

	return samples, nil
}

// parseLine parses a single sample line of the form
//
//	name[{label="value",...}] value [timestamp]
func parseLine(line string) (Sample, error) {
	var sample Sample

	i := 0
	for i < len(line) && line[i] != '{' && line[i] != ' ' && line[i] != '\t' {
		i++
	}
	if i == 0 {
		return sample, errors.New("empty metric name")
	}
	sample.Name = line[:i]

	if i < len(line) && line[i] == '{' {
		labels, n, err := parseLabels(line[i:])
		if err != nil {
			return sample, err
		}
		sample.Labels = labels
		i += n
	}

	// strings.Fields collapses any run of whitespace, which is what the
	// format allows between the label set, the value and the timestamp.
	rest := strings.Fields(line[i:])
	if len(rest) == 0 {
		return sample, errors.New("missing value")
	}
	if len(rest) > 2 {
		return sample, fmt.Errorf("unexpected trailing input %q", strings.Join(rest[2:], " "))
	}

	// ParseFloat already accepts NaN, +Inf and -Inf, which is exactly the
	// set of non-finite values the format permits.
	value, err := strconv.ParseFloat(rest[0], 64)
	if err != nil {
		return sample, fmt.Errorf("bad value %q", rest[0])
	}
	sample.Value = value

	if len(rest) == 2 {
		ts, err := strconv.ParseInt(rest[1], 10, 64)
		if err != nil {
			return sample, fmt.Errorf("bad timestamp %q", rest[1])
		}
		sample.TimestampMS = ts
	}

	return sample, nil
}

// parseLabels parses a label set starting at the opening brace of s and
// returns the labels together with how many bytes of s they occupied.
func parseLabels(s string) (map[string]string, int, error) {
	labels := make(map[string]string)

	i := 1 // skip '{'
	for {
		i = skipSpace(s, i)
		if i >= len(s) {
			return nil, 0, errors.New("unterminated label set")
		}
		if s[i] == '}' {
			return labels, i + 1, nil
		}

		start := i
		for i < len(s) && s[i] != '=' && s[i] != ' ' && s[i] != '\t' {
			i++
		}
		if start == i {
			return nil, 0, errors.New("empty label name")
		}
		name := s[start:i]

		i = skipSpace(s, i)
		if i >= len(s) || s[i] != '=' {
			return nil, 0, fmt.Errorf("label %q is missing '='", name)
		}
		i++

		i = skipSpace(s, i)
		if i >= len(s) || s[i] != '"' {
			return nil, 0, fmt.Errorf("label %q has an unquoted value", name)
		}
		i++

		value, n, err := parseLabelValue(s[i:])
		if err != nil {
			return nil, 0, fmt.Errorf("label %q: %w", name, err)
		}
		labels[name] = value
		i += n

		i = skipSpace(s, i)
		if i >= len(s) {
			return nil, 0, errors.New("unterminated label set")
		}
		switch s[i] {
		case ',':
			i++
		case '}':
			return labels, i + 1, nil
		default:
			return nil, 0, fmt.Errorf("unexpected %q in label set", s[i])
		}
	}
}

// parseLabelValue decodes a quoted label value, whose opening quote the caller
// has already consumed, and reports how many bytes it spanned including the
// closing quote.
func parseLabelValue(s string) (string, int, error) {
	var b strings.Builder

	for i := 0; i < len(s); i++ {
		switch s[i] {
		case '"':
			return b.String(), i + 1, nil

		case '\\':
			i++
			if i >= len(s) {
				return "", 0, errors.New("trailing escape")
			}
			// The exposition format defines exactly these three escapes.
			// Anything else is passed through verbatim, matching how the
			// reference parsers behave.
			switch s[i] {
			case 'n':
				b.WriteByte('\n')
			case '"':
				b.WriteByte('"')
			case '\\':
				b.WriteByte('\\')
			default:
				b.WriteByte(s[i])
			}

		default:
			b.WriteByte(s[i])
		}
	}

	return "", 0, errors.New("unterminated value")
}

func skipSpace(s string, i int) int {
	for i < len(s) && (s[i] == ' ' || s[i] == '\t') {
		i++
	}
	return i
}
