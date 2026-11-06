// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package membw

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

func TestCollectConvertsSysfsMiBScaleToBytesPerSecond(t *testing.T) {
	start := time.Unix(100, 0)
	c := &Collector{hostname: "h", sampled: start, now: func() time.Time {
		return start.Add(2 * time.Second)
	}}
	for name, delta := range map[string]uint64{"read": 32, "write": 16} {
		path := filepath.Join(t.TempDir(), name)
		var raw [8]byte
		binary.LittleEndian.PutUint64(raw[:], 10+delta)
		if err := os.WriteFile(path, raw[:], 0o600); err != nil {
			t.Fatal(err)
		}
		file, err := os.Open(path)
		if err != nil {
			t.Fatal(err)
		}
		defer file.Close()
		c.counters = append(c.counters, counter{
			canonical: name, event: name, scale: 1.0 / 16384,
			fd: int(file.Fd()), previous: 10, primed: true,
		})
	}
	points, err := c.Collect()
	if err != nil || len(points) != 1 {
		t.Fatalf("Collect() = %v, %v", points, err)
	}
	line, err := points[0].Append(nil)
	if err != nil {
		t.Fatal(err)
	}
	want := "memory_bandwidth,host=h read_bytes_per_second=1024,write_bytes_per_second=512,total_bytes_per_second=1536 102000000000\n"
	if string(line) != want {
		t.Fatalf("got %s, want %s", line, want)
	}
}

func TestControllerCPUs(t *testing.T) {
	for _, tc := range []struct {
		mask string
		want []int
	}{
		{"8\n", []int{8}},
		{"48,0,16-17,48\n", []int{0, 16, 17, 48}},
		{"", nil}, {",", nil}, {"1,,2", nil}, {"-1", nil},
		{"2-1", nil}, {"0x10", nil}, {"0-65536", nil},
		{"0-9223372036854775807", nil},
	} {
		t.Run(tc.mask, func(t *testing.T) {
			device := t.TempDir()
			writeFile(t, filepath.Join(device, "cpumask"), tc.mask)
			got, err := controllerCPUs(device)
			if tc.want == nil {
				if err == nil {
					t.Fatalf("invalid mask accepted: %q -> %v", tc.mask, got)
				}
			} else if err != nil || !slices.Equal(got, tc.want) {
				t.Fatalf("CPUs = %v, %v; want %v", got, err, tc.want)
			}
		})
	}
	if _, err := controllerCPUs(t.TempDir()); err == nil {
		t.Fatal("missing cpumask must not fall back to CPU 0")
	}
}

func TestDiscoverEventsRejectsPartialAndUnreadableControllers(t *testing.T) {
	for _, events := range [][]string{
		{"data_read"}, {"data_write"}, {"cas_count_read"},
		{"cas_count_read_sch0"},
		{"cas_count_read_sch0", "cas_count_write_sch0", "cas_count_write_sch1"},
		{"cas_count_read_schbad", "cas_count_write_schbad"},
	} {
		if _, _, err := discoverEvents(fakeController(t, events...)); err == nil {
			t.Fatalf("incomplete controller %v was silently skipped", events)
		}
	}
	device := t.TempDir()
	writeFile(t, filepath.Join(device, "events"), "not a directory")
	if _, _, err := discoverEvents(device); err == nil {
		t.Fatal("unreadable events must fail discovery")
	}
}

func TestNewCollectorOpensEveryDieAndControllerOnce(t *testing.T) {
	root := t.TempDir()
	first := controllerFixture(t, root, "uncore_imc_free_running_0", 32, "8,40,8")
	controllerFixture(t, root, "uncore_imc_free_running_1", 33, "8,40")
	if err := os.Symlink(first, filepath.Join(root, "uncore_imc_alias")); err != nil {
		t.Fatal(err)
	}
	open, calls := perfFixture(t)
	c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", open)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	if len(*calls) != 8 {
		t.Fatalf("opened %d counters, want 2 controllers * 2 dies * 2 events", len(*calls))
	}
	seen := make(map[string]bool)
	for _, call := range *calls {
		key := fmt.Sprintf("%d/%d/%d", call.attr.Type, call.cpu, call.attr.Config)
		if seen[key] || (call.cpu != 8 && call.cpu != 40) {
			t.Fatalf("duplicate or incorrect target: %s", key)
		}
		seen[key] = true
		if call.pid != -1 || call.group != -1 || call.flags != unix.PERF_FLAG_FD_CLOEXEC ||
			call.attr.Bits != unix.PerfBitPinned || call.attr.Size != unix.PERF_ATTR_SIZE_VER1 {
			t.Fatalf("wrong perf arguments: %+v", call)
		}
		delta := uint64(10)
		if call.attr.Config == 0x21ff {
			delta = 20
		} else if call.attr.Config != 0x20ff {
			t.Fatalf("unexpected event: %#x", call.attr.Config)
		}
		setCounterValue(t, call.fd, 100+delta)
	}
	start := time.Unix(100, 0)
	c.sampled = start
	c.now = func() time.Time { return start.Add(2 * time.Second) }
	assertBandwidth(t, c, 1280, 2560)
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	assertClosed(t, *calls)
}

func TestNewCollectorSubchannelsAcrossSockets(t *testing.T) {
	root := t.TempDir()
	events := map[string]string{
		"cas_count_read_sch0":  "event=0x05,umask=0xcf",
		"cas_count_read_sch1":  "event=0x06,umask=0xcf",
		"cas_count_write_sch0": "event=0x05,umask=0xf0",
		"cas_count_write_sch1": "event=0x06,umask=0xf0",
	}
	for index := 0; index < 6; index++ {
		device := filepath.Join(root, fmt.Sprintf("uncore_imc_%d", 2*index))
		if err := os.MkdirAll(filepath.Join(device, "events"), 0o755); err != nil {
			t.Fatal(err)
		}
		writeFile(t, filepath.Join(device, "type"), fmt.Sprint(318+index))
		writeFile(t, filepath.Join(device, "cpumask"), "0,96")
		for event, config := range events {
			writeFile(t, filepath.Join(device, "events", event), config)
			writeFile(t, filepath.Join(device, "events", event+".scale"), "6.103515625e-5")
			writeFile(t, filepath.Join(device, "events", event+".unit"), "MiB")
		}
	}
	open, calls := perfFixture(t)
	c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", open)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	if len(*calls) != 48 {
		t.Fatalf("opened %d events, want 6 PMUs * 2 sockets * 2 subchannels * 2 directions", len(*calls))
	}
	seen := make(map[string]bool)
	for _, call := range *calls {
		key := fmt.Sprintf("%d/%d/%x", call.attr.Type, call.cpu, call.attr.Config)
		if seen[key] || (call.cpu != 0 && call.cpu != 96) {
			t.Fatalf("duplicate or wrong socket: %s", key)
		}
		seen[key] = true
		delta := uint64(10)
		switch call.attr.Config {
		case 0xcf05, 0xcf06:
		case 0xf005, 0xf006:
			delta = 20
		default:
			t.Fatalf("wrong subchannel encoding: %#x", call.attr.Config)
		}
		setCounterValue(t, call.fd, 100+delta)
	}
	start := time.Unix(100, 0)
	c.sampled = start
	c.now = func() time.Time { return start.Add(2 * time.Second) }
	assertBandwidth(t, c, 7680, 15360)
}

func TestDiscoverEventsDoesNotAddSubchannelsToAggregate(t *testing.T) {
	device := fakeController(t, "cas_count_read", "cas_count_write",
		"cas_count_read_sch0", "cas_count_write_sch0",
		"cas_count_read_sch1", "cas_count_write_sch1")
	pairs, found, err := discoverEvents(device)
	if err != nil || !found || len(pairs) != 1 || pairs[0] != (eventPair{"cas_count_read", "cas_count_write"}) {
		t.Fatalf("aggregate selection = %v, %v, %v", pairs, found, err)
	}
}

func TestNewCollectorSingleRepresentative(t *testing.T) {
	root := t.TempDir()
	controllerFixture(t, root, "uncore_imc_0", 32, "12")
	open, calls := perfFixture(t)
	c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", open)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	if len(*calls) != 2 || (*calls)[0].cpu != 12 || (*calls)[1].cpu != 12 {
		t.Fatalf("single-die targets: %+v", *calls)
	}
	for _, call := range *calls {
		setCounterValue(t, call.fd, 110)
	}
	start := time.Unix(100, 0)
	c.sampled = start
	c.now = func() time.Time { return start.Add(time.Second) }
	assertBandwidth(t, c, 640, 640)
}

func TestNewCollectorRejectsAmbiguousFamilies(t *testing.T) {
	root := t.TempDir()
	controllerFixture(t, root, "uncore_imc_0", 32, "8,40")
	controllerFixture(t, root, "uncore_imc_free_running_0", 33, "8,40")
	open, calls := perfFixture(t)
	c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", open)
	if c != nil || err == nil || !strings.Contains(err.Error(), "complete family") || len(*calls) != 0 {
		t.Fatalf("ambiguous families = %v, %v, %d opens", c, err, len(*calls))
	}
}

func TestNewCollectorClosesAllFDsOnOpenAndPrimeFailure(t *testing.T) {
	for _, failure := range []string{"open", "prime"} {
		t.Run(failure, func(t *testing.T) {
			root := t.TempDir()
			controllerFixture(t, root, "uncore_imc_0", 32, "8,40")
			open, calls := perfFixture(t)
			failing := func(attr *unix.PerfEventAttr, pid, cpuID, group, flags int) (int, error) {
				if cpuID == 40 && failure == "open" {
					return -1, unix.EPERM
				}
				fd, err := open(attr, pid, cpuID, group, flags)
				if cpuID == 40 && failure == "prime" {
					if err := unix.Ftruncate(fd, 0); err != nil {
						t.Fatal(err)
					}
				}
				return fd, err
			}
			c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", failing)
			if c != nil || err == nil || !strings.Contains(err.Error(), "CPU 40") {
				t.Fatalf("failure = %v, %v; want diagnostic for CPU 40", c, err)
			}
			assertClosed(t, *calls)
		})
	}
}

func TestCollectNeverPublishesPartialHostTotals(t *testing.T) {
	root := t.TempDir()
	controllerFixture(t, root, "uncore_imc_0", 32, "8,40")
	open, calls := perfFixture(t)
	c, err := newCollector(filepath.Join(root, "uncore_imc*"), "h", open)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	start := time.Unix(100, 0)
	now := start.Add(time.Second)
	c.sampled, c.now = start, func() time.Time { return now }
	for _, call := range *calls {
		setCounterValue(t, call.fd, 120)
	}
	last := (*calls)[len(*calls)-1].fd
	if err := unix.Ftruncate(last, 4); err != nil {
		t.Fatal(err)
	}
	if points, err := c.Collect(); err == nil || len(points) != 0 {
		t.Fatalf("short read published a partial total: %v, %v", points, err)
	}
	if !c.sampled.Equal(start) {
		t.Fatal("failed snapshot changed its timestamp")
	}
	for _, counter := range c.counters {
		if counter.previous != 100 {
			t.Fatal("failed snapshot changed a counter baseline")
		}
	}
	now = start.Add(3 * time.Second)
	for _, call := range *calls {
		setCounterValue(t, call.fd, 160)
	}
	assertBandwidth(t, c, 2560, 2560)

	now = start.Add(4 * time.Second)
	for i, call := range *calls {
		value := uint64(170)
		if i == len(*calls)-1 {
			value = 1
		}
		setCounterValue(t, call.fd, value)
	}
	if points, err := c.Collect(); err == nil || len(points) != 0 {
		t.Fatalf("reset published a partial total: %v, %v", points, err)
	}
	now = start.Add(6 * time.Second)
	for i, call := range *calls {
		setCounterValue(t, call.fd, c.counters[i].previous+10)
	}
	assertBandwidth(t, c, 640, 640)

	for _, call := range *calls {
		setCounterValue(t, call.fd, 200)
	}
	if points, err := c.Collect(); err == nil || len(points) != 0 {
		t.Fatalf("zero interval published a total: %v, %v", points, err)
	}
}

func TestOpenCounterRejectsInvalidMetadataBeforeOpening(t *testing.T) {
	for _, scale := range []string{"0", "-1", "NaN", "+Inf", "invalid"} {
		device := fakeController(t, "data_read")
		writeFile(t, filepath.Join(device, "events", "data_read.scale"), scale)
		open, calls := perfFixture(t)
		if _, err := openCounter(device, "read", "data_read", 32, 8, open); err == nil || len(*calls) > 0 {
			t.Fatalf("invalid scale %s reached perf: %v", scale, err)
		}
	}
	device := fakeController(t, "data_read")
	if err := os.Mkdir(filepath.Join(device, "events", "data_read.unit"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := checkUnit(device, "data_read"); err == nil {
		t.Fatal("unreadable unit file was treated as absent")
	}
}

type perfCall struct {
	attr                   unix.PerfEventAttr
	pid, cpu, group, flags int
	fd                     int
}

func perfFixture(t *testing.T) (perfOpener, *[]perfCall) {
	t.Helper()
	var calls []perfCall
	dir := t.TempDir()
	return func(attr *unix.PerfEventAttr, pid, cpuID, group, flags int) (int, error) {
		path := filepath.Join(dir, fmt.Sprint(len(calls)))
		fd, err := unix.Open(path, unix.O_CREAT|unix.O_RDWR|unix.O_CLOEXEC, 0o600)
		if err != nil {
			t.Fatal(err)
		}
		setCounterValue(t, fd, 100)
		calls = append(calls, perfCall{*attr, pid, cpuID, group, flags, fd})
		return fd, nil
	}, &calls
}

func controllerFixture(t *testing.T, root, name string, kind int, mask string) string {
	t.Helper()
	device := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Join(device, "events"), 0o755); err != nil {
		t.Fatal(err)
	}
	writeFile(t, filepath.Join(device, "type"), fmt.Sprint(kind))
	writeFile(t, filepath.Join(device, "cpumask"), mask)
	for i, event := range []string{"data_read", "data_write", "data_total"} {
		writeFile(t, filepath.Join(device, "events", event), fmt.Sprintf("event=0xff,umask=0x%x", 0x20+i))
		writeFile(t, filepath.Join(device, "events", event+".scale"), "6.103515625e-5")
	}
	return device
}

func setCounterValue(t *testing.T, fd int, value uint64) {
	t.Helper()
	var raw [8]byte
	binary.LittleEndian.PutUint64(raw[:], value)
	if n, err := unix.Pwrite(fd, raw[:], 0); err != nil || n != len(raw) {
		t.Fatalf("writing fake counter: %d, %v", n, err)
	}
	if _, err := unix.Seek(fd, 0, 0); err != nil {
		t.Fatal(err)
	}
}

func assertClosed(t *testing.T, calls []perfCall) {
	t.Helper()
	for _, call := range calls {
		if _, err := unix.FcntlInt(uintptr(call.fd), unix.F_GETFD, 0); !errors.Is(err, unix.EBADF) {
			t.Fatalf("descriptor %d was not closed: %v", call.fd, err)
		}
	}
}

func assertBandwidth(t *testing.T, c *Collector, read, write float64) {
	t.Helper()
	points, err := c.Collect()
	if err != nil || len(points) != 1 {
		t.Fatalf("Collect() = %v, %v", points, err)
	}
	line, err := points[0].Append(nil)
	want := fmt.Sprintf("memory_bandwidth,host=h read_bytes_per_second=%g,write_bytes_per_second=%g,total_bytes_per_second=%g ", read, write, read+write)
	if err != nil || !strings.HasPrefix(string(line), want) {
		t.Fatalf("got %s, %v; want %s", line, err, want)
	}
}

func TestReadConfigParsesAnEventDefinition(t *testing.T) {
	for definition, want := range map[string]uint64{
		// The layout the memory controller publishes: selector in the low
		// byte, unit mask in the next.
		"event=0xff,umask=0x20": 0x20ff,
		"event=0xff,umask=0x21": 0x21ff,
		"event=0x01":            0x01,
		// Trailing newline is how sysfs actually returns these.
		"event=0xff,umask=0x20\n": 0x20ff,
		"event=0xff, umask=0x20":  0x20ff,
	} {
		path := writeDefinition(t, definition)

		got, err := readConfig(path)
		if err != nil {
			t.Errorf("readConfig(%q) error = %v", definition, err)
			continue
		}
		if got != want {
			t.Errorf("readConfig(%q) = %#x, want %#x", definition, got, want)
		}
	}
}

// TestReadConfigRejectsDefinitionsItCannotHonour matters more than it looks.
// Silently ignoring a field would open a counter measuring something other
// than what the field asked for, and the reading would look perfectly
// plausible while being wrong.
func TestReadConfigRejectsDefinitionsItCannotHonour(t *testing.T) {
	for _, definition := range []string{
		"event=0xff,umask=0x20,edge=1",
		"event=0xff,inv=1",
		"config1=0x4043200000000",
		"",
		"event=",
		"event=zz",
	} {
		if _, err := readConfig(writeDefinition(t, definition)); err == nil {
			t.Errorf("readConfig(%q) succeeded, want an error", definition)
		}
	}
}

func TestReadConfigReportsAMissingFile(t *testing.T) {
	if _, err := readConfig(filepath.Join(t.TempDir(), "absent")); err == nil {
		t.Error("readConfig() accepted a missing file, want an error")
	}
}

// TestFieldNameCarriesTheUnit guards the names that end up on the endpoint.
func TestFieldNameCarriesTheUnit(t *testing.T) {
	for canonical, want := range map[string]string{
		"read":  "read_bytes_per_second",
		"write": "write_bytes_per_second",
	} {
		if got := fieldName(canonical); got != want {
			t.Errorf("fieldName(%q) = %q, want %q", canonical, got, want)
		}
	}
}

// TestDiscoverEventsHandlesEachSpelling covers the naming differences between
// part generations. Which spelling a machine uses is a property of its memory
// controller, so it has to be discovered rather than assumed.
func TestDiscoverEventsHandlesEachSpelling(t *testing.T) {
	for name, events := range map[string][]string{
		"current client": {"data_read", "data_write", "data_total"},
		"older client":   {"data_reads", "data_writes"},
		"server":         {"cas_count_read", "cas_count_write"},
	} {
		t.Run(name, func(t *testing.T) {
			device := fakeController(t, events...)

			pairs, found, err := discoverEvents(device)
			if err != nil || !found {
				t.Fatalf("discoverEvents() found nothing in %v: %v", events, err)
			}
			if len(pairs) != 1 || !slices.Contains(events, pairs[0].read) || !slices.Contains(events, pairs[0].write) {
				t.Errorf("discoverEvents() = %+v, want a pair from %v", pairs, events)
			}
		})
	}
}

// TestDiscoverEventsSkipsUnusableControllers matters because a machine exposes
// several controllers and only some carry counters: this host publishes
// uncore_imc_0 with an empty event directory next to the free-running ones
// that work. Treating the empty one as a failure would report no bandwidth at
// all.
func TestDiscoverEventsSkipsUnusableControllers(t *testing.T) {
	for name, events := range map[string][]string{
		"no events": {},
		"unrelated": {"clockticks"},
	} {
		t.Run(name, func(t *testing.T) {
			if _, found, err := discoverEvents(fakeController(t, events...)); found || err != nil {
				t.Errorf("discoverEvents() = found %v, err %v for %v, want it skipped", found, err, events)
			}
		})
	}
}

// TestNewCollectorReportsNoUsableCounters checks that a machine with
// controllers but no counters says so, rather than reporting silence.
func TestNewCollectorReportsNoUsableCounters(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"uncore_imc_0", "uncore_imc_1"} {
		if err := os.MkdirAll(filepath.Join(root, name, "events"), 0o755); err != nil {
			t.Fatalf("cannot create %s: %v", name, err)
		}
	}

	_, err := NewCollector(filepath.Join(root, "uncore_imc*"), "test-host")
	if err == nil {
		t.Fatal("NewCollector() succeeded with no usable counters, want an error")
	}
	if !strings.Contains(err.Error(), "usable") {
		t.Errorf("NewCollector() error = %v, want it to say no usable pair was found", err)
	}
}

// TestCheckUnitRejectsSomethingElse guards against reporting a counter under a
// field name that claims mebibytes when it measures something else. The number
// would look perfectly ordinary while being wrong.
func TestCheckUnitRejectsSomethingElse(t *testing.T) {
	device := fakeController(t, "data_read")
	writeFile(t, filepath.Join(device, "events", "data_read.unit"), "ns\n")

	if err := checkUnit(device, "data_read"); err == nil {
		t.Error("checkUnit() accepted a counter measured in nanoseconds, want an error")
	}
}

func TestCheckUnitAcceptsTheExpectedUnitAndAMissingOne(t *testing.T) {
	device := fakeController(t, "data_read", "data_write")

	// Older parts omit the unit file; the scale still says how to convert.
	if err := checkUnit(device, "data_read"); err != nil {
		t.Errorf("checkUnit() rejected a counter with no published unit: %v", err)
	}

	writeFile(t, filepath.Join(device, "events", "data_write.unit"), "MiB\n")
	if err := checkUnit(device, "data_write"); err != nil {
		t.Errorf("checkUnit() rejected the expected unit: %v", err)
	}
}

func TestNewCollectorReportsAnAbsentController(t *testing.T) {
	_, err := NewCollector(filepath.Join(t.TempDir(), "uncore_imc*"), "test-host")
	if err == nil {
		t.Fatal("NewCollector() succeeded with no controllers, want an error")
	}
}

func TestReadFloatAndUint(t *testing.T) {
	dir := t.TempDir()

	scale := filepath.Join(dir, "scale")
	if err := os.WriteFile(scale, []byte("6.103515625e-5\n"), 0o644); err != nil {
		t.Fatalf("cannot write scale: %v", err)
	}
	// One count per 64 bytes, expressed in MiB, is the value current parts
	// publish. Getting this wrong scales every reading.
	if got, err := readFloat(scale); err != nil || got != 6.103515625e-5 {
		t.Errorf("readFloat() = %v, %v, want the published scale", got, err)
	}

	pmuType := filepath.Join(dir, "type")
	if err := os.WriteFile(pmuType, []byte("32\n"), 0o644); err != nil {
		t.Fatalf("cannot write type: %v", err)
	}
	if got, err := readUint(pmuType); err != nil || got != 32 {
		t.Errorf("readUint() = %v, %v, want 32", got, err)
	}
}

func writeDefinition(t *testing.T, definition string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "event")
	writeFile(t, path, definition)

	return path
}

// fakeController builds a controller directory publishing the named events.
func fakeController(t *testing.T, events ...string) string {
	t.Helper()

	device := t.TempDir()
	if err := os.MkdirAll(filepath.Join(device, "events"), 0o755); err != nil {
		t.Fatalf("cannot create event directory: %v", err)
	}
	writeFile(t, filepath.Join(device, "type"), "32\n")

	for _, event := range events {
		writeFile(t, filepath.Join(device, "events", event), "event=0xff,umask=0x20\n")
		writeFile(t, filepath.Join(device, "events", event+".scale"), "6.103515625e-5\n")
	}

	return device
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()

	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("cannot write %s: %v", path, err)
	}
}
