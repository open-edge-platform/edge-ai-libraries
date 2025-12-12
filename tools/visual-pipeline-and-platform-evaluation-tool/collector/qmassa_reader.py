#!/usr/bin/env python3

import json
import logging
import os
import re
import sys
import time

# === Constants ===
FIFO_FILE = "/app/qmassa.fifo"
DEBUG_LOG = "/app/qmassa_reader_trace.log"
HOSTNAME = os.uname()[1]
RETRY_DELAY = 1  # seconds to wait before retrying after recoverable errors

# Configure logger
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


def emit_engine_usage(eng_usage, gpu_id, ts):
    for eng, vals in eng_usage.items():
        if vals:
            print(
                f"gpu_engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id={gpu_id} usage={vals[-1]} {ts}"
            )


def emit_frequency(freqs, gpu_id, ts):
    if freqs and isinstance(freqs[-1], list):
        freq_entry = freqs[-1][0]
        if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
            print(
                f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id={gpu_id} value={freq_entry['cur_freq']} {ts}"
            )


def emit_power(power, gpu_id, ts):
    if power:
        for key, val in power[-1].items():
            print(
                f"gpu_power,type={key},host={HOSTNAME},gpu_id={gpu_id} value={val} {ts}"
            )


def process_device_metrics(dev, gpu_id, current_ts_ns):
    dev_stats = dev.get("dev_stats", {})
    eng_usage = dev_stats.get("eng_usage", {})
    freqs = dev_stats.get("freqs", [])
    power = dev_stats.get("power", [])

    emit_engine_usage(eng_usage, gpu_id, current_ts_ns)
    emit_frequency(freqs, gpu_id, current_ts_ns)
    emit_power(power, gpu_id, current_ts_ns)


def process_line(state_line):
    try:
        state = json.loads(state_line)

        # If parsed JSON is not an object, skip and log.
        if not isinstance(state, dict):
            logger.debug(
                "Skipping line: parsed JSON is not an object (expected top-level dict)"
            )
            return

        # Use state.get with a safe default list and treat missing/empty as skip.
        ts = state.get("timestamps", [])
        if not ts:
            logger.debug("Skipping line: missing or empty top-level 'timestamps'")
            return

        current_ts_ns = int(time.time() * 1e9)
        devs_state = state.get("devs_state", [])
        if not devs_state:
            logger.warning("Skipping line: no devs_state found in state line")
            return

        # Process all devices in devs_state
        for dev in devs_state:
            dev_nodes = dev.get("dev_nodes", "")
            match = re.search(r"renderD(\d+)", dev_nodes)
            if not match:
                continue  # no renderD<number> found, skip this device

            number = int(match.group(1))
            if number < 128:
                logger.warning(
                    f"renderD{number} in dev_nodes '{dev_nodes}' is less than 128, skipping device"
                )
                continue

            gpu_id = number - 128
            process_device_metrics(dev, gpu_id, current_ts_ns)
            sys.stdout.flush()
    except Exception as e:
        logger.error(f"Error processing line: {e}")


def main():
    while True:
        try:
            # Open the FIFO for reading (blocks until a writer is available)
            with open(FIFO_FILE, "r") as fifo:
                # Read lines from the FIFO, blocking until data is available
                for state_line in fifo:
                    state_line = state_line.strip()
                    if not state_line:
                        continue
                    process_line(state_line)
            # If we reach here, the writer closed the FIFO. Loop to reopen and wait for new writers.
        except (KeyboardInterrupt, SystemExit):
            # Allow graceful termination by external signals
            logger.info("Termination requested, exiting.")
            raise
        except Exception as e:
            # Log full traceback for diagnostics and retry after a delay for recoverable errors.
            logger.exception(
                f"Error reading from FIFO (will retry after {RETRY_DELAY}s): {e}"
            )
            time.sleep(RETRY_DELAY)
            continue


if __name__ == "__main__":
    main()
