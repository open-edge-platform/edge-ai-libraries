// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"slices"
	"sort"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

type NetworkConfig struct {
	Interfaces    []string           `json:"interfaces"`
	MaxInterfaces int                `json:"maxInterfaces"`
	MaxSampleAge  string             `json:"maxSampleAge"`
	SpeedMbps     map[string]float64 `json:"speedMbps"`
}

type NetworkInterface struct {
	Key, Name, Host string
	SpeedMbps       Reading
	ReceivedBytes   Reading
	SentBytes       Reading
	Metrics         map[string]timedReading
}

func (n NetworkInterface) label() string {
	label := "Network " + n.Name
	if n.Host != "" {
		label += " @ " + n.Host
	}
	return label
}

type networkTracker struct {
	states map[string]map[string]*counterRateState
}

var networkCounters = []struct {
	field, metric string
	scale         float64
}{
	{"bytes_recv", "network.rxMiBps", 1 << 20},
	{"bytes_sent", "network.txMiBps", 1 << 20},
	{"packets_recv", "network.rxPacketsPerSecond", 1},
	{"packets_sent", "network.txPacketsPerSecond", 1},
	{"err_in", "network.rxErrorsPerSecond", 1},
	{"err_out", "network.txErrorsPerSecond", 1},
	{"drop_in", "network.rxDropsPerSecond", 1},
	{"drop_out", "network.txDropsPerSecond", 1},
}

func (t *networkTracker) update(samples []promtext.Sample, now time.Time, config NetworkConfig) ([]NetworkInterface, bool) {
	allowedFields := map[string]bool{"net_speed": true}
	for _, counter := range networkCounters {
		allowedFields["net_"+counter.field] = true
	}
	type deviceSamples struct {
		name, host string
		fields     map[string]promtext.Sample
		conflicts  map[string]bool
	}
	devices := make(map[string]*deviceSamples)
	for _, sample := range samples {
		name, host := sample.Labels["interface"], sample.Labels["host"]
		if !allowedFields[sample.Name] || name == "" ||
			(len(config.Interfaces) > 0 && !slices.Contains(config.Interfaces, name)) {
			continue
		}
		key := fmt.Sprintf("%q/%q", host, name)
		device := devices[key]
		if device == nil {
			device = &deviceSamples{
				name: name, host: host, fields: make(map[string]promtext.Sample), conflicts: make(map[string]bool),
			}
			devices[key] = device
		}
		if previous, exists := device.fields[sample.Name]; exists {
			// Ambiguous label sets must not silently select an arbitrary counter.
			if previous.Value != sample.Value || previous.TimestampMS != sample.TimestampMS {
				sample.TimestampMS = 0
				device.conflicts[sample.Name] = true
			}
		}
		device.fields[sample.Name] = sample
	}
	keys := make([]string, 0, len(devices))
	for key := range devices {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	limited := len(keys) > config.MaxInterfaces
	keys = keys[:min(len(keys), config.MaxInterfaces)]
	previous := t.states
	t.states = make(map[string]map[string]*counterRateState, len(keys))
	maxAge, _ := time.ParseDuration(config.MaxSampleAge) // validated at startup
	var interfaces []NetworkInterface
	for _, key := range keys {
		device := devices[key]
		states := previous[key]
		if states == nil {
			states = make(map[string]*counterRateState)
		}
		t.states[key] = states
		n := NetworkInterface{
			Key: key, Name: device.name, Host: device.host, Metrics: make(map[string]timedReading),
		}
		if sample, ok := device.fields["net_bytes_recv"]; ok && !device.conflicts[sample.Name] && sample.Value >= 0 && finiteReading(reading(sample.Value)) {
			n.ReceivedBytes = reading(sample.Value)
		}
		if sample, ok := device.fields["net_bytes_sent"]; ok && !device.conflicts[sample.Name] && sample.Value >= 0 && finiteReading(reading(sample.Value)) {
			n.SentBytes = reading(sample.Value)
		}
		speed := device.fields["net_speed"]
		if speed.Value > 0 && finiteReading(reading(speed.Value)) && speed.TimestampMS > 0 &&
			!time.UnixMilli(speed.TimestampMS).After(now) && now.Sub(time.UnixMilli(speed.TimestampMS)) <= maxAge {
			n.SpeedMbps = reading(speed.Value)
		}
		if override, ok := config.SpeedMbps[n.Name]; ok {
			n.SpeedMbps = reading(override)
		}
		for _, counter := range networkCounters {
			state := states[counter.field]
			if state == nil {
				state = &counterRateState{}
				states[counter.field] = state
			}
			sample, present := device.fields["net_"+counter.field]
			value := Reading{Value: sample.Value, OK: present}
			result := state.update(value, sample.TimestampMS, now, maxAge)
			if device.conflicts[sample.Name] {
				result.Reason = "ambiguous host/interface counter labels"
			}
			result.Reading = scaleReading(result.Reading, counter.scale)
			n.Metrics[counter.metric] = result
		}
		for _, direction := range []string{"rx", "tx"} {
			result := n.Metrics["network."+direction+"MiBps"]
			_, overridden := config.SpeedMbps[n.Name]
			if !n.SpeedMbps.OK {
				result.Reading = Reading{}
				result.Reason = "link speed unknown; set network.speedMbps if known"
			} else if result.OK && !overridden && speed.TimestampMS != result.At.UnixMilli() {
				result.Reading = Reading{}
				result.Reason = "link speed and counter timestamps differ"
			} else if result.OK {
				result.Reading = reading(result.Value * (1 << 20) * 8 / (n.SpeedMbps.Value * 1e6) * 100)
				if !finiteReading(result.Reading) {
					result.Reading = Reading{}
					result.Reason = "utilization is outside the supported range"
				}
			}
			n.Metrics["network."+direction+"Percent"] = result
		}
		interfaces = append(interfaces, n)
	}
	return interfaces, limited
}

func (m Model) networkSection(n NetworkInterface) string {
	var b strings.Builder
	b.WriteString(headingStyle.Render(sanitize(n.label(), 100)) + "\n")
	speed := "unknown"
	if n.SpeedMbps.OK {
		speed = fmt.Sprintf("%.0f Mbit/s", n.SpeedMbps.Value)
		if _, overridden := m.config.Network.SpeedMbps[n.Name]; overridden {
			speed += " (configured)"
		}
	}
	b.WriteString(field("link capacity", speed))
	format := func(metric, unit string) string {
		value := n.Metrics[metric]
		return m.thresholdValue(metric, value.Reading, func(r Reading) string {
			if text, missing := placeholder(r); missing {
				return text
			}
			return fmt.Sprintf("%.2f%s", r.Value, unit)
		})
	}
	for _, direction := range []string{"rx", "tx"} {
		b.WriteString(field(strings.ToUpper(direction), format("network."+direction+"MiBps", " MiB/s")+
			"   "+format("network."+direction+"Percent", "%")))
		b.WriteString(field(strings.ToUpper(direction)+" packets", format("network."+direction+"PacketsPerSecond", "/s")))
		b.WriteString(field(strings.ToUpper(direction)+" faults", "errors "+format("network."+direction+"ErrorsPerSecond", "/s")+
			"   drops "+format("network."+direction+"DropsPerSecond", "/s")))
	}
	b.WriteString(field("total bytes", "RX "+formatBytes(n.ReceivedBytes)+"   TX "+formatBytes(n.SentBytes)))
	var reasons []string
	var at time.Time
	for _, metric := range networkChartSpecs() {
		value := n.Metrics[metric.Metric]
		if value.Reason != "" && !slices.Contains(reasons, value.Reason) {
			reasons = append(reasons, value.Reason)
		}
		if value.OK && (at.IsZero() || value.At.Before(at)) {
			at = value.At
		}
	}
	status := "waiting for timestamped measurements"
	if !at.IsZero() {
		status = "oldest rate " + formatAge(m.now().Sub(at))
	}
	if len(reasons) > 0 {
		if at.IsZero() {
			status = strings.Join(reasons, "; ")
		} else {
			status += "; " + strings.Join(reasons, "; ")
		}
	}
	b.WriteString(field("rates", status))
	return b.String()
}

func networkChartSpecs() []ChartSpec {
	return []ChartSpec{
		{Metric: "network.rxMiBps", Title: "RX transfer", Unit: "MiB/s", Min: floatPointer(0)},
		{Metric: "network.txMiBps", Title: "TX transfer", Unit: "MiB/s", Min: floatPointer(0)},
		fixedChart("network.rxPercent", "RX link utilization", "%", 0, 100),
		fixedChart("network.txPercent", "TX link utilization", "%", 0, 100),
		{Metric: "network.rxPacketsPerSecond", Title: "RX packets", Unit: "/s", Min: floatPointer(0)},
		{Metric: "network.txPacketsPerSecond", Title: "TX packets", Unit: "/s", Min: floatPointer(0)},
		{Metric: "network.rxErrorsPerSecond", Title: "RX errors", Unit: "/s", Min: floatPointer(0)},
		{Metric: "network.txErrorsPerSecond", Title: "TX errors", Unit: "/s", Min: floatPointer(0)},
		{Metric: "network.rxDropsPerSecond", Title: "RX drops", Unit: "/s", Min: floatPointer(0)},
		{Metric: "network.txDropsPerSecond", Title: "TX drops", Unit: "/s", Min: floatPointer(0)},
	}
}

func floatPointer(value float64) *float64 { return &value }
