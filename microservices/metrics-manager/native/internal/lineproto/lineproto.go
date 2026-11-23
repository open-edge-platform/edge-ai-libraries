// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package lineproto renders metrics as InfluxDB Line Protocol.
//
// Every collector plugin in this module speaks line protocol on stdout, which
// is what Telegraf's `inputs.execd` parses with `data_format = "influx"`. The
// same output is human-readable, so a plugin can be run straight from a shell
// to debug a machine without Telegraf being involved at all.
//
// Only the subset of the format the collectors actually need is implemented:
// integer and float fields. Escaping follows the InfluxDB v1 line protocol
// rules, which differ per position (measurement, tag, field key, field value).
package lineproto

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"
)

// Tag is a single key/value pair. Tags are emitted in the order supplied by
// the caller; line protocol does not require sorted tag keys.
type Tag struct {
	Key   string
	Value string
}

// Field is a single measurement value. Construct one with IntField or
// FloatField so the value is formatted exactly once, at construction time.
type Field struct {
	Key string

	// value holds the already-formatted field value, including the trailing
	// "i" that marks an integer. Keeping it pre-formatted means Point.Append
	// cannot accidentally change a field's type.
	value string

	// err records a formatting failure (a non-finite float) so it can be
	// surfaced when the point is rendered rather than silently emitting a
	// value Telegraf would reject.
	err error
}

// IntField creates a signed integer field. Line protocol marks integers with a
// trailing "i"; without it the value is parsed as a float, which changes the
// resulting Prometheus metric type.
func IntField(key string, value int64) Field {
	return Field{Key: key, value: strconv.FormatInt(value, 10) + "i"}
}

// FloatField creates a float field.
//
// The value is formatted with the shortest representation that round-trips, so
// a whole number such as 2385714 renders as "2385714" rather than
// "2385714.000000". Collectors that replace an existing shell script rely on
// this to stay byte-identical with the output they supersede.
//
// NaN and infinities are not representable in line protocol and are reported
// as an error instead of being emitted.
func FloatField(key string, value float64) Field {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return Field{Key: key, err: fmt.Errorf("field %q: value %v is not representable in line protocol", key, value)}
	}
	return Field{Key: key, value: strconv.FormatFloat(value, 'f', -1, 64)}
}

// FixedFloatField creates a float field rendered with a fixed number of
// decimal places.
//
// This exists for parity with collectors that replace a Python script using
// printf-style formatting such as "%.3f". Matching the number of decimals
// keeps the emitted line byte-identical to the output it supersedes. Prefer
// FloatField for new fields, which neither rounds nor pads.
func FixedFloatField(key string, value float64, decimals int) Field {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return Field{Key: key, err: fmt.Errorf("field %q: value %v is not representable in line protocol", key, value)}
	}
	return Field{Key: key, value: strconv.FormatFloat(value, 'f', decimals, 64)}
}

// NumberField creates a float field from a number's original textual form,
// such as a JSON literal.
//
// Forwarding the literal avoids a decode-and-re-encode round trip that would
// otherwise rewrite "0.0" as "0" or "1e3" as "1000". Upstream telemetry is
// reproduced exactly as it was reported.
//
// The literal is validated as a finite decimal number, so untrusted input
// cannot inject extra fields or tags into the rendered line.
func NumberField(key, literal string) Field {
	value, err := strconv.ParseFloat(literal, 64)
	switch {
	case err != nil:
		return Field{Key: key, err: fmt.Errorf("field %q: %q is not a number", key, literal)}
	case math.IsNaN(value) || math.IsInf(value, 0):
		// ParseFloat accepts "NaN" and "Inf", which line protocol cannot
		// represent, so they are rejected explicitly.
		return Field{Key: key, err: fmt.Errorf("field %q: value %q is not representable in line protocol", key, literal)}
	}
	return Field{Key: key, value: literal}
}

// Point is one line protocol record.
type Point struct {
	Measurement string
	Tags        []Tag
	Fields      []Field

	// Timestamp is emitted with nanosecond precision. A zero Timestamp omits
	// the field entirely, which tells Telegraf to stamp the metric on arrival.
	Timestamp time.Time
}

// Append renders the point, including a trailing newline, onto dst.
//
// An error is returned for points that cannot be rendered as valid line
// protocol. Emitting such a line would make Telegraf drop the whole batch, so
// callers should skip the point and carry on rather than aborting.
func (p Point) Append(dst []byte) ([]byte, error) {
	if p.Measurement == "" {
		return dst, fmt.Errorf("point has no measurement name")
	}
	if len(p.Fields) == 0 {
		return dst, fmt.Errorf("measurement %q has no fields", p.Measurement)
	}

	dst = appendEscaped(dst, p.Measurement, measurementEscaper)

	for _, tag := range p.Tags {
		// A tag with an empty key or value is not valid line protocol.
		// Dropping it keeps the rest of the point usable.
		if tag.Key == "" || tag.Value == "" {
			continue
		}
		dst = append(dst, ',')
		dst = appendEscaped(dst, tag.Key, tagEscaper)
		dst = append(dst, '=')
		dst = appendEscaped(dst, tag.Value, tagEscaper)
	}

	dst = append(dst, ' ')
	for i, field := range p.Fields {
		if field.err != nil {
			return dst, field.err
		}
		if field.Key == "" {
			return dst, fmt.Errorf("measurement %q has a field with an empty key", p.Measurement)
		}
		if i > 0 {
			dst = append(dst, ',')
		}
		dst = appendEscaped(dst, field.Key, tagEscaper)
		dst = append(dst, '=')
		dst = append(dst, field.value...)
	}

	if !p.Timestamp.IsZero() {
		dst = append(dst, ' ')
		dst = strconv.AppendInt(dst, p.Timestamp.UnixNano(), 10)
	}

	return append(dst, '\n'), nil
}

// Escaping rules, per InfluxDB line protocol. Measurement names escape fewer
// characters than tag and field keys, so the two cases need separate tables.
var (
	measurementEscaper = strings.NewReplacer(
		",", `\,`,
		" ", `\ `,
		"\n", "",
	)
	tagEscaper = strings.NewReplacer(
		",", `\,`,
		"=", `\=`,
		" ", `\ `,
		"\n", "",
	)
)

func appendEscaped(dst []byte, value string, escaper *strings.Replacer) []byte {
	return append(dst, escaper.Replace(value)...)
}
