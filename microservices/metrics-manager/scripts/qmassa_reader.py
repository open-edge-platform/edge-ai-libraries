#!/usr/bin/env python3
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
qmassa reader - Parses GPU metrics from qmassa FIFO and outputs InfluxDB Line Protocol.

This script reads JSON output from qmassa (Intel GPU monitoring tool) via a named pipe
and converts it to InfluxDB Line Protocol format for Telegraf ingestion.
"""

import json
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler

# === Constants ===
FIFO_FILE = "/app/qmassa.fifo"
DEBUG_LOG = os.environ.get("QMASSA_LOG_FILE", "/app/qmassa_reader_trace.log")
# Hostname used in the `host=` tag of every emitted line. Defaults to the
# kernel hostname (matches Telegraf's default behaviour) but can be overridden
# with METRICS_MANAGER_HOSTNAME so dashboards keep a stable label across
# reboots / container restarts where the kernel hostname may change.
HOSTNAME = os.environ.get("METRICS_MANAGER_HOSTNAME") or os.uname()[1]
RETRY_DELAY = 1  # seconds to wait before retrying after recoverable errors
# When qmassa is not producing output (e.g. no Intel GPU on host), we stop
# retrying every RETRY_DELAY seconds after this many consecutive failures and
# fall back to a long idle sleep. This keeps the Telegraf log quiet and avoids
# busy-looping on hosts without an Intel GPU.
MAX_FAST_RETRIES = 5
IDLE_SLEEP_S = 3600
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB max log size
LOG_BACKUP_COUNT = 3  # Keep 3 backup files

# Configure logger with rotating file handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Use RotatingFileHandler to prevent unbounded log growth
if os.environ.get("QMASSA_LOG_TO_STDERR", "false").lower() in ("true", "1", "yes"):
    # Log to stderr for container runtime management
    handler = logging.StreamHandler(sys.stderr)
else:
    # Use rotating file handler
    handler = RotatingFileHandler(
        DEBUG_LOG,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )

handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
)
logger.addHandler(handler)


def emit_engine_usage(eng_usage, gpu_id, ts):
    """Emit GPU engine usage metrics."""
    for eng, vals in eng_usage.items():
        if vals:
            print(
                f"gpu_engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id={gpu_id} usage={vals[-1]} {ts}"
            )


def emit_frequency(freqs, gpu_id, ts):
    """Emit GPU frequency metrics."""
    if freqs and isinstance(freqs[-1], list):
        freq_entry = freqs[-1][0]
        if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
            print(
                f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id={gpu_id} value={freq_entry['cur_freq']} {ts}"
            )


def emit_power(power, gpu_id, ts):
    """Emit GPU power metrics."""
    if power:
        for key, val in power[-1].items():
            print(
                f"gpu_power,type={key},host={HOSTNAME},gpu_id={gpu_id} value={val} {ts}"
            )


def process_device_metrics(dev, gpu_id, current_ts_ns):
    """Process and emit metrics for a single GPU device."""
    dev_stats = dev.get("dev_stats", {})
    eng_usage = dev_stats.get("eng_usage", {})
    freqs = dev_stats.get("freqs", [])
    power = dev_stats.get("power", [])

    emit_engine_usage(eng_usage, gpu_id, current_ts_ns)
    emit_frequency(freqs, gpu_id, current_ts_ns)
    emit_power(power, gpu_id, current_ts_ns)


def process_line(state_line):
    """Process a single JSON line from qmassa."""
    try:
        state = json.loads(state_line)

        if not isinstance(state, dict):
            logger.debug("Skipping: parsed JSON is not an object")
            return

        ts = state.get("timestamps", [])
        if not ts:
            logger.debug("Skipping: missing timestamps")
            return

        current_ts_ns = int(time.time() * 1e9)
        devs_state = state.get("devs_state", [])
        if not devs_state:
            logger.warning("Skipping: no devs_state found")
            return

        for dev in devs_state:
            dev_nodes = dev.get("dev_nodes", "")
            match = re.search(r"renderD(\d+)", dev_nodes)
            if not match:
                continue

            number = int(match.group(1))
            if number < 128:
                logger.warning(f"renderD{number} < 128, skipping")
                continue

            gpu_id = number - 128
            process_device_metrics(dev, gpu_id, current_ts_ns)
            sys.stdout.flush()
    except Exception as e:
        logger.error(f"Error processing line: {e}")


def main():
    """Main loop - read from FIFO and process metrics.

    On hosts without an Intel GPU the FIFO never appears (qmassa exits) or
    is never written to. After ``MAX_FAST_RETRIES`` consecutive failures we
    stop retrying every second and fall back to a long idle sleep so the
    process stays alive but quiet — Telegraf will keep streaming other
    inputs.

    A single warning is emitted across the whole missing-FIFO lifecycle:
    once when we first detect the FIFO is gone. The transition into idle
    mode is logged at INFO so log scrapers don't flag it; subsequent idle
    wake-ups are silent.
    """
    consecutive_failures = 0
    warned_missing = False
    idle_announced = False
    while True:
        try:
            with open(FIFO_FILE, "r") as fifo:
                # FIFO opened successfully — log recovery if we were idling.
                if warned_missing:
                    logger.info("qmassa FIFO %s is now available; resuming.", FIFO_FILE)
                consecutive_failures = 0
                warned_missing = False
                idle_announced = False
                for state_line in fifo:
                    state_line = state_line.strip()
                    if not state_line:
                        continue
                    process_line(state_line)
            # Reaching here means the writer closed the FIFO cleanly; reopen.
        except (KeyboardInterrupt, SystemExit):
            logger.info("Termination requested, exiting.")
            raise
        except FileNotFoundError:
            consecutive_failures += 1
            if not warned_missing:
                logger.warning(
                    "qmassa FIFO %s not found; is qmassa running / is an Intel GPU present?",
                    FIFO_FILE,
                )
                warned_missing = True
            if consecutive_failures >= MAX_FAST_RETRIES:
                if not idle_announced:
                    logger.info(
                        "qmassa FIFO still missing after %d retries; entering idle mode "
                        "(checking again every %ds, silently).",
                        MAX_FAST_RETRIES,
                        IDLE_SLEEP_S,
                    )
                    idle_announced = True
                time.sleep(IDLE_SLEEP_S)
            else:
                time.sleep(RETRY_DELAY)
            continue
        except Exception as e:
            consecutive_failures += 1
            logger.exception(f"Error reading from FIFO: {e}")
            time.sleep(RETRY_DELAY)
            continue


if __name__ == "__main__":
    main()
