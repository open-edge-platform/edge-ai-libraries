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
        "CPU Package + DRAM Power (RAPL)", uid,
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
        "NPU Power / Temperature", uid,
        [target(uid, f'npu_power{H}', "power (W)"),
         target(uid, f'npu_temperature{H}', "temp (°C)")],
        unit="short", x=8, w=8, desc="Intel NPU via PMT (npu_reader.py)."))
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
        "GPU Frequency (current vs actual)", uid,
        [target(uid, f'gpu_frequency{{type="cur_freq",host=~"$host"}}', "requested"),
         target(uid, f'gpu_frequency{{type="act_freq",host=~"$host"}}', "actual")],
        unit="megahertz", x=0, w=12, desc="Requested vs actual GPU frequency (throttle indicator)."))
    panels.append(timeseries(
        "GPU Engine Utilisation (per engine)", uid,
        [target(uid, f'gpu_engine_usage_usage{H}', "{{engine}}")],
        unit="percent", x=12, w=12, desc="Per-engine GPU busy % — MM's per-engine breakdown."))

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
        "Device IRQ Rate (top devices)", uid,
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
        "always live (from `intel_powerstat`). The **IPC / SMI / per-core** panels "
        "populate only when the opt-in turbostat reader is enabled "
        "(`ENABLE_TURBOSTAT=true`, requires the kernel-matched `linux-tools` "
        "package) — otherwise they read *No data*, which is expected. "
        "SMI (System Management Interrupts) are the #1 hidden cause of RT latency spikes.",
        x=0, w=24, h=3))
    panels.append(timeseries(
        "CPU C0-state Residency (per core)", uid,
        [target(uid, f'powerstat_core_cpu_c0_state_residency_percent{H}', "core {{core_id}}")],
        unit="percent", x=0, w=12,
        desc="Time in the active C0 state per core — a determinism signal (deep C-states add wake latency)."))
    panels.append(timeseries(
        "Per-core IPC (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_IPC{{scope="core",host=~"$host"}}', "core {{core}}")],
        unit="short", x=12, w=6,
        desc="Instructions per cycle — distinguishes 'busy' from 'stalled on memory'. Needs ENABLE_TURBOSTAT."))
    panels.append(timeseries(
        "SMI count (turbostat, opt-in)", uid,
        [target(uid, f'turbostat_SMI{{host=~"$host"}}', "{{scope}} {{core}}")],
        unit="short", x=18, w=6,
        desc="System Management Interrupts — firmware CPU pauses. Needs ENABLE_TURBOSTAT."))

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
