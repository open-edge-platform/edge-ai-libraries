// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"time"
)

const chartScaleShrinkDelay = 30 * time.Second

type chartScale struct {
	minimum, maximum float64
	ready            bool
	shrinkSince      time.Time
}

func (s *chartScale) update(metric string, points []HistoryPoint, now time.Time) {
	if len(points) == 0 {
		return
	}
	minimum, maximum := chartBounds(ChartSpec{Metric: metric}, points)
	minimum, maximum = niceChartBound(minimum, false), niceChartBound(maximum, true)
	if !s.ready {
		s.minimum, s.maximum, s.ready = minimum, maximum, true
		return
	}
	if minimum < s.minimum || maximum > s.maximum {
		s.minimum, s.maximum = math.Min(s.minimum, minimum), math.Max(s.maximum, maximum)
		s.shrinkSince = time.Time{}
		return
	}
	if maximum-minimum > (s.maximum-s.minimum)/2 {
		s.shrinkSince = time.Time{}
		return
	}
	if s.shrinkSince.IsZero() || now.Before(s.shrinkSince) {
		s.shrinkSince = now
	}
	if now.Sub(s.shrinkSince) >= chartScaleShrinkDelay {
		s.minimum, s.maximum = minimum, maximum
		s.shrinkSince = time.Time{}
	}
}

// Use 1/2/5 decade steps, rounding outward to avoid clipping measured peaks.
func niceChartBound(value float64, upper bool) float64 {
	if value == 0 || math.IsInf(value, 0) {
		return value
	}
	if value < 0 {
		return -niceChartBound(-value, !upper)
	}
	if value < 0x1p-1022 {
		return value
	}
	base := math.Pow(10, math.Floor(math.Log10(value)))
	if base == 0 {
		return value
	}
	result := base
	for _, factor := range []float64{1, 2, 5, 10} {
		candidate := factor * base
		if upper && candidate >= value {
			if math.IsInf(candidate, 0) {
				return value
			}
			return candidate
		}
		if candidate <= value {
			result = candidate
		}
	}
	if upper {
		return value
	}
	return result
}

func (s chartScale) bounds(spec ChartSpec, points []HistoryPoint) (float64, float64) {
	minimum, maximum := chartBounds(spec, points)
	if !s.ready {
		return minimum, maximum
	}
	if spec.Min == nil && s.minimum < maximum {
		minimum = s.minimum
	}
	if spec.Max == nil && s.maximum > minimum {
		maximum = s.maximum
	}
	return minimum, maximum
}
