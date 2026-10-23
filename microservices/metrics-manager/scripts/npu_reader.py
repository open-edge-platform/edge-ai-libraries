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
Long-running telegraf execd input plugin that reads NPU telemetry via PmtTelemetry
and emits InfluxDB line protocol metrics to stdout once per second.
"""

import os
import sys
import time
import logging

# Re-use the PmtTelemetry class from the npu-monitor-tool script.
# The script is installed alongside this reader in /app.
sys.path.insert(0, '/app')
from npu_monitor_tool import PmtTelemetry  # noqa: E402

# Hostname used in the `host=` tag of every emitted line. Defaults to the
# kernel hostname (matches Telegraf's default behaviour) but can be overridden
# with METRICS_MANAGER_HOSTNAME so dashboards keep a stable label across
# reboots / container restarts where the kernel hostname may change.
HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
INTERVAL_S = 1.0
# When NPU hardware is not present, sleep for this long between idle wake-ups
# instead of restarting the process every Telegraf execd retry (~10s). This
# keeps the Telegraf log quiet on hosts without an Intel NPU.
IDLE_SLEEP_S = 3600
DEBUG_LOG = os.environ.get("NPU_READER_LOG_FILE", "/app/npu_reader_trace.log")

# PmtTelemetry.get_noc_bandwidth() reads a 32-bit hardware counter (bits
# 31:0) scaled by /1e3. When the raw counter wraps around 2**32 the scaled
# delta goes negative; add back the full counter's scaled range to correct
# for the rollover before converting the delta into a MB/s rate.
NPU_BANDWIDTH_COUNTER_MAX_MB = (2 ** 32) / 1e3

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
    """Park the process when no NPU is present.

    Telegraf's ``execd`` input restarts a child that exits within ~10s, which
    floods logs on hosts without an Intel NPU. Instead of ``sys.exit(1)`` we
    log the reason once and sleep, keeping the process alive but quiet so
    other Telegraf inputs (CPU, RAM, GPU, temperature) are unaffected.
    """
    logger.warning("NPU reader entering idle mode: %s", reason)
    while True:
        time.sleep(IDLE_SLEEP_S)


def find_npu_dev_path() -> str:
    """Locate the sysfs PCI device path for the intel_vpu driver."""
    base = "/sys/bus/pci/drivers/intel_vpu/"
    if not os.path.exists(base):
        idle_forever(f"Intel NPU driver path not found: {base}")
    for entry in os.listdir(base):
        if entry.startswith("0000:"):
            return os.path.join(base, entry)
    idle_forever(f"No 0000: device found under {base}")
    return ""  # unreachable, keeps type checkers happy


def compute_npu_sample(
    *,
    elapsed_s: float,
    curr_energy: float,
    prev_energy: float,
    curr_bandwidth_mb: float,
    prev_bandwidth_mb: float,
    freq_mhz: float,
    temp_c: int,
    tile_config: int,
    curr_busy_us: int | None,
    prev_busy_us: int | None,
    mem_util_bytes: int | None,
) -> dict:
    """Compute one NPU telemetry sample from consecutive raw PMT reads.

    Pure function (no file or sysfs I/O) so it can be unit tested without
    real NPU hardware. Returns a dict of InfluxDB field name -> value.

    ``utilization`` is left out of the result (instead of a misleading
    ``0``) when ``curr_busy_us``/``prev_busy_us`` are ``None`` — i.e. when
    ``npu_busy_time_us`` isn't exposed on this platform. Likewise
    ``memory_mb`` is left out (instead of a sentinel ``-1``) when
    ``mem_util_bytes`` is ``None`` — i.e. when the memory-utilization sysfs
    node isn't supported (pre-PTL platforms).

    Args:
        elapsed_s: Actual wall-clock seconds since the previous sample
            (not the nominal sleep interval — polling jitter matters for
            rate calculations).
        curr_energy, prev_energy: ``PmtTelemetry.get_npu_energy()`` reads
            (joules), used to derive power (W).
        curr_bandwidth_mb, prev_bandwidth_mb: ``PmtTelemetry.get_noc_bandwidth()``
            reads. These are scaled readings of a 32-bit hardware counter,
            so a negative delta means the counter wrapped and is corrected
            via ``NPU_BANDWIDTH_COUNTER_MAX_MB``.
        freq_mhz: ``PmtTelemetry.get_freq()`` read, already in MHz.
        temp_c: ``PmtTelemetry.get_npu_temperature()`` read.
        tile_config: ``PmtTelemetry.get_tile_config()`` read.
        curr_busy_us, prev_busy_us: consecutive reads of
            ``npu_busy_time_us``, or ``None`` when unsupported.
        mem_util_bytes: raw ``npu_memory_utilization`` read in bytes, or
            ``None`` when unsupported/unavailable.

    Raises:
        ValueError: if ``elapsed_s`` is not strictly positive.
    """
    if elapsed_s <= 0:
        raise ValueError("elapsed_s must be > 0")

    # Power (W) — use actual elapsed time, not the nominal sleep interval.
    power_w = (curr_energy - prev_energy) / elapsed_s

    # NoC bandwidth rate (MB/s). A negative delta means the underlying
    # 32-bit counter wrapped around; correct it before converting to a rate.
    bandwidth_delta_mb = curr_bandwidth_mb - prev_bandwidth_mb
    if bandwidth_delta_mb < 0:
        bandwidth_delta_mb += NPU_BANDWIDTH_COUNTER_MAX_MB
    bandwidth_mbs = bandwidth_delta_mb / elapsed_s

    fields: dict = {
        "power": power_w,
        # Renamed from a mislabeled pseudo-Hz value to the true display
        # frequency in MHz. The InfluxDB field key stays "frequency" (and
        # the Prometheus metric stays npu_frequency) so existing
        # dashboards/queries keep working; only the unit/magnitude changes.
        "frequency": freq_mhz,
        "temperature": temp_c,
        "bandwidth": bandwidth_mbs,
        "tile_config": tile_config,
    }

    if curr_busy_us is not None and prev_busy_us is not None:
        delta_us = curr_busy_us - prev_busy_us
        interval_us = elapsed_s * 1_000_000
        fields["utilization"] = min(100, int(100 * delta_us / interval_us))
    # else: npu_busy_time_us unsupported on this platform — omit the field
    # rather than reporting a fake 0.

    if mem_util_bytes is not None:
        fields["memory_mb"] = mem_util_bytes / 1024 / 1024
    # else: npu_memory_utilization unsupported on this platform (pre-PTL)
    # — omit the field rather than reporting a fake -1.

    return fields


def format_line_protocol(host: str, fields: dict, ts_ns: int) -> str:
    """Render one NPU sample as an InfluxDB line-protocol measurement.

    Fields absent from ``fields`` (``utilization`` / ``memory_mb`` on
    unsupported platforms, see :func:`compute_npu_sample`) are simply left
    out of the line instead of being sent as a fake ``0`` / ``-1``.
    """
    parts = [
        f"power={fields['power']:.3f}",
        f"frequency={fields['frequency']:.1f}",
        f"temperature={fields['temperature']}i",
        f"bandwidth={fields['bandwidth']:.3f}",
        f"tile_config={fields['tile_config']}i",
    ]
    if "utilization" in fields:
        parts.append(f"utilization={fields['utilization']}i")
    if "memory_mb" in fields:
        parts.append(f"memory_mb={fields['memory_mb']:.2f}")
    return f"npu,host={host} " + ",".join(parts) + f" {ts_ns}"


def main():
    try:
        pu = PmtTelemetry()
    except SystemExit as e:
        idle_forever(f"PmtTelemetry initialisation failed (no NPU?): {e}")
        return

    dev_path = find_npu_dev_path()

    # npu_busy_time_us is a monotonically increasing counter in microseconds
    busy_path = os.path.join(dev_path, "npu_busy_time_us")
    npu_busy_supported = os.path.exists(busy_path)
    if not npu_busy_supported:
        logger.warning(
            "npu_busy_time_us not found at %s; utilization will be omitted",
            busy_path,
        )

    # Memory utilization is only available on PTL and later
    from npu_monitor_tool import CpuGen  # noqa: E402
    mem_util_supported = (pu.cpu_gen is not None) and (pu.cpu_gen >= CpuGen.PTL)
    mem_util_path = os.path.join(dev_path, "npu_memory_utilization")
    if not mem_util_supported:
        logger.info(
            "npu_memory_utilization not supported on %s; memory_mb will be omitted",
            pu.cpu_gen,
        )

    def read_busy_us() -> int | None:
        if not npu_busy_supported:
            return None
        try:
            with open(busy_path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except (OSError, ValueError) as e:
            logger.warning("Failed to read npu_busy_time_us: %s", e)
            return None

    def read_mem_util_bytes() -> int | None:
        if not mem_util_supported or not os.path.exists(mem_util_path):
            return None
        try:
            with open(mem_util_path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except (OSError, ValueError) as e:
            logger.warning("Failed to read npu_memory_utilization: %s", e)
            return None

    pu.update_buffer()
    prev_energy = pu.get_npu_energy()
    prev_bandwidth = pu.get_noc_bandwidth()
    prev_busy_us = read_busy_us()
    prev_ts = time.monotonic()

    while True:
        time.sleep(INTERVAL_S)
        try:
            pu.update_buffer()
        except SystemExit as e:
            logger.error("Failed to update telemetry buffer: %s", e)
            time.sleep(INTERVAL_S)
            continue

        curr_ts = time.monotonic()
        elapsed_s = curr_ts - prev_ts
        prev_ts = curr_ts

        ts_ns = time.time_ns()

        curr_energy = pu.get_npu_energy()
        curr_bandwidth = pu.get_noc_bandwidth()
        curr_busy_us = read_busy_us()

        fields = compute_npu_sample(
            elapsed_s=elapsed_s,
            curr_energy=curr_energy,
            prev_energy=prev_energy,
            curr_bandwidth_mb=curr_bandwidth,
            prev_bandwidth_mb=prev_bandwidth,
            freq_mhz=pu.get_freq(),
            temp_c=pu.get_npu_temperature(),
            tile_config=pu.get_tile_config(),
            curr_busy_us=curr_busy_us,
            prev_busy_us=prev_busy_us,
            mem_util_bytes=read_mem_util_bytes(),
        )

        prev_energy = curr_energy
        prev_bandwidth = curr_bandwidth
        prev_busy_us = curr_busy_us

        print(format_line_protocol(HOSTNAME, fields, ts_ns), flush=True)

        logger.debug(
            "npu power=%.3f freq_mhz=%.1f temp=%d bw_mbs=%.3f tile=%d util=%s mem_mb=%s",
            fields["power"],
            fields["frequency"],
            fields["temperature"],
            fields["bandwidth"],
            fields["tile_config"],
            fields.get("utilization", "n/a"),
            f'{fields["memory_mb"]:.2f}' if "memory_mb" in fields else "n/a",
        )


if __name__ == '__main__':
    main()
