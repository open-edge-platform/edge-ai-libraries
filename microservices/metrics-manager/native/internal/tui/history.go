// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"sort"
	"time"
)

const maxHistorySeries = 128

type HistoryPoint struct {
	At    time.Time
	Value float64
}

type HistorySeries struct {
	Key       string
	Metric    string
	Label     string
	Device    string
	Points    []HistoryPoint
	Available bool
	scale     chartScale
}

type History struct {
	window    time.Duration
	maxPoints int
	series    map[string]*HistorySeries
	limited   bool
}

type chartObservation struct {
	key, metric, label string
	device             string
	value              Reading
	at                 time.Time
}

func NewHistory(config ChartsConfig) History {
	return History{
		window:    config.historyWindow(),
		maxPoints: config.MaxPoints,
		series:    make(map[string]*HistorySeries),
	}
}

func (h *History) Update(dashboard Dashboard, at time.Time) {
	// Reclaim expired slots before admitting new devices.
	h.Prune(at)
	h.limited = false
	for _, series := range h.series {
		series.Available = false
	}
	for _, observation := range chartObservations(dashboard) {
		if !observation.value.OK ||
			math.IsNaN(observation.value.Value) ||
			math.IsInf(observation.value.Value, 0) {
			continue
		}
		pointAt := at
		if !observation.at.IsZero() {
			pointAt = observation.at
		}
		if pointAt.Before(at.Add(-h.window)) || pointAt.After(at) {
			continue
		}

		series := h.series[observation.key]
		if series == nil {
			if len(h.series) >= maxHistorySeries {
				h.limited = true
				continue
			}
			series = &HistorySeries{
				Key: observation.key, Metric: observation.metric, Label: observation.label,
				Device: observation.device,
			}
			h.series[observation.key] = series
		}
		point := HistoryPoint{At: pointAt, Value: observation.value.Value}
		i := sort.Search(len(series.Points), func(i int) bool {
			return !series.Points[i].At.Before(pointAt)
		})
		if i < len(series.Points) && series.Points[i].At.Equal(pointAt) {
			series.Points[i] = point
		} else {
			series.Points = append(series.Points, HistoryPoint{})
			copy(series.Points[i+1:], series.Points[i:])
			series.Points[i] = point
		}
		series.Available = true
		h.prune(series, at)
	}
}

// Prune ages retained data even when no new snapshot is received.
func (h *History) Prune(at time.Time) {
	for key, series := range h.series {
		h.prune(series, at)
		if len(series.Points) == 0 {
			delete(h.series, key)
		}
	}
}

func (h *History) prune(series *HistorySeries, now time.Time) {
	cutoff := now.Add(-h.window)
	first := sort.Search(len(series.Points), func(i int) bool {
		return !series.Points[i].At.Before(cutoff)
	})
	first = max(first, len(series.Points)-h.maxPoints)
	if first > 0 {
		// Reuse storage instead of allocating for each expired sample.
		n := copy(series.Points, series.Points[first:])
		clear(series.Points[n:])
		series.Points = series.Points[:n]
	}
	series.scale.update(series.Metric, series.Points, now)
}

func (h History) Series(metric string) []HistorySeries {
	var series []HistorySeries
	for _, candidate := range h.series {
		if candidate.Metric == metric {
			series = append(series, *candidate)
		}
	}
	sort.Slice(series, func(i, j int) bool {
		return series[i].Key < series[j].Key
	})

	return series
}

func chartObservations(d Dashboard) []chartObservation {
	observations := []chartObservation{
		{key: "cpu.total", metric: "cpu.totalPercent", label: "CPU", value: totalCPUUsage(d.CPU)},
		{key: "cpu.temperature", metric: "cpu.temperatureC", label: "CPU", value: d.CPU.PackageTempC},
		{key: "memory.used", metric: "memory.usedPercent", label: "Memory", value: d.Memory.UsedPercent},
		{
			key: "memory.bandwidth", metric: "memory.bandwidthGBps",
			label: "Memory", value: d.Memory.TotalGBps,
		},
	}
	if d.Memory.ReadGBps.OK && !math.IsNaN(d.Memory.ReadGBps.Value) && !math.IsInf(d.Memory.ReadGBps.Value, 0) {
		observations = append(observations, chartObservation{
			key: "memory.bandwidth.read", metric: "memory.readGBps",
			label: "Memory", value: d.Memory.ReadGBps,
		})
	}
	if d.Memory.WriteGBps.OK && !math.IsNaN(d.Memory.WriteGBps.Value) && !math.IsInf(d.Memory.WriteGBps.Value, 0) {
		observations = append(observations, chartObservation{
			key: "memory.bandwidth.write", metric: "memory.writeGBps",
			label: "Memory", value: d.Memory.WriteGBps,
		})
	}

	for _, domain := range d.RAPL {
		observations = append(observations, chartObservation{
			key: "rapl." + domain.Domain, metric: "rapl.powerW",
			label: domain.Domain, device: domain.Domain, value: domain.PowerW,
		})
	}

	for _, gpu := range d.GPUs {
		observations = append(observations,
			chartObservation{
				key: "gpu." + gpu.ID + ".utilization", metric: "gpu.utilizationPercent", device: gpu.ID,
				label: "GPU " + gpu.ID, value: maxEngineUsage(gpu.Engines),
			},
			chartObservation{
				key: "gpu." + gpu.ID + ".temperature", metric: "gpu.temperatureC", device: gpu.ID,
				label: "GPU " + gpu.ID, value: gpu.TempC,
			},
		)
	}
	observations = append(observations,
		chartObservation{
			key: "npu.utilization", metric: "npu.utilizationPercent",
			label: "NPU", value: d.NPU.Utilization,
		},
		chartObservation{
			key: "npu.temperature", metric: "npu.temperatureC",
			label: "NPU", value: d.NPU.TempC,
		},
	)

	observations = append(observations,
		chartObservation{key: "cpu.frequency", metric: "cpu.frequencyMHz", label: "CPU", value: scaleReading(d.CPU.FrequencyKHz, 1000)},
		chartObservation{key: "cpu.power", metric: "cpu.powerW", label: "CPU", value: d.CPU.PackagePowerW},
		chartObservation{key: "npu.frequency", metric: "npu.frequencyMHz", label: "NPU", value: scaleReading(d.NPU.FrequencyHz, 1e6)},
		chartObservation{key: "npu.power", metric: "npu.powerW", label: "NPU", value: d.NPU.PowerW},
		chartObservation{key: "npu.memory", metric: "npu.memoryMiB", label: "NPU", value: d.NPU.MemoryMiB},
	)
	for _, class := range d.CPU.Classes {
		observations = append(observations, chartObservation{
			key: "cpu.class." + class.Name, metric: "cpu.classPercent", label: class.Name,
			value: totalCPUUsage(CPU{UsageIdle: class.UsageIdle}),
		})
	}
	for _, gpu := range d.GPUs {
		observations = append(observations,
			chartObservation{key: "gpu." + gpu.ID + ".power", metric: "gpu.powerW", label: "GPU " + gpu.ID, device: gpu.ID, value: gpu.PowerW},
			chartObservation{key: "gpu." + gpu.ID + ".vram", metric: "gpu.vramPercent", label: "GPU " + gpu.ID, device: gpu.ID,
				value: usedPercent(gpu.VRAMUsedBytes, gpu.VRAMTotalBytes)},
		)
		for _, engine := range gpu.Engines {
			observations = append(observations, chartObservation{
				key: "gpu." + gpu.ID + ".engine." + engine.Name, metric: "gpu.enginePercent", device: gpu.ID,
				label: "GPU " + gpu.ID + " / " + engine.Name, value: engine.Usage,
			})
		}
		for _, tile := range gpu.Tiles {
			observations = append(observations, chartObservation{
				key: "gpu." + gpu.ID + ".tile." + tile.Name, metric: "gpu.frequencyMHz", device: gpu.ID,
				label: "GPU " + gpu.ID + " / " + tile.Name, value: tile.ActualMHz,
			})
		}
	}
	for _, network := range d.Network {
		for _, spec := range networkChartSpecs() {
			value := network.Metrics[spec.Metric]
			observations = append(observations, chartObservation{
				key: "network." + network.Key + "." + spec.Metric, metric: spec.Metric,
				label: network.label(), device: network.Key, value: value.Reading, at: value.At,
			})
		}
	}
	for _, storage := range d.Storage {
		for _, spec := range storage.specs() {
			value := storage.Metrics[spec.Metric]
			observations = append(observations, chartObservation{
				key: "storage." + storage.Key + "." + spec.Metric, metric: spec.Metric,
				label: storage.label(), device: storage.Key, value: value.Reading, at: value.At,
			})
		}
	}
	return observations
}

func scaleReading(value Reading, divisor float64) Reading {
	if !value.OK {
		return value
	}
	return reading(value.Value / divisor)
}

func usedPercent(used, total Reading) Reading {
	if !used.OK || !total.OK || total.Value <= 0 || used.Value < 0 ||
		math.IsNaN(used.Value) || math.IsInf(used.Value, 0) ||
		math.IsNaN(total.Value) || math.IsInf(total.Value, 0) {
		return Reading{}
	}
	return reading(100 * used.Value / total.Value)
}

func maxEngineUsage(engines []GPUEngine) Reading {
	maximum := Reading{}
	for _, engine := range engines {
		if !engine.Usage.OK || math.IsNaN(engine.Usage.Value) || math.IsInf(engine.Usage.Value, 0) {
			continue
		}
		if !maximum.OK || engine.Usage.Value > maximum.Value {
			maximum = engine.Usage
		}
	}

	return maximum
}

func seriesTitle(spec ChartSpec, series HistorySeries) string {
	if series.Label == "" || series.Label == spec.Title {
		return spec.Title
	}

	return fmt.Sprintf("%s · %s", spec.Title, series.Label)
}
