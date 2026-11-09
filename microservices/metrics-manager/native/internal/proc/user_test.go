// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package proc

import (
	"bytes"
	"errors"
	"log"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestReadRealUID(t *testing.T) {
	for _, tc := range []struct {
		input, want string
	}{
		{"Name:\tworker\nUid:\t1000\t0\t0\t1000\nThreads:\t16\n", "1000"},
		{"Uid:\t0\t0\t0\t0\n", "0"},
		{"Uid: 4294967295 1 2 3\n", "4294967295"},
	} {
		got, err := readUID(strings.NewReader(tc.input))
		if err != nil || got != tc.want {
			t.Errorf("UID = %q, %v; want %q", got, err, tc.want)
		}
	}
	for _, input := range []string{
		"", "Name: worker\n", "Uid: 1 2 3\n", "Uid: 1 2 3 4 5\n",
		"Uid: -1 0 0 0\n", "Uid: 4294967296 0 0 0\n", "Uid: 1 x 3 4\n",
		strings.Repeat("x", 64*1024) + "\nUid: 1 1 1 1\n",
	} {
		if _, err := readUID(strings.NewReader(input)); err == nil {
			t.Error("invalid or oversized UID record was accepted")
		}
	}
}

func TestProcessThreadCountParsing(t *testing.T) {
	for _, tc := range []struct {
		value string
		valid bool
	}{
		{"16", true}, {"1", true}, {"0", false}, {"-1", false},
		{"1.5", false}, {"x", false}, {"9223372036854775808", false},
	} {
		line := statLine("worker ) with spaces", 100, 50, 77, 12)
		cut := strings.LastIndex(line, ")") + 1
		fields := strings.Fields(line[cut:])
		fields[fieldThreads-3] = tc.value
		parsed, err := parseStat(line[:cut]+" "+strings.Join(fields, " "), 42, 4096)
		if (err == nil) != tc.valid {
			t.Fatalf("threads %s: unexpected error %v", tc.value, err)
		}
		if tc.value == "16" && (parsed.threads != 16 || parsed.cpuTime != 150 || parsed.rss != 12*4096) {
			t.Fatalf("thread parsing changed other fields: %+v", parsed)
		}
	}
}

func TestCollectIncludesThreadsAndHostUserWithoutChangingCPU(t *testing.T) {
	root := t.TempDir()
	writeProcess(t, root, 42, "worker", 0, 0, 77, 12)
	writeProcess(t, root, 43, "other", 0, 0, 78, 1)
	collector, clock := newTestCollector(t, root, 10)
	lookups := 0
	collector.lookupUser = func(uid string) (*user.User, error) {
		lookups++
		return &user.User{Uid: uid, Username: "remote-user"}, nil
	}
	writeProcess(t, root, 42, "worker", 100, 40, 77, 12)
	clock.advance(time.Second)
	points, err := collector.Collect()
	if err != nil {
		t.Fatal(err)
	}
	text := render(t, points)
	for _, want := range []string{"uid=1000,user=remote-user", "cpu_percent=140.00", "threads=1i"} {
		if !strings.Contains(text, want) {
			t.Errorf("missing %q in %s", want, text)
		}
	}
	if len(points) != 2 || lookups != 1 {
		t.Fatalf("points=%d, lookups=%d; want 2 and 1", len(points), lookups)
	}
	// Account changes are picked up next interval; the lookup cache is bounded
	// to selected UIDs in one collection, not every account ever encountered.
	collector.lookupUser = func(uid string) (*user.User, error) {
		return &user.User{Uid: uid, Username: "renamed-user"}, nil
	}
	clock.advance(time.Second)
	points, err = collector.Collect()
	if err != nil || !strings.Contains(render(t, points), "user=renamed-user") {
		t.Fatalf("account rename was not reflected: %v", err)
	}
}

func TestUnknownUserFallsBackToUIDAndFailuresAreReported(t *testing.T) {
	var logs bytes.Buffer
	previous := log.Writer()
	log.SetOutput(&logs)
	t.Cleanup(func() { log.SetOutput(previous) })
	collector := &Collector{}
	for _, tc := range []struct {
		account *user.User
		err     error
		wantLog bool
	}{
		{nil, user.UnknownUserIdError(1000), false},
		{nil, errors.New("lookup unavailable"), true},
		{&user.User{Username: "bad\nname"}, nil, true},
		{&user.User{Username: strings.Repeat("a", 257)}, nil, true},
		{nil, nil, true},
	} {
		logs.Reset()
		collector.lookupUser = func(string) (*user.User, error) { return tc.account, tc.err }
		if got := collector.username("1000"); got != "" {
			t.Fatalf("unknown or invalid name was published: %q", got)
		}
		if (logs.Len() > 0) != tc.wantLog || strings.Contains(logs.String(), "bad\nname") {
			t.Fatalf("unexpected lookup diagnostics: %q", logs.String())
		}
	}
	root := t.TempDir()
	writeProcess(t, root, 42, "worker", 0, 0, 1, 10)
	c, clock := newTestCollector(t, root, 10)
	c.lookupUser = func(string) (*user.User, error) { return nil, user.UnknownUserIdError(1000) }
	clock.advance(time.Second)
	points, err := c.Collect()
	if err != nil {
		t.Fatal(err)
	}
	text := render(t, points)
	if !strings.Contains(text, "uid=1000") || strings.Contains(text, ",user=") {
		t.Fatalf("numeric identity was not retained: %s", text)
	}
}

func TestUnreadableOwnerDoesNotDiscardProcessMeasurements(t *testing.T) {
	var logs bytes.Buffer
	previous := log.Writer()
	log.SetOutput(&logs)
	t.Cleanup(func() { log.SetOutput(previous) })
	root := t.TempDir()
	writeProcess(t, root, 42, "worker", 0, 0, 1, 10)
	if err := os.WriteFile(filepath.Join(root, "42", "status"), []byte("Uid: invalid\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	collector, clock := newTestCollector(t, root, 10)
	clock.advance(time.Second)
	points, err := collector.Collect()
	if err != nil || len(points) != 1 {
		t.Fatalf("owner failure discarded CPU/RSS: %v", err)
	}
	if text := render(t, points); strings.Contains(text, ",uid=") || !strings.Contains(text, "threads=1i") {
		t.Fatalf("unexpected owner fallback: %s", text)
	}
	if !strings.Contains(logs.String(), "user unavailable") {
		t.Fatal("malformed owner was not diagnosed")
	}
	if err := os.Remove(filepath.Join(root, "42", "status")); err != nil {
		t.Fatal(err)
	}
	if parsed, err := collector.read(42); err != nil || parsed.uid != "" || parsed.threads != 1 {
		t.Fatalf("disappearing status mixed or discarded measurements: %+v, %v", parsed, err)
	}
}

func TestReadLiveProcessMetadata(t *testing.T) {
	collector := &Collector{procRoot: "/proc", pageSize: int64(os.Getpagesize())}
	process, err := collector.read(os.Getpid())
	if err != nil {
		t.Fatal(err)
	}
	if process.uid != strconv.Itoa(os.Getuid()) || process.threads < 1 {
		t.Fatal("live procfs did not provide the current process's real UID and thread count")
	}
}

func TestOwnerLookupUsesPinnedProcessDirectory(t *testing.T) {
	path := t.TempDir()
	writeProcess(t, path, 42, "old", 0, 0, 1, 1)
	root, err := os.OpenRoot(filepath.Join(path, "42"))
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	if err := os.Rename(filepath.Join(path, "42"), filepath.Join(path, "old")); err != nil {
		t.Fatal(err)
	}
	writeProcess(t, path, 42, "new", 0, 0, 2, 1)
	if err := os.WriteFile(filepath.Join(path, "42", "status"), []byte("Uid: 2000 2000 2000 2000\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if uid := processUID(root, 42); uid != "1000" {
		t.Fatalf("recycled PID supplied another owner's UID: %q", uid)
	}
}
