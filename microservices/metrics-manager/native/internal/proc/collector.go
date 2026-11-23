// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package proc reports the processes using the most CPU and memory.
//
// Telegraf ships procstat, and it was the obvious candidate, but it answers a
// different question: it monitors processes you name in advance, by pattern or
// unit or cgroup. There is no "show me the busiest ten", and pointing it at
// everything would publish a time series per process on the machine.
//
// A developer watching a host wants the top of the list, which means ranking
// has to happen before anything is emitted. That is what this package does,
// and it is the only reason it exists rather than a configuration file.
package proc

import (
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// Measurement carries per-process usage.
const Measurement = "process"

// clockTicksPerSecond converts the CPU times in /proc into seconds.
//
// The kernel reports them in USER_HZ, which sysconf(_SC_CLK_TCK) would return.
// Reading it needs cgo, and the value has been 100 on every mainstream Linux
// build for decades, so it is fixed here rather than dragging a C toolchain
// into a static binary.
const clockTicksPerSecond = 100

// Collector samples /proc and reports the busiest processes.
//
// It keeps the previous CPU times so it can report utilisation over the
// interval rather than since boot, which is what a live dashboard needs.
type Collector struct {
	procRoot string
	hostname string
	limit    int

	pageSize int64

	// previous maps pid to the CPU time it had accumulated at the last
	// sample, keyed by pid and start time. The start time is what makes a
	// recycled pid safe: a new process reusing an old number has a
	// different one, so its usage is not computed against a stranger's
	// counter.
	previous map[processKey]uint64
	sampled  time.Time

	// now is overridden by tests so utilisation can be asserted against a
	// known interval rather than against wall-clock timing.
	now        func() time.Time
	lookupUser func(string) (*user.User, error)
}

// processKey identifies a process across samples.
type processKey struct {
	pid       int
	startTime uint64
}

// NewCollector primes the CPU counters so the first Collect reports a real
// interval rather than usage since boot.
func NewCollector(procRoot, hostname string, limit int) (*Collector, error) {
	if limit < 0 {
		return nil, fmt.Errorf("limit cannot be negative, got %d", limit)
	}

	collector := &Collector{
		procRoot:   procRoot,
		hostname:   hostname,
		limit:      limit,
		pageSize:   int64(os.Getpagesize()),
		previous:   make(map[processKey]uint64),
		now:        time.Now,
		lookupUser: user.LookupId,
	}

	snapshot, err := collector.scan()
	if err != nil {
		return nil, err
	}
	collector.remember(snapshot, collector.now())

	return collector, nil
}

// process is one entry of a scan.
type process struct {
	key     processKey
	command string
	cpuTime uint64
	rss     int64
	threads int64
	uid     string

	// cpuPercent is filled in by Collect once the previous sample is known.
	cpuPercent float64
}

// Collect returns the busiest processes as points.
func (c *Collector) Collect() ([]lineproto.Point, error) {
	snapshot, err := c.scan()
	if err != nil {
		return nil, err
	}

	now := c.now()
	elapsed := now.Sub(c.sampled).Seconds()

	for i := range snapshot {
		entry := &snapshot[i]

		before, seen := c.previous[entry.key]
		if !seen || elapsed <= 0 {
			// A process that appeared during this interval has nothing to
			// compare against. Reporting it at zero is honest; guessing
			// from its lifetime total would overstate a long-lived
			// process that just came into view.
			continue
		}
		if entry.cpuTime < before {
			// Counters only rise, so this means the pid was recycled
			// within one interval and the start time collided.
			continue
		}

		entry.cpuPercent = float64(entry.cpuTime-before) / clockTicksPerSecond / elapsed * 100
	}

	c.remember(snapshot, now)

	timestamp := now
	users := make(map[string]string)
	points := make([]lineproto.Point, 0, len(snapshot))
	for _, entry := range c.busiest(snapshot) {
		username, resolved := users[entry.uid]
		if !resolved && entry.uid != "" {
			username = c.username(entry.uid)
			users[entry.uid] = username
		}
		points = append(points, lineproto.Point{
			Measurement: Measurement,
			Tags: []lineproto.Tag{
				{Key: "host", Value: c.hostname},
				{Key: "pid", Value: strconv.Itoa(entry.key.pid)},
				{Key: "process", Value: entry.command},
				{Key: "uid", Value: entry.uid},
				{Key: "user", Value: username},
			},
			Fields: []lineproto.Field{
				lineproto.FixedFloatField("cpu_percent", entry.cpuPercent, 2),
				lineproto.IntField("memory_rss_bytes", entry.rss),
				lineproto.IntField("threads", entry.threads),
			},
			Timestamp: timestamp,
		})
	}

	return points, nil
}

// busiest ranks by CPU and by memory, then returns the union of the two tops.
//
// Ranking on one axis alone would hide the other kind of problem: a process
// leaking memory while using no CPU is exactly what someone watching a host
// wants to see, and it never appears in a CPU ranking.
func (c *Collector) busiest(snapshot []process) []process {
	if c.limit <= 0 || len(snapshot) <= c.limit {
		return sortedByCPU(snapshot)
	}

	chosen := make(map[processKey]bool, 2*c.limit)

	byCPU := sortedByCPU(snapshot)
	for _, entry := range byCPU[:c.limit] {
		chosen[entry.key] = true
	}

	byMemory := make([]process, len(snapshot))
	copy(byMemory, snapshot)
	sort.SliceStable(byMemory, func(i, j int) bool {
		if byMemory[i].rss != byMemory[j].rss {
			return byMemory[i].rss > byMemory[j].rss
		}

		return byMemory[i].key.pid < byMemory[j].key.pid
	})
	for _, entry := range byMemory[:c.limit] {
		chosen[entry.key] = true
	}

	kept := make([]process, 0, len(chosen))
	for _, entry := range byCPU {
		if chosen[entry.key] {
			kept = append(kept, entry)
		}
	}

	return kept
}

// sortedByCPU orders a copy of the snapshot, busiest first.
//
// Ties fall back to resident memory before pid. That tier is what keeps the
// list useful on an idle machine: with a pid tie-break, every process scores
// zero and the lowest numbers win, which fills the panel with kernel threads
// holding no memory and doing nothing. Falling back to memory surfaces the
// processes that actually exist, and pid last keeps the order stable.
func sortedByCPU(snapshot []process) []process {
	ranked := make([]process, len(snapshot))
	copy(ranked, snapshot)

	sort.SliceStable(ranked, func(i, j int) bool {
		if ranked[i].cpuPercent != ranked[j].cpuPercent {
			return ranked[i].cpuPercent > ranked[j].cpuPercent
		}
		if ranked[i].rss != ranked[j].rss {
			return ranked[i].rss > ranked[j].rss
		}

		return ranked[i].key.pid < ranked[j].key.pid
	})

	return ranked
}

// remember replaces the previous sample, dropping processes that have exited
// so the map does not grow for the life of the process.
func (c *Collector) remember(snapshot []process, at time.Time) {
	previous := make(map[processKey]uint64, len(snapshot))
	for _, entry := range snapshot {
		previous[entry.key] = entry.cpuTime
	}

	c.previous = previous
	c.sampled = at
}

// scan reads every process directory under /proc.
func (c *Collector) scan() ([]process, error) {
	entries, err := os.ReadDir(c.procRoot)
	if err != nil {
		return nil, fmt.Errorf("cannot read %s: %w", c.procRoot, err)
	}

	snapshot := make([]process, 0, len(entries))
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil {
			// Not a process directory.
			continue
		}

		parsed, err := c.read(pid)
		if err != nil {
			// Processes exit while /proc is being walked, which is
			// routine rather than a failure worth reporting.
			continue
		}

		snapshot = append(snapshot, parsed)
	}

	if len(snapshot) == 0 {
		return nil, fmt.Errorf("no readable processes under %s", c.procRoot)
	}

	return snapshot, nil
}

// read parses one /proc/<pid>/stat file.
func (c *Collector) read(pid int) (process, error) {
	// Pin the process directory so a recycled PID cannot mix one process's
	// CPU counters with another process's owner.
	root, err := os.OpenRoot(filepath.Join(c.procRoot, strconv.Itoa(pid)))
	if err != nil {
		return process{}, err
	}
	defer root.Close()
	raw, err := root.ReadFile("stat")
	if err != nil {
		return process{}, err
	}

	parsed, err := parseStat(string(raw), pid, c.pageSize)
	if err != nil {
		return process{}, err
	}
	parsed.uid = processUID(root, pid)
	return parsed, nil
}

// Field positions in /proc/<pid>/stat, counting from 1 as the proc(5) manual
// does. They are offsets into the part after the command, which is why the
// command itself is not listed.
const (
	fieldUTime     = 14
	fieldSTime     = 15
	fieldThreads   = 20
	fieldStartTime = 22
	fieldRSSPages  = 24
)

// parseStat extracts the fields of interest.
//
// The command sits in parentheses and may itself contain spaces and
// parentheses, so splitting the line on whitespace is wrong: a process named
// "(evil) 1 2 3" would shift every later field. Everything after the last
// closing parenthesis is parsed instead, which is what the kernel guarantees.
func parseStat(raw string, pid int, pageSize int64) (process, error) {
	open := strings.IndexByte(raw, '(')
	closing := strings.LastIndexByte(raw, ')')
	if open < 0 || closing < open {
		return process{}, fmt.Errorf("pid %d: stat has no command field", pid)
	}

	command := raw[open+1 : closing]

	// Field 3 is the first one after the command, so index 0 of the rest
	// corresponds to field 3.
	rest := strings.Fields(raw[closing+1:])
	const firstFieldAfterCommand = 3

	value := func(field int) (uint64, error) {
		index := field - firstFieldAfterCommand
		if index < 0 || index >= len(rest) {
			return 0, fmt.Errorf("pid %d: stat has %d fields, want at least %d", pid, len(rest), field)
		}

		return strconv.ParseUint(rest[index], 10, 64)
	}

	utime, err := value(fieldUTime)
	if err != nil {
		return process{}, err
	}
	stime, err := value(fieldSTime)
	if err != nil {
		return process{}, err
	}
	threads, err := value(fieldThreads)
	if err != nil {
		return process{}, err
	}
	if threads == 0 || threads > 1<<63-1 {
		return process{}, fmt.Errorf("pid %d: stat has invalid thread count", pid)
	}
	startTime, err := value(fieldStartTime)
	if err != nil {
		return process{}, err
	}
	rssPages, err := value(fieldRSSPages)
	if err != nil {
		return process{}, err
	}

	return process{
		key:     processKey{pid: pid, startTime: startTime},
		command: command,
		cpuTime: utime + stime,
		rss:     int64(rssPages) * pageSize,
		threads: int64(threads),
	}, nil
}
