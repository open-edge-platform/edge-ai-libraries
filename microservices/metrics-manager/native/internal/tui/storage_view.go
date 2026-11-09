// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"fmt"
	"slices"
	"strings"
	"time"
)

func storageChartSpecs() []ChartSpec {
	return []ChartSpec{
		fixedChart("storage.usedPercent", "Space used", "%", 0, 100),
		fixedChart("storage.inodesPercent", "Inodes used", "%", 0, 100),
		{Metric: "storage.freeGiB", Title: "Free space", Unit: "GiB", Min: floatPointer(0)},
		{Metric: "storage.readMiBps", Title: "Read transfer", Unit: "MiB/s", Min: floatPointer(0)},
		{Metric: "storage.writeMiBps", Title: "Write transfer", Unit: "MiB/s", Min: floatPointer(0)},
		{Metric: "storage.readIOPS", Title: "Read IOPS", Unit: "IOPS", Min: floatPointer(0)},
		{Metric: "storage.writeIOPS", Title: "Write IOPS", Unit: "IOPS", Min: floatPointer(0)},
		{Metric: "storage.readAwaitMs", Title: "Read await", Unit: "ms", Min: floatPointer(0)},
		{Metric: "storage.writeAwaitMs", Title: "Write await", Unit: "ms", Min: floatPointer(0)},
		{Metric: "storage.busyPercent", Title: "I/O busy time", Unit: "%", Min: floatPointer(0)},
		{Metric: "storage.queueDepth", Title: "Average queue depth", Unit: "requests", Min: floatPointer(0)},
		{Metric: "storage.inProgress", Title: "I/O in progress", Unit: "requests", Min: floatPointer(0)},
	}
}

func (s StorageResource) specs() []ChartSpec {
	specs := storageChartSpecs()
	if s.Kind == "disk" {
		return specs[:3]
	}
	return specs[3:]
}

func (m Model) storageSection(s StorageResource) string {
	var b strings.Builder
	b.WriteString(headingStyle.Render(sanitize(s.label(), 160)) + "\n")
	if s.Kind == "disk" {
		b.WriteString(field("device / fs", sanitize(s.Device+" / "+s.Filesystem, 120)))
		for _, metric := range []string{"storage.totalGiB", "storage.usedGiB"} {
			value := s.Metrics[metric]
			label := strings.TrimSuffix(strings.TrimPrefix(metric, "storage."), "GiB")
			text := unavailable
			if value.OK {
				text = fmt.Sprintf("%.2f GiB", value.Value)
			}
			b.WriteString(field(label, text))
		}
	}
	var reasons []string
	for _, spec := range s.specs() {
		value := s.Metrics[spec.Metric]
		text := m.thresholdValue(spec.Metric, value.Reading, func(r Reading) string {
			if text, missing := placeholder(r); missing {
				return text
			}
			return fmt.Sprintf("%.2f %s", r.Value, spec.Unit)
		})
		b.WriteString(field(spec.Title+" ", text))
		if value.Reason != "" && !slices.Contains(reasons, value.Reason) {
			reasons = append(reasons, value.Reason)
		}
	}
	if len(reasons) > 0 {
		b.WriteString(field("data", strings.Join(reasons, "; ")))
	}
	if s.Kind == "diskio" {
		b.WriteString("Busy time is not % of maximum SSD/NVMe throughput.\n")
	}
	return b.String()
}

func (m Model) storageIssues() []string {
	var issues []string
	maxAge, _ := time.ParseDuration(m.config.Storage.MaxSampleAge) // validated at startup
	for _, resource := range m.dash.Storage {
		for _, spec := range resource.specs() {
			if _, enabled := m.config.Thresholds[spec.Metric]; !enabled {
				continue
			}
			value := storageFresh(resource.Metrics[spec.Metric], m.now(), maxAge)
			if !value.OK {
				issues = append(issues, sanitize(resource.label(), 160)+" / "+spec.Title+": "+value.Reason)
			}
		}
	}
	if m.dash.StorageLimited {
		issues = append(issues, "Resource limit reached: only admitted filesystems/devices are assessed; adjust storage filters or limits.")
	}
	if m.storageDataSeen && len(m.dash.Storage) == 0 {
		issues = append(issues, "Previously observed storage data is unavailable; check disk/diskio collection and filters.")
	}
	return issues
}

func (m *Model) expireStorage(at time.Time) {
	maxAge, _ := time.ParseDuration(m.config.Storage.MaxSampleAge) // validated at startup
	for _, resource := range m.dash.Storage {
		for metric, value := range resource.Metrics {
			current := storageFresh(value, at, maxAge)
			resource.Metrics[metric] = current
			if !current.OK {
				if series := m.history.series["storage."+resource.Key+"."+metric]; series != nil {
					series.Available = false
				}
			}
		}
	}
}
