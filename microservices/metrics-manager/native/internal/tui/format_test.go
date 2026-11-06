// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"testing"
	"time"
)

func TestFormatPercent(t *testing.T) {
	cases := []struct {
		in   Reading
		want string
	}{
		{reading(3.5), "3.5%"},
		{reading(0), "0.0%"},
		{reading(95.25), "95.2%"},
		{reading(100), "100.0%"},
		{Reading{}, absent},
		{reading(math.NaN()), unavailable},
	}

	for _, c := range cases {
		if got := formatPercent(c.in); got != c.want {
			t.Errorf("formatPercent(%v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestFormatFrequencyKHz(t *testing.T) {
	cases := []struct {
		in   Reading
		want string
	}{
		// Below a gigahertz the megahertz figure is what an operator reads.
		{reading(400_000), "400 MHz"},
		{reading(999_999), "1000 MHz"},
		{reading(1_000_000), "1.00 GHz"},
		{reading(1_090_550), "1.09 GHz"},
		{reading(4_800_000), "4.80 GHz"},
		{Reading{}, absent},
		{reading(math.Inf(1)), unavailable},
	}

	for _, c := range cases {
		if got := formatFrequencyKHz(c.in); got != c.want {
			t.Errorf("formatFrequencyKHz(%v) = %q, want %q", c.in.Value, got, c.want)
		}
	}
}

func TestFormatBytes(t *testing.T) {
	cases := []struct {
		in   Reading
		want string
	}{
		{reading(0), "0 B"},
		{reading(512), "512 B"},
		{reading(1024), "1.0 KiB"},
		{reading(1536), "1.5 KiB"},
		{reading(1_610_612_736), "1.5 GiB"},
		{reading(34_359_738_368), "32.0 GiB"},
		{reading(1 << 50), "1.0 PiB"},
		// Beyond the largest known unit the value must keep growing in
		// that unit rather than wrapping to a wrong one.
		{reading(4 * (1 << 50)), "4.0 PiB"},
		{Reading{}, absent},
		{reading(math.NaN()), unavailable},
	}

	for _, c := range cases {
		if got := formatBytes(c.in); got != c.want {
			t.Errorf("formatBytes(%v) = %q, want %q", c.in.Value, got, c.want)
		}
	}
}

func TestFormatBytesNegative(t *testing.T) {
	// A negative byte count means a counter went backwards; showing it as
	// such is more honest than clamping it to zero and hiding the fault.
	if got := formatBytes(reading(-2048)); got != "-2.0 KiB" {
		t.Errorf("formatBytes(-2048) = %q, want -2.0 KiB", got)
	}
}

func TestFormatTemperature(t *testing.T) {
	if got := formatTemperature(reading(47.5)); got != "47.5 °C" {
		t.Errorf("got %q, want 47.5 °C", got)
	}
	if got := formatTemperature(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatCount(t *testing.T) {
	if got := formatCount(reading(12)); got != "12" {
		t.Errorf("got %q, want 12", got)
	}
	if got := formatCount(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatFrequencyMHz(t *testing.T) {
	// qmassa reports GPU tile frequencies in MHz. The unit switches at a
	// gigahertz so a boosting tile does not print as a four-digit number.
	cases := []struct {
		value float64
		want  string
	}{
		{0, "0 MHz"},
		{800, "800 MHz"},
		{999, "999 MHz"},
		{1000, "1.00 GHz"},
		{2300, "2.30 GHz"},
	}

	for _, c := range cases {
		if got := formatFrequencyMHz(reading(c.value)); got != c.want {
			t.Errorf("formatFrequencyMHz(%v) = %q, want %q", c.value, got, c.want)
		}
	}

	if got := formatFrequencyMHz(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatFrequencyHz(t *testing.T) {
	// mm-plugin-npu reports hertz, and the NPU spans idle to gigahertz.
	cases := []struct {
		value float64
		want  string
	}{
		{0, "0 Hz"},
		{999, "999 Hz"},
		{1_000, "1 kHz"},
		{1_000_000, "1 MHz"},
		{1_400_000_000, "1.40 GHz"},
	}

	for _, c := range cases {
		if got := formatFrequencyHz(reading(c.value)); got != c.want {
			t.Errorf("formatFrequencyHz(%v) = %q, want %q", c.value, got, c.want)
		}
	}

	if got := formatFrequencyHz(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatWatts(t *testing.T) {
	// Two decimals are kept because an idle integrated graphics rail draws
	// only milliwatts, and rounding it away would read as "off".
	if got := formatWatts(reading(0.0002996)); got != "0.00 W" {
		t.Errorf("got %q, want 0.00 W", got)
	}
	if got := formatWatts(reading(19.86)); got != "19.86 W" {
		t.Errorf("got %q, want 19.86 W", got)
	}
	if got := formatWatts(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatBandwidth(t *testing.T) {
	if got := formatBandwidth(reading(12.5)); got != "12.5 MB/s" {
		t.Errorf("got %q, want 12.5 MB/s", got)
	}
	if got := formatBandwidth(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatMebibytes(t *testing.T) {
	// The reading stays in the unit the plugin reported, so the number on
	// screen matches the number in the metric.
	if got := formatMebibytes(reading(512)); got != "512 MiB" {
		t.Errorf("got %q, want 512 MiB", got)
	}
	if got := formatMebibytes(Reading{}); got != absent {
		t.Errorf("got %q, want %q", got, absent)
	}
}

func TestFormatAge(t *testing.T) {
	cases := []struct {
		in   time.Duration
		want string
	}{
		{0, "0.0s ago"},
		{400 * time.Millisecond, "0.4s ago"},
		{59 * time.Second, "59.0s ago"},
		{90 * time.Second, "1m30s ago"},
		{59*time.Minute + 59*time.Second, "59m59s ago"},
		{2*time.Hour + 5*time.Minute, "2h05m ago"},
		// A clock that stepped backwards must not render a negative age.
		{-time.Second, "0.0s ago"},
	}

	for _, c := range cases {
		if got := formatAge(c.in); got != c.want {
			t.Errorf("formatAge(%v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestPlaceholderDistinguishesAbsentFromUnavailable(t *testing.T) {
	// Conflating the two would tell the operator the hardware lacks a
	// sensor when in fact the reading failed.
	if got, ok := placeholder(Reading{}); !ok || got != absent {
		t.Errorf("absent reading gave (%q, %v)", got, ok)
	}
	if got, ok := placeholder(reading(math.NaN())); !ok || got != unavailable {
		t.Errorf("NaN reading gave (%q, %v)", got, ok)
	}
	if _, ok := placeholder(reading(1)); ok {
		t.Error("a finite reading wants no placeholder")
	}
}

func TestSanitizeStripsTerminalControlSequences(t *testing.T) {
	// An error string carries fragments of the HTTP response. Writing an
	// escape sequence from it straight to the terminal would let a remote
	// endpoint move the cursor or change the terminal's mode.
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"escape", "before\x1b[2Jafter", "before\uFFFD[2Jafter"},
		{"bell", "a\x07b", "a\uFFFDb"},
		{"carriage return", "a\rb", "a\uFFFDb"},
		{"newline", "a\nb", "a\uFFFDb"},
		{"delete", "a\x7fb", "a\uFFFDb"},
		{"c1 control", "a\x9bb", "a\uFFFDb"},
		{"tab becomes space", "a\tb", "a b"},
		{"plain text untouched", "503 Service Unavailable", "503 Service Unavailable"},
		{"non-ascii kept", "47.5 °C", "47.5 °C"},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := sanitize(c.in, 100); got != c.want {
				t.Errorf("sanitize(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestSanitizeTruncates(t *testing.T) {
	// One long error must not push the rest of the panel off screen.
	got := sanitize("abcdefghij", 5)

	if got != "abcd…" {
		t.Errorf("sanitize = %q, want abcd…", got)
	}
	if n := len([]rune(got)); n != 5 {
		t.Errorf("length = %d runes, want at most 5", n)
	}
}

func TestSanitizeEdgeCases(t *testing.T) {
	if got := sanitize("abc", 0); got != "" {
		t.Errorf("sanitize with no budget = %q, want empty", got)
	}
	if got := sanitize("", 10); got != "" {
		t.Errorf("sanitize of empty = %q, want empty", got)
	}
	// A string exactly at the budget must not be truncated.
	if got := sanitize("abcde", 5); got != "abcde" {
		t.Errorf("sanitize = %q, want abcde", got)
	}
}
