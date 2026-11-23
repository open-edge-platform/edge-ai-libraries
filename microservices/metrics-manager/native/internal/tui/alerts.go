// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"math"
	"sort"
	"time"
)

type Severity int

const (
	SeverityOK Severity = iota
	SeverityCareful
	SeverityWarning
	SeverityCritical
)

func (s Severity) String() string {
	switch s {
	case SeverityCareful:
		return "CAREFUL"
	case SeverityWarning:
		return "WARNING"
	case SeverityCritical:
		return "CRITICAL"
	default:
		return "OK"
	}
}

type Alert struct {
	Key              string
	Metric           string
	Device           string
	Severity         Severity
	Value            float64
	Threshold        float64
	Since            time.Time
	Message          string
	Unavailable      bool
	TriggerValue     Reading
	TriggerThreshold float64
	PeakValue        Reading
	PeakAt           time.Time
	RecoveryValue    Reading
}

type AlertEvent struct {
	Alert
	EndedAt time.Time
	Outcome string
}

type observation struct {
	key, metric, device, message string
	value                        float64
	at                           time.Time
}

type alertState struct {
	observedAt    time.Time
	observedValue float64
	active        Severity
	pending       Severity
	pendingCount  int
	missingCount  int
	alert         Alert
}

type AlertTracker struct {
	config        AlertConfig
	processLimit  int
	processMaxAge time.Duration
	states        map[string]*alertState
	events        []AlertEvent
}

func NewAlertTracker(config AlertConfig, processes ProcessConfig) AlertTracker {
	return AlertTracker{
		config:        config,
		processLimit:  processes.MaxDisplayed,
		processMaxAge: time.Duration(processes.MaxSampleAge),
		states:        make(map[string]*alertState),
	}
}

func (t *AlertTracker) Update(dashboard Dashboard, thresholds map[string]Threshold, at time.Time) {
	seen := make(map[string]bool)
	for _, observation := range dashboardObservations(dashboard, t.processLimit, at, t.processMaxAge) {
		threshold, enabled := thresholds[observation.metric]
		if !enabled || math.IsNaN(observation.value) || math.IsInf(observation.value, 0) {
			continue
		}
		if observation.metric == "process.cpuPercent" && !freshProcessCPU(observation.at, at, t.processMaxAge) {
			continue
		}

		seen[observation.key] = true
		state := t.states[observation.key]
		if state == nil {
			state = &alertState{}
			t.states[observation.key] = state
		}
		state.missingCount = 0
		state.alert.Unavailable = false
		if !observation.at.IsZero() {
			if observation.at.Before(state.observedAt) {
				state.pending = state.active
				state.pendingCount = 0
				state.alert.Unavailable = true
				continue
			}
			if observation.at.Equal(state.observedAt) {
				if observation.value != state.observedValue {
					state.pending = state.active
					state.pendingCount = 0
					state.alert.Unavailable = true
				}
				continue
			}
			state.observedAt = observation.at
			state.observedValue = observation.value
		}

		target := classifyWithHysteresis(observation.value, threshold, state.active,
			t.config.HysteresisPercent)
		if target == state.active {
			state.pending = target
			state.pendingCount = 0
		} else {
			sameDirection := state.pendingCount > 0 &&
				(target > state.active) == (state.pending > state.active)
			if !sameDirection {
				state.pending = target
				state.pendingCount = 1
			} else {
				state.pendingCount++
				// Every sample in an upward streak supports at least its
				// lowest severity; every downward sample supports at most
				// its highest. This keeps noisy adjacent bands from
				// resetting a continuously unhealthy or recovering run.
				if target > state.active && target < state.pending {
					state.pending = target
				}
				if target < state.active && target > state.pending {
					state.pending = target
				}
			}
		}

		required := t.config.SamplesToRaise
		if state.pending < state.active {
			required = t.config.SamplesToClear
		}
		if state.pending != state.active && state.pendingCount >= required {
			previous := state.active
			state.active = state.pending
			state.pendingCount = 0
			if previous >= t.minimumSeverity() && state.active < t.minimumSeverity() {
				ended := state.alert
				ended.RecoveryValue = reading(observation.value)
				t.archive(ended, at, "recovered")
			}
			if state.active == SeverityOK {
				state.alert = Alert{}
			} else if previous == SeverityOK ||
				(previous < t.minimumSeverity() && state.active >= t.minimumSeverity()) {
				state.alert = Alert{
					Since: at, TriggerValue: reading(observation.value),
					TriggerThreshold: thresholdFor(threshold, state.active),
				}
			}
		}
		if state.active != SeverityOK {
			state.alert.Key = observation.key
			state.alert.Metric = observation.metric
			state.alert.Device = observation.device
			state.alert.Severity = state.active
			state.alert.Value = observation.value
			state.alert.Threshold = thresholdFor(threshold, state.active)
			state.alert.Message = observation.message
			if !state.alert.PeakValue.OK || observation.value > state.alert.PeakValue.Value {
				state.alert.PeakValue = reading(observation.value)
				state.alert.PeakAt = at
				if !observation.at.IsZero() {
					state.alert.PeakAt = observation.at
				}
			}
		}
	}

	keys := make([]string, 0, len(t.states))
	for key := range t.states {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		state := t.states[key]
		if seen[key] {
			continue
		}
		state.missingCount++
		state.pending = state.active
		state.pendingCount = 0
		state.alert.Unavailable = true
		if state.missingCount >= t.config.SamplesToClear {
			if state.active >= t.minimumSeverity() {
				t.archive(state.alert, at, "no longer observed")
			}
			delete(t.states, key)
		}
	}
}

// Interrupt breaks consecutive-sample runs without declaring recovery.
func (t *AlertTracker) Interrupt() {
	for _, state := range t.states {
		state.pending = state.active
		state.pendingCount = 0
		state.missingCount = 0
	}
}

func (t AlertTracker) minimumSeverity() Severity {
	if t.config.ShowCareful {
		return SeverityCareful
	}
	return SeverityWarning
}

func (t AlertTracker) Visible() []Alert {
	var alerts []Alert
	for _, alert := range t.Active() {
		if alert.Severity >= t.minimumSeverity() {
			alerts = append(alerts, alert)
		}
	}
	return alerts
}

func (t *AlertTracker) archive(alert Alert, at time.Time, outcome string) {
	if t.config.MaxHistory == 0 {
		return
	}
	t.events = append([]AlertEvent{{Alert: alert, EndedAt: at, Outcome: outcome}}, t.events...)
	if len(t.events) > t.config.MaxHistory {
		t.events = t.events[:t.config.MaxHistory]
	}
}

func (t *AlertTracker) Active() []Alert {
	alerts := make([]Alert, 0, len(t.states))
	for _, state := range t.states {
		if state.active != SeverityOK {
			alerts = append(alerts, state.alert)
		}
	}
	sort.Slice(alerts, func(i, j int) bool {
		if alerts[i].Severity != alerts[j].Severity {
			return alerts[i].Severity > alerts[j].Severity
		}
		return alerts[i].Key < alerts[j].Key
	})

	return alerts
}

func classify(value float64, threshold Threshold) Severity {
	switch {
	case value >= threshold.Critical:
		return SeverityCritical
	case value >= threshold.Warning:
		return SeverityWarning
	case value >= threshold.Careful:
		return SeverityCareful
	default:
		return SeverityOK
	}
}

func classifyWithHysteresis(value float64, threshold Threshold, active Severity, hysteresis float64) Severity {
	if active != SeverityOK {
		exit := thresholdFor(threshold, active) * (1 - hysteresis/100)
		if value >= exit {
			normal := classify(value, threshold)
			if normal < active {
				return active
			}
			return normal
		}
	}

	return classify(value, threshold)
}

func thresholdFor(threshold Threshold, severity Severity) float64 {
	switch severity {
	case SeverityCritical:
		return threshold.Critical
	case SeverityWarning:
		return threshold.Warning
	default:
		return threshold.Careful
	}
}

func dashboardObservations(d Dashboard, processLimit int, at time.Time, processMaxAge time.Duration) []observation {
	var observations []observation
	add := func(key, metric, device, message string, reading Reading) {
		if reading.OK {
			observations = append(observations, observation{
				key: key, metric: metric, device: device, message: message, value: reading.Value,
			})
		}
	}

	if total := totalCPUUsage(d.CPU); total.OK {
		add("cpu.total", "cpu.totalPercent", "", "Sustained CPU utilization is high.",
			total)
	}
	add("cpu.temperature", "cpu.temperatureC", "", "Check CPU load and cooling.",
		d.CPU.PackageTempC)
	add("memory.used", "memory.usedPercent", "", "Inspect memory-intensive processes.",
		d.Memory.UsedPercent)
	for _, class := range d.CPU.Classes {
		add("cpu.class."+class.Name, "cpu.classPercent", "CPU "+class.Name,
			"Core-class utilization is sustained.", totalCPUUsage(CPU{UsageIdle: class.UsageIdle}))
	}

	for _, gpu := range d.GPUs {
		for _, engine := range gpu.Engines {
			add(fmt.Sprintf("gpu.%s.engine.%s", gpu.ID, engine.Name), "gpu.utilizationPercent",
				"GPU "+gpu.ID+" / "+engine.Name, "High utilization can be expected during inference; check workload demand.", engine.Usage)
		}
		add("gpu."+gpu.ID+".temperature", "gpu.temperatureC", "GPU "+gpu.ID,
			"Check GPU load and cooling.", gpu.TempC)
		add("gpu."+gpu.ID+".vram", "gpu.vramPercent", "GPU "+gpu.ID,
			"Dedicated GPU memory usage is high.", usedPercent(gpu.VRAMUsedBytes, gpu.VRAMTotalBytes))
		for _, process := range gpu.Processes[:min(len(gpu.Processes), processLimit)] {
			add("gpu."+gpu.ID+".process."+process.PID, "gpu.processPercent",
				"GPU "+gpu.ID+" / "+process.Command, "GPU process utilization is sustained.", process.UsagePct)
		}
	}
	add("npu.utilization", "npu.utilizationPercent", "NPU",
		"NPU utilization is sustained.", d.NPU.Utilization)
	add("npu.temperature", "npu.temperatureC", "NPU",
		"Check NPU load and cooling.", d.NPU.TempC)

	for _, network := range d.Network {
		for _, spec := range networkChartSpecs() {
			metric := thresholdMetric(spec.Metric)
			if !supportedThresholds[metric] {
				continue
			}
			value := network.Metrics[spec.Metric]
			if value.OK {
				observations = append(observations, observation{
					key: "network." + network.Key + "." + spec.Metric, metric: metric,
					device:  network.label() + " / " + spec.Title,
					message: "Inspect interface traffic, link capacity and packet errors; thresholds are diagnostic.",
					value:   value.Value, at: value.At,
				})
			}
		}
	}
	for _, storage := range d.Storage {
		for _, spec := range storage.specs() {
			value := storage.Metrics[spec.Metric]
			if value.OK {
				message := "Filesystem capacity is running low; inspect data, logs and retention."
				if spec.Metric == "storage.inodesPercent" {
					message = "Inodes are running low; many small files can prevent writes despite free bytes."
				} else if storage.Kind == "diskio" {
					message = "Storage I/O exceeds a configured diagnostic threshold; compare with workload needs and device capabilities."
				}
				observations = append(observations, observation{
					key: "storage." + storage.Key + "." + spec.Metric, metric: spec.Metric,
					device:  storage.label() + " / " + spec.Title,
					message: message, value: value.Value, at: value.At,
				})
			}
		}
	}
	for _, process := range processAlertCandidates(d, processLimit, at, processMaxAge) {
		total := processTotalCPU(process.CPUPercent, d.Platform.LogicalCPUs)
		if total.OK {
			observations = append(observations, observation{
				key: "process." + process.PID, metric: "process.cpuPercent",
				device: process.Command + " (PID " + process.PID + ")", value: total.Value, at: process.CPUAt,
				message: "Process CPU is a share of total host CPU capacity (100%). High utilization may be expected; inspect the workload.",
			})
		}
	}

	return observations
}

func currentProcesses(d Dashboard, at time.Time, maxAge time.Duration) []Process {
	processes := make([]Process, 0, len(d.Processes))
	for _, process := range d.Processes {
		if !expiredProcessCPU(process.CPUAt, at, maxAge) {
			processes = append(processes, process)
		}
	}
	return processes
}

func processAlertCandidates(d Dashboard, limit int, at time.Time, maxAge time.Duration) []Process {
	processes := currentProcesses(d, at, maxAge)
	return processes[:min(len(processes), max(0, limit))]
}

func expiredProcessCPU(measuredAt, now time.Time, maxAge time.Duration) bool {
	return !measuredAt.IsZero() && now.Sub(measuredAt) > maxAge
}

func processTimestampIssue(measuredAt, now time.Time, maxAge time.Duration) string {
	switch {
	case measuredAt.IsZero():
		return "measurement timestamp missing"
	case measuredAt.After(now):
		return "measurement timestamp is in the future"
	case expiredProcessCPU(measuredAt, now, maxAge):
		return fmt.Sprintf("measurement is older than %s", maxAge)
	default:
		return ""
	}
}

func freshProcessCPU(measuredAt, now time.Time, maxAge time.Duration) bool {
	return processTimestampIssue(measuredAt, now, maxAge) == ""
}

func totalCPUUsage(cpu CPU) Reading {
	if !cpu.UsageIdle.OK || math.IsNaN(cpu.UsageIdle.Value) || math.IsInf(cpu.UsageIdle.Value, 0) {
		return Reading{}
	}

	return reading(math.Max(0, math.Min(100, 100-cpu.UsageIdle.Value)))
}
