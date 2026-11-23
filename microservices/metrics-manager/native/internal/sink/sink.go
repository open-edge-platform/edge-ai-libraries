// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package sink chooses where a plugin writes its line protocol.
//
// Plugins write to stdout by default, which is what Telegraf's execd input
// reads. That covers the container, where every process already runs as root.
//
// A bare-metal install draws a privilege boundary instead: Telegraf runs
// unprivileged, and the collectors that need root run as their own systemd
// units. Those units cannot be execd children, because an execd child inherits
// Telegraf's privileges, so they need somewhere else to put their samples.
// They connect to the unix socket that Telegraf's socket_listener input
// creates, which reads the same line protocol over a different transport.
//
// Selecting the destination at run time is what lets one binary serve both
// deployments, so a plugin can be moved across the privilege boundary by
// changing its unit file rather than its code.
package sink

import (
	"fmt"
	"io"
	"net"
	"os"
	"strings"
	"sync"
)

// unixScheme prefixes a destination naming a unix stream socket.
const unixScheme = "unix://"

// Usage documents the -out flag. It lives here so every plugin describes the
// destination the same way.
const Usage = `where to write line protocol: "stdout" for Telegraf's execd input, ` +
	`or "unix:///path/to.sock" for its socket_listener input`

// Open returns the destination named by spec.
//
// An empty spec and "stdout" both select stdout. The returned Close does not
// close stdout, so callers may defer it unconditionally.
func Open(spec string) (io.WriteCloser, error) {
	switch {
	case spec == "" || spec == "stdout":
		return nopCloser{os.Stdout}, nil

	case strings.HasPrefix(spec, unixScheme):
		path := strings.TrimPrefix(spec, unixScheme)
		if path == "" {
			return nil, fmt.Errorf("destination %q names no socket path", spec)
		}
		return &unixSink{path: path}, nil

	default:
		return nil, fmt.Errorf(
			"unsupported destination %q, want \"stdout\" or \"unix:///path/to.sock\"", spec)
	}
}

// nopCloser adapts stdout to io.WriteCloser without taking ownership of it.
type nopCloser struct{ io.Writer }

// Close does nothing, because the process does not own stdout.
func (nopCloser) Close() error { return nil }

// unixSink writes to a unix stream socket, dialling on demand.
//
// The socket belongs to Telegraf, so it does not exist before Telegraf starts
// and disappears whenever Telegraf restarts. Connecting lazily rather than at
// startup means a collector does not have to be ordered after Telegraf, and
// survives it going away.
type unixSink struct {
	path string

	// mu guards conn. Collectors are single-threaded today, but a sink is the
	// kind of thing that acquires a second writer later, and a torn
	// reconnect would corrupt the stream.
	mu   sync.Mutex
	conn net.Conn
}

// Write sends p, reconnecting once if the peer has gone away.
//
// A stale connection only reveals itself on write, so the first attempt after
// Telegraf restarts is expected to fail; the retry runs on a fresh connection.
// Any bytes stranded on the dead connection are harmless: a line protocol
// reader discards an unterminated trailing line, so a torn sample is dropped
// rather than misparsed.
func (s *unixSink) Write(p []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	n, err := s.write(p)
	if err == nil {
		return n, nil
	}

	s.drop()

	return s.write(p)
}

// write dials if needed, then sends p.
func (s *unixSink) write(p []byte) (int, error) {
	if s.conn == nil {
		conn, err := net.Dial("unix", s.path)
		if err != nil {
			return 0, err
		}
		s.conn = conn
	}

	return s.conn.Write(p)
}

// drop discards the current connection so the next write dials again.
func (s *unixSink) drop() {
	if s.conn == nil {
		return
	}
	// The connection is already suspect, so a close error says nothing useful.
	_ = s.conn.Close()
	s.conn = nil
}

// Close releases the connection, if one is open.
func (s *unixSink) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	conn := s.conn
	s.conn = nil

	if conn == nil {
		return nil
	}

	return conn.Close()
}
