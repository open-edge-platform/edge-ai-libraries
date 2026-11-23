// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"time"
	"unicode"
)

const (
	DefaultConfigPath = "/etc/metrics-manager/tui-dashboard.json"
	maxConfigSize     = 1 << 20
)

type DashboardConfig struct {
	SPDXFileCopyrightText string               `json:"SPDX-FileCopyrightText,omitempty"`
	SPDXLicenseIdentifier string               `json:"SPDX-License-Identifier,omitempty"`
	Processes             ProcessConfig        `json:"processes"`
	Mouse                 bool                 `json:"mouse"`
	Network               NetworkConfig        `json:"network"`
	Storage               StorageConfig        `json:"storage"`
	Alerts                AlertConfig          `json:"alerts"`
	Thresholds            map[string]Threshold `json:"thresholds"`
}

type ProcessConfig struct {
	MaxDisplayed int              `json:"maxDisplayed"`
	SortBy       string           `json:"sortBy"`
	Descending   bool             `json:"descending"`
	CPUMode      string           `json:"cpuMode"`
	MaxSampleAge processSampleAge `json:"maxSampleAge"`
}

// processSampleAge keeps the JSON duration string while parsing it at the
// configuration boundary, so display and alert paths share a typed duration.
type processSampleAge time.Duration

func (age processSampleAge) MarshalJSON() ([]byte, error) {
	return json.Marshal(time.Duration(age).String())
}

func (age *processSampleAge) UnmarshalJSON(data []byte) error {
	var text string
	if err := json.Unmarshal(data, &text); err != nil {
		return fmt.Errorf("processes.maxSampleAge must be a duration string: %w", err)
	}
	value, err := time.ParseDuration(text)
	if err != nil {
		return fmt.Errorf("processes.maxSampleAge must be a duration: %w", err)
	}
	*age = processSampleAge(value)
	return nil
}

type AlertConfig struct {
	SamplesToRaise    int     `json:"samplesToRaise"`
	SamplesToClear    int     `json:"samplesToClear"`
	HysteresisPercent float64 `json:"hysteresisPercent"`
	ShowCareful       bool    `json:"showCareful"`
	MaxHistory        int     `json:"maxHistory"`
	BottomBar         bool    `json:"bottomBar"`
}

type Threshold struct {
	Careful  float64 `json:"careful"`
	Warning  float64 `json:"warning"`
	Critical float64 `json:"critical"`
}

var supportedThresholds = map[string]bool{
	"cpu.totalPercent":        true,
	"cpu.temperatureC":        true,
	"memory.usedPercent":      true,
	"gpu.utilizationPercent":  true,
	"gpu.temperatureC":        true,
	"npu.utilizationPercent":  true,
	"npu.temperatureC":        true,
	"process.cpuPercent":      true,
	"cpu.classPercent":        true,
	"gpu.vramPercent":         true,
	"gpu.processPercent":      true,
	"network.rxPercent":       true,
	"network.txPercent":       true,
	"network.errorsPerSecond": true,
	"network.dropsPerSecond":  true,
	"storage.usedPercent":     true,
	"storage.inodesPercent":   true,
	"storage.busyPercent":     true,
	"storage.readMiBps":       true,
	"storage.writeMiBps":      true,
	"storage.readIOPS":        true,
	"storage.writeIOPS":       true,
	"storage.readAwaitMs":     true,
	"storage.writeAwaitMs":    true,
	"storage.queueDepth":      true,
	"storage.inProgress":      true,
}

func DefaultDashboardConfig() DashboardConfig {
	return DashboardConfig{
		Processes: ProcessConfig{MaxDisplayed: 10, SortBy: "usage", Descending: true, CPUMode: "total", MaxSampleAge: processSampleAge(3 * time.Second)},
		Mouse:     true,
		Network:   NetworkConfig{MaxInterfaces: 8, MaxSampleAge: "10s"},
		Storage: StorageConfig{
			MaxFilesystems: 4, MaxDevices: 4, MaxSampleAge: "10s",
			IgnoreFilesystems: []string{"tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"},
		},
		Alerts: AlertConfig{
			SamplesToRaise:    3,
			SamplesToClear:    3,
			HysteresisPercent: 5,
			MaxHistory:        50,
			BottomBar:         true,
		},
		Thresholds: map[string]Threshold{
			"cpu.totalPercent":        {Careful: 65, Warning: 75, Critical: 85},
			"cpu.temperatureC":        {Careful: 70, Warning: 85, Critical: 95},
			"memory.usedPercent":      {Careful: 50, Warning: 70, Critical: 90},
			"gpu.utilizationPercent":  {Careful: 50, Warning: 70, Critical: 90},
			"gpu.temperatureC":        {Careful: 60, Warning: 70, Critical: 80},
			"npu.utilizationPercent":  {Careful: 50, Warning: 70, Critical: 90},
			"npu.temperatureC":        {Careful: 70, Warning: 85, Critical: 95},
			"process.cpuPercent":      {Careful: 50, Warning: 70, Critical: 90},
			"cpu.classPercent":        {Careful: 65, Warning: 75, Critical: 85},
			"gpu.vramPercent":         {Careful: 70, Warning: 85, Critical: 95},
			"gpu.processPercent":      {Careful: 50, Warning: 70, Critical: 90},
			"network.rxPercent":       {Careful: 70, Warning: 80, Critical: 90},
			"network.txPercent":       {Careful: 70, Warning: 80, Critical: 90},
			"network.errorsPerSecond": {Careful: 0.1, Warning: 1, Critical: 10},
			"network.dropsPerSecond":  {Careful: 0.1, Warning: 1, Critical: 10},
			"storage.usedPercent":     {Careful: 70, Warning: 80, Critical: 90},
			"storage.inodesPercent":   {Careful: 70, Warning: 80, Critical: 90},
		},
	}
}

// LoadDashboardConfig returns built-in defaults when the standard configuration
// file is absent. An existing but invalid file is always reported.
func LoadDashboardConfig(path string) (DashboardConfig, error) {
	config := DefaultDashboardConfig()
	config, err := decodeConfig(path, "dashboard", config)
	if err != nil {
		return DashboardConfig{}, err
	}
	if err := config.Validate(); err != nil {
		return DashboardConfig{}, fmt.Errorf("validate dashboard config %q: %w", path, err)
	}

	return config, nil
}

func decodeConfig[T any](path, kind string, config T) (T, error) {
	var zero T
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return config, nil
	}
	if err != nil {
		return zero, fmt.Errorf("open %s config %q: %w", kind, path, err)
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return zero, fmt.Errorf("stat %s config %q: %w", kind, path, err)
	}
	if info.Size() > maxConfigSize {
		return zero, fmt.Errorf("%s config %q exceeds %d bytes", kind, path, maxConfigSize)
	}

	decoder := json.NewDecoder(io.LimitReader(file, maxConfigSize))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&config); err != nil {
		return zero, fmt.Errorf("decode %s config %q: %w", kind, path, err)
	}
	if err := ensureJSONEnd(decoder); err != nil {
		return zero, fmt.Errorf("decode %s config %q: %w", kind, path, err)
	}

	return config, nil
}

func ensureJSONEnd(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("configuration contains more than one JSON value")
		}
		return err
	}

	return nil
}

func (c DashboardConfig) Validate() error {
	if err := c.Storage.validate(); err != nil {
		return err
	}
	if c.Network.MaxInterfaces < 1 || c.Network.MaxInterfaces > 32 {
		return fmt.Errorf("network.maxInterfaces must be between 1 and 32")
	}
	maxAge, err := time.ParseDuration(c.Network.MaxSampleAge)
	if err != nil || maxAge < time.Second || maxAge > 5*time.Minute {
		return fmt.Errorf("network.maxSampleAge must be a duration between 1s and 5m")
	}
	if len(c.Network.Interfaces) > 32 || len(c.Network.SpeedMbps) > 32 {
		return fmt.Errorf("network.interfaces and network.speedMbps accept at most 32 entries")
	}
	seen := make(map[string]bool)
	validName := func(name string) bool {
		return name != "" && len(name) <= 64 && strings.TrimSpace(name) == name &&
			!strings.ContainsRune(name, '/') && strings.IndexFunc(name, unicode.IsControl) < 0
	}
	for _, name := range c.Network.Interfaces {
		if !validName(name) || seen[name] {
			return fmt.Errorf("network.interfaces must contain unique, nonempty interface names without control characters")
		}
		seen[name] = true
	}
	for name, speed := range c.Network.SpeedMbps {
		if !validName(name) || !finiteReading(reading(speed)) || speed <= 0 || speed > 1e7 {
			return fmt.Errorf("network.speedMbps requires valid interface names and finite speeds greater than 0 and at most 10000000 Mbit/s")
		}
	}
	switch c.Processes.SortBy {
	case "usage", "pid", "memory":
	default:
		return fmt.Errorf("processes.sortBy must be usage, pid or memory")
	}
	switch c.Processes.CPUMode {
	case "per-core", "total":
	default:
		return fmt.Errorf("processes.cpuMode must be per-core or total")
	}
	if c.Processes.MaxDisplayed <= 0 || c.Processes.MaxDisplayed > 1000 {
		return fmt.Errorf("processes.maxDisplayed must be between 1 and 1000")
	}
	if time.Duration(c.Processes.MaxSampleAge) < time.Second || time.Duration(c.Processes.MaxSampleAge) > 5*time.Minute {
		return fmt.Errorf("processes.maxSampleAge must be between 1s and 5m")
	}
	if c.Alerts.SamplesToRaise <= 0 || c.Alerts.SamplesToRaise > 1000 {
		return fmt.Errorf("alerts.samplesToRaise must be between 1 and 1000")
	}
	if c.Alerts.SamplesToClear <= 0 || c.Alerts.SamplesToClear > 1000 {
		return fmt.Errorf("alerts.samplesToClear must be between 1 and 1000")
	}
	if c.Alerts.HysteresisPercent < 0 || c.Alerts.HysteresisPercent >= 100 {
		return fmt.Errorf("alerts.hysteresisPercent must be at least 0 and less than 100")
	}
	if c.Alerts.MaxHistory < 0 || c.Alerts.MaxHistory > 1000 {
		return fmt.Errorf("alerts.maxHistory must be between 0 and 1000")
	}
	for name, threshold := range c.Thresholds {
		if !supportedThresholds[name] {
			return fmt.Errorf("threshold %q is not supported", name)
		}
		if threshold.Careful < 0 ||
			threshold.Careful >= threshold.Warning ||
			threshold.Warning >= threshold.Critical {
			return fmt.Errorf("threshold %q must satisfy 0 <= careful < warning < critical", name)
		}
		if isPercentThreshold(name) && threshold.Critical > 100 {
			return fmt.Errorf("threshold %q critical value cannot exceed 100", name)
		}
	}

	return nil
}

func isPercentThreshold(name string) bool {
	return strings.HasSuffix(name, "Percent")
}

func thresholdMetric(name string) string {
	switch name {
	case "gpu.enginePercent":
		return "gpu.utilizationPercent"
	case "network.rxErrorsPerSecond", "network.txErrorsPerSecond":
		return "network.errorsPerSecond"
	case "network.rxDropsPerSecond", "network.txDropsPerSecond":
		return "network.dropsPerSecond"
	default:
		return name
	}
}

func thresholdUnit(name string) string {
	if strings.HasPrefix(name, "storage.") {
		for _, spec := range storageChartSpecs() {
			if spec.Metric == name {
				return " " + spec.Unit
			}
		}
	}
	if isPercentThreshold(name) {
		return "%"
	}
	if strings.HasSuffix(name, "PerSecond") {
		return "/s"
	}
	return " C"
}
