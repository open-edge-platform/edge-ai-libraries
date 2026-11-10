// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package lineproto

import (
	"math"
	"testing"
	"time"
)

func render(t *testing.T, p Point) string {
	t.Helper()
	out, err := p.Append(nil)
	if err != nil {
		t.Fatalf("Append() returned an unexpected error: %v", err)
	}
	return string(out)
}

func TestPointRendersFieldsAndTags(t *testing.T) {
	tests := []struct {
		name  string
		point Point
		want  string
	}{
		{
			name: "no tags and no timestamp",
			point: Point{
				Measurement: "cpu_frequency_avg",
				Fields:      []Field{FloatField("frequency", 2385714)},
			},
			// Byte-identical to the output of the CPU frequency shell script
			// this collector replaces. A trailing "i" here would change the
			// field from float to integer and break existing dashboards.
			want: "cpu_frequency_avg frequency=2385714\n",
		},
		{
			name: "tags, mixed field types and a timestamp",
			point: Point{
				Measurement: "cpu_core_class",
				Tags:        []Tag{{Key: "class", Value: "P"}},
				Fields: []Field{
					IntField("cores", 12),
					FloatField("usage_user", 3.5),
				},
				Timestamp: time.Unix(0, 1725062400000000000),
			},
			want: "cpu_core_class,class=P cores=12i,usage_user=3.5 1725062400000000000\n",
		},
		{
			name: "empty tag values are dropped rather than emitted",
			point: Point{
				Measurement: "npu",
				Tags:        []Tag{{Key: "host", Value: ""}, {Key: "class", Value: "E"}},
				Fields:      []Field{IntField("utilization", 67)},
			},
			want: "npu,class=E utilization=67i\n",
		},
		{
			name: "separators are escaped in every position",
			point: Point{
				Measurement: "odd name,x",
				Tags:        []Tag{{Key: "a b", Value: "c=d"}},
				Fields:      []Field{IntField("e,f", 1)},
			},
			want: `odd\ name\,x,a\ b=c\=d e\,f=1i` + "\n",
		},
		{
			name: "negative and fractional values round-trip",
			point: Point{
				Measurement: "npu",
				Fields: []Field{
					FloatField("memory_mb", -1),
					FloatField("power", 4.25),
				},
			},
			want: "npu memory_mb=-1,power=4.25\n",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := render(t, tt.point); got != tt.want {
				t.Errorf("Append()\n got: %q\nwant: %q", got, tt.want)
			}
		})
	}
}

func TestPointAppendsToExistingBuffer(t *testing.T) {
	dst := []byte("existing\n")
	out, err := Point{
		Measurement: "m",
		Fields:      []Field{IntField("v", 1)},
	}.Append(dst)
	if err != nil {
		t.Fatalf("Append() error: %v", err)
	}
	if want := "existing\nm v=1i\n"; string(out) != want {
		t.Errorf("Append() = %q, want %q", out, want)
	}
}

func TestPointRejectsUnrenderableInput(t *testing.T) {
	tests := []struct {
		name  string
		point Point
	}{
		{
			name:  "missing measurement",
			point: Point{Fields: []Field{IntField("v", 1)}},
		},
		{
			name:  "no fields",
			point: Point{Measurement: "m"},
		},
		{
			name:  "empty field key",
			point: Point{Measurement: "m", Fields: []Field{IntField("", 1)}},
		},
		{
			// Telegraf rejects the entire batch when one line is malformed,
			// so a non-finite float must be caught before it is written.
			name:  "NaN field value",
			point: Point{Measurement: "m", Fields: []Field{FloatField("v", math.NaN())}},
		},
		{
			name:  "infinite field value",
			point: Point{Measurement: "m", Fields: []Field{FloatField("v", math.Inf(1))}},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := tt.point.Append(nil); err == nil {
				t.Error("Append() succeeded, want an error")
			}
		})
	}
}

func TestFixedFloatField(t *testing.T) {
	tests := []struct {
		name     string
		value    float64
		decimals int
		want     string
	}{
		// The NPU collector replaces a Python script formatting with "%.3f",
		// "%.0f" and "%.2f"; these cases pin that behaviour.
		{name: "pads to three decimals", value: 4, decimals: 3, want: "4.000"},
		{name: "rounds to three decimals", value: 128.7504, decimals: 3, want: "128.750"},
		{name: "drops the point at zero decimals", value: 1000.4, decimals: 0, want: "1000"},
		{name: "keeps a negative sentinel", value: -1, decimals: 2, want: "-1.00"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			point := Point{
				Measurement: "m",
				Fields:      []Field{FixedFloatField("power", tt.value, tt.decimals)},
			}
			rendered, err := point.Append(nil)
			if err != nil {
				t.Fatalf("Append() error: %v", err)
			}
			if got, want := string(rendered), "m power="+tt.want+"\n"; got != want {
				t.Errorf("Append() = %q, want %q", got, want)
			}
		})
	}
}

func TestFixedFloatFieldRejectsNonFinite(t *testing.T) {
	for _, value := range []float64{math.NaN(), math.Inf(1), math.Inf(-1)} {
		point := Point{
			Measurement: "m",
			Fields:      []Field{FixedFloatField("power", value, 3)},
		}
		if _, err := point.Append(nil); err == nil {
			t.Errorf("Append() with %v succeeded, want an error", value)
		}
	}
}

// TestNumberField covers forwarding a number's textual form unchanged, which
// keeps upstream telemetry (such as qmassa's JSON) byte-identical.
func TestNumberField(t *testing.T) {
	tests := []struct {
		name    string
		literal string
		wantErr bool
	}{
		{name: "keeps a trailing zero", literal: "0.0"},
		{name: "keeps full precision", literal: "3.733059578240674"},
		{name: "keeps an integer literal", literal: "800"},
		{name: "keeps exponent notation", literal: "1e3"},
		{name: "keeps a negative value", literal: "-1.5"},
		// A literal that is not a finite number could otherwise inject extra
		// fields or tags into the rendered line.
		{name: "rejects text", literal: "abc", wantErr: true},
		{name: "rejects an empty literal", literal: "", wantErr: true},
		{name: "rejects an injected field", literal: "1,x=2", wantErr: true},
		{name: "rejects NaN", literal: "NaN", wantErr: true},
		{name: "rejects Inf", literal: "Inf", wantErr: true},
		{name: "rejects -Inf", literal: "-Inf", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			point := Point{
				Measurement: "m",
				Fields:      []Field{NumberField("value", tt.literal)},
			}
			rendered, err := point.Append(nil)

			if tt.wantErr {
				if err == nil {
					t.Errorf("Append() with %q succeeded, want an error", tt.literal)
				}
				return
			}
			if err != nil {
				t.Fatalf("Append() error: %v", err)
			}
			if got, want := string(rendered), "m value="+tt.literal+"\n"; got != want {
				t.Errorf("Append() = %q, want %q", got, want)
			}
		})
	}
}
