// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"maps"
	"math"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

// Owner labels can change while Telegraf retains the old series. Select one
// current identity before looking up its memory and thread measurements.
func latestProcessCPU(idx *Index, pid string) (promtext.Sample, bool) {
	var latest promtext.Sample
	found, ambiguous := false, false
	for _, sample := range idx.All("process_cpu_percent") {
		if sample.Labels["pid"] != pid {
			continue
		}
		if !found || sample.TimestampMS > latest.TimestampMS {
			latest, found, ambiguous = sample, true, false
		} else if sample.TimestampMS == latest.TimestampMS &&
			(!maps.Equal(sample.Labels, latest.Labels) || sample.Value != latest.Value) {
			ambiguous = true
		}
	}
	if ambiguous {
		latest.Value = math.NaN()
		latest.Labels = nil
	}
	return latest, found
}

func processField(idx *Index, name string, identity promtext.Sample) Reading {
	var value Reading
	for _, sample := range idx.All(name) {
		if sample.TimestampMS != identity.TimestampMS || !maps.Equal(sample.Labels, identity.Labels) {
			continue
		}
		if value.OK && value.Value != sample.Value {
			return reading(math.NaN())
		}
		value = reading(sample.Value)
	}
	return value
}

func formatProcessThreads(threads Reading) string {
	if finiteReading(threads) && (threads.Value < 1 || math.Trunc(threads.Value) != threads.Value) {
		return unavailable
	}
	return formatCount(threads)
}

func formatProcessUser(username string) string {
	if username == "" {
		return absent
	}
	return sanitize(username, 16)
}
