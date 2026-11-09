// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

// Reading is a metric value that may be absent.
//
// Absence is a first-class state here rather than a zero value, because the
// measurements this dashboard shows are genuinely optional: a host with no
// discrete GPU, a kernel without the low-power core PMU, an NPU whose memory
// counter the platform does not expose. Rendering a missing reading as 0 would
// assert something false about the hardware.
type Reading struct {
	Value float64
	OK    bool
}

// reading returns an present Reading.
func reading(v float64) Reading { return Reading{Value: v, OK: true} }

// Index provides label-aware lookup over one snapshot of samples.
//
// The exposition is a flat list, but every panel wants "this metric for this
// label set", so the list is bucketed by name once per refresh instead of
// being rescanned by each panel.
type Index struct {
	byName map[string][]promtext.Sample
}

// NewIndex buckets samples by metric name.
func NewIndex(samples []promtext.Sample) *Index {
	byName := make(map[string][]promtext.Sample, len(samples))
	for _, s := range samples {
		byName[s.Name] = append(byName[s.Name], s)
	}

	return &Index{byName: byName}
}

// All returns every sample carrying the given metric name.
func (i *Index) All(name string) []promtext.Sample {
	return i.byName[name]
}

// Value returns the value of the first sample named name whose labels include
// every pair in match.
//
// Labels beyond those in match are ignored, so a caller can select on the one
// label it cares about without having to know that Telegraf also stamps host.
func (i *Index) Value(name string, match map[string]string) Reading {
	sample, ok := i.Sample(name, match)
	return Reading{Value: sample.Value, OK: ok}
}

func (i *Index) Sample(name string, match map[string]string) (promtext.Sample, bool) {
	for _, s := range i.byName[name] {
		if matches(s.Labels, match) {
			return s, true
		}
	}

	return promtext.Sample{}, false
}

func matches(labels, match map[string]string) bool {
	for k, want := range match {
		if labels[k] != want {
			return false
		}
	}

	return true
}

// NamesWithPrefix returns the metric names in this snapshot that start with
// prefix, sorted.
//
// It exists because parts of the exposition are deliberately open-ended: the
// GPU plugin forwards whatever throttle reasons qmassa reports rather than a
// fixed list, so the panel has to discover them instead of hardcoding them.
func (i *Index) NamesWithPrefix(prefix string) []string {
	var names []string
	for name := range i.byName {
		if strings.HasPrefix(name, prefix) {
			names = append(names, name)
		}
	}
	sort.Strings(names)

	return names
}

// LabelValues returns the distinct values of label across every metric whose
// name starts with prefix and whose labels satisfy match, sorted.
//
// This is how the GPUs, their tiles and their engines are discovered, so a
// second GPU or a third tile appears without a code change.
func (i *Index) LabelValues(prefix, label string, match map[string]string) []string {
	seen := make(map[string]struct{})
	for name, samples := range i.byName {
		if !strings.HasPrefix(name, prefix) {
			continue
		}
		for _, s := range samples {
			value := s.Labels[label]
			if value == "" || !matches(s.Labels, match) {
				continue
			}
			seen[value] = struct{}{}
		}
	}

	values := make([]string, 0, len(seen))
	for v := range seen {
		values = append(values, v)
	}
	sort.Strings(values)

	return values
}

// withLabel returns base plus one more label, leaving base untouched so a
// caller can reuse it for sibling lookups.
func withLabel(base map[string]string, key, value string) map[string]string {
	out := make(map[string]string, len(base)+1)
	for k, v := range base {
		out[k] = v
	}
	out[key] = value

	return out
}

// CoreClass is one CPU core class as reported by mm-plugin-cpu.
type CoreClass struct {
	// Name is P, E or LPE.
	Name string

	// Source is how the class was determined: "pmu" when the kernel
	// reported it directly, "heuristic" when it was inferred. Surfacing
	// this lets an operator judge how much to trust the split rather than
	// having to take it on faith.
	Source string

	Cores        Reading
	FrequencyKHz Reading
	UsageUser    Reading
	UsageSystem  Reading
	UsageIdle    Reading
}

// CPU aggregates the processor panel.
type CPU struct {
	UsageUser    Reading
	UsageSystem  Reading
	UsageIdle    Reading
	FrequencyKHz Reading

	// Classes is ordered P, E, LPE, with any unrecognised class after them
	// so the panel does not reshuffle between refreshes.
	Classes []CoreClass

	// PackageTempC is the CPU package temperature, when a coretemp sensor
	// is exposed.
	PackageTempC Reading

	// The rest comes from intel_powerstat, which needs privileges the other
	// CPU readings do not. On a host without the msr module, or with the
	// collector stopped, these are absent and the panel says so rather than
	// showing zeros.
	PackagePowerW Reading
	TDPW          Reading
	BaseFreqMHz   Reading

	// TurboPrimaryMHz and TurboSecondaryMHz are the single-core turbo limits
	// of the two core kinds on a hybrid part, which line up with the P and E
	// rows of the class table.
	TurboPrimaryMHz   Reading
	TurboSecondaryMHz Reading

	UncoreMHz Reading

	// CStates is ordered shallowest first, so the deepest state, which is
	// where an idle machine spends its time, reads last.
	CStates []CState
}

// CState is one idle state, averaged over the logical CPUs that report it.
//
// Averaging is the honest summary for a panel: residency is a per-CPU
// percentage, and a machine with 22 of them cannot show a row each without
// burying everything else.
type CState struct {
	Name      string
	Residency Reading
}

// Memory aggregates the memory panel.
type Memory struct {
	UsedPercent      Reading
	AvailablePercent Reading
	TotalBytes       Reading
	UsedBytes        Reading

	// Bandwidth is what the memory controller is moving, for the whole
	// package. It is not attributable to any one device, and on a machine
	// with an integrated GPU it includes the GPU's traffic.
	ReadGBps  Reading
	WriteGBps Reading
	TotalGBps Reading
}

type RAPLPower struct {
	Domain string
	PowerW Reading
}

// GPUEngine is one engine's share of busy time, in percent.
type GPUEngine struct {
	Name  string
	Usage Reading
}

// GPUTile is one graphics tile.
//
// Meteor Lake exposes two of them with different frequency ranges and
// independent throttle state, so they are kept apart rather than averaged into
// a single figure that would describe neither.
type GPUTile struct {
	Name string

	// ActualMHz is the frequency the tile ran at and RequestedMHz the one
	// the driver asked for. A gap between them is what the throttle reasons
	// explain, which is why both are shown.
	ActualMHz    Reading
	RequestedMHz Reading
	MinMHz       Reading
	MaxMHz       Reading

	// ThrottleReported distinguishes "this host publishes no throttle
	// series" from "nothing is throttling". Showing the first as the second
	// would be an unearned reassurance.
	ThrottleReported bool

	// Throttled is qmassa's own summary flag, kept apart from the specific
	// reasons so the panel can still say something when the cause is set
	// but unnamed.
	Throttled Reading

	// ThrottleReasons are the individual flags currently set, excluding the
	// summary. The set is discovered rather than fixed.
	ThrottleReasons []string
}

// GPU aggregates one Intel GPU.
type GPU struct {
	ID string

	// Driver is the kernel driver the plugin tagged the device with, "i915"
	// or "xe". It decides which counters are meaningful, and is shown so an
	// operator can see why one of them reads as unavailable.
	Driver string

	Engines []GPUEngine
	Tiles   []GPUTile

	// PowerW is the graphics domain alone, PackagePowerW the whole package
	// including the CPU cores. They differ by an order of magnitude on an
	// integrated part, so labelling them apart matters.
	PowerW        Reading
	PackagePowerW Reading

	TempC Reading

	// SharedTotalBytes and SharedUsedBytes describe system memory the GPU
	// can address; VRAM is the dedicated kind, which an integrated GPU
	// reports as zero rather than omitting.
	SharedTotalBytes Reading
	SharedUsedBytes  Reading
	VRAMTotalBytes   Reading
	VRAMUsedBytes    Reading

	// Processes are those currently using the device, busiest first. The
	// collector caps how many it publishes, so this is already a short list.
	Processes []GPUProcess
}

// GPUProcess is one process using a GPU.
type GPUProcess struct {
	PID string

	// Command is the process name. The full command line is deliberately not
	// collected, because arguments routinely carry credentials.
	Command string

	// UsagePct sums the engines, which is what "how much of the GPU is this
	// process using" means to someone looking at the panel. It can exceed
	// 100 when a process keeps several engines busy at once.
	UsagePct Reading

	// MemoryBytes is shared and dedicated memory together, since a process
	// on an integrated part uses one and a process on a discrete part the
	// other.
	MemoryBytes Reading
}

// NPU aggregates the neural accelerator panel.
type NPU struct {
	// Present records whether the host published any NPU series at all, so
	// the panel can be omitted on a machine without one instead of showing
	// a column of dashes.
	Present bool

	Utilization   Reading
	FrequencyHz   Reading
	PowerW        Reading
	TempC         Reading
	BandwidthMBps Reading
	TileConfig    Reading
	MemoryMiB     Reading
	PowerState    Reading

	// MaxFrequencyMHz is the ceiling the driver reports, which is what
	// makes the current frequency mean anything.
	MaxFrequencyMHz Reading
}

// Platform describes the machine itself, as opposed to what it is doing.
type Platform struct {
	Model  string
	Kernel string
	Arch   string

	LogicalCPUs Reading
}

// Process is one row of the process panel.
type Process struct {
	PID string

	// Command is the process name from the kernel. The full command line is
	// never collected, because arguments routinely carry credentials.
	Command string

	Threads     Reading
	User        string
	CPUPercent  Reading
	CPUAt       time.Time
	MemoryBytes Reading
}

// Dashboard is everything the view needs for one refresh.
type Dashboard struct {
	Host           string
	Platform       Platform
	CPU            CPU
	Memory         Memory
	RAPL           []RAPLPower
	GPUs           []GPU
	NPU            NPU
	Network        []NetworkInterface
	NetworkLimited bool
	Storage        []StorageResource
	StorageLimited bool
	Optional       []OptionalPanel

	// Processes are the busiest on the machine, by CPU and by resident
	// memory. The collector caps how many it publishes.
	Processes []Process
}

// classOrder fixes the display order of the known core classes, strongest
// first. Sorting alphabetically would put E before P, which reads oddly.
var classOrder = map[string]int{"P": 0, "E": 1, "LPE": 2}

// BuildDashboard projects one snapshot of samples onto the panels.
//
// Every field is optional. A host without a given measurement yields an absent
// Reading, which the view renders as unavailable rather than as zero.
func BuildDashboard(samples []promtext.Sample) Dashboard {
	idx := NewIndex(samples)
	rapl := buildRAPL(idx)

	return Dashboard{
		Host:      hostOf(samples),
		Platform:  buildPlatform(idx),
		CPU:       buildCPU(idx),
		Memory:    buildMemory(idx),
		RAPL:      rapl,
		GPUs:      buildGPUs(idx),
		NPU:       buildNPU(idx),
		Optional:  buildOptionalPanels(idx, rapl),
		Processes: buildProcesses(idx),
	}
}

func buildRAPL(idx *Index) []RAPLPower {
	var domains []RAPLPower
	for _, sample := range idx.All("rapl_power_power_w") {
		if domain := sample.Labels["domain"]; domain != "" &&
			!math.IsNaN(sample.Value) && !math.IsInf(sample.Value, 0) {
			domains = append(domains, RAPLPower{Domain: domain, PowerW: reading(sample.Value)})
		}
	}
	sort.Slice(domains, func(i, j int) bool { return domains[i].Domain < domains[j].Domain })
	return domains
}

// buildPlatform reads the description the CPU collector publishes.
//
// The facts live in labels rather than in a value, so they are read from the
// label set of the single series that carries them.
func buildPlatform(idx *Index) Platform {
	return Platform{
		Model:       soleValue(idx.LabelValues("platform_", "model", nil)),
		Kernel:      soleValue(idx.LabelValues("platform_", "kernel", nil)),
		Arch:        soleValue(idx.LabelValues("platform_", "arch", nil)),
		LogicalCPUs: idx.Value("platform_logical_cpus", nil),
	}
}

// buildProcesses collects the per-process points into one row each, busiest
// first.
func buildProcesses(idx *Index) []Process {
	pids := idx.LabelValues("process_", "pid", nil)
	if len(pids) == 0 {
		return nil
	}

	processes := make([]Process, 0, len(pids))
	for _, pid := range pids {
		match := map[string]string{"pid": pid}
		cpu, cpuOK := latestProcessCPU(idx, pid)
		var cpuAt time.Time
		if cpu.TimestampMS > 0 {
			cpuAt = time.UnixMilli(cpu.TimestampMS)
		}

		process := Process{
			PID:        pid,
			Command:    soleValue(idx.LabelValues("process_", "process", match)),
			CPUPercent: Reading{Value: cpu.Value, OK: cpuOK},
			CPUAt:      cpuAt,
		}
		if cpuOK && cpu.Labels == nil {
			processes = append(processes, process)
			continue
		}
		if cpuOK {
			match = cpu.Labels
			process.Command = match["process"]
			process.User = match["user"]
			if process.User == "" {
				process.User = match["uid"]
			}
			process.MemoryBytes = processField(idx, "process_memory_rss_bytes", cpu)
			process.Threads = processField(idx, "process_threads", cpu)
		} else {
			process.MemoryBytes = idx.Value("process_memory_rss_bytes", match)
			process.Threads = idx.Value("process_threads", match)
		}
		processes = append(processes, process)
	}

	// By CPU, then by memory, then by pid. The last tier matters: on an idle
	// machine every process reports zero, and without it the rows would
	// reshuffle on every refresh.
	sort.SliceStable(processes, func(i, j int) bool {
		if processes[i].CPUPercent.Value != processes[j].CPUPercent.Value {
			return processes[i].CPUPercent.Value > processes[j].CPUPercent.Value
		}
		if processes[i].MemoryBytes.Value != processes[j].MemoryBytes.Value {
			return processes[i].MemoryBytes.Value > processes[j].MemoryBytes.Value
		}

		return numericPID(processes[i].PID) < numericPID(processes[j].PID)
	})

	return processes
}

// hostOf reports the host label that Telegraf stamps on every metric.
func hostOf(samples []promtext.Sample) string {
	for _, s := range samples {
		if host := s.Labels["host"]; host != "" {
			return host
		}
	}

	return ""
}

func buildCPU(idx *Index) CPU {
	// Telegraf's cpu input emits one series per core plus an aggregate
	// tagged cpu-total, which is the only one the summary line wants.
	total := map[string]string{"cpu": "cpu-total"}

	cpu := CPU{
		UsageUser:    idx.Value("cpu_usage_user", total),
		UsageSystem:  idx.Value("cpu_usage_system", total),
		UsageIdle:    idx.Value("cpu_usage_idle", total),
		FrequencyKHz: scaleReading(idx.Value("cpu_frequency_avg_frequency_hz", nil), 1e3),
		Classes:      buildCoreClasses(idx),
		PackageTempC: packageTemp(idx),

		PackagePowerW: idx.Value("powerstat_package_current_power_consumption_watts", nil),
		TDPW:          idx.Value("powerstat_package_thermal_design_power_watts", nil),
		BaseFreqMHz:   statedLimit(idx.Value("powerstat_package_cpu_base_frequency_mhz", nil)),
		// The single-core limit is the headline number; the series also
		// carries the limit for every other count of active cores.
		TurboPrimaryMHz: statedLimit(idx.Value("powerstat_package_max_turbo_frequency_mhz",
			map[string]string{"hybrid": "primary", "active_cores": "1"})),
		TurboSecondaryMHz: statedLimit(idx.Value("powerstat_package_max_turbo_frequency_mhz",
			map[string]string{"hybrid": "secondary", "active_cores": "1"})),
		UncoreMHz: statedLimit(idx.Value("powerstat_package_uncore_frequency_mhz_cur",
			map[string]string{"type": "current"})),
		CStates: buildCStates(idx),
	}

	return cpu
}

// statedLimit rejects a frequency limit of zero.
//
// A ceiling of 0 MHz says nothing about the part; it is what the platform
// reports when it does not know the answer. Panther Lake publishes a
// max_turbo_frequency series whose value is zero, and rendering that as
// "turbo 0 MHz" would assert something false about the hardware. Utilisation
// and power are left alone, because zero is a perfectly ordinary reading for
// those.
func statedLimit(r Reading) Reading {
	if r.OK && r.Value == 0 {
		return Reading{}
	}

	return r
}

// cStateOrder lists the idle states shallowest first. A machine reports only
// some of them, and which ones differs by part.
var cStateOrder = []string{"c0", "c1", "c3", "c6", "c7"}

// buildCStates averages each idle state across the CPUs reporting it.
func buildCStates(idx *Index) []CState {
	var states []CState

	for _, name := range cStateOrder {
		samples := idx.All("powerstat_core_cpu_" + name + "_state_residency_percent")
		if len(samples) == 0 {
			continue
		}

		sum := 0.0
		for _, sample := range samples {
			sum += sample.Value
		}

		states = append(states, CState{
			Name:      name,
			Residency: reading(sum / float64(len(samples))),
		})
	}

	return states
}

// buildCoreClasses collects the per-class series into one row per class.
func buildCoreClasses(idx *Index) []CoreClass {
	// The class set is discovered from whichever series is present rather
	// than hardcoded, so a future class needs no change here.
	type key struct{ name, source string }
	seen := make(map[key]struct{})

	for _, metric := range []string{
		"cpu_core_class_cores",
		"cpu_core_class_frequency_avg_hz",
		"cpu_core_class_usage_user",
		"cpu_core_class_usage_system",
		"cpu_core_class_usage_idle",
	} {
		for _, s := range idx.All(metric) {
			name := s.Labels["class"]
			if name == "" {
				continue
			}
			seen[key{name: name, source: s.Labels["source"]}] = struct{}{}
		}
	}

	classes := make([]CoreClass, 0, len(seen))
	for k := range seen {
		match := map[string]string{"class": k.name}
		if k.source != "" {
			match["source"] = k.source
		}

		classes = append(classes, CoreClass{
			Name:         k.name,
			Source:       k.source,
			Cores:        idx.Value("cpu_core_class_cores", match),
			FrequencyKHz: scaleReading(idx.Value("cpu_core_class_frequency_avg_hz", match), 1e3),
			UsageUser:    idx.Value("cpu_core_class_usage_user", match),
			UsageSystem:  idx.Value("cpu_core_class_usage_system", match),
			UsageIdle:    idx.Value("cpu_core_class_usage_idle", match),
		})
	}

	sort.Slice(classes, func(a, b int) bool {
		ra, oka := classOrder[classes[a].Name]
		rb, okb := classOrder[classes[b].Name]
		switch {
		case oka && okb:
			return ra < rb
		// An unrecognised class sorts after the known ones, then by name,
		// so the ordering stays stable across refreshes.
		case oka:
			return true
		case okb:
			return false
		default:
			return classes[a].Name < classes[b].Name
		}
	})

	return classes
}

// packageTempMetric is the CPU package temperature series.
//
// The name reads oddly because Prometheus joins the measurement and the field:
// Telegraf's temp input calls both of them "temp". Guessing "temp_temperature"
// instead silently drops the reading, since a series that does not exist is
// indistinguishable from a host with no sensor.
const packageTempMetric = "temp_temp"

// packageTemp picks the CPU package sensor out of the temp input, whose
// sensor set varies by platform.
func packageTemp(idx *Index) Reading {
	for _, s := range idx.All(packageTempMetric) {
		if sensor := s.Labels["sensor"]; sensor != "" && isPackageSensor(sensor) {
			return reading(s.Value)
		}
	}

	return Reading{}
}

// isPackageSensor reports whether a sensor name is a CPU package sensor.
// telegraf.conf already narrows the input to coretemp_package_id_*, but the
// filter lives in configuration an operator may change, so the check is
// repeated here rather than assumed.
func isPackageSensor(sensor string) bool {
	const prefix = "coretemp_package_id_"

	return len(sensor) > len(prefix) && sensor[:len(prefix)] == prefix
}

func buildMemory(idx *Index) Memory {
	return Memory{
		UsedPercent:      idx.Value("mem_used_percent", nil),
		AvailablePercent: idx.Value("mem_available_percent", nil),
		TotalBytes:       idx.Value("mem_total", nil),
		UsedBytes:        idx.Value("mem_used", nil),
		ReadGBps:         scaleReading(idx.Value("memory_bandwidth_read_bytes_per_second", nil), 1e9),
		WriteGBps:        scaleReading(idx.Value("memory_bandwidth_write_bytes_per_second", nil), 1e9),
		TotalGBps:        scaleReading(idx.Value("memory_bandwidth_total_bytes_per_second", nil), 1e9),
	}
}

const (
	gpuPrefix      = "gpu_"
	npuPrefix      = "npu_"
	throttlePrefix = "gpu_throttle_"

	// throttleAggregate is qmassa's own summary flag. It arrives in the same
	// map as the specific reasons, so it has to be separated by name.
	throttleAggregate = "status"
)

// engineOrder puts the engines in a fixed, familiar order instead of the
// alphabetical one.
//
// The two Intel drivers name the same engines differently -- i915 spells them
// out while xe uses the ring abbreviations -- so both spellings map to the same
// position and the panel keeps its shape across drivers.
var engineOrder = map[string]int{
	"render": 0, "rcs": 0,
	"compute": 1, "ccs": 1,
	"copy": 2, "bcs": 2,
	"video": 3, "vcs": 3,
	"video-enhance": 4, "vecs": 4,
}

func buildGPUs(idx *Index) []GPU {
	ids := idx.LabelValues(gpuPrefix, "gpu_id", nil)

	gpus := make([]GPU, 0, len(ids))
	for _, id := range ids {
		match := map[string]string{"gpu_id": id}
		driver := soleValue(idx.LabelValues(gpuPrefix, "driver", match))

		gpus = append(gpus, GPU{
			ID:      id,
			Driver:  driver,
			Engines: buildEngines(idx, match),
			Tiles:   buildTiles(idx, match),
			// qmassa separates the graphics rail from the package rail.
			PowerW:           idx.Value("gpu_power_power_w", withLabel(match, "type", "gpu_cur_power")),
			PackagePowerW:    idx.Value("gpu_power_power_w", withLabel(match, "type", "pkg_cur_power")),
			TempC:            idx.Value("gpu_temperature_temperature_c", match),
			SharedTotalBytes: idx.Value("gpu_memory_smem_total_bytes", match),
			SharedUsedBytes:  sharedMemoryUsed(idx, driver, match),
			VRAMTotalBytes:   idx.Value("gpu_memory_vram_total_bytes", match),
			VRAMUsedBytes:    idx.Value("gpu_memory_vram_used_bytes", match),
			Processes:        buildGPUProcesses(idx, match),
		})
	}

	return gpus
}

// buildGPUProcesses collects the per-process points into one row each.
//
// The engines a process uses are discovered rather than fixed, because the
// names differ between drivers: i915 says "render" where xe says "rcs".
func buildGPUProcesses(idx *Index, match map[string]string) []GPUProcess {
	pids := idx.LabelValues("gpu_client", "pid", match)
	if len(pids) == 0 {
		return nil
	}

	engineNames := idx.NamesWithPrefix("gpu_client_engine_")

	processes := make([]GPUProcess, 0, len(pids))
	for _, pid := range pids {
		processMatch := withLabel(match, "pid", pid)

		usage := 0.0
		usageKnown := false
		for _, name := range engineNames {
			if value := idx.Value(name, processMatch); value.OK {
				usage += value.Value
				usageKnown = true
			}
		}

		memory := Reading{}
		for _, name := range []string{"gpu_client_smem_used_bytes", "gpu_client_vram_used_bytes"} {
			if value := idx.Value(name, processMatch); value.OK {
				memory = reading(memory.Value + value.Value)
			}
		}

		process := GPUProcess{
			PID:         pid,
			Command:     soleValue(idx.LabelValues("gpu_client", "comm", processMatch)),
			MemoryBytes: memory,
		}
		if usageKnown {
			process.UsagePct = reading(usage)
		}

		processes = append(processes, process)
	}

	// Busiest first, and by process identifier when usage ties, so an idle
	// machine does not reshuffle the rows between refreshes.
	sort.SliceStable(processes, func(i, j int) bool {
		if processes[i].UsagePct.Value != processes[j].UsagePct.Value {
			return processes[i].UsagePct.Value > processes[j].UsagePct.Value
		}

		return numericPID(processes[i].PID) < numericPID(processes[j].PID)
	})

	return processes
}

// numericPID orders process identifiers as numbers, so 9 comes before 10.
// A value that is not a number sorts last rather than failing.
func numericPID(pid string) int {
	value, err := strconv.Atoi(pid)
	if err != nil {
		return math.MaxInt
	}

	return value
}

// soleValue returns the only value of a label, or "" when the label is missing
// or disagrees across the device's series.
func soleValue(values []string) string {
	if len(values) != 1 {
		return ""
	}

	return values[0]
}

// driversWithoutSharedMemoryUsage lists the drivers that leave
// gpu_memory_smem_used_bytes at zero because they do not expose per-device shared
// memory usage the way xe does.
//
// The plugin passes qmassa's counter through unaltered rather than
// second-guessing the driver, which is what keeps the raw value available to
// Grafana. The judgement is made here instead, once, and only for display.
var driversWithoutSharedMemoryUsage = map[string]bool{"i915": true}

// sharedMemoryUsed reads the shared memory counter, marking it unavailable on
// a driver that never populates it.
//
// Rendering that constant zero as "0 B" would state that the GPU is using no
// system memory, which is not something the host measured. The substitution is
// deliberately limited to a zero reading, so a driver that starts reporting the
// counter is shown rather than suppressed.
func sharedMemoryUsed(idx *Index, driver string, match map[string]string) Reading {
	used := idx.Value("gpu_memory_smem_used_bytes", match)
	if used.OK && used.Value == 0 && driversWithoutSharedMemoryUsage[driver] {
		return Reading{Value: math.NaN(), OK: true}
	}

	return used
}

func buildEngines(idx *Index, match map[string]string) []GPUEngine {
	names := idx.LabelValues("gpu_engine_usage", "engine", match)

	engines := make([]GPUEngine, 0, len(names))
	for _, name := range names {
		engines = append(engines, GPUEngine{
			Name:  name,
			Usage: idx.Value("gpu_engine_usage_usage", withLabel(match, "engine", name)),
		})
	}

	sort.SliceStable(engines, func(a, b int) bool {
		ra, oka := engineOrder[engines[a].Name]
		rb, okb := engineOrder[engines[b].Name]
		switch {
		case oka && okb:
			return ra < rb
		// An engine this code has never heard of still gets shown, just
		// after the familiar ones.
		case oka:
			return true
		case okb:
			return false
		default:
			return engines[a].Name < engines[b].Name
		}
	})

	return engines
}

func buildTiles(idx *Index, match map[string]string) []GPUTile {
	names := idx.LabelValues(gpuPrefix, "tile", match)

	tiles := make([]GPUTile, 0, len(names))
	for _, name := range names {
		tileMatch := withLabel(match, "tile", name)

		tile := GPUTile{
			Name:         name,
			ActualMHz:    scaleReading(idx.Value("gpu_frequency_act_freq_hz", tileMatch), 1e6),
			RequestedMHz: scaleReading(idx.Value("gpu_frequency_cur_freq_hz", tileMatch), 1e6),
			MinMHz:       scaleReading(idx.Value("gpu_frequency_min_freq_hz", tileMatch), 1e6),
			MaxMHz:       scaleReading(idx.Value("gpu_frequency_max_freq_hz", tileMatch), 1e6),
		}
		tile.Throttled, tile.ThrottleReasons, tile.ThrottleReported = throttleState(idx, tileMatch)

		tiles = append(tiles, tile)
	}

	return tiles
}

// throttleState collects the throttle flags set for one tile.
//
// The flags are read by prefix rather than from a fixed list because the
// plugin forwards qmassa's throttle_reasons map verbatim; a reason added by a
// future qmassa release should appear here without anyone editing this file.
func throttleState(idx *Index, match map[string]string) (aggregate Reading, reasons []string, reported bool) {
	for _, name := range idx.NamesWithPrefix(throttlePrefix) {
		value := idx.Value(name, match)
		if !value.OK {
			continue
		}
		reported = true

		if flag := strings.TrimPrefix(name, throttlePrefix); flag == throttleAggregate {
			aggregate = value
		} else if value.Value != 0 {
			reasons = append(reasons, flag)
		}
	}
	sort.Strings(reasons)

	return aggregate, reasons, reported
}

func buildNPU(idx *Index) NPU {
	return NPU{
		Present:       len(idx.NamesWithPrefix(npuPrefix)) > 0,
		Utilization:   idx.Value("npu_utilization", nil),
		FrequencyHz:   idx.Value("npu_frequency_hz", nil),
		PowerW:        idx.Value("npu_power_w", nil),
		TempC:         idx.Value("npu_temperature_c", nil),
		BandwidthMBps: scaleReading(idx.Value("npu_bandwidth_bytes_per_second", nil), 1e6),
		TileConfig:    idx.Value("npu_tile_config", nil),
		MemoryMiB:     npuMemory(idx),
		PowerState:    idx.Value("npu_power_state", nil),
		// A ceiling of zero would be as meaningless here as it is for the
		// CPU, so the same guard applies.
		MaxFrequencyMHz: statedLimit(scaleReading(idx.Value("npu_frequency_max_hz", nil), 1e6)),
	}
}

// npuMemory converts bytes to display MiB and rejects invalid negative sizes.
func npuMemory(idx *Index) Reading {
	if r := idx.Value("npu_memory_bytes", nil); !r.OK || r.Value >= 0 {
		return scaleReading(r, 1<<20)
	}

	return Reading{}
}
