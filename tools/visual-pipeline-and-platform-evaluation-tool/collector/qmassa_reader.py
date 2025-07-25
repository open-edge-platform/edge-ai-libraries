#!/usr/bin/env python3

import json
import logging
import subprocess
import time
import fcntl
import sys
import os

# === Constants ===
LOG_FILE = "/app/qmassa_log.json"
DEBUG_LOG = "/tmp/qmassa_reader_trace.log"
LOCK_FILE = "/tmp/qmassa_reader.lock"
HOSTNAME = os.uname()[1]

# Configure logger
logging.basicConfig(
    filename=DEBUG_LOG,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s (line %(lineno)d)",
)

def execute_qmassa_command():
    qmassa_command = [
        # Run qmassa with a 100ms interval and 2 iterations to calculate power as the delta between iterations
        "qmassa", "--ms-interval", "100", "--no-tui", "--nr-iterations", "2", "--to-json", LOG_FILE
    ]

    try:
        subprocess.run(qmassa_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Error running qmassa command: {' '.join(qmassa_command)}. Exception: {e}")
        sys.exit(1)

def load_log_file():
    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Log file {LOG_FILE} not found.")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from log file: {e}")
    except Exception as e:
        logging.error(f"Unexpected error while loading log file: {e}")
    sys.exit(1)

def emit_engine_usage(eng_usage, gpu_id, ts):
    for eng, vals in eng_usage.items():
        if vals:
            print(f"engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id={gpu_id} usage={vals[-1]} {ts}")

def emit_frequency(freqs, gpu_id, ts):
    if freqs and isinstance(freqs[-1], list):
        freq_entry = freqs[-1][0]
        if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
            print(f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id={gpu_id} value={freq_entry['cur_freq']} {ts}")

def emit_power(power, gpu_id, ts):
    if power:
        for key, val in power[-1].items():
            print(f"power,type={key},host={HOSTNAME},gpu_id={gpu_id} value={val} {ts}")

def process_device_metrics(dev, gpu_id, current_ts_ns):
    dev_stats = dev.get("dev_stats", {})
    eng_usage = dev_stats.get("eng_usage", {})
    freqs = dev_stats.get("freqs", [])
    power = dev_stats.get("power", [])

    emit_engine_usage(eng_usage, gpu_id, current_ts_ns)
    emit_frequency(freqs, gpu_id, current_ts_ns)
    emit_power(power, gpu_id, current_ts_ns)

def process_states(data):
    try:
        states = data.get("states", [])
        if not states:
            logging.error("No states found in the log file")
            return

        current_ts_ns = int(time.time() * 1e9)

        # Use the last state from 2 iterations, to get the non-zero power values
        devs_state = states[-1].get("devs_state", [])
        if not devs_state:
            logging.warning("No devs_state found in the log file")
            return

        # If there are multiple devices, process the last two
        if len(devs_state) >= 2:
            for gpu_id, dev in enumerate(devs_state[-2:]):
                process_device_metrics(dev, gpu_id, current_ts_ns)
        else:
            # If only one device, process it
            dev = devs_state[-1]
            process_device_metrics(dev, 0, current_ts_ns)
    except Exception as e:
        logging.error(f"Error processing log file: {e}")


# === Lock to prevent multiple instances ===
with open(LOCK_FILE, "w") as lock_fp:
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logging.error("Another instance is running")
        sys.exit(1)

    # Execute the qmassa command to generate the log file
    execute_qmassa_command()

    # Load the log file
    data = load_log_file()

    # Process the states from the log file
    process_states(data)
