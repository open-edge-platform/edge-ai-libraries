// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"strings"
	"time"
)

const DefaultChartsConfigPath = "/etc/metrics-manager/tui-charts.json"

type ChartsConfig struct {
	SPDXFileCopyrightText string        `json:"SPDX-FileCopyrightText,omitempty"`
	SPDXLicenseIdentifier string        `json:"SPDX-License-Identifier,omitempty"`
	HistoryDuration       string        `json:"historyDuration"`
	MaxPoints             int           `json:"maxPoints"`
	ChartHeight           int           `json:"chartHeight"`
	GraphMode             string        `json:"graphMode"`
	Charts                []ChartSpec   `json:"charts"`
	Details               DetailsConfig `json:"details"`
}

type DetailsConfig struct {
	DefaultMetric string      `json:"defaultMetric"`
	ChartHeight   int         `json:"chartHeight"`
	Mouse         bool        `json:"mouse"`
	Metrics       []ChartSpec `json:"metrics"`
}

type ChartSpec struct {
	Metric string   `json:"metric"`
	Title  string   `json:"title"`
	Unit   string   `json:"unit"`
	Min    *float64 `json:"min,omitempty"`
	Max    *float64 `json:"max,omitempty"`
}

var supportedCharts = map[string]bool{
	"cpu.totalPercent":           true,
	"cpu.temperatureC":           true,
	"memory.usedPercent":         true,
	"memory.bandwidthGBps":       true,
	"memory.readGBps":            true,
	"memory.writeGBps":           true,
	"rapl.powerW":                true,
	"gpu.utilizationPercent":     true,
	"gpu.temperatureC":           true,
	"npu.utilizationPercent":     true,
	"npu.temperatureC":           true,
	"cpu.classPercent":           true,
	"cpu.frequencyMHz":           true,
	"cpu.powerW":                 true,
	"gpu.enginePercent":          true,
	"gpu.frequencyMHz":           true,
	"gpu.powerW":                 true,
	"gpu.vramPercent":            true,
	"npu.frequencyMHz":           true,
	"npu.powerW":                 true,
	"npu.memoryMiB":              true,
	"network.rxMiBps":            true,
	"network.txMiBps":            true,
	"network.rxPercent":          true,
	"network.txPercent":          true,
	"network.rxPacketsPerSecond": true,
	"network.txPacketsPerSecond": true,
	"network.rxErrorsPerSecond":  true,
	"network.txErrorsPerSecond":  true,
	"network.rxDropsPerSecond":   true,
	"network.txDropsPerSecond":   true,
	"storage.usedPercent":        true,
	"storage.inodesPercent":      true,
	"storage.freeGiB":            true,
	"storage.readMiBps":          true,
	"storage.writeMiBps":         true,
	"storage.readIOPS":           true,
	"storage.writeIOPS":          true,
	"storage.readAwaitMs":        true,
	"storage.writeAwaitMs":       true,
	"storage.busyPercent":        true,
	"storage.queueDepth":         true,
	"storage.inProgress":         true,
}

func nonnegativeChart(metric string) bool {
	if strings.HasPrefix(metric, "storage.") && supportedCharts[metric] {
		return true
	}
	switch metric {
	case "cpu.totalPercent", "cpu.classPercent", "cpu.frequencyMHz", "cpu.powerW",
		"memory.usedPercent", "memory.bandwidthGBps", "memory.readGBps", "memory.writeGBps", "rapl.powerW",
		"gpu.utilizationPercent", "gpu.enginePercent", "gpu.frequencyMHz", "gpu.powerW", "gpu.vramPercent",
		"npu.utilizationPercent", "npu.frequencyMHz", "npu.powerW", "npu.memoryMiB",
		"network.rxMiBps", "network.txMiBps", "network.rxPercent", "network.txPercent",
		"network.rxPacketsPerSecond", "network.txPacketsPerSecond",
		"network.rxErrorsPerSecond", "network.txErrorsPerSecond",
		"network.rxDropsPerSecond", "network.txDropsPerSecond":
		return true
	default:
		return false
	}
}

func DefaultChartsConfig() ChartsConfig {
	config := ChartsConfig{
		HistoryDuration: "5m",
		MaxPoints:       600,
		ChartHeight:     6,
		GraphMode:       "braille",
		Details: DetailsConfig{
			DefaultMetric: "cpu.totalPercent",
			ChartHeight:   10,
			Mouse:         true,
			Metrics: []ChartSpec{
				fixedChart("cpu.totalPercent", "CPU utilization", "%", 0, 100),
				fixedChart("cpu.classPercent", "Core class utilization", "%", 0, 100),
				fixedChart("cpu.temperatureC", "CPU temperature", "°C", 0, 110),
				{Metric: "cpu.frequencyMHz", Title: "CPU frequency", Unit: "MHz"},
				{Metric: "cpu.powerW", Title: "CPU package power", Unit: "W"},
				fixedChart("memory.usedPercent", "Memory used", "%", 0, 100),
				{Metric: "memory.bandwidthGBps", Title: "Memory bandwidth", Unit: "GB/s"},
				{Metric: "memory.readGBps", Title: "DRAM read", Unit: "GB/s"},
				{Metric: "memory.writeGBps", Title: "DRAM write", Unit: "GB/s"},
				{Metric: "rapl.powerW", Title: "RAPL power", Unit: "W"},
				fixedChart("gpu.utilizationPercent", "GPU utilization", "%", 0, 100),
				fixedChart("gpu.enginePercent", "GPU engine utilization", "%", 0, 100),
				fixedChart("gpu.temperatureC", "GPU temperature", "°C", 0, 110),
				{Metric: "gpu.frequencyMHz", Title: "GPU tile frequency", Unit: "MHz"},
				{Metric: "gpu.powerW", Title: "GPU graphics power", Unit: "W"},
				fixedChart("gpu.vramPercent", "GPU VRAM used", "%", 0, 100),
				fixedChart("npu.utilizationPercent", "NPU utilization", "%", 0, 100),
				fixedChart("npu.temperatureC", "NPU temperature", "°C", 0, 110),
				{Metric: "npu.frequencyMHz", Title: "NPU frequency", Unit: "MHz"},
				{Metric: "npu.powerW", Title: "NPU power", Unit: "W"},
				{Metric: "npu.memoryMiB", Title: "NPU memory", Unit: "MiB"},
			},
		},
		Charts: []ChartSpec{
			fixedChart("cpu.totalPercent", "CPU utilization", "%", 0, 100),
			fixedChart("memory.usedPercent", "Memory used", "%", 0, 100),
			fixedChart("cpu.temperatureC", "CPU temperature", "°C", 0, 110),
			fixedChart("gpu.utilizationPercent", "GPU utilization", "%", 0, 100),
			fixedChart("gpu.temperatureC", "GPU temperature", "°C", 0, 110),
			fixedChart("npu.utilizationPercent", "NPU utilization", "%", 0, 100),
		},
	}
	config.Details.Metrics = append(config.Details.Metrics, networkChartSpecs()...)
	config.Charts = append(config.Charts, networkChartSpecs()[:2]...)
	storage := storageChartSpecs()
	config.Details.Metrics = append(config.Details.Metrics, storage...)
	config.Charts = append(config.Charts, storage[0], storage[3], storage[4])
	return config
}

func fixedChart(metric, title, unit string, minValue, maxValue float64) ChartSpec {
	return ChartSpec{
		Metric: metric,
		Title:  title,
		Unit:   unit,
		Min:    &minValue,
		Max:    &maxValue,
	}
}

func LoadChartsConfig(path string) (ChartsConfig, error) {
	config, err := decodeConfig(path, "charts", DefaultChartsConfig())
	if err != nil {
		return ChartsConfig{}, err
	}
	if err := config.Validate(); err != nil {
		return ChartsConfig{}, fmt.Errorf("validate charts config %q: %w", path, err)
	}

	return config, nil
}

func (c ChartsConfig) Validate() error {
	if c.GraphMode != "solid" && c.GraphMode != "unicode" && c.GraphMode != "ascii" && c.GraphMode != "braille" {
		return fmt.Errorf("graphMode must be solid, unicode, ascii or braille")
	}
	duration, err := time.ParseDuration(c.HistoryDuration)
	if err != nil {
		return fmt.Errorf("historyDuration: %w", err)
	}
	if duration < 10*time.Second || duration > 24*time.Hour {
		return fmt.Errorf("historyDuration must be between 10s and 24h")
	}
	if c.MaxPoints < 10 || c.MaxPoints > 3600 {
		return fmt.Errorf("maxPoints must be between 10 and 3600")
	}
	if c.ChartHeight < 3 || c.ChartHeight > 20 {
		return fmt.Errorf("chartHeight must be between 3 and 20")
	}
	if err := validateChartSpecs("charts", c.Charts); err != nil {
		return err
	}
	if c.Details.ChartHeight < 3 || c.Details.ChartHeight > 20 {
		return fmt.Errorf("details.chartHeight must be between 3 and 20")
	}
	if err := validateChartSpecs("details.metrics", c.Details.Metrics); err != nil {
		return err
	}
	for _, spec := range c.Details.Metrics {
		if spec.Metric == c.Details.DefaultMetric {
			return nil
		}
	}
	return fmt.Errorf("details.defaultMetric must be included in details.metrics")
}

func validateChartSpecs(name string, specs []ChartSpec) error {
	if len(specs) == 0 || len(specs) > 64 {
		return fmt.Errorf("%s must contain between 1 and 64 entries", name)
	}
	seen := make(map[string]bool, len(specs))
	for i, chart := range specs {
		if !supportedCharts[chart.Metric] {
			return fmt.Errorf("%s[%d].metric %q is not supported", name, i, chart.Metric)
		}
		if seen[chart.Metric] {
			return fmt.Errorf("%s[%d].metric %q is duplicated", name, i, chart.Metric)
		}
		seen[chart.Metric] = true
		if chart.Title == "" || len([]rune(chart.Title)) > 80 {
			return fmt.Errorf("%s[%d].title must contain 1 to 80 characters", name, i)
		}
		if len([]rune(chart.Unit)) > 16 {
			return fmt.Errorf("%s[%d].unit cannot exceed 16 characters", name, i)
		}
		if chart.Min != nil && (math.IsNaN(*chart.Min) || math.IsInf(*chart.Min, 0)) {
			return fmt.Errorf("%s[%d].min must be finite", name, i)
		}
		if chart.Max != nil && (math.IsNaN(*chart.Max) || math.IsInf(*chart.Max, 0)) {
			return fmt.Errorf("%s[%d].max must be finite", name, i)
		}
		if chart.Min != nil && chart.Max != nil && *chart.Min >= *chart.Max {
			return fmt.Errorf("%s[%d] must satisfy min < max", name, i)
		}
		if nonnegativeChart(chart.Metric) {
			if chart.Min != nil && *chart.Min < 0 {
				return fmt.Errorf("%s[%d].min must be nonnegative for %s", name, i, chart.Metric)
			}
			if chart.Max != nil && *chart.Max <= 0 {
				return fmt.Errorf("%s[%d].max must be positive for %s", name, i, chart.Metric)
			}
		}
	}

	return nil
}

func (c ChartsConfig) historyWindow() time.Duration {
	duration, err := time.ParseDuration(c.HistoryDuration)
	if err != nil {
		return 5 * time.Minute
	}

	return duration
}
