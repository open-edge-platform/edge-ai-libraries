// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import "time"

type timedReading struct {
	Reading
	At     time.Time
	From   time.Time
	Reason string
}

type counterRateState struct {
	value  float64
	at     time.Time
	result timedReading
}

// update uses measurement timestamps, never scrape cadence. Re-reading a cached
// sample returns the same rate and timestamp instead of manufacturing a zero.
func (s *counterRateState) update(value Reading, timestampMS int64, now time.Time, maxAge time.Duration) timedReading {
	missing := func(reason string, reset bool) timedReading {
		if reset {
			*s = counterRateState{}
		}
		return timedReading{Reason: reason}
	}
	if !finiteReading(value) || value.Value < 0 {
		return missing("counter missing or invalid", true)
	}
	if timestampMS <= 0 {
		return missing("measurement timestamp missing", true)
	}
	at := time.UnixMilli(timestampMS)
	if at.After(now) {
		return missing("measurement timestamp is in the future", true)
	}
	if now.Sub(at) > maxAge {
		return missing("measurement is stale", true)
	}
	if !s.at.IsZero() && at.Before(s.at) {
		return missing("out-of-order measurement", false)
	}
	if at.Equal(s.at) {
		if value.Value != s.value {
			return missing("conflicting values at one timestamp", true)
		}
		return s.result
	}
	result := timedReading{At: at, From: s.at, Reason: "waiting for a second measurement"}
	if !s.at.IsZero() {
		if value.Value < s.value {
			result.Reason = "counter reset; waiting for next measurement"
		} else {
			result.Reading = reading((value.Value - s.value) / at.Sub(s.at).Seconds())
			result.Reason = ""
			if !finiteReading(result.Reading) {
				result = timedReading{At: at, Reason: "rate is outside the supported range"}
			}
		}
	}
	s.value, s.at, s.result = value.Value, at, result
	return result
}
