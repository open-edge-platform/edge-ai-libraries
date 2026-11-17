// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"math"
	"strings"
	"testing"

	"github.com/open-edge-platform/edge-ai-libraries/microservices/metrics-manager/native/internal/promtext"
)

// hostExposition is an excerpt of what the container's Prometheus endpoint
// actually served on a Meteor Lake host, trimmed to the measurements the CPU
// and memory panels use. It is a capture rather than a hand-written sample:
// an earlier hand-written fixture invented the name "temp_temperature" and so
// agreed with a lookup that found nothing on a real host.
const hostExposition = `cpu_usage_user{cpu="cpu-total",host="itest"} 3.5
cpu_usage_system{cpu="cpu-total",host="itest"} 1.25
cpu_usage_idle{cpu="cpu-total",host="itest"} 95.25
cpu_usage_user{cpu="cpu0",host="itest"} 9
cpu_frequency_avg_frequency_hz{host="itest"} 1090550000
cpu_core_class_cores{class="P",host="itest",source="pmu"} 12
cpu_core_class_cores{class="E",host="itest",source="pmu"} 8
cpu_core_class_cores{class="LPE",host="itest",source="heuristic"} 2
cpu_core_class_frequency_avg_hz{class="P",host="itest",source="pmu"} 1200000000
cpu_core_class_usage_user{class="P",host="itest",source="pmu"} 4.5
cpu_core_class_usage_system{class="P",host="itest",source="pmu"} 2
cpu_core_class_usage_idle{class="P",host="itest",source="pmu"} 93.5
temp_temp{host="itest",sensor="coretemp_package_id_0"} 47.5
mem_used_percent{host="itest"} 42.5
mem_available_percent{host="itest"} 57.5
mem_total{host="itest"} 3.3554432e+10
mem_used{host="itest"} 1.426063e+10
`

// acceleratorExposition captures the gpu_ and npu_ series of the same Meteor
// Lake host, including the i915 engine names and the two frequency tiles.
//
// The metric names, labels and units are exactly as served. The values are
// not: the host was idle, and a fixture of zeros could not tell the act_freq
// field apart from cur_freq, nor one engine from another. Readings that were
// genuinely constant on the host -- the frequency limits, the shared memory
// total, the -1 memory sentinel -- are kept verbatim.
const acceleratorExposition = `gpu_engine_usage_usage{engine="render",gpu_id="0",driver="i915",host="itest",type="render"} 11
gpu_engine_usage_usage{engine="compute",gpu_id="0",driver="i915",host="itest",type="compute"} 22
gpu_engine_usage_usage{engine="copy",gpu_id="0",driver="i915",host="itest",type="copy"} 33
gpu_engine_usage_usage{engine="video",gpu_id="0",driver="i915",host="itest",type="video"} 44
gpu_engine_usage_usage{engine="video-enhance",gpu_id="0",driver="i915",host="itest",type="video-enhance"} 55
gpu_frequency{gpu_id="0",driver="i915",host="itest",tile="gt0",type="cur_freq"} 700
gpu_frequency_act_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt0",type="cur_freq"} 650000000
gpu_frequency_cur_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt0",type="cur_freq"} 700000000
gpu_frequency_min_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt0",type="cur_freq"} 800000000
gpu_frequency_max_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt0",type="cur_freq"} 2300000000
gpu_frequency_act_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt1",type="cur_freq"} 150000000
gpu_frequency_cur_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt1",type="cur_freq"} 200000000
gpu_frequency_min_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt1",type="cur_freq"} 100000000
gpu_frequency_max_freq_hz{gpu_id="0",driver="i915",host="itest",tile="gt1",type="cur_freq"} 1300000000
gpu_memory_smem_total_bytes{gpu_id="0",driver="i915",host="itest"} 1.0051622912e+11
gpu_memory_smem_used_bytes{gpu_id="0",driver="i915",host="itest"} 0
gpu_memory_vram_total_bytes{gpu_id="0",driver="i915",host="itest"} 0
gpu_memory_vram_used_bytes{gpu_id="0",driver="i915",host="itest"} 0
gpu_power_power_w{gpu_id="0",driver="i915",host="itest",type="gpu_cur_power"} 0.0002996
gpu_power_power_w{gpu_id="0",driver="i915",host="itest",type="pkg_cur_power"} 19.86
gpu_temperature_temperature_c{gpu_id="0",driver="i915",host="itest",sensor="pkg"} 42
gpu_throttle_status{gpu_id="0",driver="i915",host="itest",tile="gt0"} 1
gpu_throttle_pl1{gpu_id="0",driver="i915",host="itest",tile="gt0"} 0
gpu_throttle_thermal{gpu_id="0",driver="i915",host="itest",tile="gt0"} 1
gpu_throttle_vr_tdc{gpu_id="0",driver="i915",host="itest",tile="gt0"} 1
gpu_throttle_status{gpu_id="0",driver="i915",host="itest",tile="gt1"} 0
gpu_throttle_pl1{gpu_id="0",driver="i915",host="itest",tile="gt1"} 0
gpu_throttle_thermal{gpu_id="0",driver="i915",host="itest",tile="gt1"} 0
gpu_throttle_vr_tdc{gpu_id="0",driver="i915",host="itest",tile="gt1"} 0
npu_bandwidth_bytes_per_second{host="itest"} 12500000
npu_frequency_hz{host="itest"} 1.4e+09
npu_memory_bytes{host="itest"} -1048576
npu_power_w{host="itest"} 1.75
npu_temperature_c{host="itest"} 36
npu_tile_config{host="itest"} 2
npu_utilization{host="itest"} 63.5
`

func parseFixture(t *testing.T, s string) []promtext.Sample {
	t.Helper()

	samples, err := promtext.Parse(strings.NewReader(s))
	if err != nil {
		t.Fatalf("parse fixture: %v", err)
	}
	return samples
}

func buildFixture(t *testing.T, s string) Dashboard {
	t.Helper()

	return BuildDashboard(parseFixture(t, s))
}

func wantReading(t *testing.T, label string, got Reading, want float64) {
	t.Helper()

	if !got.OK {
		t.Errorf("%s is absent, want %v", label, want)
		return
	}
	if got.Value != want {
		t.Errorf("%s = %v, want %v", label, got.Value, want)
	}
}

func TestBuildDashboardCPUSummary(t *testing.T) {
	d := buildFixture(t, hostExposition)

	// The summary line must read the cpu-total aggregate, not whichever
	// per-core series happens to come first.
	wantReading(t, "UsageUser", d.CPU.UsageUser, 3.5)
	wantReading(t, "UsageSystem", d.CPU.UsageSystem, 1.25)
	wantReading(t, "UsageIdle", d.CPU.UsageIdle, 95.25)
	wantReading(t, "FrequencyKHz", d.CPU.FrequencyKHz, 1090550)
	wantReading(t, "PackageTempC", d.CPU.PackageTempC, 47.5)
}

func TestBuildDashboardHost(t *testing.T) {
	d := buildFixture(t, hostExposition)

	if d.Host != "itest" {
		t.Errorf("Host = %q, want itest", d.Host)
	}
}

func TestBuildDashboardCoreClassOrder(t *testing.T) {
	d := buildFixture(t, hostExposition)

	var got []string
	for _, c := range d.CPU.Classes {
		got = append(got, c.Name)
	}

	// Strongest first. Alphabetical order would put E before P, which
	// reads oddly, and any instability would make the panel jump between
	// refreshes.
	want := []string{"P", "E", "LPE"}
	if len(got) != len(want) {
		t.Fatalf("classes = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("classes = %v, want %v", got, want)
		}
	}
}

func TestBuildDashboardCoreClassFields(t *testing.T) {
	d := buildFixture(t, hostExposition)

	p := d.CPU.Classes[0]
	if p.Source != "pmu" {
		t.Errorf("P source = %q, want pmu", p.Source)
	}
	wantReading(t, "P cores", p.Cores, 12)
	wantReading(t, "P frequency", p.FrequencyKHz, 1200000)
	wantReading(t, "P user", p.UsageUser, 4.5)
	wantReading(t, "P system", p.UsageSystem, 2)
	wantReading(t, "P idle", p.UsageIdle, 93.5)

	// The E class fixture carries only a core count, so the remaining
	// fields must read as absent rather than as zero usage.
	e := d.CPU.Classes[1]
	wantReading(t, "E cores", e.Cores, 8)
	if e.UsageUser.OK {
		t.Errorf("E user = %v, want absent", e.UsageUser.Value)
	}

	lpe := d.CPU.Classes[2]
	if lpe.Source != "heuristic" {
		t.Errorf("LPE source = %q, want heuristic", lpe.Source)
	}
}

func TestBuildDashboardUnknownCoreClassSortsLast(t *testing.T) {
	d := buildFixture(t, `cpu_core_class_cores{class="Z",source="pmu"} 1
cpu_core_class_cores{class="P",source="pmu"} 2
cpu_core_class_cores{class="A",source="pmu"} 3
`)

	want := []string{"P", "A", "Z"}
	for i, c := range d.CPU.Classes {
		if c.Name != want[i] {
			t.Fatalf("class %d = %q, want %q", i, c.Name, want[i])
		}
	}
}

func TestBuildDashboardMemory(t *testing.T) {
	d := buildFixture(t, hostExposition)

	wantReading(t, "UsedPercent", d.Memory.UsedPercent, 42.5)
	wantReading(t, "AvailablePercent", d.Memory.AvailablePercent, 57.5)
	wantReading(t, "TotalBytes", d.Memory.TotalBytes, 33554432000)
	wantReading(t, "UsedBytes", d.Memory.UsedBytes, 14260630000)
}

func TestBuildDashboardEmptySnapshot(t *testing.T) {
	// A host that has not reported yet must produce absent readings, never
	// zeroes that would read as real measurements.
	d := BuildDashboard(nil)

	if d.Host != "" {
		t.Errorf("Host = %q, want empty", d.Host)
	}
	if d.CPU.UsageUser.OK || d.CPU.FrequencyKHz.OK || d.Memory.UsedPercent.OK {
		t.Error("empty snapshot produced present readings")
	}
	if len(d.CPU.Classes) != 0 {
		t.Errorf("Classes = %v, want none", d.CPU.Classes)
	}
}

func TestBuildDashboardIgnoresNonPackageTempSensors(t *testing.T) {
	// telegraf.conf narrows the temp input to coretemp packages, but that
	// filter is operator-editable, so an unrelated sensor must not be
	// mistaken for the CPU package.
	d := buildFixture(t, `temp_temp{sensor="acpitz"} 30
temp_temp{sensor="nvme_composite"} 35
`)

	if d.CPU.PackageTempC.OK {
		t.Errorf("PackageTempC = %v, want absent", d.CPU.PackageTempC.Value)
	}
}

func TestBuildDashboardPrefersPackageTempAmongSensors(t *testing.T) {
	d := buildFixture(t, `temp_temp{sensor="acpitz"} 30
temp_temp{sensor="coretemp_package_id_0"} 47
`)

	wantReading(t, "PackageTempC", d.CPU.PackageTempC, 47)
}

func TestBuildDashboardTemperatureMetricName(t *testing.T) {
	// Prometheus joins the measurement and field names, and Telegraf's temp
	// input calls both "temp". Looking up the plausible-sounding
	// "temp_temperature" finds nothing, which is indistinguishable from a
	// host with no sensor.
	if packageTempMetric != "temp_temp" {
		t.Errorf("packageTempMetric = %q, want temp_temp", packageTempMetric)
	}

	d := buildFixture(t, `temp_temperature{sensor="coretemp_package_id_0"} 47
`)
	if d.CPU.PackageTempC.OK {
		t.Error("the old invented name was accepted")
	}
}

func TestIndexValueMatchesLabelSubset(t *testing.T) {
	idx := NewIndex(parseFixture(t, hostExposition))

	// Selecting on one label must work even though Telegraf also stamps
	// host on every series.
	wantReading(t, "P cores", idx.Value("cpu_core_class_cores", map[string]string{"class": "P"}), 12)

	// A label that matches nothing must report absence, not the first
	// sample of the family.
	if got := idx.Value("cpu_core_class_cores", map[string]string{"class": "nope"}); got.OK {
		t.Errorf("value = %v, want absent", got.Value)
	}
}

func TestIndexAllUnknownName(t *testing.T) {
	idx := NewIndex(nil)

	if got := idx.All("nothing"); len(got) != 0 {
		t.Errorf("All = %v, want empty", got)
	}
}

// gpuFixture builds the dashboard's single GPU, failing if it is missing.
func gpuFixture(t *testing.T, exposition string) GPU {
	t.Helper()

	gpus := buildFixture(t, exposition).GPUs
	if len(gpus) != 1 {
		t.Fatalf("got %d GPUs, want 1", len(gpus))
	}
	return gpus[0]
}

func TestBuildDashboardGPUEngineOrder(t *testing.T) {
	// Engines are listed in pipeline order rather than the alphabetical
	// order the labels arrive in, so the table reads the same on every host.
	gpu := gpuFixture(t, acceleratorExposition)

	var got []string
	for _, e := range gpu.Engines {
		got = append(got, e.Name)
	}

	want := []string{"render", "compute", "copy", "video", "video-enhance"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("engines = %v, want %v", got, want)
	}

	wantReading(t, "render usage", gpu.Engines[0].Usage, 11)
	wantReading(t, "video-enhance usage", gpu.Engines[4].Usage, 55)
}

func TestBuildDashboardGPUEngineOrderAcceptsXeNames(t *testing.T) {
	// i915 and xe name the same engines differently. A host on xe must get
	// the same ordering, or the two drivers would render inconsistently.
	gpu := gpuFixture(t, `gpu_engine_usage_usage{engine="vecs",gpu_id="0"} 5
gpu_engine_usage_usage{engine="rcs",gpu_id="0"} 1
gpu_engine_usage_usage{engine="bcs",gpu_id="0"} 3
gpu_engine_usage_usage{engine="ccs",gpu_id="0"} 2
gpu_engine_usage_usage{engine="vcs",gpu_id="0"} 4
`)

	var got []string
	for _, e := range gpu.Engines {
		got = append(got, e.Name)
	}

	want := []string{"rcs", "ccs", "bcs", "vcs", "vecs"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("engines = %v, want %v", got, want)
	}
}

func TestBuildDashboardGPUKeepsUnknownEngine(t *testing.T) {
	// A future driver may expose an engine this code has never heard of.
	// Dropping it would silently lose a measurement, so it is shown after
	// the familiar ones instead.
	gpu := gpuFixture(t, `gpu_engine_usage_usage{engine="quantum",gpu_id="0"} 7
gpu_engine_usage_usage{engine="render",gpu_id="0"} 1
`)

	if len(gpu.Engines) != 2 {
		t.Fatalf("got %d engines, want 2", len(gpu.Engines))
	}
	if gpu.Engines[0].Name != "render" || gpu.Engines[1].Name != "quantum" {
		t.Errorf("engines = %v, want render then quantum", gpu.Engines)
	}
	wantReading(t, "quantum usage", gpu.Engines[1].Usage, 7)
}

func TestBuildDashboardGPUTiles(t *testing.T) {
	gpu := gpuFixture(t, acceleratorExposition)

	if len(gpu.Tiles) != 2 {
		t.Fatalf("got %d tiles, want 2", len(gpu.Tiles))
	}

	gt0 := gpu.Tiles[0]
	if gt0.Name != "gt0" {
		t.Errorf("first tile = %q, want gt0", gt0.Name)
	}
	// act_freq and cur_freq are separate measurements: what the tile is
	// running at versus what was asked for.
	wantReading(t, "gt0 actual", gt0.ActualMHz, 650)
	wantReading(t, "gt0 requested", gt0.RequestedMHz, 700)
	wantReading(t, "gt0 min", gt0.MinMHz, 800)
	wantReading(t, "gt0 max", gt0.MaxMHz, 2300)

	wantReading(t, "gt1 max", gpu.Tiles[1].MaxMHz, 1300)
}

func TestBuildDashboardGPUIgnoresLegacyFrequencySeries(t *testing.T) {
	// Older plugins published a bare gpu_frequency duplicating
	// cur_freq. Ignore any such leftover series; reading it as the actual
	// frequency would report the requested value twice.
	gpu := gpuFixture(t, acceleratorExposition)

	if got := gpu.Tiles[0].ActualMHz; got.Value == 700 {
		t.Error("actual frequency came from the legacy gpu_frequency series")
	}
}

func TestBuildDashboardGPUThrottleReasons(t *testing.T) {
	gpu := gpuFixture(t, acceleratorExposition)

	gt0 := gpu.Tiles[0]
	if !gt0.ThrottleReported {
		t.Fatal("gt0 throttle state is unreported")
	}
	// Only the flags that are set are listed, and the aggregate "status"
	// flag is not one of the reasons.
	if got := strings.Join(gt0.ThrottleReasons, ","); got != "thermal,vr_tdc" {
		t.Errorf("gt0 reasons = %q, want thermal,vr_tdc", got)
	}
	wantReading(t, "gt0 throttle status", gt0.Throttled, 1)

	if got := gpu.Tiles[1].ThrottleReasons; len(got) != 0 {
		t.Errorf("gt1 reasons = %v, want none", got)
	}
}

func TestBuildDashboardGPUThrottleDiscoversNewFlags(t *testing.T) {
	// The plugin forwards qmassa's throttle map verbatim, so a reason added
	// upstream must appear without this code being edited.
	gpu := gpuFixture(t, `gpu_throttle_status{gpu_id="0",tile="gt0"} 1
gpu_throttle_future_reason{gpu_id="0",tile="gt0"} 1
`)

	if got := strings.Join(gpu.Tiles[0].ThrottleReasons, ","); got != "future_reason" {
		t.Errorf("reasons = %q, want future_reason", got)
	}
}

func TestBuildDashboardGPUThrottleUnreportedWhenAbsent(t *testing.T) {
	// No throttle series at all is not the same as nothing throttling, and
	// must not be reported as the reassuring case.
	gpu := gpuFixture(t, `gpu_temperature_temperature_c{gpu_id="0"} 42
gpu_frequency_act_freq_hz{gpu_id="0",tile="gt0"} 650000000
`)

	if gpu.Tiles[0].ThrottleReported {
		t.Error("throttle reported although no throttle series exists")
	}
}

func TestBuildDashboardGPUPowerMemoryAndTemperature(t *testing.T) {
	gpu := gpuFixture(t, acceleratorExposition)

	// The two power rails share a metric name and differ only by label.
	wantReading(t, "graphics power", gpu.PowerW, 0.0002996)
	wantReading(t, "package power", gpu.PackagePowerW, 19.86)
	wantReading(t, "temperature", gpu.TempC, 42)
	wantReading(t, "shared total", gpu.SharedTotalBytes, 1.0051622912e+11)
	wantReading(t, "vram total", gpu.VRAMTotalBytes, 0)

	// SharedUsedBytes is deliberately not a plain zero on this driver; see
	// TestBuildDashboardSharedMemoryUnavailableOnI915.
}

func TestBuildDashboardMultipleGPUs(t *testing.T) {
	// Discrete cards appear as additional gpu_id values; nothing may assume
	// a single GPU.
	gpus := buildFixture(t, `gpu_temperature_temperature_c{gpu_id="0"} 42
gpu_temperature_temperature_c{gpu_id="1"} 61
gpu_engine_usage_usage{engine="render",gpu_id="1"} 90
`).GPUs

	if len(gpus) != 2 {
		t.Fatalf("got %d GPUs, want 2", len(gpus))
	}
	if gpus[0].ID != "0" || gpus[1].ID != "1" {
		t.Errorf("ids = %q, %q, want 0, 1", gpus[0].ID, gpus[1].ID)
	}
	wantReading(t, "gpu 1 temperature", gpus[1].TempC, 61)
	// Engines must be attributed to the right card.
	if len(gpus[0].Engines) != 0 {
		t.Errorf("gpu 0 engines = %v, want none", gpus[0].Engines)
	}
}

func TestBuildDashboardNPU(t *testing.T) {
	npu := buildFixture(t, acceleratorExposition).NPU

	if !npu.Present {
		t.Fatal("NPU is absent")
	}
	wantReading(t, "utilization", npu.Utilization, 63.5)
	wantReading(t, "frequency", npu.FrequencyHz, 1.4e9)
	wantReading(t, "power", npu.PowerW, 1.75)
	wantReading(t, "temperature", npu.TempC, 36)
	wantReading(t, "bandwidth", npu.BandwidthMBps, 12.5)
	wantReading(t, "tile config", npu.TileConfig, 2)
}

func TestBuildDashboardNPUMemorySentinel(t *testing.T) {
	// The plugin reports -1 where the sysfs node does not exist, which is
	// the case on Meteor Lake and Arrow Lake. Showing "-1 MB" would dress a
	// sentinel up as a measurement.
	if got := buildFixture(t, acceleratorExposition).NPU.MemoryMiB; got.OK {
		t.Errorf("memory = %v, want absent", got.Value)
	}

	wantReading(t, "real memory", buildFixture(t, `npu_memory_bytes{host="itest"} 536870912
`).NPU.MemoryMiB, 512)
}

func TestBuildDashboardNPUAbsentOnHostWithout(t *testing.T) {
	// A machine with no NPU publishes no npu_ series at all. A panel of
	// dashes would suggest a broken sensor rather than absent hardware.
	if buildFixture(t, hostExposition).NPU.Present {
		t.Error("NPU reported present without any npu_ series")
	}
}

func TestBuildDashboardNoAcceleratorsOnCPUOnlyHost(t *testing.T) {
	if got := buildFixture(t, hostExposition).GPUs; len(got) != 0 {
		t.Errorf("GPUs = %v, want none", got)
	}
}

func TestBuildDashboardGPUDriver(t *testing.T) {
	if got := gpuFixture(t, acceleratorExposition).Driver; got != "i915" {
		t.Errorf("driver = %q, want i915", got)
	}

	// The driver is read from the tag, not inferred, so a host on xe is
	// reported as xe without any change here.
	if got := gpuFixture(t, `gpu_temperature_temperature_c{gpu_id="0",driver="xe"} 42
`).Driver; got != "xe" {
		t.Errorf("driver = %q, want xe", got)
	}
}

func TestBuildDashboardGPUDriverAbsent(t *testing.T) {
	// Telemetry from an older plugin carries no driver tag. That must read
	// as "unknown" rather than being guessed at.
	if got := gpuFixture(t, `gpu_temperature_temperature_c{gpu_id="0"} 42
`).Driver; got != "" {
		t.Errorf("driver = %q, want empty", got)
	}
}

func TestBuildDashboardSharedMemoryUnavailableOnI915(t *testing.T) {
	// i915 leaves smem_used at zero because it does not expose per-device
	// shared memory usage. Reporting that as a measured zero would state
	// the GPU is using no system memory, which the host never measured.
	got := gpuFixture(t, acceleratorExposition).SharedUsedBytes
	if !got.OK {
		t.Fatal("shared memory used is absent, want unavailable")
	}
	if !math.IsNaN(got.Value) {
		t.Errorf("shared memory used = %v, want NaN", got.Value)
	}

	// The total is a real figure and must survive.
	wantReading(t, "shared total", gpuFixture(t, acceleratorExposition).SharedTotalBytes, 1.0051622912e+11)
}

func TestBuildDashboardSharedMemoryKeptOnReportingDriver(t *testing.T) {
	// xe does populate the counter, so its zero is a measurement.
	wantReading(t, "xe shared used", gpuFixture(t, `gpu_memory_smem_used_bytes{gpu_id="0",driver="xe"} 0
`).SharedUsedBytes, 0)

	// An i915 host that does start reporting the counter must not be
	// suppressed either: the substitution applies only to a zero.
	wantReading(t, "i915 non-zero shared used", gpuFixture(t, `gpu_memory_smem_used_bytes{gpu_id="0",driver="i915"} 4096
`).SharedUsedBytes, 4096)
}

func TestBuildDashboardSharedMemoryAbsentStaysAbsent(t *testing.T) {
	// No counter at all is not the same as one the driver cannot fill in,
	// and must not be turned into the "unavailable" case.
	got := gpuFixture(t, `gpu_temperature_temperature_c{gpu_id="0",driver="i915"} 42
`).SharedUsedBytes
	if got.OK {
		t.Errorf("shared memory used = %v, want absent", got.Value)
	}
}

// TestBuildDashboardRejectsAZeroFrequencyLimit covers Panther Lake, which
// publishes a max_turbo_frequency series whose value is zero. A ceiling of
// 0 MHz says nothing about the part, and showing it would assert something
// false about the hardware.
func TestBuildDashboardRejectsAZeroFrequencyLimit(t *testing.T) {
	dash := buildFixture(t, `powerstat_package_max_turbo_frequency_mhz{hybrid="primary",active_cores="1"} 0
powerstat_package_max_turbo_frequency_mhz{hybrid="secondary",active_cores="1"} 0
powerstat_package_cpu_base_frequency_mhz 0
powerstat_package_uncore_frequency_mhz_cur{type="current"} 600
`)

	for name, got := range map[string]Reading{
		"turbo primary":   dash.CPU.TurboPrimaryMHz,
		"turbo secondary": dash.CPU.TurboSecondaryMHz,
		"base":            dash.CPU.BaseFreqMHz,
	} {
		if got.OK {
			t.Errorf("%s = %v, want it treated as unavailable", name, got.Value)
		}
	}

	// A real limit alongside the zeros must survive, or the guard would be
	// throwing away readings rather than rejecting a sentinel.
	wantReading(t, "uncore", dash.CPU.UncoreMHz, 600)
}
