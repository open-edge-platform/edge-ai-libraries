// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/source"
)

// renderFixture returns the view of a model fed the given exposition.
//
// The window is made taller than any panel set so these tests are about what
// is rendered, not about the scroll clipping, which is covered separately.
func renderFixture(t *testing.T, exposition string) string {
	t.Helper()

	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, exposition),
	}))
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 100, Height: 200})

	return m.View()
}

func wantContains(t *testing.T, view, want string) {
	t.Helper()

	if !strings.Contains(view, want) {
		t.Errorf("view is missing %q\n--- view ---\n%s", want, view)
	}
}

func TestViewRendersCPUAndMemory(t *testing.T) {
	view := renderFixture(t, hostExposition)

	for _, want := range []string{
		"metrics-manager",
		"itest",
		"CPU",
		"user 3.5%",
		"system 1.2%",
		"idle 95.2%",
		"1.09 GHz",
		"47.5 °C",
		"Memory",
		"42.5%",
		"57.5%",
		"q quit",
	} {
		wantContains(t, view, want)
	}
}

func TestViewRendersCoreClassTable(t *testing.T) {
	view := renderFixture(t, hostExposition)

	for _, want := range []string{"class", "cores", "frequency", "source", "P", "E", "LPE", "pmu", "heuristic"} {
		wantContains(t, view, want)
	}

	// The E and LPE rows carry only a core count in the fixture, so their
	// remaining cells must read as absent rather than as zero usage.
	wantContains(t, view, absent)
}

func TestViewOmitsCoreClassTableWhenAbsent(t *testing.T) {
	// A host whose kernel does not report core classes should not show an
	// empty table with only a header.
	view := renderFixture(t, "mem_used_percent{host=\"h\"} 10\n")

	if strings.Contains(view, "cores") {
		t.Errorf("view shows the class table with no classes\n%s", view)
	}
}

func TestViewShowsPlaceholdersForMissingMeasurements(t *testing.T) {
	m := testModel(nil)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{At: fixedNow}))

	view := m.View()

	// An empty snapshot must never render as zeroes, which would assert
	// something false about the host.
	if strings.Contains(view, "0.0%") {
		t.Errorf("missing measurements rendered as zero\n%s", view)
	}
	wantContains(t, view, absent)
}

func TestViewShowsConnectingBeforeFirstSnapshot(t *testing.T) {
	wantContains(t, testModel(nil).View(), "connecting")
}

func TestViewShowsLostContact(t *testing.T) {
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:  fixedNow,
		Err: errors.New("connection refused"),
	}))

	view := m.View()
	wantContains(t, view, "no contact")
	wantContains(t, view, "connection refused")
}

func TestViewShowsAgeOfLastSuccessWhileDisconnected(t *testing.T) {
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow.Add(-90 * time.Second),
		Samples: parseFixture(t, hostExposition),
	}))
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At:  fixedNow,
		Err: errors.New("refused"),
	}))

	view := m.View()
	wantContains(t, view, "1m30s ago")
	// The last known numbers stay on screen so the operator keeps context.
	wantContains(t, view, "3.5%")
}

func TestViewSanitizesRemoteText(t *testing.T) {
	// The host label and the error text both originate outside this
	// process. An escape sequence reaching the terminal could move the
	// cursor or change its mode.
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:  fixedNow,
		Err: errors.New("boom \x1b[2J\x07"),
	}))
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, "up{host=\"h\x1b[31m\"} 1\n"),
	}))

	view := m.View()
	if strings.Contains(view, "\x1b[2J") {
		t.Errorf("a screen-clearing sequence survived into the view\n%q", view)
	}
	if strings.Contains(view, "\x07") {
		t.Errorf("a bell character survived into the view\n%q", view)
	}
}

func TestViewFitsRequestedWidth(t *testing.T) {
	for _, width := range []int{20, 60, 79, 80, 100, 138, 139, 209, 210} {
		t.Run(fmt.Sprintf("%d_columns", width), func(t *testing.T) {
			m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
				At:      fixedNow,
				Samples: parseFixture(t, hostExposition+acceleratorExposition),
			}))
			m, _ = update(t, m, tea.WindowSizeMsg{Width: width, Height: 200})

			for _, line := range strings.Split(m.View(), "\n") {
				if n := lipgloss.Width(line); n > width {
					t.Errorf("line of %d columns exceeds the %d-column window: %q",
						n, width, line)
				}
			}
		})
	}
}

func TestViewUsesReportedWidthForNarrowWindows(t *testing.T) {
	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, hostExposition),
	}))
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 40, Height: 100})

	view := m.View()
	wantContains(t, view, "CPU")
	wantContains(t, view, "Memory")
	for _, line := range strings.Split(view, "\n") {
		if n := lipgloss.Width(line); n > 40 {
			t.Errorf("line of %d columns exceeds the terminal: %q", n, line)
		}
	}
}

func TestViewPacksPanelsAcrossWideWindows(t *testing.T) {
	for _, tt := range []struct {
		name        string
		width       int
		sameLine    []string
		notSameLine []string
	}{
		{
			name:        "single column",
			width:       152,
			notSameLine: []string{"CPU", "Memory"},
		},
		{
			name:     "two columns",
			width:    153,
			sameLine: []string{"┌ CPU", "┌ Processes"},
		},
		{
			name:        "three priority columns",
			width:       224,
			sameLine:    []string{"┌ CPU", "┌ GPU 0", "┌ Processes"},
			notSameLine: []string{"┌ CPU", "┌ Memory"},
		},
	} {
		t.Run(tt.name, func(t *testing.T) {
			m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
				At:      fixedNow,
				Samples: parseFixture(t, hostExposition+acceleratorExposition),
			}))
			m.dash.Processes = []Process{{PID: "42", Command: "worker"}}
			m, _ = update(t, m, tea.WindowSizeMsg{Width: tt.width, Height: 200})

			lines := strings.Split(m.View(), "\n")
			if len(tt.sameLine) > 0 && !lineContainsAll(lines, tt.sameLine...) {
				t.Errorf("%v are not rendered in the same row\n%s", tt.sameLine, m.View())
			}
			if len(tt.notSameLine) > 0 && lineContainsAll(lines, tt.notSameLine...) {
				t.Errorf("%v unexpectedly share a row\n%s", tt.notSameLine, m.View())
			}
		})
	}
}

func lineContainsAll(lines []string, values ...string) bool {
	for _, line := range lines {
		all := true
		for _, value := range values {
			if !strings.Contains(line, value) {
				all = false
				break
			}
		}
		if all {
			return true
		}
	}

	return false
}

func TestViewMarksStaleData(t *testing.T) {
	fresh, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow.Add(-100 * time.Millisecond),
		Samples: parseFixture(t, hostExposition),
	}))
	stale, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow.Add(-time.Hour),
		Samples: parseFixture(t, hostExposition),
	}))

	// Nothing failed in either case, so the distinction has to come from
	// the age readout itself.
	wantContains(t, fresh.View(), "0.1s ago")
	wantContains(t, stale.View(), "1h00m ago")
}

func TestViewRendersTrendCharts(t *testing.T) {
	m := testModel(nil)
	for sample, memory := range []float64{40, 50, 60} {
		m, _ = update(t, m, snapshotMsg(source.Snapshot{
			At: fixedNow.Add(time.Duration(sample) * time.Second),
			Samples: parseFixture(t, fmt.Sprintf(`
cpu_usage_idle{cpu="cpu-total"} %g
mem_used_percent %g
`, 100-memory, memory)),
		}))
	}
	m.now = func() time.Time { return fixedNow.Add(2 * time.Second) }
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 120, Height: 100})
	m, _ = update(t, m, key("2"))

	view := m.View()
	wantContains(t, view, "[2 Trends]")
	wantContains(t, view, "CPU utilization")
	wantContains(t, view, "Memory used")
	wantContains(t, view, "last 60.0%")
	wantContains(t, view, "-5m")
	wantContains(t, view, "⣿")

	for _, line := range strings.Split(view, "\n") {
		if width := lipgloss.Width(line); width > 120 {
			t.Errorf("trend line is %d columns wide, want at most 120: %q", width, line)
		}
	}
}

func TestViewOmitsChartsWithoutMeasurements(t *testing.T) {
	m := testModel(nil)
	m, _ = update(t, m, snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, hostExposition),
	}))
	m, _ = update(t, m, key("2"))

	view := m.View()
	if strings.Contains(view, "GPU utilization") || strings.Contains(view, "NPU utilization") {
		t.Errorf("view renders charts for absent accelerators\n%s", view)
	}
}

func TestViewLimitsDisplayedProcesses(t *testing.T) {
	config := DefaultDashboardConfig()
	config.Processes.MaxDisplayed = 2
	m := NewModelWithConfig(nil, config)
	m.now = func() time.Time { return fixedNow }
	m.dash.Processes = []Process{
		{PID: "1", Command: "first", CPUPercent: reading(90)},
		{PID: "2", Command: "second", CPUPercent: reading(80)},
		{PID: "3", Command: "third", CPUPercent: reading(70)},
	}

	view := m.View()
	wantContains(t, view, "first")
	wantContains(t, view, "second")
	if strings.Contains(view, "third") {
		t.Errorf("view exceeded the configured process limit\n%s", view)
	}
}

func TestViewShowsActiveWarnings(t *testing.T) {
	config := DefaultDashboardConfig()
	m := NewModelWithConfig(nil, config)
	m.now = func() time.Time { return fixedNow }
	for range config.Alerts.SamplesToRaise {
		next, _ := m.Update(snapshotMsg(source.Snapshot{
			At: fixedNow,
			Samples: parseFixture(t, `
mem_used_percent{host="h"} 95
mem_available_percent{host="h"} 5
`),
		}))
		m = next.(Model)
	}

	view := m.View()
	wantContains(t, view, "Alerts: 1 critical | 0 warning")
	if strings.Contains(view, "Inspect memory-intensive processes") {
		t.Fatal("alert details displaced the hardware panels")
	}
	m, _ = update(t, m, key("a"))
	view = m.View()
	wantContains(t, view, "Active (1)")
	wantContains(t, view, "CRITICAL")
	wantContains(t, view, "Inspect memory-intensive processes")
	wantContains(t, view, "95.0%")
}

func TestViewShowsMemoryTotals(t *testing.T) {
	view := renderFixture(t, hostExposition)

	wantContains(t, view, "of ")
	wantContains(t, view, "GiB")
}

func TestViewRendersGPUPanel(t *testing.T) {
	view := renderFixture(t, acceleratorExposition)

	wantContains(t, view, "GPU 0")
	// The driver is named so an unavailable counter below is explicable
	// rather than looking like a fault.
	wantContains(t, view, "i915")
	wantContains(t, view, "graphics 0.00 W")
	wantContains(t, view, "package 19.86 W")
	wantContains(t, view, "42.0 °C")

	// Every engine the driver reports is listed, including the longest
	// name, which must not be truncated by the column width.
	for _, engine := range []string{"render", "compute", "copy", "video", "video-enhance"} {
		wantContains(t, view, engine)
	}
	wantContains(t, view, "55.0%")

	wantContains(t, view, "gt0")
	wantContains(t, view, "gt1")
	wantContains(t, view, "2.30 GHz")
}

func TestViewSeparatesTileColumns(t *testing.T) {
	// Regression: the throttle column is left-aligned and follows a
	// right-aligned one that can fill its width exactly, which ran the two
	// cells together as "2.30 GHznone".
	view := renderFixture(t, acceleratorExposition)

	var checked int
	for _, line := range strings.Split(view, "\n") {
		line = strings.TrimRight(strings.TrimSuffix(strings.TrimPrefix(line, "│"), "│"), " ")
		if !strings.HasPrefix(line, "  gt") {
			continue
		}
		checked++

		fields := strings.Fields(line)
		throttle := fields[len(fields)-1]
		if !strings.HasSuffix(line, "  "+throttle) {
			t.Errorf("throttle cell is not separated from the frequency: %q", line)
		}
	}

	if checked != 2 {
		t.Fatalf("checked %d tile rows, want 2", checked)
	}
}

func TestViewShowsThrottleReasons(t *testing.T) {
	view := renderFixture(t, acceleratorExposition)

	// A throttled tile must name why, not merely say that it is throttled.
	wantContains(t, view, "thermal,vr_tdc")
	wantContains(t, view, "none")
}

func TestThrottleText(t *testing.T) {
	cases := []struct {
		name string
		tile GPUTile
		want string
	}{{
		// No throttle series at all is not evidence that nothing is
		// throttling, so it must not render as the reassuring "none".
		name: "unreported",
		tile: GPUTile{},
		want: absent,
	}, {
		name: "clear",
		tile: GPUTile{ThrottleReported: true, Throttled: reading(0)},
		want: "none",
	}, {
		name: "named reasons",
		tile: GPUTile{ThrottleReported: true, Throttled: reading(1), ThrottleReasons: []string{"thermal", "pl1"}},
		want: "thermal,pl1",
	}, {
		// The summary flag is set while every named reason is clear:
		// the cause is unknown, which is not the same as absent.
		name: "aggregate only",
		tile: GPUTile{ThrottleReported: true, Throttled: reading(1)},
		want: "yes",
	}}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := throttleText(c.tile); got != c.want {
				t.Errorf("got %q, want %q", got, c.want)
			}
		})
	}
}

func TestViewOmitsVRAMOnIntegratedGPU(t *testing.T) {
	// qmassa reports a zero VRAM total on integrated graphics rather than
	// omitting the field, and "0 B of 0 B" is not worth a line.
	if strings.Contains(renderFixture(t, acceleratorExposition), "vram") {
		t.Error("a VRAM row was rendered for an integrated GPU")
	}

	wantContains(t, renderFixture(t, `gpu_memory_vram_total_bytes{gpu_id="0"} 8.589934592e+09
gpu_memory_vram_used_bytes{gpu_id="0"} 1.073741824e+09
`), "vram")
}

func TestViewRendersNPUPanel(t *testing.T) {
	view := renderFixture(t, acceleratorExposition)

	wantContains(t, view, "NPU")
	wantContains(t, view, "63.5%")
	wantContains(t, view, "1.40 GHz")
	wantContains(t, view, "1.75 W")
	wantContains(t, view, "12.5 MB/s")
	// The -1 sentinel means the counter does not exist on this platform.
	wantContains(t, view, "memory        "+absent)
}

func TestViewOmitsNPUPanelWhenAbsent(t *testing.T) {
	// A host with no NPU publishes no npu_ series. A panel of dashes would
	// suggest a broken sensor rather than absent hardware.
	if strings.Contains(renderFixture(t, hostExposition), "NPU") {
		t.Error("an NPU panel was rendered on a host without one")
	}
}

func TestViewShowsSharedMemoryAsUnavailableOnI915(t *testing.T) {
	view := renderFixture(t, acceleratorExposition)

	// "0 B of 93.6 GiB" would read as a measurement of no usage. The
	// counter is one this driver never fills in, so it is marked
	// unavailable while the total, which is real, is still shown.
	wantContains(t, view, unavailable+" of ")
	for _, line := range strings.Split(view, "\n") {
		if strings.Contains(line, "shared mem") && strings.Contains(line, "0 B") {
			t.Errorf("shared memory rendered as a measured zero: %q", line)
		}
	}
}

func TestViewScrollsWhenContentExceedsWindow(t *testing.T) {
	m := acceleratorModel(t, 24)

	first := m.View()
	wantContains(t, first, "CPU")
	// The window is too short for everything, so the operator is told the
	// view is partial rather than left to assume the NPU is missing.
	wantContains(t, first, "of ")
	wantContains(t, first, "scroll")

	end, _ := update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	wantContains(t, end.View(), "NPU")
}

func TestViewScrollClampsAtBothEnds(t *testing.T) {
	m := acceleratorModel(t, 24)

	// Scrolling up from the top must not move, and the top line must stay
	// on screen.
	up, _ := update(t, m, tea.KeyMsg{Type: tea.KeyUp})
	if up.offset != 0 {
		t.Errorf("offset = %d after scrolling up from the top, want 0", up.offset)
	}

	end, _ := update(t, m, tea.KeyMsg{Type: tea.KeyEnd})
	past, _ := update(t, end, tea.KeyMsg{Type: tea.KeyDown})
	if past.offset != end.offset {
		t.Errorf("offset = %d past the end, want %d", past.offset, end.offset)
	}
	// The last body line must still be visible rather than scrolled off
	// into a screen of blanks.
	wantContains(t, past.View(), "tile config")
}

func TestViewScrollResetsWhenWindowGrows(t *testing.T) {
	// A window that grows can leave the view scrolled past the end, which
	// would render a screen of blank lines.
	m := acceleratorModel(t, 24)
	m, _ = update(t, m, tea.KeyMsg{Type: tea.KeyEnd})

	grown, _ := update(t, m, tea.WindowSizeMsg{Width: 100, Height: 200})
	if grown.offset != 0 {
		t.Errorf("offset = %d after the window grew, want 0", grown.offset)
	}
	wantContains(t, grown.View(), "CPU")
	wantContains(t, grown.View(), "NPU")
}

func TestViewFillsWindowHeightExactly(t *testing.T) {
	// Rendering more lines than the terminal has would scroll the header
	// away and defeat the clipping.
	const height = 24

	view := acceleratorModel(t, height).View()
	if got := len(strings.Split(view, "\n")); got != height {
		t.Errorf("view has %d lines, want %d", got, height)
	}
}

// acceleratorModel returns a model showing every panel in a window of the
// given height.
func acceleratorModel(t *testing.T, height int) Model {
	t.Helper()

	m, _ := update(t, testModel(nil), snapshotMsg(source.Snapshot{
		At:      fixedNow,
		Samples: parseFixture(t, hostExposition+acceleratorExposition),
	}))
	m, _ = update(t, m, tea.WindowSizeMsg{Width: 100, Height: height})

	return m
}
