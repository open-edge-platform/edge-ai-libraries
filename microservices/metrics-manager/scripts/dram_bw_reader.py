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
Long-running telegraf execd input plugin: DRAM read/write bandwidth (GB/s) from
the Intel IMC uncore free-running counters, via `perf stat`.

Fills TCMI's dram_read_gbps / dram_write_gbps gap without the external Intel PCM
binary. Chosen over the native inputs.intel_pmu plugin because the PTL target
reports a MASKED CPU model ("Genuine Intel(R) 0000", ES/QS silicon): intel_pmu
resolves named events (UNC_M_CAS_COUNT.*) through a model-keyed perfmon JSON, so
name lookup fails there. `perf stat` on RAW free-running event codes is
model-independent and was verified counting on the target (116.6 / 7.4 MiB in 1s).

Counters (probed on PTL, perf type = uncore_imc_free_running):
  data_read / data_write — the sysfs event ALIASES the IMC free-running PMU
  publishes under events/ (raw encodings event=0xff,umask=0x20 / 0x30). Using
  the named aliases (not raw codes) is deliberate: perf then applies the driver's
  per.unit scale and reports the result already in MiB, and — crucially — the
  aliases live in sysfs, NOT in the model-keyed perfmon JSON, so they resolve
  even on the masked-model PTL silicon. We read the MiB totals over a fixed
  window and divide by the window to get bandwidth.

Emits once per INTERVAL_S:
  dram_bw,host=<h> read_gbps=12.34,write_gbps=1.23,total_gbps=13.57 <ts>

Requires: `perf` on PATH, perf_event_paranoid <= 0 (PTL is -1), and the IMC
free-running PMU exposed. Runs fine in the --privileged container. If any of
that is missing, the reader idles quietly instead of hot-looping under execd.
"""

import os
import re
import shutil
import subprocess
import time
import logging

HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
INTERVAL_S = float(os.environ.get("DRAM_BW_INTERVAL", "1"))
IDLE_SLEEP_S = 3600
PMU = "uncore_imc_free_running"
# Named sysfs aliases (model-independent, auto-scaled to MiB by perf). Raw
# equivalents are event=0xff,umask=0x20 (read) / 0x30 (write), 64 B/count.
READ_EVENT = f"{PMU}/data_read/"
WRITE_EVENT = f"{PMU}/data_write/"
DEBUG_LOG = "/app/dram_bw_reader_trace.log"

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
    """Park the process when DRAM-BW counting is unavailable (mirrors npu_reader.py)."""
    logger.warning("dram_bw reader entering idle mode: %s", reason)
    while True:
        time.sleep(IDLE_SLEEP_S)


def _pmu_available() -> bool:
    # The IMC free-running PMU is exposed as NUMBERED instances
    # (uncore_imc_free_running_0, _1, ...), while perf's event spec uses the
    # un-numbered PMU name to aggregate across them. Match on the prefix.
    devices = "/sys/bus/event_source/devices"
    try:
        return any(name.startswith(PMU) for name in os.listdir(devices))
    except OSError:
        return False


def _parse_perf_value(stderr_text: str, event: str) -> float:
    """Extract the numeric count for one event from `perf stat -x,` CSV stderr.

    perf stat -x, prints one CSV line per event:
        <count>,<unit>,<event_name>,<run_time_ns>,<pct>,...
    The count for the IMC free-running events may already be in MiB (the driver's
    native unit); we detect the unit column and normalize to bytes.

    Matching is done on the event token (e.g. "data_read") — perf echoes the
    requested event string in column 3, which uniquely identifies read vs write.
    """
    # The distinguishing token is the alias name, e.g. "data_read"/"data_write".
    m = re.search(r"/([A-Za-z0-9_]+)/", event)
    token = m.group(1) if m else event

    total_bytes = 0.0
    matched = False
    for line in stderr_text.splitlines():
        line = line.strip()
        if not line or token not in line:
            continue
        cols = line.split(",")
        if len(cols) < 3:
            continue
        raw = cols[0].strip()
        unit = cols[1].strip()
        if raw in ("<not counted>", "<not supported>", ""):
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        # Normalize the driver's reported unit to bytes.
        u = unit.lower()
        if u in ("mib", "mb"):
            val *= 1024 * 1024
        elif u in ("kib", "kb"):
            val *= 1024
        # else assume already bytes
        total_bytes += val
        matched = True
    return total_bytes if matched else -1.0


def sample_once() -> str:
    """Run one perf-stat window and return an InfluxDB line, or "" on failure."""
    cmd = [
        "perf", "stat", "-x", ",", "-a",
        "-e", READ_EVENT,
        "-e", WRITE_EVENT,
        "--", "sleep", str(INTERVAL_S),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=INTERVAL_S + 10
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("perf stat failed: %s", exc)
        return ""

    read_bytes = _parse_perf_value(proc.stderr, READ_EVENT)
    write_bytes = _parse_perf_value(proc.stderr, WRITE_EVENT)
    if read_bytes < 0 and write_bytes < 0:
        logger.warning("perf produced no counts; stderr=%s", proc.stderr.strip()[:400])
        return ""

    read_bytes = max(read_bytes, 0.0)
    write_bytes = max(write_bytes, 0.0)
    # bytes over the window -> GB/s (decimal GB, matching TCMI's dram_*_gbps).
    read_gbps = read_bytes / INTERVAL_S / 1e9
    write_gbps = write_bytes / INTERVAL_S / 1e9
    total_gbps = read_gbps + write_gbps
    ts_ns = time.time_ns()
    return (
        f"dram_bw,host={HOSTNAME} "
        f"read_gbps={read_gbps:.4f},write_gbps={write_gbps:.4f},"
        f"total_gbps={total_gbps:.4f} {ts_ns}"
    )


def main():
    if shutil.which("perf") is None:
        idle_forever("perf binary not found on PATH (install linux-tools)")
    if not _pmu_available():
        idle_forever(f"{PMU} PMU not exposed under /sys/bus/event_source/devices")

    # Probe once; if perf can't count these events at all, idle rather than loop.
    first = sample_once()
    if not first:
        idle_forever("perf could not count IMC free-running events (paranoid/perms?)")
    print(first, flush=True)

    while True:
        # sample_once() already blocks for INTERVAL_S via `sleep`, so no extra
        # sleep is needed — the perf window IS the cadence.
        line = sample_once()
        if line:
            print(line, flush=True)
            logger.debug("%s", line)


if __name__ == "__main__":
    main()
