#!/usr/bin/env python3

# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Generator for the unified TCMI hardware-telemetry Grafana dashboard.

Emits dashboards/tcmi-hardware-telemetry.json — the P3 deliverable of
docs/TCMI-INTEGRATION-PROPOSAL.md. Ports TCMI's original T/C/M/I dashboard to
the Metrics Manager metric names (powerstat_*, rapl_power_*, dram_bw_*,
diskio_*, net_*, interrupts_*, gpu_*, npu_*) and adds a 5th row for the new
R = Real-Time Determinism dimension.

Why a generator instead of hand-written JSON: gridPos math and the ~40 repeated
panel/target structures are error-prone by hand; this keeps the layout correct
and the old->new metric mapping in one readable place.

Usage:
    python3 dashboards/generate_dashboard.py [--ds-uid UID] [--out PATH]

The datasource UID defaults to the provisioned Prometheus on the reference
stack; pass --ds-uid to target a different Grafana.
"""

import argparse
import json

# Prometheus datasource UID from the reference stack's Grafana provisioning
# (grafana/provisioning/datasources/prometheus.yml). Override with --ds-uid.
DEFAULT_DS_UID = "PBFA97CFB590B2093"

_panel_id = [0]
_y = [0]  # running vertical cursor for gridPos


def next_id():
    _panel_id[0] += 1
    return _panel_id[0]


def ds(uid):
    return {"type": "prometheus", "uid": uid}


def target(uid, expr, legend=""):
    return {
        "datasource": ds(uid),
        "expr": expr,
        "legendFormat": legend,
        "refId": chr(65 + (next_id() % 26)),
    }


def row(title, uid):
    """A collapsed=false row header spanning the full width."""
    p = {
        "title": title,
        "type": "row",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": _y[0]},
        "id": next_id(),
        "panels": [],
    }
    _y[0] += 1
    return p


def timeseries(title, uid, targets, unit="short", x=0, w=8, h=8, desc="", fill=10):
    p = {
        "title": title,
        "description": desc,
        "type": "timeseries",
        "datasource": ds(uid),
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "id": next_id(),
        "targets": targets,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 1,
                    "fillOpacity": fill,
                    "showPoints": "never",
                    "spanNulls": True,
                },
                "color": {"mode": "palette-classic"},
            },
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "calcs": ["last", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }
    if x + w >= 24:
        _y[0] += h
    return p


def gauge(title, uid, expr, x=0, w=8, h=7, unit="percent",
          thresholds=((0, "green"), (60, "yellow"), (85, "red")), maxv=100, desc=""):
    steps = [{"value": None if v == 0 else v, "color": c} for v, c in thresholds]
    p = {
        "title": title,
        "description": desc,
        "type": "gauge",
        "datasource": ds(uid),
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "id": next_id(),
        "targets": [target(uid, expr, "")],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "max": maxv,
                "thresholds": {"mode": "absolute", "steps": steps},
            },
            "overrides": [],
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
        },
    }
    if x + w >= 24:
        _y[0] += h
    return p


def stat(title, uid, targets, x=0, w=8, h=6, unit="short", desc=""):
    p = {
        "title": title,
        "description": desc,
        "type": "stat",
        "datasource": ds(uid),
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "id": next_id(),
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "thresholds"},
                                     "thresholds": {"mode": "absolute",
                                                    "steps": [{"value": None, "color": "blue"}]}},
                        "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "value", "graphMode": "area", "textMode": "auto"},
    }
    if x + w >= 24:
        _y[0] += h
    return p


def text_panel(title, uid, content, x=0, w=24, h=3):
    p = {
        "title": title,
        "type": "text",
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "id": next_id(),
        "options": {"mode": "markdown", "content": content},
    }
    if x + w >= 24:
        _y[0] += h
    return p


def build(uid):
    # Host filter applied to every query via the $host template variable.
    H = '{host=~"$host"}'
    panels = []

    # ── T — Thermal & Power ───────────────────────────────────────────────
    panels.append(row("T — Thermal & Power", uid))
    panels.append(timeseries(
        "CPU Package + DRAM Power (RAPL = Running Average Power Limit)", uid,
        [target(uid, f'powerstat_package_current_power_consumption_watts{H}', "pkg {{package_id}}"),
         target(uid, f'powerstat_package_current_dram_power_consumption_watts{H}', "dram {{package_id}}")],
        unit="watt", x=0, w=8, desc="CPU package + DRAM RAPL power via intel_powerstat."))
    panels.append(timeseries(
        "Platform (psys) Power — NEW", uid,
        [target(uid, f'rapl_power_power_w{{domain="psys",host=~"$host"}}', "psys"),
         target(uid, f'rapl_power_power_w{{domain="package-0",host=~"$host"}}', "package-0")],
        unit="watt", x=8, w=8,
        desc="Total board power (CPU+iGPU+NPU+mem) from RAPL platform domain. "
             "Filled by the rapl_reader.py execd reader — intel_powerstat cannot see psys."))
    panels.append(timeseries(
        "CPU Temperature (package + per-core)", uid,
        [target(uid, f'temp_temp{{sensor=~"coretemp.*",host=~"$host"}}', "{{sensor}}")],
        unit="celsius", x=16, w=8, desc="coretemp package + per-core, via inputs.temp."))
    panels.append(timeseries(
        "NVMe + Board Temperature", uid,
        [target(uid, f'temp_temp{{sensor=~"nvme.*|acpitz",host=~"$host"}}', "{{sensor}}")],
        unit="celsius", x=0, w=8, desc="NVMe Composite + ACPI board thermal zone."))
    panels.append(timeseries(
        "NPU (Neural Processing Unit) Power / Temperature", uid,
        [target(uid, f'npu_power{H}', "power (W)"),
         target(uid, f'npu_temperature{H}', "temp (°C)"),
         target(uid, f'npu_power_state{H}', "power state (0=D0..4=D3cold)")],
        unit="short", x=8, w=8,
        desc="Intel NPU via PMT = Platform Monitoring Technology (npu_reader.py). "
             "power_state: PCI runtime-PM state, 0=D0 active .. 4=D3cold (−1=unknown)."))
    panels.append(timeseries(
        "Uncore Frequency", uid,
        [target(uid, f'powerstat_package_uncore_frequency_mhz_cur{H}', "uncore {{package_id}}")],
        unit="rothz" if False else "megahertz", x=16, w=8, desc="Current uncore (ring/LLC) frequency."))

    # ── C — Compute ───────────────────────────────────────────────────────
    panels.append(row("C — Compute", uid))
    panels.append(gauge("CPU Busy %", uid, f'100 - cpu_usage_idle{H}', x=0, w=6,
                        desc="100 − idle. Aggregate CPU utilisation."))
    panels.append(gauge("GPU Busy %", uid, f'max by (host) (gpu_engine_usage_usage{H})', x=6, w=6,
                        desc="Max across GPU engines (rcs/ccs/vcs/bcs/vecs) via qmassa."))
    panels.append(gauge("NPU Busy %", uid, f'npu_utilization{H}', x=12, w=6,
                        desc="Intel NPU utilisation via PMT."))
    panels.append(gauge("RAM Used %", uid, f'mem_used_percent{H}', x=18, w=6,
                        thresholds=((0, "green"), (75, "yellow"), (90, "red")),
                        desc="System memory utilisation."))
    panels.append(timeseries(
        "CPU / GPU / NPU Busy % — Time Series", uid,
        [target(uid, f'100 - cpu_usage_idle{H}', "CPU"),
         target(uid, f'max by (host) (gpu_engine_usage_usage{H})', "GPU"),
         target(uid, f'npu_utilization{H}', "NPU")],
        unit="percent", x=0, w=12, desc="Compute utilisation across all three accelerators."))
    panels.append(timeseries(
        "Per-core CPU Frequency", uid,
        [target(uid, f'powerstat_core_cpu_frequency_mhz{H}', "core {{core_id}}/cpu {{cpu_id}}")],
        unit="megahertz", x=12, w=12, desc="Per-core frequency via intel_powerstat."))
    panels.append(timeseries(
        "GPU Frequency (requested vs actual)", uid,
        [target(uid, f'gpu_throttle_driver_freq_mhz{H}', "requested {{card}}/{{gt}}"),
         target(uid, f'gpu_throttle_act_freq_mhz{H}', "actual {{card}}/{{gt}}")],
        unit="megahertz", x=0, w=12,
        desc="Driver-requested (cur_freq) vs achieved (act_freq) GPU frequency per GT, "
             "via gpu_throttle_reader.py. A gap = the GPU couldn't hold the requested clock."))
    panels.append(timeseries(
        "GPU Engine Utilisation (per engine)", uid,
        [target(uid, f'gpu_engine_usage_usage{H}', "{{engine}}")],
        unit="percent", x=12, w=12, desc="Per-engine GPU busy % — MM's per-engine breakdown."))
    panels.append(timeseries(
        "GPU Throttle Reasons (per GT)", uid,
        [target(uid, f'gpu_throttle_throttled{H}', "any {{card}}/{{gt}}"),
         target(uid, f'gpu_throttle_throttle_thermal{H}', "thermal {{card}}/{{gt}}"),
         target(uid, f'gpu_throttle_throttle_pl1{H}', "PL1 {{card}}/{{gt}}"),
         target(uid, f'gpu_throttle_throttle_pl2{H}', "PL2 {{card}}/{{gt}}"),
         target(uid, f'gpu_throttle_throttle_prochot{H}', "PROCHOT {{card}}/{{gt}}")],
        unit="short", x=0, w=12,
        desc="xe DRM throttle flags (1 = actively throttling). 'any' = OR of all reasons; "
             "thermal is the headline for the T envelope. Via gpu_throttle_reader.py."))

    # ── M — Memory ────────────────────────────────────────────────────────
    panels.append(row("M — Memory", uid))
    panels.append(timeseries(
        "DRAM Bandwidth (read/write/total) — NEW", uid,
        [target(uid, f'dram_bw_read_gbps{H}', "read"),
         target(uid, f'dram_bw_write_gbps{H}', "write"),
         target(uid, f'dram_bw_total_gbps{H}', "total")],
        unit="GBs" if False else "decgbytes", x=0, w=12,
        desc="DRAM bandwidth via perf on IMC free-running counters (dram_bw_reader.py). Unit is GB/s."))
    panels.append(timeseries(
        "RAM Used / Available", uid,
        [target(uid, f'mem_used{H}', "used"),
         target(uid, f'mem_total{H} - mem_used{H}', "available")],
        unit="bytes", x=12, w=8, desc="System memory used vs available (auto-scaled)."))
    panels.append(stat(
        "RAM Stats", uid,
        [target(uid, f'mem_total{H}', "total"),
         target(uid, f'mem_used{H}', "used"),
         target(uid, f'mem_used_percent{H}', "used %")],
        x=20, w=4, unit="bytes", desc="Total / used bytes and utilisation."))

    # ── I — I/O Concurrency ───────────────────────────────────────────────
    panels.append(row("I — I/O Concurrency", uid))
    # diskio_io_time is a cumulative ms-busy counter: rate(ms/s)/10 = % busy.
    disk_filter = 'name!~"loop.*|ram.*|dm-.*|sr.*"'
    panels.append(timeseries(
        "Disk Utilisation % (per device)", uid,
        [target(uid, f'rate(diskio_io_time{{{disk_filter},host=~"$host"}}[1m])/10', "{{name}}")],
        unit="percent", x=0, w=8,
        desc="rate(io_time)/10 → %busy. Loop/ram/dm/sr devices filtered."))
    panels.append(timeseries(
        "Disk Throughput (read/write)", uid,
        [target(uid, f'rate(diskio_read_bytes{{{disk_filter},host=~"$host"}}[1m])', "read {{name}}"),
         target(uid, f'rate(diskio_write_bytes{{{disk_filter},host=~"$host"}}[1m])', "write {{name}}")],
        unit="Bps", x=8, w=8, desc="Per-device read/write throughput (auto-scaled to MB/s)."))
    panels.append(timeseries(
        "Device Interrupt (IRQ) Rate (top devices)", uid,
        [target(uid, f'topk(8, sum by (device) (rate(interrupts_total{H}[1m])))', "{{device}}")],
        unit="cps", x=16, w=8,
        desc="Per-device interrupt rate (numeric device IRQs only; housekeeping dropped)."))
    panels.append(timeseries(
        "Network RX Throughput", uid,
        [target(uid, f'rate(net_bytes_recv{H}[1m])', "rx {{interface}}")],
        unit="Bps", x=0, w=12, desc="Per-interface receive throughput (auto-scaled)."))
    panels.append(timeseries(
        "Network TX Throughput", uid,
        [target(uid, f'rate(net_bytes_sent{H}[1m])', "tx {{interface}}")],
        unit="Bps", x=12, w=12, desc="Per-interface transmit throughput (auto-scaled)."))

    # ── R — Real-Time Determinism (NEW dimension) ─────────────────────────
    panels.append(row("R — Real-Time Determinism", uid))
    panels.append(text_panel(
        "About the R dimension", uid,
        "**R = Real-Time Determinism.** The C0-state residency panel below is "
        "always live (from `intel_powerstat`). Every other panel in this row comes "
        "from the opt-in **turbostat** plugin and populates only when "
        "`ENABLE_TURBOSTAT=true` (needs the kernel-matched `linux-tools` package) — "
        "otherwise they read *No data*, which is expected. Acronyms are spelled out "
        "in each panel title. **SMI** (System Management Interrupts) are the #1 "
        "hidden cause of RT latency spikes.",
        x=0, w=24, h=4))

    # Always-on baseline from intel_powerstat (no turbostat needed).
    panels.append(timeseries(
        "CPU C0-state (active) Residency (per core)", uid,
        [target(uid, f'powerstat_core_cpu_c0_state_residency_percent{H}', "core {{core_id}}")],
        unit="percent", x=0, w=12,
        desc="Time each core spent in the active C0 state — a determinism signal "
             "(deep C-states add wake-up latency). Source: intel_powerstat (always on)."))

    # Native inputs.turbostat (Telegraf >=1.36) snake-cases every field and tags
    # each row core/cpu/apic/x2apic; the system-wide summary row carries core="-".
    # Per-core panels filter core!="-"; package/system panels select core="-".
    PC = '{core!="-",host=~"$host"}'   # per-core series only (drops the summary row)
    PKG = '{core="-",host=~"$host"}'   # single system-summary series

    # -- latency-critical interrupt & efficiency signals --
    panels.append(timeseries(
        "Instructions Per Cycle — IPC (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_ipc{PC}', "core {{core}}")],
        unit="short", x=12, w=6,
        desc="IPC = Instructions Per Cycle. High = productive work each cycle; low = "
             "the core is 'busy' but stalled on memory. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "System Management Interrupts — SMI (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_smi{PC}', "core {{core}}")],
        unit="short", x=18, w=6,
        desc="SMI = System Management Interrupt: invisible firmware/BIOS CPU pauses, "
             "the #1 hidden cause of RT latency spikes. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Hardware Interrupts — IRQ (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_irq{PC}', "core {{core}}")],
        unit="short", x=0, w=8,
        desc="IRQ = Interrupt Request count per core over the sample interval. "
             "A core fielding heavy IRQs is a poor RT-thread home. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Non-Maskable Interrupts — NMI (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_nmi{PC}', "core {{core}}")],
        unit="short", x=8, w=8,
        desc="NMI = Non-Maskable Interrupt count per core — cannot be deferred by "
             "the OS. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Per-core Temperature — CoreTmp (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_core_temperature_celsius{PC}', "core {{core}}")],
        unit="celsius", x=16, w=8,
        desc="Per-core die temperature. intel_powerstat is package-level; this "
             "exposes a single hot core (e.g. an RT executor pinned to it). Needs ENABLE_TURBOSTAT."))

    # -- per-core utilisation / frequency / throttle --
    panels.append(timeseries(
        "Per-core Busy % (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_busy_percent{PC}', "core {{core}}")],
        unit="percent", x=0, w=8,
        desc="Fraction of the interval the core ran in C0 (active). Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Per-core Frequency: Average vs Busy MHz (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_average_frequency_mhz{PC}', "avg core {{core}}"),
         target(uid, f'turbostat_busy_frequency_mhz{PC}', "busy core {{core}}")],
        unit="megahertz", x=8, w=8,
        desc="Average MHz (over the whole interval) vs Busy MHz (only while running). "
             "A large gap means the core spent most of the interval idle/throttled. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Core Throttle events — CoreThr (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_core_throttle{PC}', "core {{core}}")],
        unit="short", x=16, w=8,
        desc="Thermal-throttle activations per core. Non-zero = the core hit a "
             "thermal limit and was clocked down. Needs ENABLE_TURBOSTAT."))

    # -- C-state residency detail --
    panels.append(timeseries(
        "CPU Core C-state Residency: C1 / C6 / C7 (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_cpu_percent_c1{PC}', "C1 core {{core}}"),
         target(uid, f'turbostat_cpu_percent_c6{PC}', "C6 core {{core}}"),
         target(uid, f'turbostat_cpu_percent_c7{PC}', "C7 core {{core}}")],
        unit="percent", x=0, w=12,
        desc="Hardware C-state residency per core. Deeper states (C6/C7) save power "
             "but add wake-up latency — the core RT determinism trade-off. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "ACPI C-state Residency: C1 / C2 / C3 (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_c1acpi_percent{PC}', "C1 core {{core}}"),
         target(uid, f'turbostat_c2acpi_percent{PC}', "C2 core {{core}}"),
         target(uid, f'turbostat_c3acpi_percent{PC}', "C3 core {{core}}")],
        unit="percent", x=12, w=12,
        desc="ACPI = Advanced Configuration and Power Interface: the OS-visible "
             "C-state residency per core. Needs ENABLE_TURBOSTAT."))

    # -- package / system-wide (single summary series, core=\"-\") --
    panels.append(timeseries(
        "Power Breakdown — Package / Core / GPU / RAM / System Watts (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_package_power_watt{PKG}', "package"),
         target(uid, f'turbostat_core_power_watt{PKG}', "core"),
         target(uid, f'turbostat_gfx_power_watt{PKG}', "GPU (graphics)"),
         target(uid, f'turbostat_ram_power_watt{PKG}', "RAM"),
         target(uid, f'turbostat_system_power_watt{PKG}', "system (whole platform)")],
        unit="watt", x=0, w=12,
        desc="turbostat's RAPL power domains: package, cores, graphics, RAM and the "
             "whole platform. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Package Deep-Idle Residency: PC2 / PC6 / PC10 (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_package_percent_pc2{PKG}', "PC2"),
         target(uid, f'turbostat_package_percent_pc6{PKG}', "PC6"),
         target(uid, f'turbostat_pk_percent_pc10{PKG}', "PC10")],
        unit="percent", x=12, w=12,
        desc="Package (whole-SoC) deep-idle residency. PC10 is the deepest package "
             "sleep; high PC-state time means the entire SoC idled. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "System C0 (active) Residency: Total / Any-core / GPU (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_totl_percent_c0{PKG}', "total C0"),
         target(uid, f'turbostat_any_percent_c0{PKG}', "any-core C0"),
         target(uid, f'turbostat_gfx_percent_c0{PKG}', "GPU C0")],
        unit="percent", x=0, w=12,
        desc="Aggregate active-state residency: all cores summed, at-least-one-core "
             "active, and GPU active. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Low-Power Idle Residency — LPI: CPU / System (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_cpu_percent_lpi{PKG}', "CPU LPI"),
         target(uid, f'turbostat_system_percent_lpi{PKG}', "System LPI")],
        unit="percent", x=12, w=12,
        desc="LPI = Low-Power Idle, the platform's deepest S0ix-style idle state. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Uncore & TSC Frequency (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_uncore_frequency_mhz{PKG}', "uncore"),
         target(uid, f'turbostat_tsc_frequency_mhz{PC}', "TSC core {{core}}")],
        unit="megahertz", x=0, w=12,
        desc="Uncore (ring / last-level-cache / memory-controller) frequency, plus "
             "TSC = Time Stamp Counter reference frequency. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "Package Temperature — PkgTmp (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_package_temperature_celsius{PKG}', "package")],
        unit="celsius", x=12, w=12,
        desc="Package-level temperature reported by turbostat. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "POLL Residency + CPU-GFX / RAM overlap (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_poll_percent{PC}', "POLL core {{core}}"),
         target(uid, f'turbostat_cpu_gfx_percent{PKG}', "CPU+GFX C0"),
         target(uid, f'turbostat_ram_percent{PKG}', "RAM throttle %")],
        unit="percent", x=0, w=12,
        desc="POLL = the shallow spin-idle state (no power saving, lowest wake "
             "latency). CPU+GFX = fraction where both CPU and graphics were active; "
             "RAM % = memory RAPL throttle. Needs ENABLE_TURBOSTAT."))

    return panels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds-uid", default=DEFAULT_DS_UID, help="Prometheus datasource UID")
    ap.add_argument("--out", default=None, help="output path (default: alongside this script)")
    args = ap.parse_args()

    uid = args.ds_uid
    panels = build(uid)

    dashboard = {
        "title": "Intel TCMI Hardware Telemetry (Metrics Manager)",
        "description": "Unified T/C/M/I + R hardware telemetry for robotics / Edge AI / physical AI "
                       "on Intel platforms, served by the Metrics Manager microservice.",
        "uid": "tcmi-mm-unified-v1",
        "tags": ["tcmi", "metrics-manager", "intel", "hardware-telemetry"],
        "editable": True,
        "graphTooltip": 1,  # shared crosshair
        "time": {"from": "now-15m", "to": "now"},
        "refresh": "5s",
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "templating": {
            "list": [
                {
                    "name": "host",
                    "label": "Host",
                    "type": "query",
                    "datasource": ds(uid),
                    "definition": "label_values(mem_used_percent, host)",
                    "query": {"query": "label_values(mem_used_percent, host)", "refId": "hostVar"},
                    "refresh": 2,
                    "includeAll": True,
                    "allValue": ".*",
                    "multi": False,
                    "current": {"text": "All", "value": "$__all"},
                }
            ]
        },
        "panels": panels,
    }

    out = args.out or __file__.rsplit("/", 1)[0] + "/tcmi-hardware-telemetry.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
        f.write("\n")
    print(f"wrote {out} ({len(panels)} panels, ds-uid={uid})")


if __name__ == "__main__":
    main()
