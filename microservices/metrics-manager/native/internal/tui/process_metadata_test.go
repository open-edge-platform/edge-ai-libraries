// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"slices"
	"strings"
	"testing"
	"unicode"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

func processMetadataExposition(uid, username string, stamp int64, cpu, threads, memory float64) string {
	labels := fmt.Sprintf("{host=\"remote-host\",pid=\"42\",process=\"worker\",uid=%q,user=%q}", uid, username)
	return fmt.Sprintf("process_cpu_percent%s %g %d\nprocess_threads%s %g %d\nprocess_memory_rss_bytes%s %g %d\n",
		labels, cpu, stamp, labels, threads, stamp, labels, memory, stamp)
}

func TestProcessMetadataFromMonitoredHost(t *testing.T) {
	for _, username := range []string{"remote-user", ""} {
		d := BuildDashboard(parseFixture(t, processMetadataExposition("1000", username, fixedNow.UnixMilli(), 140, 16, 1048576)))
		if len(d.Processes) != 1 {
			t.Fatalf("process count=%d", len(d.Processes))
		}
		p := d.Processes[0]
		wantUser := username
		if wantUser == "" {
			wantUser = "1000"
		}
		if p.User != wantUser || p.Threads != reading(16) || p.MemoryBytes != reading(1048576) ||
			p.CPUPercent != reading(140) || !p.CPUAt.Equal(fixedNow) {
			t.Fatalf("metadata changed process measurements: %+v", p)
		}
	}
}

func TestOldProcessCollectorsKeepCPUAndMemoryWithoutMetadata(t *testing.T) {
	d := BuildDashboard(parseFixture(t,
		"process_cpu_percent{pid=\"42\",process=\"worker\"} 140\n"+
			"process_memory_rss_bytes{pid=\"42\",process=\"worker\"} 1048576\n"))
	p := d.Processes[0]
	if p.User != "" || p.Threads.OK || p.CPUPercent != reading(140) || p.MemoryBytes != reading(1048576) {
		t.Fatalf("old collector compatibility lost: %+v", p)
	}
	if formatProcessUser(p.User) != absent || formatProcessThreads(p.Threads) != absent {
		t.Fatal("missing metadata was displayed as a measured value")
	}
}

func TestNewestProcessIdentityWinsOverExporterCache(t *testing.T) {
	old := processMetadataExposition("1000", "old-user", fixedNow.UnixMilli()-1000, 99, 32, 2097152)
	current := processMetadataExposition("2000", "new-user", fixedNow.UnixMilli(), 14, 2, 1048576)
	for _, text := range []string{old + current, current + old} {
		samples := parseFixture(t, text)
		for range 2 {
			p := BuildDashboard(samples).Processes[0]
			if p.User != "new-user" || p.Threads != reading(2) ||
				p.CPUPercent != reading(14) || p.MemoryBytes != reading(1048576) {
				t.Fatalf("cached identity contaminated current process: %+v", p)
			}
			slices.Reverse(samples)
		}
	}
}

func TestProcessFieldsDoNotBorrowAnotherIdentityOrTimestamp(t *testing.T) {
	old := processMetadataExposition("1000", "old-user", fixedNow.UnixMilli()-1000, 99, 32, 2097152)
	currentCPU := fmt.Sprintf("process_cpu_percent{host=\"remote-host\",pid=\"42\",process=\"worker\"} 14 %d\n", fixedNow.UnixMilli())
	p := BuildDashboard(parseFixture(t, old+currentCPU)).Processes[0]
	if p.User != "" || p.Threads.OK || p.MemoryBytes.OK || p.CPUPercent != reading(14) {
		t.Fatalf("unavailable owner borrowed cached fields: %+v", p)
	}
	newIdentityCPU := fmt.Sprintf("process_cpu_percent{host=\"remote-host\",pid=\"42\",process=\"worker\",uid=\"1000\",user=\"old-user\"} 14 %d\n", fixedNow.UnixMilli())
	p = BuildDashboard(parseFixture(t, old+newIdentityCPU)).Processes[0]
	if p.Threads.OK || p.MemoryBytes.OK || p.CPUPercent != reading(14) {
		t.Fatalf("incomplete current snapshot borrowed stale fields: %+v", p)
	}
}

func TestConflictingProcessIdentitiesAreUnavailable(t *testing.T) {
	first := processMetadataExposition("1000", "first", fixedNow.UnixMilli(), 14, 2, 1048576)
	second := processMetadataExposition("2000", "second", fixedNow.UnixMilli(), 99, 8, 2097152)
	for _, text := range []string{first + second, second + first} {
		m := testModel(nil)
		m.dash = BuildDashboard(parseFixture(t, text))
		p := m.dash.Processes[0]
		if !math.IsNaN(p.CPUPercent.Value) || p.User != "" || p.Threads.OK || p.MemoryBytes.OK {
			t.Fatalf("ambiguous sample presented as a valid identity: %+v", p)
		}
		if !m.processCoverageLimited() {
			t.Fatal("ambiguous CPU was not reported in alert diagnostics")
		}
	}
}

func TestProcessMetadataFormatting(t *testing.T) {
	for _, tc := range []struct {
		value Reading
		want  string
	}{
		{reading(16), "16"}, {Reading{}, absent}, {reading(0), unavailable},
		{reading(-1), unavailable}, {reading(1.5), unavailable},
		{reading(math.NaN()), unavailable}, {reading(math.Inf(1)), unavailable},
	} {
		if got := formatProcessThreads(tc.value); got != tc.want {
			t.Errorf("threads %+v: %q, want %q", tc.value, got, tc.want)
		}
	}
	for _, username := range []string{"bad\x1b[2J\nname", "bad\u009b2Jname", strings.Repeat("u", 200)} {
		got := formatProcessUser(username)
		if strings.IndexFunc(got, unicode.IsControl) >= 0 || lipgloss.Width(got) > 16 {
			t.Fatalf("user was not sanitized and bounded: %q", got)
		}
	}
}

func TestProcessColumnsFollowBtopOrderAcrossLayouts(t *testing.T) {
	if got := strings.Join(titles(processColumns), ","); got != "pid,process,threads,user,memory,cpu" {
		t.Fatalf("unexpected process column order: %s", got)
	}
	m := testModel(nil)
	m.dash = BuildDashboard(parseFixture(t, processMetadataExposition("1000", "remote-user", fixedNow.UnixMilli(), 140, 16, 1048576)))
	m.dash.Platform.LogicalCPUs = reading(14)
	for _, width := range []int{30, 40, 80, 100, 180, 300} {
		m.width = width
		for _, mode := range []string{"per-core", "total"} {
			m.config.Processes.CPUMode = mode
			m.processColumnOffset = 0
			panel := framePanel(m.processSection(), width)
			for _, line := range strings.Split(panel, "\n") {
				if lipgloss.Width(line) > width {
					t.Fatalf("panel at %d columns overflowed: %q", width, line)
				}
			}
			for offset := 1; offset < 100; offset++ {
				m.processColumnOffset = offset
				panel += "\n" + framePanel(m.processSection(), width)
			}
			for _, want := range []string{"worker", "16", "remote-user", "1.0 MiB"} {
				wantContains(t, panel, want)
			}
			cpu := "140.0%"
			if mode == "total" {
				cpu = "10.0%"
			}
			wantContains(t, panel, cpu)
			text := ansi.Strip(fittedProcessTable(processColumns, m.processRows(m.sortedProcesses()), width-2))
			previous := -1
			for _, title := range titles(processColumns) {
				position := strings.Index(text, title)
				if position <= previous {
					t.Fatalf("column %s was out of order at width %d:\n%s", title, width, text)
				}
				previous = position
			}
		}
	}
}
