// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package gpu

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// fixedTime is an arbitrary instant used so rendered timestamps are stable.
var fixedTime = time.Unix(0, 1725062400000000000)

func newTestParser() *Parser {
	parser := NewParser("test-host")
	parser.now = func() time.Time { return fixedTime }
	return parser
}

// render turns points into the lines the plugin would print.
func render(t *testing.T, points []lineproto.Point) []string {
	t.Helper()
	lines := make([]string, 0, len(points))
	for _, point := range points {
		rendered, err := point.Append(nil)
		if err != nil {
			t.Fatalf("Append() error: %v", err)
		}
		lines = append(lines, strings.TrimSuffix(string(rendered), "\n"))
	}
	return lines
}

// TestParseRealSample runs the parser over a line captured from qmassa 2.1.0
// on an Intel Meteor Lake iGPU, so the expectations are pinned to output the
// tool actually produces rather than to an assumed schema.
func TestParseRealSample(t *testing.T) {
	line := readFixture(t, "sample_state.json")

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	want := []string{
		// i915 engine names, sorted for a stable order.
		"gpu_engine_usage,engine=compute,type=compute,host=test-host,gpu_id=0,driver=i915 usage=0.0 1725062400000000000",
		"gpu_engine_usage,engine=copy,type=copy,host=test-host,gpu_id=0,driver=i915 usage=0.0 1725062400000000000",
		"gpu_engine_usage,engine=render,type=render,host=test-host,gpu_id=0,driver=i915 usage=0.0 1725062400000000000",
		"gpu_engine_usage,engine=video,type=video,host=test-host,gpu_id=0,driver=i915 usage=0.0 1725062400000000000",
		"gpu_engine_usage,engine=video-enhance,type=video-enhance,host=test-host,gpu_id=0,driver=i915 usage=0.0 1725062400000000000",
		// Both tiles are reported. gt1 has a lower ceiling than gt0 and was
		// dropped entirely by the Python reader.
		"gpu_frequency,type=cur_freq,tile=gt0,host=test-host,gpu_id=0,driver=i915 act_freq_hz=800000000,cur_freq_hz=800000000,max_freq_hz=2300000000,min_freq_hz=800000000 1725062400000000000",
		"gpu_throttle,tile=gt0,host=test-host,gpu_id=0,driver=i915 pl1=0i,pl2=0i,pl4=0i,prochot=0i,ratl=0i,status=0i,thermal=0i,vr_tdc=0i,vr_thermalert=0i 1725062400000000000",
		"gpu_frequency,type=cur_freq,tile=gt1,host=test-host,gpu_id=0,driver=i915 act_freq_hz=450000000,cur_freq_hz=100000000,max_freq_hz=1300000000,min_freq_hz=100000000 1725062400000000000",
		"gpu_throttle,tile=gt1,host=test-host,gpu_id=0,driver=i915 pl1=0i,pl2=0i,pl4=0i,prochot=0i,ratl=0i,status=0i,thermal=0i,vr_tdc=0i,vr_thermalert=0i 1725062400000000000",
		"gpu_power,type=gpu_cur_power,host=test-host,gpu_id=0,driver=i915 power_w=0.0 1725062400000000000",
		"gpu_power,type=pkg_cur_power,host=test-host,gpu_id=0,driver=i915 power_w=0.0 1725062400000000000",
		// smem_used is zero because i915 does not expose it; xe does.
		"gpu_memory,host=test-host,gpu_id=0,driver=i915 smem_total_bytes=100516229120,smem_used_bytes=0,vram_total_bytes=0,vram_used_bytes=0 1725062400000000000",
		"gpu_temperature,sensor=pkg,host=test-host,gpu_id=0,driver=i915 temperature_c=42.0 1725062400000000000",
	}

	got := render(t, points)
	if len(got) != len(want) {
		t.Fatalf("got %d lines, want %d:\n%s", len(got), len(want), strings.Join(got, "\n"))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("line %d:\n got: %s\nwant: %s", i, got[i], want[i])
		}
	}
}

// TestParseIgnoresStreamHeader covers the two lines qmassa prints before any
// telemetry: a bare version string and the options object. Neither is an
// error, and neither may produce metrics.
func TestParseIgnoresStreamHeader(t *testing.T) {
	header := readFixture(t, "header.json")
	parser := newTestParser()

	for _, line := range bytes.Split(bytes.TrimSpace(header), []byte("\n")) {
		points, err := parser.Parse(line)
		if err != nil {
			t.Errorf("Parse(%.40s) error: %v", line, err)
		}
		if len(points) != 0 {
			t.Errorf("Parse(%.40s) produced %d points, want none", line, len(points))
		}
	}
}

func TestParseRejectsInvalidJSON(t *testing.T) {
	if _, err := newTestParser().Parse([]byte("{not json")); err == nil {
		t.Error("Parse() accepted invalid JSON, want an error")
	}
}

func TestFractionalClockAndMemoryBaseUnits(t *testing.T) {
	points, err := newTestParser().Parse([]byte(`{"timestamps":[1],"devs_state":[{
			"dev_nodes":"renderD128","dev_stats":{
			"freqs":[[{"cur_freq":700.25,"act_freq":0}]],
			"mem_info":[{"smem_used":9007199254740993}]}}]}`))
	if err != nil {
		t.Fatal(err)
	}
	got := strings.Join(render(t, points), "\n")
	for _, want := range []string{
		"act_freq_hz=0,cur_freq_hz=700250000",
		"smem_used_bytes=9007199254740993",
	} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %s in %s", want, got)
		}
	}
	for _, legacy := range []string{"value=", "cur_freq=", "act_freq=", "smem_used="} {
		if strings.Contains(got, legacy) {
			t.Fatalf("legacy alias %s emitted", legacy)
		}
	}
}

// TestParseUsesMostRecentSample verifies the rolling window is read from the
// end: qmassa resends the last 40 readings on every line.
func TestParseUsesMostRecentSample(t *testing.T) {
	line := []byte(`{"timestamps":[1,2,3],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "dev_stats":{"eng_usage":{"rcs":[1,2,42]},
	  "freqs":[[{"cur_freq":100}],[{"cur_freq":2300}]],
	  "power":[{"gpu_cur_power":1},{"gpu_cur_power":9.5}]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	for _, want := range []string{"usage=42", "cur_freq_hz=2300000000", "power_w=9.5"} {
		if !strings.Contains(got, want) {
			t.Errorf("Parse() = %s, want it to contain %s", got, want)
		}
	}
}

// TestParsePreservesNumericLiterals guards against a decode/re-encode round
// trip silently rewriting the values qmassa reported.
func TestParsePreservesNumericLiterals(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{"rcs":[0.0],"ccs":[100.0],"bcs":[3.733059578240674]},
	  "freqs":[],"power":[]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	for _, want := range []string{"usage=3.733059578240674", "usage=100.0", "usage=0.0"} {
		if !strings.Contains(got, want) {
			t.Errorf("Parse() = %s, want it to contain %s", got, want)
		}
	}
}

func TestParseGPUIdentifiers(t *testing.T) {
	tests := []struct {
		name     string
		devNodes string
		want     string
		skipped  bool
	}{
		{name: "first render node", devNodes: "card1, renderD128", want: "gpu_id=0"},
		{name: "second render node", devNodes: "card2, renderD129", want: "gpu_id=1"},
		{name: "high minor number", devNodes: "renderD200", want: "gpu_id=72"},
		// Minors below 128 are primary nodes, not render nodes.
		{name: "primary node only", devNodes: "card0", skipped: true},
		{name: "minor below the render range", devNodes: "renderD127", skipped: true},
		{name: "empty", devNodes: "", skipped: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"` + tt.devNodes + `",
			  "dev_stats":{"eng_usage":{"rcs":[1]},"freqs":[],"power":[]}}]}`)

			points, err := newTestParser().Parse(line)
			if err != nil {
				t.Fatalf("Parse() error: %v", err)
			}
			if tt.skipped {
				if len(points) != 0 {
					t.Errorf("Parse(%q) produced %d points, want none", tt.devNodes, len(points))
				}
				return
			}
			got := strings.Join(render(t, points), "\n")
			if !strings.Contains(got, tt.want) {
				t.Errorf("Parse(%q) = %s, want it to contain %s", tt.devNodes, got, tt.want)
			}
		})
	}
}

// TestParseEscapesTagValues covers engine and power names being interpolated
// into tags. The Python reader used plain string formatting, so a name
// containing a space or comma would have produced a corrupt line.
func TestParseEscapesTagValues(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{"odd name,x":[5]},"freqs":[],"power":[]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	if !strings.Contains(got, `engine=odd\ name\,x`) {
		t.Errorf("Parse() = %s, want the space and comma escaped", got)
	}
}

// TestParseSkipsEmptyAndAbsentSections covers a device that reports no
// telemetry at all; the line must be dropped rather than rendered with
// missing fields.
func TestParseSkipsEmptyAndAbsentSections(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{"rcs":[]},"freqs":[[]],"power":[]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}
	if len(points) != 0 {
		t.Errorf("Parse() produced %d points, want none", len(points))
	}
}

func TestParseMultipleDevices(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[
	  {"dev_nodes":"renderD128","dev_stats":{"eng_usage":{"rcs":[1]},"freqs":[],"power":[]}},
	  {"dev_nodes":"renderD129","dev_stats":{"eng_usage":{"rcs":[2]},"freqs":[],"power":[]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}
	if len(points) != 2 {
		t.Fatalf("got %d points, want 2", len(points))
	}
}

// TestParseTagsEveryPointWithDriver checks the driver name reaches every
// measurement, not just the memory one it was introduced for.
//
// i915 and xe populate different counters, so a consumer that cannot see the
// driver cannot tell a counter this driver never fills from a measured zero.
func TestParseTagsEveryPointWithDriver(t *testing.T) {
	points, err := newTestParser().Parse(readFixture(t, "sample_state.json"))
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}
	if len(points) == 0 {
		t.Fatal("no points parsed")
	}

	for _, line := range render(t, points) {
		if !strings.Contains(line, ",driver=i915 ") {
			t.Errorf("point carries no driver tag: %s", line)
		}
	}
}

func TestParseUsesDriverNameFromDevice(t *testing.T) {
	// The tag is whatever qmassa reported, not a value this code chose, so
	// a host on xe is labelled xe without any change here.
	line := []byte(`{"timestamps":[1],"devs_state":[
	  {"dev_nodes":"renderD128","drv_name":"xe","dev_stats":{"eng_usage":{"rcs":[1]}}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := render(t, points)
	if len(got) != 1 {
		t.Fatalf("got %d points, want 1", len(got))
	}
	if !strings.Contains(got[0], ",driver=xe ") {
		t.Errorf("got %s, want a driver=xe tag", got[0])
	}
}

func TestParseOmitsDriverTagWhenUnreported(t *testing.T) {
	// An empty tag value is not a usable label. Emitting driver="" would be
	// worse than omitting it: it looks like a driver whose name is blank.
	line := []byte(`{"timestamps":[1],"devs_state":[
	  {"dev_nodes":"renderD128","dev_stats":{"eng_usage":{"rcs":[1]}}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := render(t, points)
	if len(got) != 1 {
		t.Fatalf("got %d points, want 1", len(got))
	}
	if strings.Contains(got[0], "driver=") {
		t.Errorf("got %s, want no driver tag", got[0])
	}
}

func TestParseKeepsRawMemoryCountersOnI915(t *testing.T) {
	// The zero smem_used is deliberately passed through rather than
	// suppressed here. Dropping it would lose the counter for a driver that
	// does report it, and the driver tag is what lets a consumer decide.
	points, err := newTestParser().Parse(readFixture(t, "sample_state.json"))
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	var found bool
	for _, line := range render(t, points) {
		if strings.HasPrefix(line, "gpu_memory,") {
			found = true
			if !strings.Contains(line, "smem_used_bytes=0") {
				t.Errorf("smem_used was not reported: %s", line)
			}
		}
	}
	if !found {
		t.Error("no gpu_memory point was emitted")
	}
}

// --- Follow -----------------------------------------------------------------

// TestFollowReadsFIFOAndReopens verifies the reader survives qmassa
// restarting, which closes and reopens the write end of the FIFO.
func TestFollowReadsFIFOAndReopens(t *testing.T) {
	fifo := filepath.Join(t.TempDir(), "qmassa.fifo")
	if err := syscall.Mkfifo(fifo, 0o600); err != nil {
		t.Fatalf("Mkfifo: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var mu sync.Mutex
	var lines []string
	received := make(chan struct{}, 8)

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		// The reopen pause is shortened so the test asserts the reopen
		// behaviour rather than the wall clock.
		followWithRetry(ctx, fifo, func(line []byte) {
			mu.Lock()
			lines = append(lines, string(line))
			mu.Unlock()
			received <- struct{}{}
		}, func(string, ...any) {}, time.Millisecond)
	}()

	// Each payload is delivered through its own open/close cycle of the
	// write end, which is what makes the reader reopen. The blank line
	// travels with "second" instead of taking a session of its own: a
	// session that never reached the reader would otherwise let "the blank
	// line was dropped" pass for the wrong reason.
	deliver(t, fifo, "first\n", received)
	deliver(t, fifo, "\nsecond\n", received)

	cancel()
	wg.Wait()

	mu.Lock()
	defer mu.Unlock()
	if len(lines) != 2 || lines[0] != "first" || lines[1] != "second" {
		t.Errorf("got %q, want [first second]", lines)
	}
}

// deliver sends payload through one open/close cycle of the FIFO's write end
// and returns once the reader has reported a line from it.
//
// The handoff is retried because the test restarts the writer far faster than
// qmassa ever would. A writer that opens while the reader is still tearing
// down the previous session gets hold of a descriptor the reader is about to
// drop, and the bytes are then either refused with EPIPE or discarded
// unnoticed. Both outcomes are artefacts of the test's timing rather than
// anything the reader did wrong, so the session is simply repeated.
func deliver(t *testing.T, fifo, payload string, received <-chan struct{}) {
	t.Helper()

	for deadline := time.Now().Add(15 * time.Second); time.Now().Before(deadline); {
		if deliverOnce(t, fifo, payload, received) {
			return
		}
	}

	t.Fatalf("reader never picked up %q", payload)
}

// deliverOnce runs a single writer session and reports whether the reader
// acknowledged it.
//
// The writer is held open until the acknowledgement arrives, because the
// reader cannot reach EOF -- and so cannot drop the descriptor holding these
// bytes -- while a writer is still attached.
func deliverOnce(t *testing.T, fifo, payload string, received <-chan struct{}) bool {
	t.Helper()

	writer, err := os.OpenFile(fifo, os.O_WRONLY, 0)
	if err != nil {
		t.Fatalf("open for writing: %v", err)
	}
	defer writer.Close()

	if _, err := writer.WriteString(payload); err != nil {
		if errors.Is(err, syscall.EPIPE) {
			return false
		}
		t.Fatalf("write: %v", err)
	}

	select {
	case <-received:
		return true
	case <-time.After(2 * time.Second):
		// The bytes landed in a descriptor the reader had already
		// abandoned, so nothing will ever come back for them.
		return false
	}
}

// TestFollowReturnsWhenCancelledBeforeWriter checks that a plugin waiting for
// qmassa still honours SIGTERM. Opening a FIFO for reading blocks until a
// writer appears, so a naive implementation would hang here.
func TestFollowReturnsWhenCancelledBeforeWriter(t *testing.T) {
	fifo := filepath.Join(t.TempDir(), "qmassa.fifo")
	if err := syscall.Mkfifo(fifo, 0o600); err != nil {
		t.Fatalf("Mkfifo: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		Follow(ctx, fifo, func([]byte) {}, func(string, ...any) {})
		close(done)
	}()

	cancel()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("Follow() did not return after cancellation")
	}
}

// TestFollowWarnsOnceThenIdles pins the backoff: a host with no Intel GPU must
// produce one warning and then go quiet, instead of logging every second.
func TestFollowWarnsOnceThenIdles(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "absent.fifo")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var mu sync.Mutex
	var messages []string
	go Follow(ctx, missing, func([]byte) {}, func(format string, args ...any) {
		mu.Lock()
		messages = append(messages, format)
		mu.Unlock()
	})

	// retryDelay is one second, so this covers several fast retries without
	// reaching the idle threshold.
	time.Sleep(2500 * time.Millisecond)
	cancel()

	mu.Lock()
	defer mu.Unlock()
	if len(messages) != 1 {
		t.Fatalf("got %d messages, want exactly one: %q", len(messages), messages)
	}
	if !strings.Contains(messages[0], "not found") {
		t.Errorf("got %q, want a not-found warning", messages[0])
	}
}

// TestFollowRejectsOversizedLine ensures a corrupt stream cannot make the
// plugin allocate without bound.
func TestFollowRejectsOversizedLine(t *testing.T) {
	path := filepath.Join(t.TempDir(), "huge.json")
	file, err := os.Create(path)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	writer := bufio.NewWriter(file)
	chunk := bytes.Repeat([]byte("x"), 1<<20)
	for i := 0; i < (maxLineBytes>>20)+1; i++ {
		if _, err := writer.Write(chunk); err != nil {
			t.Fatalf("write: %v", err)
		}
	}
	writer.Flush()
	file.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var mu sync.Mutex
	var messages []string
	go Follow(ctx, path, func([]byte) {
		t.Error("oversized line was delivered, want it rejected")
	}, func(format string, args ...any) {
		mu.Lock()
		messages = append(messages, format)
		mu.Unlock()
	})

	time.Sleep(500 * time.Millisecond)
	cancel()

	mu.Lock()
	defer mu.Unlock()
	if len(messages) == 0 {
		t.Error("oversized line was ignored silently, want it reported")
	}
}

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	content, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatalf("reading fixture %s: %v", name, err)
	}
	return content
}

// TestParseTileNaming covers the tile label, which comes from freq_limits and
// falls back to a positional name when qmassa does not supply one.
func TestParseTileNaming(t *testing.T) {
	tests := []struct {
		name       string
		freqLimits string
		want       []string
	}{
		{
			name:       "named by freq_limits",
			freqLimits: `[{"name":"gt0"},{"name":"gt1"}]`,
			want:       []string{"tile=gt0", "tile=gt1"},
		},
		{
			// A discrete card can expose more tiles than freq_limits names.
			name:       "falls back for unnamed tiles",
			freqLimits: `[{"name":"gtA"}]`,
			want:       []string{"tile=gtA", "tile=gt1"},
		},
		{
			name:       "falls back when absent",
			freqLimits: `[]`,
			want:       []string{"tile=gt0", "tile=gt1"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
			  "freq_limits":` + tt.freqLimits + `,
			  "dev_stats":{"eng_usage":{},"freqs":[[{"cur_freq":1},{"cur_freq":2}]],"power":[]}}]}`)

			points, err := newTestParser().Parse(line)
			if err != nil {
				t.Fatalf("Parse() error: %v", err)
			}
			got := strings.Join(render(t, points), "\n")
			for _, want := range tt.want {
				if !strings.Contains(got, want) {
					t.Errorf("Parse() = %s, want it to contain %s", got, want)
				}
			}
		})
	}
}

// TestParseThrottleReasons checks that a tile running below its requested
// frequency reports why, as 0/1 so the Prometheus output can expose it.
func TestParseThrottleReasons(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{},"power":[],"freqs":[[{"cur_freq":2300,"act_freq":900,
	  "throttle_reasons":{"pl1":true,"thermal":false,"status":true}}]]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	want := "gpu_throttle,tile=gt0,host=test-host,gpu_id=0 pl1=1i,status=1i,thermal=0i"
	if !strings.Contains(got, want) {
		t.Errorf("Parse() = %s, want it to contain %s", got, want)
	}
	// act_freq well below cur_freq is what makes the throttle flags useful.
	if !strings.Contains(got, "act_freq_hz=900000000,cur_freq_hz=2300000000") {
		t.Errorf("Parse() = %s, want both the requested and actual frequency", got)
	}
}

// TestParseFans covers a discrete card; an integrated GPU reports no fans.
func TestParseFans(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{},"power":[],"freqs":[],
	  "fans":[[{"name":"fan1","speed":1200},{"name":"fan2","speed":0}]]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	for _, want := range []string{
		"gpu_fan,fan=fan1,host=test-host,gpu_id=0 speed_hz=20",
		"gpu_fan,fan=fan2,host=test-host,gpu_id=0 speed_hz=0",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("Parse() = %s, want it to contain %s", got, want)
		}
	}
}

// TestParseForwardsUnknownKeys guards the decision to decode power, mem_info
// and throttle_reasons as maps: a field added by a future qmassa release must
// reach Telegraf rather than be silently dropped.
func TestParseForwardsUnknownKeys(t *testing.T) {
	line := []byte(`{"timestamps":[1],"devs_state":[{"dev_nodes":"renderD128",
	  "dev_stats":{"eng_usage":{},"freqs":[],
	  "power":[{"vram_cur_power":7.5}],
	  "mem_info":[{"smem_used":1024,"future_field":42}]}}]}`)

	points, err := newTestParser().Parse(line)
	if err != nil {
		t.Fatalf("Parse() error: %v", err)
	}

	got := strings.Join(render(t, points), "\n")
	for _, want := range []string{"type=vram_cur_power", "future_field_bytes=42", "smem_used_bytes=1024"} {
		if !strings.Contains(got, want) {
			t.Errorf("Parse() = %s, want it to contain %s", got, want)
		}
	}
}

// newClientParser builds a parser with the opt-in per-process measurement and
// a frozen clock. The limit is left off so the existing expectations see every
// process in the fixture; the cap has tests of its own.
func newClientParser() *Parser {
	parser := NewParser("test-host", WithClientStats(0))
	parser.now = func() time.Time { return fixedTime }
	return parser
}

// TestParseOmitsClientStatsByDefault guards the default that keeps per-process
// series out of Prometheus.
func TestParseOmitsClientStatsByDefault(t *testing.T) {
	points, err := newTestParser().Parse(readFixture(t, "sample_state.json"))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	for _, line := range render(t, points) {
		if strings.HasPrefix(line, MeasurementClient) {
			t.Errorf("client point emitted without WithClientStats(): %s", line)
		}
	}
}

// TestParseClientStatsAggregatesPerProcess covers the opt-in measurement,
// including a process holding two DRM clients on the same device.
func TestParseClientStatsAggregatesPerProcess(t *testing.T) {
	const sample = `{"timestamps":[1],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "clis_stats":[
	    {"clients":[[1,10]],"pid":7,"comm":"infer","cpu_usage":[1.5],
	     "eng_usage":{"render":[10.0],"compute":[4.0]},
	     "mem_info":[{"smem_used":100,"vram_used":0}],"is_active":false},
	    {"clients":[[1,11]],"pid":7,"comm":"infer","cpu_usage":[0.5],
	     "eng_usage":{"render":[5.0],"compute":[1.0]},
	     "mem_info":[{"smem_used":50,"vram_used":0}],"is_active":true},
	    {"clients":[[1,12]],"pid":10,"comm":"other","cpu_usage":[2.0],
	     "eng_usage":{"render":[1.0]},"mem_info":[{"smem_used":7,"vram_used":0}],
	     "is_active":false}],
	  "dev_stats":{}}]}`

	points, err := newClientParser().Parse([]byte(sample))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}

	// pid 7 is summed across both of its clients and stays active because one
	// of them is; pid 10 sorts after pid 7 numerically, not lexicographically.
	want := strings.Join([]string{
		"gpu_client,pid=7,comm=infer,host=test-host,gpu_id=0 active=1i,cpu=2,engine_compute=5,engine_render=15,smem_used_bytes=150,vram_used_bytes=0 1725062400000000000",
		"gpu_client,pid=10,comm=other,host=test-host,gpu_id=0 active=0i,cpu=2,engine_render=1,smem_used_bytes=7,vram_used_bytes=0 1725062400000000000",
	}, "\n")

	if got := strings.Join(render(t, points), "\n"); got != want {
		t.Errorf("client points mismatch:\ngot:\n%s\nwant:\n%s", got, want)
	}
}

// crowdedGPU describes four processes with distinct engine usage, so a ranked
// cap has an unambiguous answer. The render node in dev_nodes is what the
// parser derives gpu_id from; without it the whole device is skipped.
const crowdedGPU = `{"timestamps":[1],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "clis_stats":[
	    {"clients":[[1,1]],"pid":11,"comm":"idle","cpu_usage":[0.0],
	     "eng_usage":{"render":[0.0]},"mem_info":[{}],"is_active":false},
	    {"clients":[[1,2]],"pid":12,"comm":"busiest","cpu_usage":[0.0],
	     "eng_usage":{"render":[80.0]},"mem_info":[{}],"is_active":true},
	    {"clients":[[1,3]],"pid":13,"comm":"middling","cpu_usage":[0.0],
	     "eng_usage":{"render":[40.0]},"mem_info":[{}],"is_active":true},
	    {"clients":[[1,4]],"pid":14,"comm":"cpubound","cpu_usage":[99.0],
	     "eng_usage":{"render":[0.0]},"mem_info":[{}],"is_active":false}],
	  "dev_stats":{}}]}`

// TestParseClientStatsKeepsTheBusiest covers the cap that replaced excluding
// the measurement from Prometheus altogether.
func TestParseClientStatsKeepsTheBusiest(t *testing.T) {
	parser := NewParser("test-host", WithClientStats(2))
	parser.now = func() time.Time { return fixedTime }

	points, err := parser.Parse([]byte(crowdedGPU))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}

	got := strings.Join(render(t, points), "\n")

	for _, want := range []string{"comm=busiest", "comm=middling"} {
		if !strings.Contains(got, want) {
			t.Errorf("Parse() dropped %s, want the two busiest processes kept:\n%s", want, got)
		}
	}
	// The CPU-bound process outscores the idle one, but neither touches the
	// engines, so both fall outside a cap of two.
	for _, unwanted := range []string{"comm=idle", "comm=cpubound"} {
		if strings.Contains(got, unwanted) {
			t.Errorf("Parse() kept %s, want it dropped by the cap:\n%s", unwanted, got)
		}
	}
}

// TestParseClientStatsCapZeroKeepsEveryProcess covers the escape hatch for an
// operator who would rather have the full picture than a bounded one.
func TestParseClientStatsCapZeroKeepsEveryProcess(t *testing.T) {
	parser := NewParser("test-host", WithClientStats(0))
	parser.now = func() time.Time { return fixedTime }

	points, err := parser.Parse([]byte(crowdedGPU))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}

	if got := len(render(t, points)); got != 4 {
		t.Errorf("Parse() emitted %d client points, want all 4", got)
	}
}

// TestParseClientStatsCapIsStableWhenIdle guards against the cap flapping on a
// machine where nothing is using the GPU and every process scores zero. An
// unstable choice would make series appear and disappear every second.
func TestParseClientStatsCapIsStableWhenIdle(t *testing.T) {
	const idleGPU = `{"timestamps":[1],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "clis_stats":[
	    {"clients":[[1,1]],"pid":31,"comm":"a","cpu_usage":[0.0],"eng_usage":{"render":[0.0]},"mem_info":[{}],"is_active":false},
	    {"clients":[[1,2]],"pid":32,"comm":"b","cpu_usage":[0.0],"eng_usage":{"render":[0.0]},"mem_info":[{}],"is_active":false},
	    {"clients":[[1,3]],"pid":33,"comm":"c","cpu_usage":[0.0],"eng_usage":{"render":[0.0]},"mem_info":[{}],"is_active":false}],
	  "dev_stats":{}}]}`

	parser := NewParser("test-host", WithClientStats(2))
	parser.now = func() time.Time { return fixedTime }

	first, err := parser.Parse([]byte(idleGPU))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	second, err := parser.Parse([]byte(idleGPU))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}

	if a, b := strings.Join(render(t, first), "\n"), strings.Join(render(t, second), "\n"); a != b {
		t.Errorf("the cap picked different processes for identical input:\nfirst:\n%s\nsecond:\n%s", a, b)
	}
}

// TestParseClientStatsNeverLeaksCmdline is a security regression test: a
// process command line may hold credentials, so it must not reach the output
// even though qmassa reports it.
func TestParseClientStatsNeverLeaksCmdline(t *testing.T) {
	sample := `{"timestamps":[1],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "clis_stats":[{"clients":[[1,10]],"pid":7,"comm":"infer",
	    "cmdline":"serve --api-key=SUPERSECRET","cpu_usage":[1.0],
	    "eng_usage":{},"mem_info":[],"is_active":true}],"dev_stats":{}}]}`

	points, err := newClientParser().Parse([]byte(sample))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	if len(points) == 0 {
		t.Fatal("expected a client point")
	}
	for _, line := range render(t, points) {
		if strings.Contains(line, "SUPERSECRET") || strings.Contains(line, "cmdline") {
			t.Fatalf("command line leaked into output: %s", line)
		}
	}
}

// TestParseClientStatsSkipsIncompleteEntries checks that an entry carrying no
// DRM client is ignored rather than emitted under an empty tag.
func TestParseClientStatsSkipsIncompleteEntries(t *testing.T) {
	const sample = `{"timestamps":[1],"devs_state":[{"dev_nodes":"card1, renderD128",
	  "clis_stats":[{"clients":[],"pid":7,"comm":"gone","cpu_usage":[1.0]}],
	  "dev_stats":{}}]}`

	points, err := newClientParser().Parse([]byte(sample))
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	if len(points) != 0 {
		t.Errorf("expected no points, got %v", render(t, points))
	}
}
