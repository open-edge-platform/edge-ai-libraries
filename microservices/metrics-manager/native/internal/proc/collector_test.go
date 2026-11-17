// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package proc

import (
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// TestParseStatSurvivesAHostileCommand is the reason this parser does not
// split the line on whitespace. A process can name itself anything, including
// something that looks like the rest of the record, and a naive parser would
// read the fake fields instead of the real ones.
func TestParseStatSurvivesAHostileCommand(t *testing.T) {
	// The command contains spaces, a closing parenthesis and digits that
	// would be mistaken for the numeric fields.
	line := statLine("evil ) 1 2 3 4 5 6 7 8 9", 111, 222, 999, 100)

	got, err := parseStat(line, 42, 4096)
	if err != nil {
		t.Fatalf("parseStat() error = %v", err)
	}

	if got.command != "evil ) 1 2 3 4 5 6 7 8 9" {
		t.Errorf("command = %q, want the whole parenthesised name", got.command)
	}
	if got.cpuTime != 333 {
		t.Errorf("cpuTime = %d, want 333 from the real utime and stime", got.cpuTime)
	}
	if got.rss != 100*4096 {
		t.Errorf("rss = %d, want %d", got.rss, 100*4096)
	}
	if got.key.startTime != 999 {
		t.Errorf("startTime = %d, want 999", got.key.startTime)
	}
}

func TestParseStatRejectsUnusableLines(t *testing.T) {
	for name, line := range map[string]string{
		"no command":     "42 sh S 1 2 3",
		"truncated":      "42 (sh) S 1 2 3",
		"non-numeric":    statLine("sh", 111, 222, 999, 100) + " x",
		"unclosed comm":  "42 (sh S 1 2 3 4 5 6 7 8 9 10 11 12 13",
		"nothing at all": "",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := parseStat(line, 42, 4096); err == nil && name != "non-numeric" {
				t.Errorf("parseStat(%q) succeeded, want an error", line)
			}
		})
	}
}

// TestCollectReportsUsageOverTheInterval checks the arithmetic that turns two
// counter readings into a percentage.
func TestCollectReportsUsageOverTheInterval(t *testing.T) {
	root := t.TempDir()
	writeProcess(t, root, 10, "busy", 0, 0, 1, 50)

	collector, clock := newTestCollector(t, root, 0)

	// Half a second of CPU time over one second of wall clock is 50%.
	writeProcess(t, root, 10, "busy", 30, 20, 1, 50)
	clock.advance(time.Second)

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	line := render(t, points)
	if !strings.Contains(line, "cpu_percent=50.00") {
		t.Errorf("Collect() = %s, want cpu_percent=50.00", line)
	}
	if !strings.Contains(line, "memory_rss_bytes="+strconv.Itoa(50*os.Getpagesize())+"i") {
		t.Errorf("Collect() = %s, want the resident size in bytes", line)
	}
}

// TestCollectIgnoresARecycledPID guards the start-time check. Without it a new
// process inheriting an old pid would be measured against a counter that
// belongs to a process that has already exited, and would report a nonsense
// spike.
func TestCollectIgnoresARecycledPID(t *testing.T) {
	root := t.TempDir()
	writeProcess(t, root, 10, "old", 5000, 0, 1, 10)

	collector, clock := newTestCollector(t, root, 0)

	// Same pid, later start time, counter back near zero.
	writeProcess(t, root, 10, "new", 10, 0, 7777, 10)
	clock.advance(time.Second)

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	if line := render(t, points); !strings.Contains(line, "cpu_percent=0.00") {
		t.Errorf("Collect() = %s, want the recycled pid reported at zero", line)
	}
}

// TestCollectKeepsBothTopsCovers the union ranking: a process can earn its row
// by using CPU or by holding memory, and ranking on CPU alone would hide the
// second kind.
func TestCollectKeepsBothTops(t *testing.T) {
	root := t.TempDir()
	for pid := 1; pid <= 6; pid++ {
		writeProcess(t, root, pid, "p"+strconv.Itoa(pid), 0, 0, 1, 0)
	}

	collector, clock := newTestCollector(t, root, 1)

	// pid 2 burns CPU and holds nothing; pid 5 holds memory and burns
	// nothing. A cap of one per axis has to keep both.
	writeProcess(t, root, 1, "p1", 0, 0, 1, 0)
	writeProcess(t, root, 2, "cpuhog", 100, 0, 1, 0)
	writeProcess(t, root, 3, "p3", 0, 0, 1, 0)
	writeProcess(t, root, 4, "p4", 0, 0, 1, 0)
	writeProcess(t, root, 5, "memhog", 0, 0, 1, 9999)
	writeProcess(t, root, 6, "p6", 0, 0, 1, 0)
	clock.advance(time.Second)

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	got := render(t, points)
	for _, want := range []string{"process=cpuhog", "process=memhog"} {
		if !strings.Contains(got, want) {
			t.Errorf("Collect() dropped %s:\n%s", want, got)
		}
	}
	if strings.Count(got, "\n") != 2 {
		t.Errorf("Collect() emitted %d lines, want one per axis:\n%s", strings.Count(got, "\n"), got)
	}
}

// TestCollectIsStableWhenIdle guards against the ranking flapping on a machine
// where nothing is running, which would make series appear and disappear.
func TestCollectIsStableWhenIdle(t *testing.T) {
	root := t.TempDir()
	for pid := 1; pid <= 5; pid++ {
		writeProcess(t, root, pid, "p"+strconv.Itoa(pid), 0, 0, 1, 0)
	}

	collector, clock := newTestCollector(t, root, 2)

	clock.advance(time.Second)
	first, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	clock.advance(time.Second)
	second, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	if a, b := tagsOf(t, first), tagsOf(t, second); a != b {
		t.Errorf("ranking changed between identical samples:\nfirst:  %s\nsecond: %s", a, b)
	}
}

func TestNewCollectorRejectsANegativeLimit(t *testing.T) {
	if _, err := NewCollector(t.TempDir(), "h", -1); err == nil {
		t.Error("NewCollector() accepted a negative limit, want an error")
	}
}

// TestCollectPrefersRealProcessesWhenIdle covers the tie-break that keeps the
// panel useful on a quiet machine. With a pid tie-break the lowest numbers
// win, and those are kernel threads holding no memory and doing nothing.
func TestCollectPrefersRealProcessesWhenIdle(t *testing.T) {
	root := t.TempDir()
	// Low pids look like kernel threads: no memory, no CPU. The high pid
	// holds memory, which is the only thing distinguishing it.
	writeProcess(t, root, 2, "kthreadd", 0, 0, 1, 0)
	writeProcess(t, root, 3, "rcu_gp", 0, 0, 1, 0)
	writeProcess(t, root, 900, "database", 0, 0, 1, 5000)

	collector, clock := newTestCollector(t, root, 1)

	writeProcess(t, root, 2, "kthreadd", 0, 0, 1, 0)
	writeProcess(t, root, 3, "rcu_gp", 0, 0, 1, 0)
	writeProcess(t, root, 900, "database", 0, 0, 1, 5000)
	clock.advance(time.Second)

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	if got := render(t, points); !strings.Contains(got, "process=database") {
		t.Errorf("Collect() = %s, want the process holding memory to outrank the idle kernel threads", got)
	}
}

func TestNewCollectorReportsAnEmptyProcRoot(t *testing.T) {
	if _, err := NewCollector(filepath.Join(t.TempDir(), "missing"), "h", 0); err == nil {
		t.Error("NewCollector() accepted an unreadable proc root, want an error")
	}
}

// --- helpers ---------------------------------------------------------------

// testClock advances only when a test says so.
type testClock struct{ at time.Time }

func (c *testClock) advance(d time.Duration) { c.at = c.at.Add(d) }

func newTestCollector(t *testing.T, root string, limit int) (*Collector, *testClock) {
	t.Helper()

	clock := &testClock{at: time.Unix(1725062400, 0).UTC()}

	collector, err := NewCollector(root, "test-host", limit)
	if err != nil {
		t.Fatalf("NewCollector() error = %v", err)
	}
	collector.now = func() time.Time { return clock.at }
	collector.sampled = clock.at
	collector.lookupUser = func(uid string) (*user.User, error) {
		return &user.User{Uid: uid, Username: "test-user"}, nil
	}

	return collector, clock
}

// statLine builds a /proc/<pid>/stat record with the fields this package reads
// at their documented positions and plausible filler elsewhere.
func statLine(command string, utime, stime, startTime, rssPages uint64) string {
	// Fields 3 through 41, indexed from 0 as fields[field-3].
	fields := make([]string, 39)
	for i := range fields {
		fields[i] = "0"
	}
	fields[0] = "S"
	fields[fieldUTime-3] = strconv.FormatUint(utime, 10)
	fields[fieldSTime-3] = strconv.FormatUint(stime, 10)
	fields[fieldThreads-3] = "1"
	fields[fieldStartTime-3] = strconv.FormatUint(startTime, 10)
	fields[fieldRSSPages-3] = strconv.FormatUint(rssPages, 10)

	return "1 (" + command + ") " + strings.Join(fields, " ")
}

func writeProcess(t *testing.T, root string, pid int, command string, utime, stime, startTime, rssPages uint64) {
	t.Helper()

	dir := filepath.Join(root, strconv.Itoa(pid))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("cannot create %s: %v", dir, err)
	}

	line := statLine(command, utime, stime, startTime, rssPages)
	if err := os.WriteFile(filepath.Join(dir, "stat"), []byte(line), 0o644); err != nil {
		t.Fatalf("cannot write stat for pid %d: %v", pid, err)
	}
	if err := os.WriteFile(filepath.Join(dir, "status"), []byte("Uid:\t1000\t1000\t1000\t1000\n"), 0o644); err != nil {
		t.Fatalf("cannot write status for pid %d: %v", pid, err)
	}
}

func render(t *testing.T, points []lineproto.Point) string {
	t.Helper()

	var b strings.Builder
	for _, point := range points {
		rendered, err := point.Append(nil)
		if err != nil {
			t.Fatalf("Append() error = %v", err)
		}
		b.Write(rendered)
	}

	return b.String()
}

// tagsOf reduces points to their identifying tags, which is what has to stay
// stable between refreshes.
func tagsOf(t *testing.T, points []lineproto.Point) string {
	t.Helper()

	names := make([]string, 0, len(points))
	for _, point := range points {
		for _, tag := range point.Tags {
			if tag.Key == "pid" {
				names = append(names, tag.Value)
			}
		}
	}

	return strings.Join(names, ",")
}
