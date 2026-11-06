// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"maps"
	"slices"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

type StorageConfig struct {
	MountPoints       []string `json:"mountPoints"`
	Devices           []string `json:"devices"`
	IgnoreFilesystems []string `json:"ignoreFilesystems"`
	MaxFilesystems    int      `json:"maxFilesystems"`
	MaxDevices        int      `json:"maxDevices"`
	MaxSampleAge      string   `json:"maxSampleAge"`
}

func (c StorageConfig) validate() error {
	if c.MaxFilesystems < 1 || c.MaxFilesystems > 32 || c.MaxDevices < 1 || c.MaxDevices > 32 {
		return fmt.Errorf("storage.maxFilesystems and storage.maxDevices must be between 1 and 32")
	}
	age, err := time.ParseDuration(c.MaxSampleAge)
	if err != nil || age < time.Second || age > 5*time.Minute {
		return fmt.Errorf("storage.maxSampleAge must be a duration between 1s and 5m")
	}
	for _, list := range []struct {
		name   string
		values []string
	}{
		{"mountPoints", c.MountPoints}, {"devices", c.Devices}, {"ignoreFilesystems", c.IgnoreFilesystems},
	} {
		if len(list.values) > 32 {
			return fmt.Errorf("storage.%s accepts at most 32 entries", list.name)
		}
		seen := make(map[string]bool)
		for _, name := range list.values {
			if name == "" || len(name) > 256 || strings.TrimSpace(name) != name ||
				strings.IndexFunc(name, unicode.IsControl) >= 0 || seen[name] ||
				(list.name == "mountPoints" && !strings.HasPrefix(name, "/")) {
				return fmt.Errorf("storage.%s requires unique nonempty names without control characters; mount points must be absolute", list.name)
			}
			seen[name] = true
		}
	}
	return nil
}

type StorageResource struct {
	Key, Kind, Name, Host, Device, Filesystem string
	Metrics                                   map[string]timedReading
}

func (s StorageResource) label() string {
	prefix := "Storage I/O "
	if s.Kind == "disk" {
		prefix = "Filesystem "
	}
	label := prefix + s.Name
	if s.Host != "" {
		label += " @ " + s.Host
	}
	return label
}

type storageMetric struct {
	field, metric string
	scale         float64
	counter       bool
}

var filesystemFields = []storageMetric{
	{"used_percent", "storage.usedPercent", 1, false},
	{"inodes_used_percent", "storage.inodesPercent", 1, false},
	{"free", "storage.freeGiB", 1 << 30, false},
	{"total", "storage.totalGiB", 1 << 30, false},
	{"used", "storage.usedGiB", 1 << 30, false},
	{"inodes_total", "storage.inodesTotal", 1, false},
}

var storageIOFields = []storageMetric{
	{"read_bytes", "storage.readMiBps", 1 << 20, true},
	{"write_bytes", "storage.writeMiBps", 1 << 20, true},
	{"reads", "storage.readIOPS", 1, true},
	{"writes", "storage.writeIOPS", 1, true},
	{"read_time", "storage.readTimeRate", 1, true},
	{"write_time", "storage.writeTimeRate", 1, true},
	{"io_time", "storage.busyPercent", 10, true},
	{"weighted_io_time", "storage.queueDepth", 1000, true},
	{"iops_in_progress", "storage.inProgress", 1, false},
}

type storageState struct {
	counters map[string]*counterRateState
	gauges   map[string]timedReading
}

type storageTracker struct {
	states map[string]*storageState
}

func storageFresh(value timedReading, now time.Time, maxAge time.Duration) timedReading {
	switch {
	case !value.OK:
		return value
	case !finiteReading(value.Reading) || value.Value < 0:
		value.Reason = "measurement missing or invalid"
	case value.At.IsZero():
		value.Reason = "measurement timestamp missing"
	case value.At.After(now):
		value.Reason = "measurement timestamp is in the future"
	case now.Sub(value.At) > maxAge:
		value.Reason = "measurement is stale"
	default:
		return value
	}
	value.Reading = Reading{}
	return value
}

func (t *storageTracker) update(samples []promtext.Sample, now time.Time, config StorageConfig) ([]StorageResource, bool) {
	type grouped struct {
		resource  StorageResource
		fields    map[string]promtext.Sample
		conflicts map[string]bool
	}
	groups := make(map[string]*grouped)
	for _, sample := range samples {
		kind, field, found := strings.Cut(sample.Name, "_")
		if !found || (kind != "disk" && kind != "diskio") {
			continue
		}
		fields := storageIOFields
		if kind == "disk" {
			fields = filesystemFields
		}
		if !slices.ContainsFunc(fields, func(f storageMetric) bool { return f.field == field }) {
			continue
		}
		name, host := sample.Labels["name"], sample.Labels["host"]
		device, filesystem := "", ""
		if kind == "disk" {
			name, device, filesystem = sample.Labels["path"], sample.Labels["device"], sample.Labels["fstype"]
			if slices.Contains(config.IgnoreFilesystems, filesystem) ||
				(len(config.MountPoints) > 0 && !slices.Contains(config.MountPoints, name)) {
				continue
			}
		} else if len(config.Devices) > 0 {
			if !slices.Contains(config.Devices, name) {
				continue
			}
		} else if strings.HasPrefix(name, "loop") || strings.HasPrefix(name, "ram") {
			continue
		}
		if name == "" {
			continue
		}
		key := fmt.Sprintf("%q/%q/%q/%q/%q/%q/%q", kind, host, name, device, filesystem,
			sample.Labels["wwid"], sample.Labels["serial"])
		g := groups[key]
		if g == nil {
			g = &grouped{
				resource: StorageResource{Key: key, Kind: kind, Name: name, Host: host, Device: device, Filesystem: filesystem},
				fields:   make(map[string]promtext.Sample), conflicts: make(map[string]bool),
			}
			groups[key] = g
		}
		if previous, exists := g.fields[field]; exists {
			if sample.TimestampMS < previous.TimestampMS {
				continue
			}
			if sample.TimestampMS == previous.TimestampMS {
				if sample.Value != previous.Value || !maps.Equal(sample.Labels, previous.Labels) {
					g.conflicts[field] = true
				}
			} else {
				g.conflicts[field] = false
			}
		}
		g.fields[field] = sample
	}
	keys := make([]string, 0, len(groups))
	for key := range groups {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	previous := t.states
	t.states = make(map[string]*storageState)
	maxAge, _ := time.ParseDuration(config.MaxSampleAge) // validated at startup
	var resources []StorageResource
	counts := make(map[string]int)
	limited := false
	for _, key := range keys {
		g := groups[key]
		limit, fields := config.MaxDevices, storageIOFields
		if g.resource.Kind == "disk" {
			limit, fields = config.MaxFilesystems, filesystemFields
		}
		if counts[g.resource.Kind] >= limit {
			limited = true
			continue
		}
		counts[g.resource.Kind]++
		state := previous[key]
		if state == nil {
			state = &storageState{counters: make(map[string]*counterRateState), gauges: make(map[string]timedReading)}
		}
		t.states[key] = state
		resource := g.resource
		resource.Metrics = make(map[string]timedReading)
		for _, f := range fields {
			sample, present := g.fields[f.field]
			valid := present && !g.conflicts[f.field]
			value := Reading{Value: sample.Value, OK: valid}
			var result timedReading
			if f.counter {
				counter := state.counters[f.field]
				if counter == nil {
					counter = &counterRateState{}
					state.counters[f.field] = counter
				}
				result = counter.update(value, sample.TimestampMS, now, maxAge)
			} else {
				result = timedReading{Reading: value}
				if sample.TimestampMS > 0 {
					result.At = time.UnixMilli(sample.TimestampMS)
				}
				if !valid {
					result.Reason = "measurement missing or invalid"
				}
				result = storageFresh(result, now, maxAge)
				last := state.gauges[f.field]
				if result.OK && !last.At.IsZero() {
					if result.At.Before(last.At) {
						result = timedReading{Reason: "out-of-order measurement"}
					} else if result.At.Equal(last.At) && (!last.OK || result.Value != last.Value) {
						result = timedReading{At: result.At, Reason: "conflicting values at one timestamp"}
					}
				}
				// Rejected future timestamps must not prevent later valid samples.
				if result.OK || (!last.At.IsZero() && result.At.Equal(last.At)) {
					state.gauges[f.field] = result
				}
			}
			if g.conflicts[f.field] {
				result.Reason = "ambiguous storage measurement labels or values"
			}
			result.Reading = scaleReading(result.Reading, f.scale)
			if result.OK && strings.HasSuffix(f.metric, "Percent") && g.resource.Kind == "disk" && result.Value > 100 {
				result = timedReading{Reason: "filesystem percentage outside 0..100"}
			}
			resource.Metrics[f.metric] = result
		}
		if resource.Kind == "disk" {
			capacity := resource.Metrics["storage.totalGiB"]
			used := resource.Metrics["storage.usedPercent"]
			if !capacity.OK || capacity.Value == 0 || !capacity.At.Equal(used.At) {
				resource.Metrics["storage.usedPercent"] = timedReading{Reason: "filesystem capacity unavailable or timestamps differ"}
			}
			total := resource.Metrics["storage.inodesTotal"]
			inodes := resource.Metrics["storage.inodesPercent"]
			if !total.OK || total.Value == 0 || !total.At.Equal(inodes.At) {
				resource.Metrics["storage.inodesPercent"] = timedReading{Reason: "inode capacity unavailable or timestamps differ"}
			}
		} else {
			for _, direction := range []string{"read", "write"} {
				numerator := resource.Metrics["storage."+direction+"TimeRate"]
				denominator := resource.Metrics["storage."+direction+"IOPS"]
				result := timedReading{Reason: "I/O latency needs matching counter intervals"}
				if numerator.OK && denominator.OK && numerator.At.Equal(denominator.At) && numerator.From.Equal(denominator.From) {
					if denominator.Value > 0 {
						result = timedReading{Reading: reading(numerator.Value / denominator.Value), At: numerator.At, From: numerator.From}
						if !finiteReading(result.Reading) {
							result = timedReading{Reason: "I/O latency outside supported range"}
						}
					} else {
						result.Reason = "no completed " + direction + " I/O in interval"
					}
				}
				resource.Metrics["storage."+direction+"AwaitMs"] = result
			}
		}
		resources = append(resources, resource)
	}
	return resources, limited
}
