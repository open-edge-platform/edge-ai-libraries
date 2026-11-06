// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"testing"
	"time"
)

func TestBaseUnitTemperaturesRetainAlertThresholds(t *testing.T) {
	dashboard := buildFixture(t, "npu_temperature_c 100\ngpu_temperature_temperature_c{gpu_id=\"0\"} 100\n")
	config := DefaultDashboardConfig()
	tracker := NewAlertTracker(config.Alerts, config.Processes)
	for sample := range 3 {
		tracker.Update(dashboard, config.Thresholds, fixedNow.Add(time.Duration(sample)*time.Second))
	}
	alerts := tracker.Active()
	if len(alerts) != 2 {
		t.Fatalf("expected GPU and NPU temperature alerts, got %+v", alerts)
	}
	for _, alert := range alerts {
		if alert.Severity != SeverityCritical {
			t.Fatalf("temperature alert no longer critical: %+v", alert)
		}
	}
}

func TestBaseUnitsReachDisplayAndCharts(t *testing.T) {
	dashboard := buildFixture(t, `cpu_frequency_avg_frequency_hz 2400000000
cpu_core_class_frequency_avg_hz{class="P"} 3200000000
gpu_frequency_act_freq_hz{gpu_id="0",tile="gt0"} 750000000
gpu_memory_vram_total_bytes{gpu_id="0"} 8589934592
gpu_memory_vram_used_bytes{gpu_id="0"} 2147483648
gpu_power_power_w{gpu_id="0",type="gpu_cur_power"} 12.5
gpu_temperature_temperature_c{gpu_id="0"} 65
npu_frequency_hz 1600000000
npu_frequency_max_hz 1800000000
npu_memory_bytes 536870912
npu_bandwidth_bytes_per_second 12500000
npu_power_w 2.5
npu_temperature_c 75
memory_bandwidth_read_bytes_per_second 1000000000
memory_bandwidth_write_bytes_per_second 250000000
memory_bandwidth_total_bytes_per_second 1250000000
`)
	wantReading(t, "CPU display kHz", dashboard.CPU.FrequencyKHz, 2400000)
	wantReading(t, "GPU display MHz", dashboard.GPUs[0].Tiles[0].ActualMHz, 750)
	wantReading(t, "GPU bytes", dashboard.GPUs[0].VRAMUsedBytes, 2147483648)
	wantReading(t, "NPU memory MiB", dashboard.NPU.MemoryMiB, 512)
	wantReading(t, "NPU rate MB/s", dashboard.NPU.BandwidthMBps, 12.5)
	wantReading(t, "DRAM rate GB/s", dashboard.Memory.TotalGBps, 1.25)
	if got := npuFrequency(dashboard.NPU); got != "1.60 GHz of 1.80 GHz" {
		t.Fatalf("NPU frequency = %q", got)
	}
	if got := formatBandwidthGBps(dashboard.Memory.TotalGBps); got != "1.250 GB/s" {
		t.Fatalf("DRAM display = %q", got)
	}
	history := NewHistory(DefaultChartsConfig())
	history.Update(dashboard, fixedNow)
	for metric, want := range map[string]float64{
		"cpu.frequencyMHz":     2400,
		"gpu.frequencyMHz":     750,
		"gpu.vramPercent":      25,
		"gpu.temperatureC":     65,
		"npu.frequencyMHz":     1600,
		"npu.memoryMiB":        512,
		"npu.temperatureC":     75,
		"memory.readGBps":      1,
		"memory.writeGBps":     0.25,
		"memory.bandwidthGBps": 1.25,
	} {
		series := history.Series(metric)
		if len(series) != 1 || len(series[0].Points) != 1 || series[0].Points[0].Value != want {
			t.Errorf("%s = %+v, want %v", metric, series, want)
		}
	}
}

func TestLegacyScaledNamesAreNotAliases(t *testing.T) {
	dashboard := buildFixture(t, `cpu_frequency_avg_frequency 2400000
gpu_frequency_act_freq{gpu_id="0",tile="gt0"} 750
npu_memory_mb 512
npu_frequency 1600000000
memory_bandwidth_total_mibps 1024
`)
	if dashboard.CPU.FrequencyKHz.OK || dashboard.NPU.MemoryMiB.OK ||
		dashboard.NPU.FrequencyHz.OK || dashboard.Memory.TotalGBps.OK ||
		dashboard.GPUs[0].Tiles[0].ActualMHz.OK {
		t.Fatal("legacy unit-bearing series unexpectedly treated as current metrics")
	}
}
