// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package gpu

import (
	"encoding/json"
	"sort"
	"strconv"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/lineproto"
)

// MeasurementClient carries per-process GPU usage.
//
// Each point is tagged with a process identifier, and every restart of a
// workload allocates a fresh one, so an uncapped stream grows the number of
// time series without bound for as long as a scrape runs. That is why
// emission is opt-in through WithClientStats and why the option takes a limit
// rather than a plain flag: what reaches the endpoint is the handful of
// processes actually using the device, not a record of every process that ever
// touched it.
const MeasurementClient = "gpu_client"

// clientStats is one DRM client entry of qmassa's clis_stats array.
//
// The upstream structure also carries "cmdline", the full command line of the
// process. It is deliberately not decoded: arguments routinely hold access
// tokens, connection strings and file paths, none of which belong in a
// telemetry stream. The process name in "comm" identifies a workload well
// enough for a dashboard.
type clientStats struct {
	// Clients holds (drm_minor, client_id) pairs. Only its presence matters
	// here; the owning device already establishes which GPU is involved.
	Clients [][]json.Number `json:"clients"`

	PID  json.Number `json:"pid"`
	Comm string      `json:"comm"`

	// CPUUsage, EngUsage and MemInfo are rolling windows, as everywhere else
	// in the qmassa schema, so only the final entry is current.
	CPUUsage []json.Number            `json:"cpu_usage"`
	EngUsage map[string][]json.Number `json:"eng_usage"`
	MemInfo  []map[string]json.Number `json:"mem_info"`

	IsActive bool `json:"is_active"`
}

// clientTotals accumulates every DRM client belonging to one process.
type clientTotals struct {
	pid    string
	comm   string
	cpu    float64
	engine map[string]float64
	memory map[string]float64
	active bool
}

// appendClients emits one point per process using the device.
//
// A process may hold several DRM clients on the same GPU, which would produce
// repeated points carrying identical tags, so the entries are summed per
// process. That mirrors qmassa's own clients_stats_by_pid, meaning the
// dashboard shows the same totals as the upstream tool.
func appendClients(dev device, limit int, emit emitFunc) {
	totals := make(map[string]*clientTotals)

	for _, cli := range dev.ClisStats {
		pid := cli.PID.String()
		if pid == "" || len(cli.Clients) == 0 {
			continue
		}

		total, ok := totals[pid]
		if !ok {
			total = &clientTotals{
				pid:    pid,
				comm:   cli.Comm,
				engine: make(map[string]float64),
				memory: make(map[string]float64),
			}
			totals[pid] = total
		}

		if cpu, ok := lastFloat(cli.CPUUsage); ok {
			total.cpu += cpu
		}
		for engine, samples := range cli.EngUsage {
			if usage, ok := lastFloat(samples); ok {
				total.engine[engine] += usage
			}
		}
		if mem := lastMap(cli.MemInfo); mem != nil {
			for key, raw := range mem {
				if value, err := raw.Float64(); err == nil {
					total.memory[key] += value
				}
			}
		}
		total.active = total.active || cli.IsActive
	}

	// Points are ordered by process identifier so repeated samples of an
	// unchanged system produce byte-identical output.
	pids := sortedKeys(totals)
	sortedPIDs(pids)

	if limit > 0 && len(pids) > limit {
		pids = busiest(pids, totals, limit)
	}

	for _, pid := range pids {
		total := totals[pid]

		// Summing rewrites the numbers, so the literal-preserving path used
		// for device counters does not apply and plain floats are correct.
		fields := []lineproto.Field{
			lineproto.IntField("active", boolToInt(total.active)),
			lineproto.FloatField("cpu", total.cpu),
		}
		for _, engine := range sortedKeys(total.engine) {
			fields = append(fields, lineproto.FloatField("engine_"+engine, total.engine[engine]))
		}
		for _, key := range sortedKeys(total.memory) {
			fields = append(fields, lineproto.FloatField(key+"_bytes", total.memory[key]))
		}

		emit(MeasurementClient,
			[]lineproto.Tag{{Key: "pid", Value: total.pid}, {Key: "comm", Value: total.comm}},
			fields)
	}
}

// busiest returns the limit processes using the most of the GPU, back in
// process-identifier order.
//
// Ranking happens on a copy that is already sorted by pid, and the sort is
// stable, so two processes with equal usage are always dropped in the same
// order. Without that, an idle machine where everything scores zero would
// shuffle which processes are reported from one sample to the next.
func busiest(pids []string, totals map[string]*clientTotals, limit int) []string {
	ranked := make([]string, len(pids))
	copy(ranked, pids)

	sort.SliceStable(ranked, func(i, j int) bool {
		return usageScore(totals[ranked[i]]) > usageScore(totals[ranked[j]])
	})

	kept := ranked[:limit]
	sortedPIDs(kept)

	return kept
}

// usageScore ranks a process by how much of the device it is using.
//
// Engine usage is what the question "which process is using the GPU" means, so
// it dominates; the CPU time qmassa reports alongside it only breaks ties
// between processes that are not touching the engines at all.
func usageScore(total *clientTotals) float64 {
	score := 0.0
	for _, usage := range total.engine {
		score += usage
	}

	return score*1000 + total.cpu
}

// lastFloat returns the most recent sample of a rolling window.
func lastFloat(samples []json.Number) (float64, bool) {
	if len(samples) == 0 {
		return 0, false
	}
	value, err := samples[len(samples)-1].Float64()
	if err != nil {
		return 0, false
	}
	return value, true
}

func boolToInt(value bool) int64 {
	if value {
		return 1
	}
	return 0
}

// sortedPIDs keeps numeric process identifiers in numeric rather than
// lexicographic order, so 9 sorts before 10.
func sortedPIDs(pids []string) {
	sort.Slice(pids, func(i, j int) bool {
		left, leftErr := strconv.Atoi(pids[i])
		right, rightErr := strconv.Atoi(pids[j])
		if leftErr == nil && rightErr == nil {
			return left < right
		}
		return pids[i] < pids[j]
	})
}
