// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package promtext

import (
	"errors"
	"math"
	"strings"
	"testing"
)

// telegrafSample is a verbatim excerpt of what the container's
// outputs.prometheus_client endpoint serves, captured from a live run. Parsing
// the real thing guards against the format drifting away from the parser.
const telegrafSample = `# HELP cpu_core_class_cores Telegraf collected metric
# TYPE cpu_core_class_cores untyped
cpu_core_class_cores{class="E",host="itest",source="pmu"} 8
cpu_core_class_cores{class="LPE",host="itest",source="heuristic"} 2
cpu_core_class_cores{class="P",host="itest",source="pmu"} 12
# HELP cpu_frequency_avg_frequency Telegraf collected metric
# TYPE cpu_frequency_avg_frequency untyped
cpu_frequency_avg_frequency{host="itest"} 1.09055e+06
# HELP gpu_engine_usage_usage Telegraf collected metric
# TYPE gpu_engine_usage_usage untyped
gpu_engine_usage_usage{engine="rcs",gpu_id="0",host="itest"} 17.34
# HELP mem_used_percent Telegraf collected metric
# TYPE mem_used_percent untyped
mem_used_percent{host="itest"} 42.5
`

func parseString(t *testing.T, s string) []Sample {
	t.Helper()

	samples, err := Parse(strings.NewReader(s))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	return samples
}

func TestParseTelegrafExposition(t *testing.T) {
	samples := parseString(t, telegrafSample)

	if len(samples) != 6 {
		t.Fatalf("got %d samples, want 6", len(samples))
	}

	first := samples[0]
	if first.Name != "cpu_core_class_cores" {
		t.Errorf("name = %q, want cpu_core_class_cores", first.Name)
	}
	if first.Value != 8 {
		t.Errorf("value = %v, want 8", first.Value)
	}
	if first.TimestampMS != 0 {
		t.Errorf("timestamp = %d, want 0 for a line that carries none", first.TimestampMS)
	}
	wantLabels := map[string]string{"class": "E", "host": "itest", "source": "pmu"}
	for k, want := range wantLabels {
		if got := first.Labels[k]; got != want {
			t.Errorf("label %s = %q, want %q", k, got, want)
		}
	}
	if len(first.Labels) != len(wantLabels) {
		t.Errorf("got %d labels, want %d", len(first.Labels), len(wantLabels))
	}

	// Telegraf renders large numbers in exponent form, so the value parser
	// has to accept it rather than only plain decimals.
	if got := samples[3].Value; got != 1090550 {
		t.Errorf("cpu_frequency_avg_frequency = %v, want 1090550", got)
	}
}

func TestParseSkipsCommentsAndBlankLines(t *testing.T) {
	samples := parseString(t, "\n# HELP x help text\n\n# TYPE x gauge\nx 1\n")

	if len(samples) != 1 {
		t.Fatalf("got %d samples, want 1", len(samples))
	}
	if samples[0].Name != "x" || samples[0].Value != 1 {
		t.Errorf("got %+v, want x = 1", samples[0])
	}
}

func TestParseWithoutLabelsLeavesLabelsNil(t *testing.T) {
	samples := parseString(t, "up 1\n")

	// A nil map keeps the unlabelled case allocation-free and still reads
	// as empty, so the display layer needs no special case.
	if samples[0].Labels != nil {
		t.Errorf("Labels = %v, want nil", samples[0].Labels)
	}
}

func TestParseEmptyLabelSet(t *testing.T) {
	samples := parseString(t, "up{} 1\n")

	if len(samples[0].Labels) != 0 {
		t.Errorf("Labels = %v, want empty", samples[0].Labels)
	}
}

func TestParseTimestamp(t *testing.T) {
	samples := parseString(t, `x{a="b"} 2.5 1750000000123`)

	if samples[0].TimestampMS != 1750000000123 {
		t.Errorf("timestamp = %d, want 1750000000123", samples[0].TimestampMS)
	}
	if samples[0].Value != 2.5 {
		t.Errorf("value = %v, want 2.5", samples[0].Value)
	}
}

func TestParseNonFiniteValues(t *testing.T) {
	// Prometheus uses these to mean "collected but unavailable". Dropping
	// them would make an unavailable reading indistinguishable from a
	// missing series.
	samples := parseString(t, "a NaN\nb +Inf\nc -Inf\n")

	if !math.IsNaN(samples[0].Value) {
		t.Errorf("a = %v, want NaN", samples[0].Value)
	}
	if !math.IsInf(samples[1].Value, 1) {
		t.Errorf("b = %v, want +Inf", samples[1].Value)
	}
	if !math.IsInf(samples[2].Value, -1) {
		t.Errorf("c = %v, want -Inf", samples[2].Value)
	}
}

func TestParseLabelValueEscapes(t *testing.T) {
	samples := parseString(t, `x{path="a\\b",text="say \"hi\"",multi="one\ntwo",other="\q"} 1`)

	labels := samples[0].Labels
	cases := map[string]string{
		"path":  `a\b`,
		"text":  `say "hi"`,
		"multi": "one\ntwo",
		// An undefined escape is passed through verbatim, matching the
		// behaviour of the reference parsers.
		"other": "q",
	}
	for name, want := range cases {
		if got := labels[name]; got != want {
			t.Errorf("label %s = %q, want %q", name, got, want)
		}
	}
}

func TestParseToleratesWhitespace(t *testing.T) {
	samples := parseString(t, "  x{ a = \"b\" , c = \"d\" }   1.5   17  \n")

	if len(samples) != 1 {
		t.Fatalf("got %d samples, want 1", len(samples))
	}
	got := samples[0]
	if got.Name != "x" || got.Value != 1.5 || got.TimestampMS != 17 {
		t.Errorf("got %+v, want x=1.5 @17", got)
	}
	if got.Labels["a"] != "b" || got.Labels["c"] != "d" {
		t.Errorf("labels = %v, want a=b c=d", got.Labels)
	}
}

func TestParseCommaSeparatedLabelsWithBraceInValue(t *testing.T) {
	// A '}' inside a quoted value must not end the label set.
	samples := parseString(t, `x{cmd="a}b",host="h"} 1`)

	if samples[0].Labels["cmd"] != "a}b" {
		t.Errorf("cmd = %q, want a}b", samples[0].Labels["cmd"])
	}
	if samples[0].Labels["host"] != "h" {
		t.Errorf("host = %q, want h", samples[0].Labels["host"])
	}
}

func TestParseRejectsMalformedInput(t *testing.T) {
	cases := map[string]string{
		"missing value":              "x\n",
		"missing value after labels": `x{a="b"}` + "\n",
		"unterminated label set":     `x{a="b" 1` + "\n",
		"unterminated value":         `x{a="b} 1` + "\n",
		"unquoted value":             "x{a=b} 1\n",
		"missing equals":             "x{a} 1\n",
		"empty label name":           `x{="b"} 1` + "\n",
		"bad value":                  "x abc\n",
		"bad timestamp":              "x 1 abc\n",
		"trailing input":             "x 1 2 3\n",
		"unexpected separator":       `x{a="b";c="d"} 1` + "\n",
		"trailing escape":            `x{a="b\` + "\n",
	}

	for name, input := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := Parse(strings.NewReader(input)); err == nil {
				t.Fatalf("Parse(%q) succeeded, want an error", input)
			}
		})
	}
}

func TestParseErrorNamesTheLine(t *testing.T) {
	// The endpoint serves thousands of lines; an error that does not say
	// which one is nearly useless when diagnosing a live host.
	_, err := Parse(strings.NewReader("good 1\nalso_good 2\nbad abc\n"))
	if err == nil {
		t.Fatal("Parse succeeded, want an error")
	}
	if !strings.Contains(err.Error(), "line 3") {
		t.Errorf("error = %q, want it to mention line 3", err)
	}
}

func TestParseRejectsTooManySamples(t *testing.T) {
	// The body size can be capped by the caller and the payload can still
	// carry an unreasonable number of very short lines.
	var b strings.Builder
	for i := 0; i <= MaxSamples; i++ {
		b.WriteString("x 1\n")
	}

	_, err := Parse(strings.NewReader(b.String()))
	if !errors.Is(err, ErrTooManySamples) {
		t.Fatalf("err = %v, want ErrTooManySamples", err)
	}
}

func TestParseRejectsOverlongLine(t *testing.T) {
	long := "x{a=\"" + strings.Repeat("z", maxLineBytes) + "\"} 1\n"

	if _, err := Parse(strings.NewReader(long)); err == nil {
		t.Fatal("Parse succeeded on an overlong line, want an error")
	}
}

func TestParseEmptyInput(t *testing.T) {
	samples := parseString(t, "")

	if len(samples) != 0 {
		t.Errorf("got %d samples, want 0", len(samples))
	}
}
