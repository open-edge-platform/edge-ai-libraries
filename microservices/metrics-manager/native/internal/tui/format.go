// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"time"
)

const (
	// absent marks a measurement the host does not report at all, such as
	// NPU memory on a platform whose sysfs does not expose it.
	absent = "—"

	// unavailable marks a measurement that was collected but has no usable
	// value. Prometheus uses NaN and the infinities for exactly this, and
	// conflating it with absent would tell the operator the hardware lacks
	// a sensor when in fact the reading failed.
	unavailable = "n/a"
)

// formatPercent renders a percentage to one decimal.
func formatPercent(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.1f%%", r.Value)
}

// formatFrequencyKHz renders the CPU panel's display-unit reading.
func formatFrequencyKHz(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	// Below a gigahertz the megahertz figure is the one an operator reads,
	// and a fractional megahertz is noise from the sysfs sampling.
	if r.Value < 1_000_000 {
		return fmt.Sprintf("%.0f MHz", r.Value/1_000)
	}

	return fmt.Sprintf("%.2f GHz", r.Value/1_000_000)
}

// formatTemperature renders a Celsius reading.
func formatTemperature(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.1f °C", r.Value)
}

// formatFrequencyMHz renders a frequency given in MHz, the unit qmassa reports
// for GPU tiles.
func formatFrequencyMHz(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	if math.Abs(r.Value) < 1_000 {
		return fmt.Sprintf("%.0f MHz", r.Value)
	}

	return fmt.Sprintf("%.2f GHz", r.Value/1_000)
}

// formatFrequencyHz renders a frequency given in Hz, the unit mm-plugin-npu
// reports.
//
// The NPU idles at zero and runs into the gigahertz, so the unit is chosen per
// reading rather than fixed; a bare Hz figure would be unreadable under load.
func formatFrequencyHz(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	switch magnitude := math.Abs(r.Value); {
	case magnitude < 1_000:
		return fmt.Sprintf("%.0f Hz", r.Value)
	case magnitude < 1_000_000:
		return fmt.Sprintf("%.0f kHz", r.Value/1_000)
	case magnitude < 1_000_000_000:
		return fmt.Sprintf("%.0f MHz", r.Value/1_000_000)
	default:
		return fmt.Sprintf("%.2f GHz", r.Value/1_000_000_000)
	}
}

// formatWatts renders a power reading. Two decimals are kept because the
// graphics rail of an idle integrated GPU draws only milliwatts.
func formatWatts(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.2f W", r.Value)
}

// formatBandwidth renders a reading already expressed in MB/s.
func formatBandwidth(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.1f MB/s", r.Value)
}

// formatBandwidthGBps renders memory throughput in decimal GB/s.
func formatBandwidthGBps(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.3f GB/s", r.Value)
}

// formatMebibytes renders a reading already expressed in MiB.
func formatMebibytes(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.0f MiB", r.Value)
}

// formatCount renders a whole-number reading such as a core count.
func formatCount(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	return fmt.Sprintf("%.0f", r.Value)
}

// byteUnits are binary multiples, matching how the kernel reports memory.
var byteUnits = []string{"B", "KiB", "MiB", "GiB", "TiB", "PiB"}

// formatBytes renders a byte count in binary units.
func formatBytes(r Reading) string {
	if s, ok := placeholder(r); ok {
		return s
	}

	value := r.Value
	negative := value < 0
	if negative {
		value = -value
	}

	unit := 0
	for value >= 1024 && unit < len(byteUnits)-1 {
		value /= 1024
		unit++
	}
	if negative {
		value = -value
	}

	// Whole bytes have no meaningful fraction; larger units do.
	if unit == 0 {
		return fmt.Sprintf("%.0f %s", value, byteUnits[unit])
	}

	return fmt.Sprintf("%.1f %s", value, byteUnits[unit])
}

// formatAge renders how stale the displayed snapshot is.
func formatAge(d time.Duration) string {
	if d < 0 {
		d = 0
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs ago", d.Seconds())
	}
	if d < time.Hour {
		return fmt.Sprintf("%dm%02ds ago", int(d.Minutes()), int(d.Seconds())%60)
	}

	return fmt.Sprintf("%dh%02dm ago", int(d.Hours()), int(d.Minutes())%60)
}

// placeholder reports the text to show instead of a number, when there is one.
func placeholder(r Reading) (string, bool) {
	if !r.OK {
		return absent, true
	}
	if math.IsNaN(r.Value) || math.IsInf(r.Value, 0) {
		return unavailable, true
	}

	return "", false
}

// sanitize prepares text that originated outside this process for display.
//
// Error strings carry fragments of the HTTP response, and writing those to a
// terminal verbatim would let an escape sequence in them move the cursor,
// repaint the screen or change the terminal's mode. Control characters are
// therefore replaced rather than passed through, and the result is truncated
// so one long error cannot push the rest of the panel off screen.
func sanitize(s string, max int) string {
	if max <= 0 {
		return ""
	}

	out := make([]rune, 0, len(s))
	for _, r := range s {
		switch {
		case r == '\t':
			out = append(out, ' ')
		// C0 controls including ESC, DEL, and the C1 range that some
		// terminals also act on.
		case r < 0x20, r == 0x7f, r >= 0x80 && r <= 0x9f:
			out = append(out, '\uFFFD')
		default:
			out = append(out, r)
		}

		if len(out) > max {
			// One rune of the budget is spent on the ellipsis so the
			// result never exceeds max.
			return string(out[:max-1]) + "…"
		}
	}

	return string(out)
}
