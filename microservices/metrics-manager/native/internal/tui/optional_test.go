// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package tui

import (
	"reflect"
	"regexp"
	"strings"
	"testing"
)

const optionalExposition = `temp_highres_temp{host="itest",sensor="coretemp_package_id_0"} 45
temp_highres_temp_min{host="itest",sensor="coretemp_package_id_0"} 40
temp_highres_temp_max{host="itest",sensor="coretemp_package_id_0"} 54
temp_highres_temp_mean{host="itest",sensor="coretemp_package_id_0"} 47
temp_highres_temp_max{host="itest",sensor="coretemp_core_id_0"} 99
powerstat_package_current_dram_power_consumption_watts{host="itest",package_id="0"} 1.5
powerstat_core_cpu_frequency_mhz{host="itest",cpu_id="0"} 2000
powerstat_core_cpu_temperature_celsius{host="itest",cpu_id="0"} 52
interrupts_total{host="itest",irq="42",device="nvme0q1"} 1234
ethtool_rx_errors{host="itest",interface="enp1s0"} 3
`

func TestOptionalPanelsAppearOnlyWithSamples(t *testing.T) {
	baseline := buildFixture(t, hostExposition)
	if len(baseline.Optional) != 0 {
		t.Fatalf("baseline unexpectedly has optional panels: %+v", baseline.Optional)
	}
	view := renderFixture(t, hostExposition)
	for _, title := range []string{"Package temperature (100 ms)", "RAPL power", "DRAM power", "Per-CPU telemetry",
		"Device interrupts (counters)", "NIC driver enp1s0"} {
		if strings.Contains(view, title) {
			t.Errorf("baseline contains opt-in panel %q", title)
		}
	}

	view = renderFixture(t, hostExposition+optionalExposition)
	for _, want := range []string{
		"Package temperature (100 ms)", "54.00 °C", "DRAM power", "1.50 W",
		"Per-CPU telemetry", "frequency", "temperature", "CPU 0", "2000.00 MHz", "52.00 °C",
		"Device interrupts (counters)", "IRQ 42 nvme0q1", "1234.00",
		"NIC driver enp1s0", "rx_errors",
	} {
		wantContains(t, view, want)
	}
	if strings.Contains(view, "99.00 °C") {
		t.Error("non-package sensor leaked into optional temperature panel")
	}
}

func TestRAPLPanelRequiresSamplesAndShowsDomains(t *testing.T) {
	exposition := hostExposition + `rapl_power_power_w{host="itest",domain="psys"} 9.83
rapl_power_power_w{host="itest",domain="package-0"} 6.51
`
	dashboard := buildFixture(t, exposition)
	var rows []OptionalRow
	for _, panel := range dashboard.Optional {
		if panel.Title == "RAPL power" {
			rows = panel.Rows
		}
	}
	if want := []OptionalRow{
		{Label: "package-0", Value: "6.51 W"},
		{Label: "psys", Value: "9.83 W"},
	}; !reflect.DeepEqual(rows, want) {
		t.Errorf("RAPL panel rows = %+v, want %+v", rows, want)
	}
	view := renderFixture(t, exposition)
	wantContains(t, view, "RAPL power")
	wantContains(t, view, "psys")
}

func TestMemoryPanelShowsDRAMBandwidthColumnsOnlyWithSamples(t *testing.T) {
	baseline := buildFixture(t, hostExposition)
	for _, panel := range baseline.Optional {
		if panel.Title == "DRAM bandwidth" {
			t.Fatal("DRAM bandwidth should be part of Memory, not an optional panel")
		}
	}
	if strings.Contains(renderFixture(t, hostExposition), "DRAM bandwidth") {
		t.Fatal("Memory contains an empty DRAM bandwidth row")
	}

	exposition := hostExposition + `memory_bandwidth_read_bytes_per_second{host="itest"} 2147483648
memory_bandwidth_write_bytes_per_second{host="itest"} 134217728
memory_bandwidth_total_bytes_per_second{host="itest"} 2281701376
`
	dash := buildFixture(t, exposition)
	if len(dash.Optional) != 0 {
		t.Fatalf("bandwidth created an optional panel: %+v", dash.Optional)
	}
	view := renderFixture(t, exposition)
	for _, want := range []string{"Memory", "DRAM bandwidth", "read", "write", "total"} {
		wantContains(t, view, want)
	}
	if !regexp.MustCompile(`DRAM bandwidth\s+2\.147 GB/s\s+0\.134 GB/s\s+2\.282 GB/s`).MatchString(view) {
		t.Errorf("Memory DRAM row missing or values in wrong columns:\n%s", view)
	}

	partial := renderFixture(t, "memory_bandwidth_write_bytes_per_second 0\n")
	if !regexp.MustCompile(`DRAM bandwidth\s+-\s+0\.000 GB/s\s+-`).MatchString(partial) {
		t.Errorf("missing bandwidth reading not shown in its column:\n%s", partial)
	}
	for _, panel := range buildFixture(t, "memory_bandwidth_write_bytes_per_second 0\n").Optional {
		if panel.Title == "DRAM bandwidth" {
			t.Fatal("partial bandwidth created a second panel")
		}
	}
}

func TestPerCPUTelemetryRowsKeepMissingValuesInTheirColumns(t *testing.T) {
	view := renderFixture(t, `powerstat_core_cpu_frequency_mhz{cpu_id="10"} 2000
powerstat_core_cpu_temperature_celsius{cpu_id="8"} 42
powerstat_core_cpu_frequency_mhz{cpu_id="1"} 0
powerstat_core_cpu_temperature_celsius{cpu_id="1"} 51
`)

	patterns := []string{
		`CPU 1\s+0\.00 MHz\s+51\.00 °C`,
		`CPU 8\s+-\s+42\.00 °C`,
		`CPU 10\s+2000\.00 MHz\s+-`,
	}
	previous := -1
	for _, pattern := range patterns {
		location := regexp.MustCompile(pattern).FindStringIndex(view)
		if location == nil {
			t.Errorf("missing CPU row matching %q", pattern)
			continue
		}
		if location[0] <= previous {
			t.Errorf("CPU rows not sorted numerically: %q", pattern)
		}
		previous = location[0]
	}
}

func TestTurbostatPanelRequiresSamples(t *testing.T) {
	baseline := renderFixture(t, hostExposition)
	if strings.Contains(baseline, "Turbostat") {
		t.Fatal("turbostat panel is visible without samples")
	}

	view := renderFixture(t, hostExposition+`turbostat_ipc{host="itest",core="0",cpu="8"} 1.24
turbostat_smi{host="itest",core="-",cpu="-"} 3
`)
	wantContains(t, view, "Turbostat")
	wantContains(t, view, "IPC CPU 8")
	wantContains(t, view, "SMI system")
}

func TestTurbostatIRQAndNMITable(t *testing.T) {
	exposition := `turbostat_irq{cpu="10",core="3"} 45
turbostat_nmi{cpu="2",core="1"} 0
turbostat_irq{cpu="8",core="0"} 12
turbostat_nmi{cpu="8",core="0"} 3
turbostat_irq{cpu="-",core="-"} 57
turbostat_nmi{core="4"} 1
turbostat_ipc{cpu="8",core="0"} 1.5
turbostat_smi{cpu="-",core="-"} 2
`
	panel := buildTurbostatPanel(NewIndex(parseFixture(t, exposition)))
	var gotColumns []string
	for _, column := range panel.TableColumns {
		gotColumns = append(gotColumns, column.title)
	}
	if want := []string{"CPU", "IRQ", "NMI"}; !reflect.DeepEqual(gotColumns, want) {
		t.Errorf("table columns = %v, want %v", gotColumns, want)
	}
	wantRows := [][]string{
		{"CPU 2", "-", "0"},
		{"CPU 8", "12", "3"},
		{"CPU 10", "45", "-"},
		{"core 4", "-", "1"},
		{"system", "57", "-"},
	}
	if !reflect.DeepEqual(panel.TableRows, wantRows) {
		t.Errorf("table rows = %v, want %v", panel.TableRows, wantRows)
	}

	view := renderFixture(t, exposition)
	wantContains(t, view, "IRQ")
	wantContains(t, view, "NMI")
	wantContains(t, view, "IPC CPU 8")
	wantContains(t, view, "SMI system")
}

func TestNPUPowerStateInPanel(t *testing.T) {
	baseline := renderFixture(t, acceleratorExposition)
	if strings.Contains(baseline, "power state") {
		t.Fatal("NPU power state is visible before a collector publishes it")
	}
	view := renderFixture(t, acceleratorExposition+"npu_power_state{host=\"itest\"} 3\n")
	wantContains(t, view, "power state")
	wantContains(t, view, "D3hot")
	view = renderFixture(t, acceleratorExposition+"npu_power_state{host=\"itest\"} -1\n")
	wantContains(t, view, "unknown")
}
