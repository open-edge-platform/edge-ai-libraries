// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package npu reads Intel NPU telemetry through the kernel's Platform
// Monitoring Technology (PMT) sysfs interface.
//
// It is a port of the Python NPU readers this package replaced, and
// deliberately reproduces their arithmetic and output formatting so that the
// switch does not change a single emitted byte.
package npu

import (
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// CPUGen identifies the SoC generation, which determines the telemetry
// register layout.
//
// The order matters: memory utilisation is only exposed from PTL onwards, and
// that check is a numeric comparison.
type CPUGen int

const (
	GenMTL CPUGen = iota
	GenARL
	GenLNL
	GenPTL
)

func (g CPUGen) String() string {
	switch g {
	case GenMTL:
		return "Meteor Lake"
	case GenARL:
		return "Arrow Lake"
	case GenLNL:
		return "Lunar Lake"
	case GenPTL:
		return "Panther Lake"
	default:
		return "unknown"
	}
}

// guidToGen maps the PMT telemetry GUID advertised by the kernel onto a SoC
// generation. Arrow Lake ships three GUIDs for its H and S variants, all of
// which share the Meteor Lake register layout.
var guidToGen = map[string]CPUGen{
	"0x130670b2": GenMTL,
	"0x1306a0b3": GenARL,
	"0x1306a0b2": GenARL,
	"0x1306a0b4": GenARL,
	"0x3072005":  GenLNL,
	"0x3086000":  GenPTL,
}

// registers holds the byte offsets of the telemetry containers we read.
type registers struct {
	energy          int
	socTemperatures int
	workpoint       int
	memoryBW        int
}

// registerSets are the per-generation offsets. Arrow Lake reuses the Meteor
// Lake layout.
var registerSets = map[CPUGen]registers{
	GenMTL: {energy: 0x628, socTemperatures: 0x98, workpoint: 0x68, memoryBW: 0x0},
	GenARL: {energy: 0x628, socTemperatures: 0x98, workpoint: 0x68, memoryBW: 0x0},
	GenLNL: {energy: 0x5d0, socTemperatures: 0x70, workpoint: 0x18, memoryBW: 0xc18},
	GenPTL: {energy: 0x670, socTemperatures: 0x78, workpoint: 0x18, memoryBW: 0xc18},
}

// Telemetry is an open PMT telemetry device.
//
// Reads are served from a snapshot taken by Update, so all values derived from
// one snapshot describe the same instant.
type Telemetry struct {
	path   string
	gen    CPUGen
	regs   registers
	buffer []byte
}

// Open finds the PMT telemetry device whose GUID identifies a supported SoC.
//
// sysfsRoot is normally "/sys"; tests point it at a fixture directory.
func Open(sysfsRoot string) (*Telemetry, error) {
	root := filepath.Join(sysfsRoot, "class/intel_pmt")

	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("PMT sysfs interface not available at %s: %w", root, err)
	}

	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "telem") {
			continue
		}
		dir := filepath.Join(root, entry.Name())

		// A telemetry device is only usable if the kernel exposes the whole
		// set of attributes; a partially populated directory is skipped.
		guid, err := readTrimmed(filepath.Join(dir, "guid"))
		if err != nil {
			continue
		}
		for _, attr := range []string{"telem", "size", "offset"} {
			if _, statErr := os.Stat(filepath.Join(dir, attr)); statErr != nil {
				err = statErr
			}
		}
		if err != nil {
			continue
		}

		gen, known := guidToGen[guid]
		if !known {
			continue
		}
		return &Telemetry{
			path: filepath.Join(dir, "telem"),
			gen:  gen,
			regs: registerSets[gen],
		}, nil
	}

	return nil, fmt.Errorf("no PMT telemetry device with a known GUID found in %s", root)
}

// Gen reports the detected SoC generation.
func (t *Telemetry) Gen() CPUGen { return t.gen }

// Update takes a fresh snapshot of the telemetry buffer.
func (t *Telemetry) Update() error {
	buffer, err := os.ReadFile(t.path)
	if err != nil {
		return fmt.Errorf("reading telemetry from %s: %w", t.path, err)
	}
	t.buffer = buffer
	return nil
}

// read extracts the bits [msb:lsb] of the 64-bit little-endian word at offset.
//
// A container that runs past the end of the buffer is read from the bytes that
// are present, matching the Python slice semantics this was ported from; an
// offset beyond the buffer yields zero.
func (t *Telemetry) read(offset, msb, lsb uint) uint64 {
	if offset >= uint(len(t.buffer)) {
		return 0
	}

	end := offset + 8
	if end > uint(len(t.buffer)) {
		end = uint(len(t.buffer))
	}

	var word [8]byte
	copy(word[:], t.buffer[offset:end])
	data := binary.LittleEndian.Uint64(word[:])

	// Build the mask as bits [msb:lsb]. The msb == 63 case is special because
	// 1<<64 overflows a uint64.
	msbMask := ^uint64(0)
	if msb < 63 {
		msbMask = (uint64(1) << (msb + 1)) - 1
	}
	lsbMask := (uint64(1) << lsb) - 1

	return (data & msbMask & ^lsbMask) >> lsb
}

// FrequencyHz decodes the DPU PLL ratio using the intel_vpu buttress formulas.
func (t *Telemetry) FrequencyHz() float64 {
	raw := float64(t.read(uint(t.regs.workpoint), 7, 0))
	if t.gen == GenMTL || t.gen == GenARL {
		return raw * 50_000_000 * 2 / 3
	}
	return raw * 50_000_000 / 2
}

// TileConfig returns the active NPU tile configuration.
func (t *Telemetry) TileConfig() uint64 {
	return t.read(uint(t.regs.workpoint), 23, 16)
}

// TemperatureC returns the NPU temperature in degrees Celsius.
func (t *Telemetry) TemperatureC() uint64 {
	return t.read(uint(t.regs.socTemperatures), 47, 40)
}

// EnergyJoules returns the accumulated NPU energy counter in joules.
//
// The register is U32.18.14 fixed point: the low 14 bits are the fraction.
func (t *Telemetry) EnergyJoules() float64 {
	raw := t.read(uint(t.regs.energy), 63, 0)
	const fractionBits = 14
	whole := raw >> fractionBits
	fraction := float64(raw&((1<<fractionBits)-1)) / (1 << fractionBits)
	return float64(whole) + fraction
}

// BandwidthBytes returns the accumulated network-on-chip transfer counter.
// The 32-bit counter counts decimal kilobytes.
func (t *Telemetry) BandwidthBytes() float64 {
	return float64(t.read(uint(t.regs.memoryBW), 31, 0)) * 1e3
}

// readTrimmed reads a sysfs attribute and strips surrounding whitespace.
func readTrimmed(path string) (string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(raw)), nil
}

// readUint reads a sysfs attribute holding a single unsigned integer.
func readUint(path string) (uint64, error) {
	text, err := readTrimmed(path)
	if err != nil {
		return 0, err
	}
	return strconv.ParseUint(text, 10, 64)
}
