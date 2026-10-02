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
Long-running telegraf execd input plugin that reads Intel RAPL energy counters
and emits per-domain power (W) as InfluxDB line protocol once per second.

Fills the platform (psys) power gap that intel_powerstat does not cover:
intel_powerstat exposes the package and DRAM RAPL domains, but NOT the platform
(intel-rapl:1 / psys) domain — the only Linux proxy for total board power
(CPU + iGPU + NPU + memory) on Intel client SoCs like Panther Lake.

Emits one measurement `rapl_power` with a `domain` tag per RAPL zone found:
  rapl_power,host=<h>,domain=package-0 power_w=6.51 <ts>
  rapl_power,host=<h>,domain=psys      power_w=9.83 <ts>
  rapl_power,host=<h>,domain=dram      power_w=0.42 <ts>

Power is computed the same way as TCMI monitor_thermal.py's RaplPower:
  power_w = (energy_uj_now - energy_uj_prev) / elapsed_s / 1e6
with wraparound handled via each zone's max_energy_range_uj.

Root note: energy_uj is root-readable on most kernels (-r--------). The
Metrics Manager container runs privileged, so this works there; as a non-root
user it will find no readable zones and idle quietly.
"""

import os
import sys
import time
import glob
import logging

HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
INTERVAL_S = 1.0
IDLE_SLEEP_S = 3600
RAPL_GLOB = "/sys/class/powercap/intel-rapl:*"
DEBUG_LOG = "/app/rapl_reader_trace.log"

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
    """Park the process when RAPL is unavailable, instead of exiting.

    Telegraf's execd restarts a child that exits within ~10s, flooding logs on
    hosts without readable RAPL. Log once and sleep so other inputs are
    unaffected (mirrors npu_reader.py).
    """
    logger.warning("RAPL reader entering idle mode: %s", reason)
    while True:
        time.sleep(IDLE_SLEEP_S)


def _read_int(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _read_str(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


class RaplZone:
    """One RAPL domain: name + energy counter with delta/wraparound handling."""

    def __init__(self, sysfs_dir):
        self.dir = sysfs_dir
        self.name = _read_str(os.path.join(sysfs_dir, "name")) or os.path.basename(sysfs_dir)
        self.energy_path = os.path.join(sysfs_dir, "energy_uj")
        # Wraparound ceiling; energy_uj wraps to 0 after this many uJ.
        self.max_range = _read_int(os.path.join(sysfs_dir, "max_energy_range_uj"))
        self._prev_uj = _read_int(self.energy_path)
        self._prev_ts = time.monotonic()

    @property
    def readable(self):
        return self._prev_uj is not None

    def power_w(self):
        now_uj = _read_int(self.energy_path)
        now_ts = time.monotonic()
        if now_uj is None or self._prev_uj is None:
            self._prev_uj = now_uj
            self._prev_ts = now_ts
            return None
        delta_uj = now_uj - self._prev_uj
        delta_s = now_ts - self._prev_ts
        self._prev_uj = now_uj
        self._prev_ts = now_ts
        # Counter wrapped: add one full range back.
        if delta_uj < 0 and self.max_range:
            delta_uj += self.max_range
        if delta_s <= 0 or delta_uj < 0:
            return None
        return round(delta_uj / delta_s / 1_000_000, 3)


def discover_zones():
    """Top-level RAPL zones only (intel-rapl:N), not sub-domains (intel-rapl:N:M).

    Sub-domains (core/uncore/dram) are covered by intel_powerstat; here we want
    the package and — crucially — the psys platform zone.
    """
    zones = []
    for d in sorted(glob.glob(RAPL_GLOB)):
        base = os.path.basename(d)
        # intel-rapl:1 has one colon-number after the prefix; skip ":N:M".
        if base.count(":") != 1:
            continue
        zone = RaplZone(d)
        if zone.readable:
            zones.append(zone)
            logger.info("RAPL zone: %s (%s) max_range=%s", zone.name, d, zone.max_range)
        else:
            logger.warning("RAPL zone %s not readable (need root?): %s", zone.name, d)
    return zones


def main():
    if not glob.glob(RAPL_GLOB):
        idle_forever(f"No RAPL zones under {RAPL_GLOB} (intel_rapl module loaded?)")

    zones = discover_zones()
    if not zones:
        idle_forever("No readable RAPL energy_uj counters (run privileged / as root)")

    # Prime the deltas.
    for z in zones:
        z.power_w()

    while True:
        time.sleep(INTERVAL_S)
        ts_ns = time.time_ns()
        for z in zones:
            p = z.power_w()
            if p is None:
                continue
            # domain is a string tag; escape spaces just in case.
            domain = z.name.replace(" ", "\\ ")
            print(
                f"rapl_power,host={HOSTNAME},domain={domain} power_w={p:.3f} {ts_ns}",
                flush=True,
            )
            logger.debug("rapl_power domain=%s power_w=%.3f", z.name, p)


if __name__ == "__main__":
    main()
