// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package sink

import (
	"bufio"
	"errors"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestOpenSelectsStdout(t *testing.T) {
	for _, spec := range []string{"", "stdout"} {
		out, err := Open(spec)
		if err != nil {
			t.Fatalf("Open(%q) returned %v", spec, err)
		}

		writer, ok := out.(nopCloser)
		if !ok {
			t.Fatalf("Open(%q) returned %T, want the stdout adapter", spec, out)
		}
		if writer.Writer != os.Stdout {
			t.Errorf("Open(%q) wrapped %v, want os.Stdout", spec, writer.Writer)
		}

		// Plugins defer Close unconditionally, so closing the stdout sink has
		// to leave the descriptor usable for the stderr diagnostics that
		// follow.
		if err := out.Close(); err != nil {
			t.Errorf("Close() on the stdout sink returned %v, want nil", err)
		}
		if _, err := os.Stdout.Stat(); err != nil {
			t.Errorf("stdout is unusable after Close(): %v", err)
		}
	}
}

func TestOpenRejectsUnusableDestinations(t *testing.T) {
	for _, spec := range []string{"unix://", "/run/collect.sock", "tcp://127.0.0.1:8094", "file:///tmp/x"} {
		if _, err := Open(spec); err == nil {
			t.Errorf("Open(%q) succeeded, want an error naming the supported forms", spec)
		}
	}
}

func TestUnixSinkDelivers(t *testing.T) {
	path := socketPath(t)
	server := listen(t, path)
	defer server.stop()

	out, err := Open("unix://" + path)
	if err != nil {
		t.Fatalf("Open() returned %v", err)
	}
	defer out.Close()

	if _, err := out.Write([]byte("npu,host=a busy=1i\n")); err != nil {
		t.Fatalf("Write() returned %v", err)
	}

	if got := server.next(t); got != "npu,host=a busy=1i" {
		t.Errorf("server received %q, want the line as written", got)
	}
}

// TestUnixSinkReconnects covers a Telegraf restart, which is the routine way
// for the socket to go away underneath a long-lived collector.
func TestUnixSinkReconnects(t *testing.T) {
	path := socketPath(t)
	first := listen(t, path)

	out, err := Open("unix://" + path)
	if err != nil {
		t.Fatalf("Open() returned %v", err)
	}
	defer out.Close()

	if _, err := out.Write([]byte("before\n")); err != nil {
		t.Fatalf("Write() before the restart returned %v", err)
	}
	if got := first.next(t); got != "before" {
		t.Fatalf("server received %q, want %q", got, "before")
	}

	// Tear the socket down the way Telegraf does: the listener goes, then the
	// established connection.
	first.stop()

	second := listen(t, path)
	defer second.stop()

	if _, err := out.Write([]byte("after\n")); err != nil {
		t.Fatalf("Write() after the restart returned %v, want the retry to succeed", err)
	}
	if got := second.next(t); got != "after" {
		t.Errorf("server received %q, want %q", got, "after")
	}
}

// TestUnixSinkReportsAnAbsentPeer checks that a collector started before
// Telegraf, or left running after it, learns that its samples are going
// nowhere rather than silently discarding them.
func TestUnixSinkReportsAnAbsentPeer(t *testing.T) {
	out, err := Open("unix://" + socketPath(t))
	if err != nil {
		t.Fatalf("Open() returned %v", err)
	}
	defer out.Close()

	_, err = out.Write([]byte("orphan\n"))
	if err == nil {
		t.Fatal("Write() to a socket nobody is listening on succeeded, want an error")
	}
	if !errors.Is(err, os.ErrNotExist) && !strings.Contains(err.Error(), "connect") {
		t.Errorf("Write() returned %v, want a dial failure", err)
	}
}

func TestUnixSinkCloseIsIdempotent(t *testing.T) {
	path := socketPath(t)
	server := listen(t, path)
	defer server.stop()

	out, err := Open("unix://" + path)
	if err != nil {
		t.Fatalf("Open() returned %v", err)
	}

	if _, err := out.Write([]byte("once\n")); err != nil {
		t.Fatalf("Write() returned %v", err)
	}

	if err := out.Close(); err != nil {
		t.Fatalf("first Close() returned %v", err)
	}
	if err := out.Close(); err != nil {
		t.Errorf("second Close() returned %v, want nil", err)
	}
}

// socketPath returns a path in a temporary directory. Unix socket paths are
// limited to about 100 bytes, which the short test directories stay well
// under.
func socketPath(t *testing.T) string {
	t.Helper()
	return filepath.Join(t.TempDir(), "collect.sock")
}

// fakeReader stands in for Telegraf's socket_listener input.
type fakeReader struct {
	listener net.Listener
	lines    chan string

	mu    sync.Mutex
	conns []net.Conn
}

func listen(t *testing.T, path string) *fakeReader {
	t.Helper()

	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatalf("cannot listen on %s: %v", path, err)
	}

	reader := &fakeReader{listener: listener, lines: make(chan string, 16)}

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}

			reader.mu.Lock()
			reader.conns = append(reader.conns, conn)
			reader.mu.Unlock()

			go func() {
				scanner := bufio.NewScanner(conn)
				for scanner.Scan() {
					reader.lines <- scanner.Text()
				}
			}()
		}
	}()

	return reader
}

// next returns the next line the reader received.
func (r *fakeReader) next(t *testing.T) string {
	t.Helper()

	select {
	case line := <-r.lines:
		return line
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for a line")
		return ""
	}
}

// stop closes the listener and every connection it accepted, so a writer that
// still holds one sees the peer go away.
func (r *fakeReader) stop() {
	_ = r.listener.Close()

	r.mu.Lock()
	defer r.mu.Unlock()

	for _, conn := range r.conns {
		_ = conn.Close()
	}
	r.conns = nil
}
