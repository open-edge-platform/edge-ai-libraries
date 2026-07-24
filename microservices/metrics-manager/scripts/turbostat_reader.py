#!/usr/bin/env python3

# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Long-running telegraf execd input plugin wrapping Intel `turbostat`.

turbostat is the engineering microscope for real-time tuning that
intel_powerstat cannot provide: per-core IPC, SMI (System Management
Interrupts — the #1 hidden cause of RT latency spikes), per-core IRQ counts,
and per-core temperature. This maps to the proposed 5th TCMI dimension:
R = Real-Time Determinism.

turbostat's native output is a whitespace-aligned table, one block per
interval, NOT a Telegraf-parseable format. This wrapper spawns turbostat once
with `--interval`, parses each block's header + rows, and emits InfluxDB line
protocol on stdout:

  Summary (aggregate) row -> whole-package view:
    turbostat,host=<h>,scope=package Busy%=3.2,Bzy_MHz=3100,IPC=0.85,\
      SMI=0i,IRQ=5123i,CoreTmp=54,PkgTmp=55,PkgWatt=6.5 <ts>
  Per-core rows -> pinpoint a hot / stalled / SMI-hit core:
    turbostat,host=<h>,scope=core,core=3,cpu=6 Busy%=98.1,IPC=1.9,... <ts>

Requires: `turbostat` on PATH (linux-tools) and MSR access (--privileged + the
`msr` kernel module; the container already runs privileged with -v /sys and
--pid host). If turbostat is absent or MSRs are unreadable, the reader idles
quietly instead of letting execd restart it in a tight loop.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import logging

HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
# Lower cadence than the 1s production inputs: MSR reads are not free and
# per-core series would otherwise flood Grafana with redundant points.
INTERVAL_S = os.environ.get("TURBOSTAT_INTERVAL", "5")
IDLE_SLEEP_S = 3600
DEBUG_LOG = "/app/turbostat_reader_trace.log"

# Columns worth shipping. turbostat prints many more; we keep the R-dimension
# set. Only columns actually present in the header are emitted, so this list is
# a superset that degrades gracefully across turbostat versions / SKUs.
SHOW_COLUMNS = [
    "Core", "CPU", "Busy%", "Bzy_MHz", "TSC_MHz", "IPC", "IRQ", "SMI",
    "CoreTmp", "PkgTmp", "PkgWatt", "CorWatt", "GFXWatt", "RAMWatt",
    "Pkg%pc6", "Pkg%pc10", "CPU%c1", "CPU%c6", "CPU%c7",
]
# Fields that are integer counters in turbostat; emit them with an `i` suffix
# so InfluxDB/Prometheus treats them as integers, not floats.
INT_FIELDS = {"IRQ", "SMI", "POLL", "C1", "C1E", "C6", "C7s"}
# Columns that identify the row rather than carry a measurement.
TAG_COLUMNS = {"Core", "CPU"}

file_handler = logging.FileHandler(DEBUG_LOG)
file_handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers = [file_handler]


def idle_forever(reason: str) -> None:
    """Park the process when turbostat is unusable (mirrors npu_reader.py)."""
    logger.warning("turbostat reader entering idle mode: %s", reason)
    while True:
        time.sleep(IDLE_SLEEP_S)


def _escape_tag(value: str) -> str:
    # InfluxDB line-protocol tag escaping: space, comma, equals.
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _looks_like_header(fields):
    # turbostat repeats the header each interval; the header row always has the
    # literal column names, so detect it by the presence of a known label.
    return "Busy%" in fields or "Bzy_MHz" in fields or ("Core" in fields and "CPU" in fields)


def _emit_row(header, fields):
    """Turn one parsed data row into an InfluxDB line-protocol string, or None."""
    if len(fields) != len(header):
        # Ragged row (turbostat sometimes prints blank separator lines) — skip.
        return None
    row = dict(zip(header, fields))

    core = row.get("Core", "")
    cpu = row.get("CPU", "")
    # turbostat's aggregate/summary row uses "-" for Core and CPU.
    is_summary = core in ("-", "") and cpu in ("-", "")

    tags = [f"host={_escape_tag(HOSTNAME)}"]
    if is_summary:
        tags.append("scope=package")
    else:
        tags.append("scope=core")
        if core not in ("-", ""):
            tags.append(f"core={_escape_tag(core)}")
        if cpu not in ("-", ""):
            tags.append(f"cpu={_escape_tag(cpu)}")

    field_parts = []
    for col, raw in row.items():
        if col in TAG_COLUMNS:
            continue
        if raw in ("-", ""):
            continue
        try:
            num = float(raw)
        except ValueError:
            continue  # non-numeric cell, skip
        if col in INT_FIELDS:
            field_parts.append(f"{_escape_field_key(col)}={int(num)}i")
        else:
            field_parts.append(f"{_escape_field_key(col)}={num}")

    if not field_parts:
        return None
    ts_ns = time.time_ns()
    return f"turbostat,{','.join(tags)} {','.join(field_parts)} {ts_ns}"


def _escape_field_key(key: str) -> str:
    # Field keys share tag-escaping rules; '%' is legal but keep it readable.
    return key.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def build_command():
    show = ",".join(SHOW_COLUMNS)
    # --quiet suppresses the config banner; --show curates the columns; --interval
    # streams a fresh block every INTERVAL_S seconds.
    return ["turbostat", "--quiet", "--show", show, "--interval", str(INTERVAL_S)]


def main():
    if shutil.which("turbostat") is None:
        idle_forever("turbostat binary not found on PATH (install linux-tools)")

    cmd = build_command()
    logger.info("launching: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        idle_forever(f"failed to launch turbostat: {exc}")

    # If turbostat dies immediately (no MSR access), don't hot-loop under execd.
    header = None
    got_any_data = False
    start = time.monotonic()

    assert proc.stdout is not None
    for line in proc.stdout:
        fields = line.split()
        if not fields:
            continue
        if _looks_like_header(fields):
            header = fields
            logger.info("turbostat header: %s", header)
            continue
        if header is None:
            continue
        lp = _emit_row(header, fields)
        if lp is not None:
            print(lp, flush=True)
            got_any_data = True

    # turbostat exited. Capture why and idle rather than let execd respawn it.
    rc = proc.wait()
    err = ""
    if proc.stderr is not None:
        err = proc.stderr.read().strip()
    elapsed = time.monotonic() - start
    if not got_any_data and elapsed < 10:
        idle_forever(f"turbostat exited rc={rc} in {elapsed:.1f}s without data: {err}")
    logger.warning("turbostat exited rc=%s after %.0fs: %s", rc, elapsed, err)
    # Fall through: returning lets execd restart us for a fresh stream, which is
    # correct once we've proven turbostat produces data.


if __name__ == "__main__":
    main()
