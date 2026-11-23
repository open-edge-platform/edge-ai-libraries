// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package cpu

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// MeasurementPlatform identifies the machine itself.
//
// It carries no readings, only a value of 1 tagged with what the machine is.
// That is the usual shape for describing a target in a metrics system: the
// facts live in labels, so a dashboard can show them and a query can filter on
// them, without inventing a number for a string.
const MeasurementPlatform = "platform"

// maxDescriptionLength bounds every value read from the kernel before it
// becomes a tag. The model name comes from firmware, and a tag that turns out
// to be several kilobytes long would bloat the endpoint and every scrape of
// it.
const maxDescriptionLength = 96

// PlatformPoint describes the machine: what CPU it has, what kernel it runs,
// and how many logical processors are online.
//
// Every value is best-effort. One that cannot be read is reported as "unknown"
// rather than omitted, so the tag set stays the same shape across hosts and a
// missing value is visible instead of silently absent.
//
// No host tag is set here: Telegraf stamps one on every metric, and the other
// points from this package leave it to do so.
func PlatformPoint(procRoot string) lineproto.Point {
	return lineproto.Point{
		Measurement: MeasurementPlatform,
		Tags: []lineproto.Tag{
			{Key: "model", Value: cpuModel(procRoot)},
			{Key: "kernel", Value: kernelRelease(procRoot)},
			{Key: "arch", Value: runtime.GOARCH},
		},
		Fields: []lineproto.Field{
			lineproto.IntField("logical_cpus", int64(runtime.NumCPU())),
		},
	}
}

// cpuModel reads the marketing name of the processor from /proc/cpuinfo.
//
// Every logical CPU repeats the same line, so the first one is enough.
func cpuModel(procRoot string) string {
	raw, err := os.ReadFile(filepath.Join(procRoot, "cpuinfo"))
	if err != nil {
		return "unknown"
	}

	for _, line := range strings.Split(string(raw), "\n") {
		name, value, found := strings.Cut(line, ":")
		if !found || strings.TrimSpace(name) != "model name" {
			continue
		}

		return describe(value)
	}

	return "unknown"
}

// kernelRelease reads the running kernel version.
func kernelRelease(procRoot string) string {
	raw, err := os.ReadFile(filepath.Join(procRoot, "sys", "kernel", "osrelease"))
	if err != nil {
		return "unknown"
	}

	return describe(string(raw))
}

// describe normalises a value read from the kernel into a tag.
//
// Collapsing runs of whitespace matters because firmware pads model names to a
// fixed width, which would otherwise appear verbatim in the label.
func describe(raw string) string {
	value := strings.Join(strings.Fields(raw), " ")
	if value == "" {
		return "unknown"
	}

	if len(value) > maxDescriptionLength {
		value = value[:maxDescriptionLength]
	}

	return value
}
