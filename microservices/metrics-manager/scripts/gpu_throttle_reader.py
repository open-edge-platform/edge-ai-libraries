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
Long-running telegraf execd input plugin that reads Intel xe DRM GPU frequency
and throttle state straight from sysfs, emitting InfluxDB line protocol once
per second.

Fills a gap qmassa does not cover: qmassa_reader.py reports the *requested*
(cur_freq) GPU frequency and per-engine busy %, but not the *actual* achieved
frequency or the throttle reasons behind a shortfall. The xe driver exposes
both under each GT's freq domain:

  /sys/class/drm/cardN/device/tile*/gt*/freq0/act_freq   -> gpu_act_freq_mhz
  /sys/class/drm/cardN/device/tile*/gt*/freq0/cur_freq   -> gpu_driver_freq_mhz
  /sys/class/drm/cardN/device/tile*/gt*/freq0/throttle/status         -> gpu_throttled
  /sys/class/drm/cardN/device/tile*/gt*/freq0/throttle/reason_thermal -> gpu_throttle_thermal

A gap between the driver-requested cur_freq and the achieved act_freq, together
with a non-zero throttle status, is the direct signal for the T (thermal)
envelope — the GPU wanted to clock higher but the hardware held it back.

Emits one `gpu_throttle` measurement per GT, tagged with the card and gt so
multi-tile / multi-GPU systems stay disambiguated:
  gpu_throttle,host=<h>,card=card1,gt=gt0 act_freq_mhz=1550,driver_freq_mhz=2000,\
      throttled=1i,throttle_thermal=1i,throttle_pl1=0i,throttle_pl2=0i,\
      throttle_prochot=0i <ts>

On a host with no xe GPU the freq globs match nothing and the reader idles
quietly instead of restart-storming Telegraf — same contract as
npu_reader.py / rapl_reader.py.
"""

import os
import sys
import time
import glob
import logging

HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
INTERVAL_S = 1.0
IDLE_SLEEP_S = 3600
# Every GT frequency domain across all cards/tiles. freq0 is the only domain
# the xe driver exposes today, but the glob keeps us forward-compatible.
FREQ_GLOB = "/sys/class/drm/card*/device/tile*/gt*/freq0"
DEBUG_LOG = "/app/gpu_throttle_reader_trace.log"

# Throttle reason files under freq0/throttle/. `status` is the OR of all
# reasons; the individual reason_* files pinpoint why. We surface the ones that
# matter for the TCMI envelopes (thermal is the headline; power-limit and
# prochot are the common others) and skip the long tail of VR/RATL reasons to
# keep the series count sane.
THROTTLE_FIELDS = {
    "throttled": "status",
    "throttle_thermal": "reason_thermal",
    "throttle_pl1": "reason_pl1",
    "throttle_pl2": "reason_pl2",
    "throttle_prochot": "reason_prochot",
}

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
    """Park the process when no xe GPU is present, instead of exiting.

    Telegraf's execd restarts a child that exits within ~10s, flooding logs on
    hosts without an Intel GPU. Log once and sleep so other inputs are
    unaffected (mirrors npu_reader.py / rapl_reader.py).
    """
    logger.warning("GPU throttle reader entering idle mode: %s", reason)
    while True:
        time.sleep(IDLE_SLEEP_S)


def _read_int(path):
    """Read a sysfs attr as int, or None if missing/unreadable/non-numeric."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class GpuFreqDomain:
    """One xe GT frequency domain: act/cur freq + throttle reasons."""

    def __init__(self, freq_dir):
        self.dir = freq_dir
        # freq_dir looks like /sys/class/drm/card1/device/tile0/gt0/freq0.
        # Tag with the card and gt so multi-tile / multi-GPU stays separable.
        parts = freq_dir.split("/")
        self.card = next((p for p in parts if p.startswith("card")), "card?")
        self.gt = next((p for p in parts if p.startswith("gt")), "gt?")
        self.act_path = os.path.join(freq_dir, "act_freq")
        self.cur_path = os.path.join(freq_dir, "cur_freq")
        self.throttle_dir = os.path.join(freq_dir, "throttle")

    @property
    def readable(self):
        # act_freq is the field we most care about; if it's gone the domain is
        # not usable. (cur_freq alone is already covered by qmassa.)
        return _read_int(self.act_path) is not None

    def sample(self):
        """Return a dict of field -> value for this GT, or None if it vanished."""
        act = _read_int(self.act_path)
        cur = _read_int(self.cur_path)
        if act is None and cur is None:
            return None
        fields = {}
        if act is not None:
            fields["act_freq_mhz"] = act
        if cur is not None:
            fields["driver_freq_mhz"] = cur
        for field, fname in THROTTLE_FIELDS.items():
            val = _read_int(os.path.join(self.throttle_dir, fname))
            if val is not None:
                fields[field] = val
        return fields


def discover_domains():
    domains = []
    for d in sorted(glob.glob(FREQ_GLOB)):
        dom = GpuFreqDomain(d)
        if dom.readable:
            domains.append(dom)
            logger.info("xe GPU freq domain: %s/%s (%s)", dom.card, dom.gt, d)
        else:
            logger.warning("xe GPU freq domain not readable: %s", d)
    return domains


def _fmt_field(key, val):
    """Freqs are floats; throttle flags are integer counters (`i` suffix)."""
    if key.endswith("_mhz"):
        return f"{key}={val}"
    return f"{key}={val}i"


def main():
    if not glob.glob(FREQ_GLOB):
        idle_forever(f"No xe GPU freq domains under {FREQ_GLOB} (Intel GPU / xe driver present?)")

    domains = discover_domains()
    if not domains:
        idle_forever("No readable xe GPU freq domains")

    while True:
        time.sleep(INTERVAL_S)
        ts_ns = time.time_ns()
        for dom in domains:
            fields = dom.sample()
            if not fields:
                continue
            field_str = ",".join(_fmt_field(k, v) for k, v in fields.items())
            print(
                f"gpu_throttle,host={HOSTNAME},card={dom.card},gt={dom.gt} {field_str} {ts_ns}",
                flush=True,
            )
            logger.debug("gpu_throttle %s/%s %s", dom.card, dom.gt, field_str)


if __name__ == "__main__":
    main()
