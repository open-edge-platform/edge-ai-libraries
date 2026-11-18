// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package source polls a Prometheus exposition endpoint and delivers
// successive snapshots of it.
//
// The endpoint is Telegraf's own outputs.prometheus_client listener, which is
// also what the service's /metrics/stream polls. Sharing that one source is
// deliberate: the TUI cannot drift from what the REST interface reports,
// because there is nothing to drift from.
//
// A failed poll is reported rather than fatal. A terminal dashboard whose
// backing service restarts should show that it lost contact and then recover
// on its own, not exit and lose the operator's session.
package source

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

const (
	// DefaultInterval matches the PROMETHEUS_POLLER_INTERVAL_MS default that
	// the service uses for its own SSE stream, so the TUI refreshes at the
	// same rate as the existing browser view.
	DefaultInterval = 500 * time.Millisecond

	// DefaultMaxBodyBytes bounds a single response. A host exposing the
	// documented measurements produces a few kilobytes; this leaves several
	// orders of magnitude of headroom while still refusing to read an
	// endless body into memory.
	DefaultMaxBodyBytes = 8 << 20

	// DefaultTimeout bounds one request. It is kept below the poll interval
	// multiplier so a wedged endpoint surfaces as an error quickly instead
	// of freezing the display.
	DefaultTimeout = 5 * time.Second

	// maxBackoff caps the pause between failing polls. It stays short
	// because the operator is watching: a longer backoff would leave the
	// screen stale for seconds after the service came back.
	maxBackoff = 5 * time.Second
)

// Snapshot is the result of one poll.
//
// Exactly one of Samples and Err is meaningful. Err is carried rather than
// returned so the display layer can distinguish "no contact" from "contacted,
// nothing to report" and tell the operator which it is.
type Snapshot struct {
	// At is when the poll completed.
	At time.Time

	// Samples holds the parsed exposition, or nil when Err is set.
	Samples []promtext.Sample

	// Err is the reason this poll produced nothing, or nil on success.
	Err error
}

// Poller repeatedly fetches an exposition endpoint.
type Poller struct {
	// URL is the exposition endpoint, for example
	// http://127.0.0.1:9273/metrics.
	URL string

	// Interval is the pause between successful polls. Zero selects
	// DefaultInterval.
	Interval time.Duration

	// MaxBodyBytes bounds one response body. Zero selects
	// DefaultMaxBodyBytes.
	MaxBodyBytes int64

	// Client issues the requests. Nil selects a client with DefaultTimeout.
	Client *http.Client
}

// New returns a Poller for endpoint with the defaults applied.
//
// The URL is validated up front so a typo in a flag fails at startup with a
// clear message instead of turning into a per-poll error behind the UI.
func New(endpoint string) (*Poller, error) {
	parsed, err := url.Parse(endpoint)
	if err != nil {
		return nil, fmt.Errorf("source: bad endpoint %q: %w", endpoint, err)
	}
	// Restricting the scheme keeps an operator-supplied value from reaching
	// a transport nobody intended, such as file://.
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, fmt.Errorf("source: endpoint %q must use http or https", endpoint)
	}
	if parsed.Host == "" {
		return nil, fmt.Errorf("source: endpoint %q has no host", endpoint)
	}

	return &Poller{
		URL:          endpoint,
		Interval:     DefaultInterval,
		MaxBodyBytes: DefaultMaxBodyBytes,
		Client:       &http.Client{Timeout: DefaultTimeout},
	}, nil
}

// Run polls until ctx is cancelled, passing every snapshot to emit.
//
// emit is called from Run's goroutine and must not block for long, or it will
// delay the next poll.
func (p *Poller) Run(ctx context.Context, emit func(Snapshot)) {
	interval := p.Interval
	if interval <= 0 {
		interval = DefaultInterval
	}

	// Consecutive failures lengthen the pause so a stopped service is not
	// polled twice a second for as long as the TUI is open.
	backoff := interval

	for {
		samples, err := p.Poll(ctx)

		// A cancellation is the operator quitting, not a fault worth
		// reporting on screen.
		if ctx.Err() != nil {
			return
		}

		emit(Snapshot{At: time.Now(), Samples: samples, Err: err})

		wait := interval
		if err != nil {
			wait = backoff
			backoff = min(backoff*2, maxBackoff)
		} else {
			backoff = interval
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(wait):
		}
	}
}

// Poll performs one request and parses the response.
//
// Run calls it on a schedule; it is exported so a caller can take a single
// reading without starting a polling loop.
func (p *Poller) Poll(ctx context.Context) ([]promtext.Sample, error) {
	client := p.Client
	if client == nil {
		client = &http.Client{Timeout: DefaultTimeout}
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, p.URL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "text/plain")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("source: %s returned %s", p.URL, resp.Status)
	}

	limit := p.MaxBodyBytes
	if limit <= 0 {
		limit = DefaultMaxBodyBytes
	}

	// One byte beyond the limit is read so an oversized body can be
	// reported as such instead of being silently truncated into a snapshot
	// that looks complete but is missing series.
	body := io.LimitReader(resp.Body, limit+1)
	counter := &countingReader{r: body}

	samples, err := promtext.Parse(counter)
	if counter.n > limit {
		return nil, fmt.Errorf("source: %s body exceeds %d bytes", p.URL, limit)
	}
	if err != nil {
		return nil, err
	}

	return samples, nil
}

// countingReader tracks how many bytes were read so the caller can tell a
// body that merely reached the limit from one that ran past it.
type countingReader struct {
	r io.Reader
	n int64
}

func (c *countingReader) Read(p []byte) (int, error) {
	n, err := c.r.Read(p)
	c.n += int64(n)
	return n, err
}
