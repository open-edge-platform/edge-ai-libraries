// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package npu

import (
	"encoding/binary"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// telemetryBuffer builds a PMT buffer with the given 64-bit words placed at
// the given byte offsets.
func telemetryBuffer(size int, words map[int]uint64) []byte {
	buffer := make([]byte, size)
	for offset, value := range words {
		binary.LittleEndian.PutUint64(buffer[offset:offset+8], value)
	}
	return buffer
}

func writeFile(t *testing.T, path string, content []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("MkdirAll(%s): %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, content, 0o644); err != nil {
		t.Fatalf("WriteFile(%s): %v", path, err)
	}
}

// pmtDevice writes a complete PMT telemetry device into a synthetic sysfs.
func pmtDevice(t *testing.T, root, name, guid string, buffer []byte) {
	t.Helper()
	dir := filepath.Join(root, "class/intel_pmt", name)
	writeFile(t, filepath.Join(dir, "guid"), []byte(guid+"\n"))
	writeFile(t, filepath.Join(dir, "size"), []byte("4096\n"))
	writeFile(t, filepath.Join(dir, "offset"), []byte("0\n"))
	writeFile(t, filepath.Join(dir, "telem"), buffer)
}

func TestOpenDetectsGeneration(t *testing.T) {
	tests := []struct {
		guid string
		want CPUGen
	}{
		{"0x130670b2", GenMTL},
		{"0x1306a0b3", GenARL},
		{"0x1306a0b2", GenARL},
		{"0x1306a0b4", GenARL},
		{"0x3072005", GenLNL},
		{"0x3086000", GenPTL},
	}

	for _, tt := range tests {
		t.Run(tt.guid, func(t *testing.T) {
			root := t.TempDir()
			pmtDevice(t, root, "telem1", tt.guid, make([]byte, 4096))

			telemetry, err := Open(root)
			if err != nil {
				t.Fatalf("Open() error: %v", err)
			}
			if telemetry.Gen() != tt.want {
				t.Errorf("Gen() = %v, want %v", telemetry.Gen(), tt.want)
			}
		})
	}
}

func TestOpenSkipsUnusableDevices(t *testing.T) {
	root := t.TempDir()

	// An unknown GUID, and a device missing the `offset` attribute, must both
	// be skipped in favour of the usable one.
	pmtDevice(t, root, "telem0", "0xdeadbeef", make([]byte, 4096))
	incomplete := filepath.Join(root, "class/intel_pmt/telem1")
	writeFile(t, filepath.Join(incomplete, "guid"), []byte("0x3086000\n"))
	writeFile(t, filepath.Join(incomplete, "telem"), make([]byte, 4096))
	writeFile(t, filepath.Join(incomplete, "size"), []byte("4096\n"))
	pmtDevice(t, root, "telem2", "0x130670b2", make([]byte, 4096))

	telemetry, err := Open(root)
	if err != nil {
		t.Fatalf("Open() error: %v", err)
	}
	if telemetry.Gen() != GenMTL {
		t.Errorf("Gen() = %v, want %v", telemetry.Gen(), GenMTL)
	}
}

func TestOpenFailsWithoutKnownDevice(t *testing.T) {
	root := t.TempDir()
	pmtDevice(t, root, "telem0", "0xdeadbeef", make([]byte, 4096))

	if _, err := Open(root); err == nil {
		t.Error("Open() succeeded with only an unknown GUID, want an error")
	}
	if _, err := Open(t.TempDir()); err == nil {
		t.Error("Open() succeeded with no PMT interface at all, want an error")
	}
}

// TestReadExtractsBitFields checks the mask-and-shift arithmetic, including
// the full-width case where a naive 1<<(msb+1) would overflow.
func TestReadExtractsBitFields(t *testing.T) {
	telemetry := &Telemetry{buffer: telemetryBuffer(64, map[int]uint64{
		0: 0xFEDCBA9876543210,
	})}

	tests := []struct {
		name     string
		offset   uint
		msb, lsb uint
		want     uint64
	}{
		{name: "low byte", offset: 0, msb: 7, lsb: 0, want: 0x10},
		{name: "second byte", offset: 0, msb: 15, lsb: 8, want: 0x32},
		{name: "bits 23:16", offset: 0, msb: 23, lsb: 16, want: 0x54},
		{name: "bits 47:40", offset: 0, msb: 47, lsb: 40, want: 0xBA},
		{name: "full width", offset: 0, msb: 63, lsb: 0, want: 0xFEDCBA9876543210},
		{name: "low half", offset: 0, msb: 31, lsb: 0, want: 0x76543210},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := telemetry.read(tt.offset, tt.msb, tt.lsb); got != tt.want {
				t.Errorf("read(%d, %d, %d) = %#x, want %#x", tt.offset, tt.msb, tt.lsb, got, tt.want)
			}
		})
	}
}

func TestEnergyIsFixedPoint(t *testing.T) {
	// 5.5 J in U32.18.14: 5 << 14 plus half of 1 << 14.
	raw := uint64(5)<<14 | uint64(1)<<13
	telemetry := &Telemetry{
		gen:    GenMTL,
		regs:   registerSets[GenMTL],
		buffer: telemetryBuffer(4096, map[int]uint64{0x628: raw}),
	}

	if got, want := telemetry.EnergyJoules(), 5.5; got != want {
		t.Errorf("EnergyJoules() = %v, want %v", got, want)
	}
}

// TestFrequencyScalingPerGeneration pins the intel_vpu PLL formulas in Hz.
func TestFrequencyScalingPerGeneration(t *testing.T) {
	tests := []struct {
		gen    CPUGen
		raw    uint64
		wantHz float64
	}{
		{gen: GenMTL, raw: 48, wantHz: 1_600_000_000},
		{gen: GenARL, raw: 48, wantHz: 1_600_000_000},
		{gen: GenLNL, raw: 78, wantHz: 1_950_000_000},
		{gen: GenPTL, raw: 78, wantHz: 1_950_000_000},
		{gen: GenMTL, raw: 1, wantHz: 100_000_000.0 / 3},
		{gen: GenPTL, raw: 0, wantHz: 0},
	}

	for _, tt := range tests {
		t.Run(tt.gen.String(), func(t *testing.T) {
			regs := registerSets[tt.gen]
			telemetry := &Telemetry{
				gen:    tt.gen,
				regs:   regs,
				buffer: telemetryBuffer(4096, map[int]uint64{regs.workpoint: tt.raw}),
			}
			if got := telemetry.FrequencyHz(); got != tt.wantHz {
				t.Errorf("FrequencyHz() = %v, want %v", got, tt.wantHz)
			}
		})
	}
}

// buildNPUSysfs creates a synthetic sysfs with a PMT device and an intel_vpu
// PCI device.
func buildNPUSysfs(t *testing.T, guid string, buffer []byte, busyUS, memoryBytes string) string {
	t.Helper()

	root := t.TempDir()
	pmtDevice(t, root, "telem1", guid, buffer)

	dev := filepath.Join(root, "bus/pci/drivers/intel_vpu/0000:00:0b.0")
	writeFile(t, filepath.Join(dev, "device"), []byte("0x7d1d\n"))
	if busyUS != "" {
		writeFile(t, filepath.Join(dev, "npu_busy_time_us"), []byte(busyUS+"\n"))
	}
	if memoryBytes != "" {
		writeFile(t, filepath.Join(dev, "npu_memory_utilization"), []byte(memoryBytes+"\n"))
	}

	return root
}

// TestCollectBaseUnits checks the native 2026.3.0 wire contract.
func TestCollectBaseUnits(t *testing.T) {
	regs := registerSets[GenPTL]
	root := buildNPUSysfs(t, "0x3086000",
		telemetryBuffer(4096, map[int]uint64{
			regs.energy:          uint64(10) << 14, // 10 J
			regs.workpoint:       0x02_00_28,       // tile 2, work point 40
			regs.socTemperatures: uint64(45) << 40, // 45 C
			regs.memoryBW:        128_750,          // 128.75 MB
		}),
		"1000", "536870912") // 1 ms busy, 512 MiB

	collector, err := NewCollector(root, "test-host")
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}

	// Advance the counters over exactly one second.
	start := time.Unix(0, 1725062400000000000)
	collector.prevTime = start
	collector.now = func() time.Time { return start.Add(time.Second) }
	collector.prevEnergy = 6.0 // 4 J over 1 s -> 4.000 W
	collector.prevBandwidth = 0
	collector.prevBusyUS = 0 // 1000 us over 1 s -> 0 %

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}
	if len(points) != 1 {
		t.Fatalf("got %d points, want 1", len(points))
	}

	rendered, err := points[0].Append(nil)
	if err != nil {
		t.Fatalf("Append() error: %v", err)
	}

	want := "npu,host=test-host frequency_hz=1000000000,temperature_c=45i,tile_config=2i," +
		"power_w=4,bandwidth_bytes_per_second=131840000,utilization=0i,memory_bytes=536870912,power_state=-1i 1725062401000000000\n"
	if got := string(rendered); got != want {
		t.Errorf("Collect()\n got: %s\nwant: %s", got, want)
	}
}

func TestBandwidthRateAndRollover(t *testing.T) {
	for _, tt := range []struct {
		name     string
		previous uint32
		raw      uint64
		interval time.Duration
		want     string
	}{
		{"two seconds", 90_000, 100_000, 2 * time.Second, "bandwidth_bytes_per_second=5120000,"},
		{"half second", 90_000, 100_000, time.Second / 2, "bandwidth_bytes_per_second=20480000,"},
		{"wrap", ^uint32(0) - 4_999, 10_000, time.Second, "bandwidth_bytes_per_second=15360000,"},
		{"idle", 100_000, 100_000, time.Second, "bandwidth_bytes_per_second=0,"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			regs := registerSets[GenPTL]
			root := buildNPUSysfs(t, "0x3086000",
				telemetryBuffer(4096, map[int]uint64{regs.memoryBW: tt.raw}), "", "")
			c, err := NewCollector(root, "h")
			if err != nil {
				t.Fatal(err)
			}

			start := time.Unix(100, 0)
			c.prevTime, c.prevBandwidth = start, tt.previous
			c.now = func() time.Time { return start.Add(tt.interval) }
			points, err := c.Collect()
			if err != nil {
				t.Fatal(err)
			}
			line, err := points[0].Append(nil)
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(line), tt.want) {
				t.Fatalf("got %s, want %s", line, tt.want)
			}
		})
	}
}

func TestMemoryAndCeilingUseUnroundedBaseUnits(t *testing.T) {
	root := buildNPUSysfs(t, "0x3086000", make([]byte, 4096), "", "1048577")
	device := filepath.Join(root, "bus/pci/drivers/intel_vpu/0000:00:0b.0")
	writeFile(t, filepath.Join(device, "npu_max_frequency_mhz"), []byte("1800"))
	c, err := NewCollector(root, "h")
	if err != nil {
		t.Fatal(err)
	}
	start := c.prevTime
	c.now = func() time.Time { return start.Add(time.Second) }
	points, err := c.Collect()
	if err != nil {
		t.Fatal(err)
	}
	line, err := points[0].Append(nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"memory_bytes=1048577,", "frequency_max_hz=1800000000 "} {
		if !strings.Contains(string(line), want) {
			t.Fatalf("missing %q in %s", want, line)
		}
	}
}

func TestInvalidSamplingIntervalPreservesBaseline(t *testing.T) {
	regs := registerSets[GenPTL]
	root := buildNPUSysfs(t, "0x3086000",
		telemetryBuffer(4096, map[int]uint64{regs.memoryBW: 100_000}), "1000", "")
	c, err := NewCollector(root, "h")
	if err != nil {
		t.Fatal(err)
	}
	start := time.Unix(100, 0)
	c.prevTime, c.prevBandwidth = start, 90
	for _, interval := range []time.Duration{0, -time.Second} {
		c.now = func() time.Time { return start.Add(interval) }
		if points, err := c.Collect(); err == nil || len(points) != 0 {
			t.Fatalf("Collect() = %v, %v, want an error without a point", points, err)
		}
		if c.prevTime != start || c.prevBandwidth != 90 {
			t.Fatal("invalid interval changed the counter baseline")
		}
	}
}

func TestOptionalReadFailureAndRecovery(t *testing.T) {
	root := buildNPUSysfs(t, "0x3086000", make([]byte, 4096), "0", "0")
	c, err := NewCollector(root, "h")
	if err != nil {
		t.Fatal(err)
	}
	start := time.Unix(100, 0)
	c.prevTime = start
	for i, tt := range []struct {
		busy, memory string
		wantBusy     bool
		wantMemory   bool
	}{
		{"bad", "bad", false, false},
		{"1000000", "0", false, true},
		{"1500000", "1048576", true, true},
	} {
		writeFile(t, c.busyPath, []byte(tt.busy))
		writeFile(t, c.memoryPath, []byte(tt.memory))
		c.now = func() time.Time { return start.Add(time.Duration(i+1) * time.Second) }
		points, err := c.Collect()
		if err != nil {
			t.Fatal(err)
		}
		line, err := points[0].Append(nil)
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(line), "utilization=") != tt.wantBusy ||
			strings.Contains(string(line), "memory_bytes=") != tt.wantMemory {
			t.Fatalf("unexpected optional fields: %s", line)
		}
		if tt.wantBusy && !strings.Contains(string(line), "utilization=50i") {
			t.Fatalf("recovery must use a fresh busy-time baseline: %s", line)
		}
		if i == 1 && !strings.Contains(string(line), "memory_bytes=0") {
			t.Fatalf("a measured zero is not missing: %s", line)
		}
	}
}

func TestPowerState(t *testing.T) {
	tests := []struct {
		state string
		want  int64
	}{
		{"D0", 0}, {"D1", 1}, {"D2", 2},
		{"D3hot", 3}, {"D3cold", 4}, {"unrecognised", -1},
	}
	for _, tt := range tests {
		t.Run(tt.state, func(t *testing.T) {
			root := buildNPUSysfs(t, "0x130670b2", make([]byte, 4096), "", "")
			path := filepath.Join(root, "bus/pci/drivers/intel_vpu/0000:00:0b.0/power_state")
			writeFile(t, path, []byte(tt.state+"\n"))
			collector, err := NewCollector(root, "h")
			if err != nil {
				t.Fatal(err)
			}
			if got := collector.powerState(); got != tt.want {
				t.Errorf("powerState() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestPowerStateUnavailable(t *testing.T) {
	root := buildNPUSysfs(t, "0x130670b2", make([]byte, 4096), "", "")
	collector, err := NewCollector(root, "h")
	if err != nil {
		t.Fatal(err)
	}
	if got := collector.powerState(); got != -1 {
		t.Errorf("absent power_state = %d, want -1", got)
	}
	path := filepath.Join(root, "bus/pci/drivers/intel_vpu/0000:00:0b.0/power_state")
	writeFile(t, path, []byte("D3hot\n"))
	collector, err = NewCollector(root, "h")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if got := collector.powerState(); got != -1 {
		t.Errorf("unreadable power_state = %d, want -1", got)
	}
}

func TestCollectorUtilisation(t *testing.T) {
	tests := []struct {
		name     string
		prevBusy uint64
		currBusy string
		elapsed  time.Duration
		want     string
	}{
		{name: "half busy", prevBusy: 0, currBusy: "500000", elapsed: time.Second, want: "utilization=50i"},
		{name: "fully busy", prevBusy: 0, currBusy: "1000000", elapsed: time.Second, want: "utilization=100i"},
		{name: "capped above 100", prevBusy: 0, currBusy: "5000000", elapsed: time.Second, want: "utilization=100i"},
		{name: "idle", prevBusy: 500, currBusy: "500", elapsed: time.Second, want: "utilization=0i"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			regs := registerSets[GenMTL]
			root := buildNPUSysfs(t, "0x130670b2",
				telemetryBuffer(4096, map[int]uint64{regs.energy: 0}), tt.currBusy, "")

			collector, err := NewCollector(root, "h")
			if err != nil {
				t.Fatalf("NewCollector() error: %v", err)
			}
			start := time.Unix(0, 0)
			collector.prevTime = start
			collector.now = func() time.Time { return start.Add(tt.elapsed) }
			collector.prevBusyUS = tt.prevBusy
			collector.hasPrevBusy = true

			points, err := collector.Collect()
			if err != nil {
				t.Fatalf("Collect() error: %v", err)
			}
			rendered, err := points[0].Append(nil)
			if err != nil {
				t.Fatalf("Append() error: %v", err)
			}
			if !strings.Contains(string(rendered), tt.want) {
				t.Errorf("Collect() = %s, want it to contain %s", rendered, tt.want)
			}
		})
	}
}

// TestUnsupportedAttributesDegradeGracefully covers an older NPU that exposes
// neither the busy counter nor memory usage.
func TestUnsupportedAttributesDegradeGracefully(t *testing.T) {
	regs := registerSets[GenMTL]
	root := buildNPUSysfs(t, "0x130670b2",
		telemetryBuffer(4096, map[int]uint64{regs.energy: 0}), "", "")

	collector, err := NewCollector(root, "h")
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}
	if collector.BusyTimeSupported() {
		t.Error("BusyTimeSupported() = true, want false")
	}
	if collector.MemoryUtilisationSupported() {
		t.Error("MemoryUtilisationSupported() = true, want false")
	}

	start := time.Unix(0, 0)
	collector.prevTime = start
	collector.now = func() time.Time { return start.Add(time.Second) }

	points, err := collector.Collect()
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}
	rendered, err := points[0].Append(nil)
	if err != nil {
		t.Fatalf("Append() error: %v", err)
	}
	for _, absent := range []string{"utilization=", "memory_bytes="} {
		if strings.Contains(string(rendered), absent) {
			t.Errorf("Collect() = %s, must omit %s", rendered, absent)
		}
	}
}

// TestMemoryUtilisationReadWhereverExposed replaces a generation gate that was
// measured to be wrong. The collector used to ignore npu_memory_utilization on
// anything older than Panther Lake, on the belief that older parts did not
// publish it; a Meteor Lake was then found exposing the attribute with a
// perfectly good value, which the gate was discarding in favour of -1.
//
// Presence is now the only test, which is what the file itself already told
// us.
func TestMemoryUtilisationReadWhereverExposed(t *testing.T) {
	regs := registerSets[GenMTL]
	root := buildNPUSysfs(t, "0x130670b2",
		telemetryBuffer(4096, map[int]uint64{regs.energy: 0}), "0", "536870912")

	collector, err := NewCollector(root, "h")
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}
	if !collector.MemoryUtilisationSupported() {
		t.Fatal("MemoryUtilisationSupported() = false on Meteor Lake, want the exposed attribute to be read")
	}

	if got, ok := collector.memoryBytes(); !ok || got != 536870912 {
		t.Errorf("memoryBytes() = %v, %t, want 536870912, true", got, ok)
	}
}

// TestMemoryUtilisationAbsentStaysUnavailable keeps the other half honest: a
// part that really does not publish the attribute must not fabricate a zero.
func TestMemoryUtilisationAbsentStaysUnavailable(t *testing.T) {
	regs := registerSets[GenMTL]
	root := buildNPUSysfs(t, "0x130670b2",
		telemetryBuffer(4096, map[int]uint64{regs.energy: 0}), "0", "")

	collector, err := NewCollector(root, "h")
	if err != nil {
		t.Fatalf("NewCollector() error: %v", err)
	}
	if collector.MemoryUtilisationSupported() {
		t.Error("MemoryUtilisationSupported() = true with no attribute present, want false")
	}
	if got, ok := collector.memoryBytes(); ok {
		t.Errorf("memoryBytes() = %v, true, want unavailable", got)
	}
}

func TestNewCollectorFailsWithoutDriver(t *testing.T) {
	root := t.TempDir()
	pmtDevice(t, root, "telem1", "0x130670b2", make([]byte, 4096))

	if _, err := NewCollector(root, "h"); err == nil {
		t.Error("NewCollector() succeeded without an intel_vpu device, want an error")
	}
}

func TestBandwidthPlatformScaling(t *testing.T) {
	for _, tt := range []struct {
		guid string
		gen  CPUGen
		want string
	}{
		{"0x130670b2", GenMTL, "bandwidth_bytes_per_second=10000,"},
		{"0x1306a0b3", GenARL, "bandwidth_bytes_per_second=10000,"},
		{"0x3072005", GenLNL, "bandwidth_bytes_per_second=10240,"},
		{"0x3086000", GenPTL, "bandwidth_bytes_per_second=10240,"},
	} {
		t.Run(tt.gen.String(), func(t *testing.T) {
			regs := registerSets[tt.gen]
			root := buildNPUSysfs(t, tt.guid, telemetryBuffer(4096, map[int]uint64{
				regs.memoryBW: 100,
				0xc20:         999,
			}), "", "")
			c, err := NewCollector(root, "h")
			if err != nil {
				t.Fatal(err)
			}
			start := c.prevTime
			c.now = func() time.Time { return start.Add(time.Second) }
			writeFile(t, c.telemetry.path, telemetryBuffer(4096, map[int]uint64{
				regs.memoryBW: 110,
				0xc20:         1, // D0-entry counter, not bandwidth, even when it decreases.
			}))
			points, err := c.Collect()
			if err != nil {
				t.Fatal(err)
			}
			line, err := points[0].Append(nil)
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(line), tt.want) {
				t.Fatalf("got %s, want %s", line, tt.want)
			}
		})
	}
}

func TestIncompleteSnapshotPreservesBaselineAndRecovers(t *testing.T) {
	for _, tt := range []struct {
		guid   string
		gen    CPUGen
		size   int
		wantBW string
	}{
		{"0x130670b2", GenMTL, 0x630, "bandwidth_bytes_per_second=5000,"},
		{"0x1306a0b3", GenARL, 0x630, "bandwidth_bytes_per_second=5000,"},
		{"0x3072005", GenLNL, 0xc20, "bandwidth_bytes_per_second=5120,"},
		{"0x3086000", GenPTL, 0xc20, "bandwidth_bytes_per_second=5120,"},
	} {
		t.Run(tt.gen.String(), func(t *testing.T) {
			regs := registerSets[tt.gen]
			buffer := telemetryBuffer(tt.size, map[int]uint64{regs.energy: 10 << 14, regs.memoryBW: 100})
			root := buildNPUSysfs(t, tt.guid, buffer, "0", "")
			c, err := NewCollector(root, "h")
			if err != nil {
				t.Fatal(err)
			}
			start := c.prevTime
			c.now = func() time.Time { return start.Add(time.Second) }
			for _, size := range []int{0, regs.energy + 1, tt.size - 1} {
				writeFile(t, c.telemetry.path, make([]byte, size))
				points, err := c.Collect()
				if err == nil || !strings.Contains(err.Error(), "incomplete") || len(points) != 0 {
					t.Fatalf("size %d: got %v, %v", size, points, err)
				}
				if c.prevTime != start || c.prevEnergy != 10 || c.prevBandwidth != 100 ||
					c.prevBusyUS != 0 || !c.hasPrevBusy || string(c.telemetry.buffer) != string(buffer) {
					t.Fatal("rejected snapshot changed the baseline")
				}
				if _, err := NewCollector(root, "h"); err == nil {
					t.Fatal("incomplete initial snapshot accepted")
				}
			}
			writeFile(t, c.telemetry.path, telemetryBuffer(tt.size, map[int]uint64{regs.energy: 14 << 14, regs.memoryBW: 110}))
			writeFile(t, c.busyPath, []byte("500000"))
			c.now = func() time.Time { return start.Add(2 * time.Second) }
			points, err := c.Collect()
			if err != nil {
				t.Fatal(err)
			}
			line, err := points[0].Append(nil)
			if err != nil {
				t.Fatal(err)
			}
			for _, want := range []string{"power_w=2,", tt.wantBW, "utilization=25i,"} {
				if !strings.Contains(string(line), want) {
					t.Fatalf("recovery: got %s, want %s", line, want)
				}
			}
		})
	}
}

func TestCounterDiscontinuityOmitsDeltasAndRebuildsBaseline(t *testing.T) {
	for _, tt := range []struct {
		name     string
		energy   uint64
		busy     string
		nextBusy string
	}{
		{"energy decreases", 5, "1500000", "2000000"},
		{"busy time resets", 12, "0", "500000"},
		{"both reset", 0, "0", "500000"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			regs := registerSets[GenPTL]
			root := buildNPUSysfs(t, "0x3086000", telemetryBuffer(4096, map[int]uint64{
				regs.energy: 10 << 14, regs.memoryBW: 100,
			}), "1000000", "")
			c, err := NewCollector(root, "h")
			if err != nil {
				t.Fatal(err)
			}
			start := c.prevTime
			for i := range 2 {
				energy, bandwidth, busy := tt.energy, uint64(10), tt.busy
				if i == 1 {
					energy, bandwidth, busy = energy+2, 20, tt.nextBusy
				}
				writeFile(t, c.telemetry.path, telemetryBuffer(4096, map[int]uint64{regs.energy: energy << 14, regs.memoryBW: bandwidth}))
				writeFile(t, c.busyPath, []byte(busy))
				c.now = func() time.Time { return start.Add(time.Duration(i+1) * time.Second) }
				points, err := c.Collect()
				if err != nil {
					t.Fatal(err)
				}
				line, err := points[0].Append(nil)
				if err != nil {
					t.Fatal(err)
				}
				if i == 0 {
					for _, absent := range []string{"power_w=", "bandwidth_bytes_per_second=", "utilization="} {
						if strings.Contains(string(line), absent) {
							t.Fatalf("invalid interval emitted %s", line)
						}
					}
					if !strings.Contains(string(line), "frequency_hz=") {
						t.Fatal("instantaneous fields lost")
					}
				} else {
					for _, want := range []string{"power_w=2,", "bandwidth_bytes_per_second=10240,", "utilization=50i,"} {
						if !strings.Contains(string(line), want) {
							t.Fatalf("recovery: got %s, want %s", line, want)
						}
					}
				}
			}
		})
	}
}
