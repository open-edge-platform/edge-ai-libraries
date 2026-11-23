// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package source

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// collector accumulates snapshots from a Poller running in another goroutine.
type collector struct {
	mu   sync.Mutex
	got  []Snapshot
	done chan struct{}
	want int
}

func newCollector(want int) *collector {
	return &collector{done: make(chan struct{}), want: want}
}

func (c *collector) emit(s Snapshot) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.got = append(c.got, s)
	if len(c.got) == c.want {
		close(c.done)
	}
}

func (c *collector) snapshots() []Snapshot {
	c.mu.Lock()
	defer c.mu.Unlock()

	return append([]Snapshot(nil), c.got...)
}

// wait blocks until the wanted number of snapshots arrived.
func (c *collector) wait(t *testing.T) {
	t.Helper()

	select {
	case <-c.done:
	case <-time.After(5 * time.Second):
		t.Fatalf("timed out after %d of %d snapshots", len(c.snapshots()), c.want)
	}
}

// runPoller starts p against a collector and returns once enough snapshots
// arrived, cancelling the poller before it returns.
func runPoller(t *testing.T, p *Poller, want int) []Snapshot {
	t.Helper()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	c := newCollector(want)

	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		p.Run(ctx, c.emit)
	}()

	c.wait(t)
	cancel()

	select {
	case <-stopped:
	case <-time.After(5 * time.Second):
		t.Fatal("Run did not return after cancellation")
	}

	return c.snapshots()
}

func TestNewRejectsUnusableEndpoints(t *testing.T) {
	cases := map[string]string{
		// Restricting the scheme keeps an operator-supplied value from
		// reaching a transport nobody intended.
		"file scheme": "file:///etc/passwd",
		"unix scheme": "unix:///run/telegraf.sock",
		"no scheme":   "127.0.0.1:9273/metrics",
		"no host":     "http:///metrics",
		"unparseable": "http://[::1",
		"empty":       "",
	}

	for name, endpoint := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := New(endpoint); err == nil {
				t.Fatalf("New(%q) succeeded, want an error", endpoint)
			}
		})
	}
}

func TestNewAppliesDefaults(t *testing.T) {
	p, err := New("http://127.0.0.1:9273/metrics")
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	if p.Interval != DefaultInterval {
		t.Errorf("Interval = %v, want %v", p.Interval, DefaultInterval)
	}
	if p.MaxBodyBytes != DefaultMaxBodyBytes {
		t.Errorf("MaxBodyBytes = %d, want %d", p.MaxBodyBytes, DefaultMaxBodyBytes)
	}
	if p.Client == nil || p.Client.Timeout != DefaultTimeout {
		t.Errorf("Client = %+v, want one with a %v timeout", p.Client, DefaultTimeout)
	}
}

func TestRunDeliversParsedSamples(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, "# TYPE mem_used_percent untyped\nmem_used_percent{host=\"h\"} 42.5\n")
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	got := runPoller(t, p, 1)

	if got[0].Err != nil {
		t.Fatalf("Err = %v, want nil", got[0].Err)
	}
	if len(got[0].Samples) != 1 {
		t.Fatalf("got %d samples, want 1", len(got[0].Samples))
	}
	if got[0].Samples[0].Name != "mem_used_percent" {
		t.Errorf("name = %q, want mem_used_percent", got[0].Samples[0].Name)
	}
	if got[0].At.IsZero() {
		t.Error("At is zero, want the poll time")
	}
}

func TestRunPollsRepeatedly(t *testing.T) {
	var hits int64
	var mu sync.Mutex
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		mu.Lock()
		hits++
		n := hits
		mu.Unlock()
		fmt.Fprintf(w, "polls %d\n", n)
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	got := runPoller(t, p, 3)

	// Each snapshot must be a fresh read, not a cached first response.
	for i, s := range got[:3] {
		if s.Err != nil {
			t.Fatalf("snapshot %d: Err = %v", i, s.Err)
		}
		if want := float64(i + 1); s.Samples[0].Value != want {
			t.Errorf("snapshot %d value = %v, want %v", i, s.Samples[0].Value, want)
		}
	}
}

func TestRunReportsHTTPErrorStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "nope", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	got := runPoller(t, p, 1)

	if got[0].Err == nil {
		t.Fatal("Err = nil, want the 503 to be reported")
	}
	if !strings.Contains(got[0].Err.Error(), "503") {
		t.Errorf("Err = %q, want it to name the status", got[0].Err)
	}
	if got[0].Samples != nil {
		t.Errorf("Samples = %v, want nil on failure", got[0].Samples)
	}
}

func TestRunReportsUnreachableEndpointAndKeepsGoing(t *testing.T) {
	// A closed server stands in for the service being restarted while the
	// operator watches. The poller must report it and stay alive rather
	// than exiting and losing the session.
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	endpoint := server.URL
	server.Close()

	p := newTestPoller(t, endpoint)
	got := runPoller(t, p, 2)

	for i, s := range got[:2] {
		if s.Err == nil {
			t.Errorf("snapshot %d: Err = nil, want a connection failure", i)
		}
	}
}

func TestRunReportsMalformedBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, "this is not exposition\n")
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	got := runPoller(t, p, 1)

	if got[0].Err == nil {
		t.Fatal("Err = nil, want a parse failure")
	}
}

func TestRunRejectsOversizedBody(t *testing.T) {
	// The endpoint is trusted by convention, not by construction, so an
	// unbounded body must not be read into memory.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		for i := 0; i < 500; i++ {
			fmt.Fprintf(w, "x{a=\"%s\"} 1\n", strings.Repeat("y", 100))
		}
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	p.MaxBodyBytes = 1024

	got := runPoller(t, p, 1)

	if got[0].Err == nil {
		t.Fatal("Err = nil, want the oversized body to be rejected")
	}
	if !strings.Contains(got[0].Err.Error(), "exceeds") {
		t.Errorf("Err = %q, want it to say the body was too large", got[0].Err)
	}
}

func TestRunAcceptsBodyExactlyAtTheLimit(t *testing.T) {
	// The limit is inclusive; a body that lands exactly on it is complete
	// and must not be mistaken for a truncated one.
	body := "x 1\n"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, body)
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	p.MaxBodyBytes = int64(len(body))

	got := runPoller(t, p, 1)

	if got[0].Err != nil {
		t.Fatalf("Err = %v, want a body at the limit to be accepted", got[0].Err)
	}
}

func TestRunStopsOnContextCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, "x 1\n")
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	// Cancelling before the first poll must produce no snapshot at all: a
	// cancellation is the operator quitting, not a fault to display.
	var emitted int
	done := make(chan struct{})
	go func() {
		defer close(done)
		p.Run(ctx, func(Snapshot) { emitted++ })
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("Run did not return for a cancelled context")
	}

	if emitted != 0 {
		t.Errorf("emitted %d snapshots, want 0", emitted)
	}
}

func TestRunBacksOffWhileFailing(t *testing.T) {
	// Successive failures must lengthen the pause so a stopped service is
	// not polled at full rate for as long as the TUI stays open.
	var mu sync.Mutex
	var at []time.Time
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		mu.Lock()
		at = append(at, time.Now())
		mu.Unlock()
		http.Error(w, "down", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	p := newTestPoller(t, server.URL)
	runPoller(t, p, 4)

	mu.Lock()
	defer mu.Unlock()
	if len(at) < 4 {
		t.Fatalf("server saw %d requests, want at least 4", len(at))
	}

	first := at[1].Sub(at[0])
	third := at[3].Sub(at[2])
	if third <= first {
		t.Errorf("gap did not grow: first %v, third %v", first, third)
	}
}

// newTestPoller builds a Poller with an interval short enough to keep the
// tests quick, so they assert behaviour rather than the wall clock.
func newTestPoller(t *testing.T, endpoint string) *Poller {
	t.Helper()

	p, err := New(endpoint)
	if err != nil {
		t.Fatalf("New(%q): %v", endpoint, err)
	}
	p.Interval = time.Millisecond

	return p
}
