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
DEBUG_LOG = "/app/npu_reader_trace.log"

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
        logger.warning("npu_busy_time_us not found at %s; utilization will be 0", busy_path)

    # Memory utilization is only available on PTL and later
    from npu_monitor_tool import CpuGen  # noqa: E402
    mem_util_supported = (pu.cpu_gen is not None) and (pu.cpu_gen >= CpuGen.PTL)
    mem_util_path = os.path.join(dev_path, "npu_memory_utilization")

    def read_busy_us():
        if not npu_busy_supported:
            return None
        try:
            with open(busy_path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except (OSError, ValueError) as e:
            logger.warning("Failed to read npu_busy_time_us: %s", e)
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

        # Power (W) – use actual elapsed time, not the nominal sleep interval
        curr_energy = pu.get_npu_energy()
        power_w = (curr_energy - prev_energy) / elapsed_s
        prev_energy = curr_energy

        # Frequency (Hz) – same display conversion as npu-monitor-tool
        freq_hz = pu.get_display_freq_hz()

        # Temperature (°C)
        temp_c = pu.get_npu_temperature()

        # NoC bandwidth delta (MB/s)
        curr_bandwidth = pu.get_noc_bandwidth()
        bandwidth_mbs = curr_bandwidth - prev_bandwidth
        prev_bandwidth = curr_bandwidth

        # Tile configuration
        tile_config = pu.get_tile_config()

        # Utilization (%) – delta of busy_time_us over the actual elapsed interval
        curr_busy_us = read_busy_us()
        if prev_busy_us is not None and curr_busy_us is not None:
            delta_us = curr_busy_us - prev_busy_us
            interval_us = elapsed_s * 1_000_000
            utilization = min(100, int(100 * delta_us / interval_us))
        else:
            utilization = 0
        prev_busy_us = curr_busy_us

        # Memory utilization (MB), -1 if unsupported/unavailable
        mem_util_mb = -1.0
        if mem_util_supported and os.path.exists(mem_util_path):
            try:
                with open(mem_util_path, 'r', encoding='utf-8') as f:
                    mem_util_mb = int(f.read().strip()) / 1024 / 1024
            except (OSError, ValueError) as e:
                logger.warning("Failed to read npu_memory_utilization: %s", e)

        # Emit influx line protocol – all fields in one measurement
        print(
            f"npu,host={HOSTNAME}"
            f" power={power_w:.3f},"
            f"frequency={freq_hz:.0f},"
            f"temperature={temp_c}i,"
            f"bandwidth={bandwidth_mbs:.3f},"
            f"tile_config={tile_config}i,"
            f"utilization={utilization}i,"
            f"memory_mb={mem_util_mb:.2f}"
            f" {ts_ns}",
            flush=True,
        )

        logger.debug(
            "npu power=%.3f freq=%.0f temp=%d bw=%.3f tile=%d util=%d%% mem=%.2fMB",
            power_w, freq_hz, temp_c, bandwidth_mbs, tile_config, utilization, mem_util_mb,
        )

        logger.debug(
            "emitted npu metrics power=%.3f freq=%.0f temp=%d bw=%.3f tile=%d",
            power_w, freq_hz, temp_c, bandwidth_mbs, tile_config,
        )


if __name__ == '__main__':
    main()
