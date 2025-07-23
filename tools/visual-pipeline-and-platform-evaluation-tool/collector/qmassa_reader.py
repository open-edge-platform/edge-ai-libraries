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
        "qmassa", "--ms-interval", "500", "--no-tui", "--nr-iterations", "2", "--to-json", LOG_FILE
    ]

    try:
        subprocess.run(qmassa_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Error running qmassa command: {''.join(qmassa_command)}. Exception: {e}")
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

def process_states(data):
    try:
        states = data.get("states", [])
        if not states:
            logging.error("No states found in the log file")
            sys.exit(1)

        current_ts_ns = int(time.time() * 1e9)

        for state in states:
            devs_state = state.get("devs_state", [])
            if not devs_state:
                continue

            # --- For devs_state[-2] if it exists ---
            if len(devs_state) >= 2:
                # Use the last device state
                dev = devs_state[-1]
                dev_stats = dev.get("dev_stats", {})
                eng_usage = dev_stats.get("eng_usage", {})
                freqs = dev_stats.get("freqs", [])
                power = dev_stats.get("power", [])

                ts = current_ts_ns  # Same timestamp for simplicity

                # === Emit engine usage
                for eng, vals in eng_usage.items():
                    if vals:
                        print(f"engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id=1 usage={vals[-1]} {ts}")

                # === Emit frequency
                if freqs and isinstance(freqs[-1], list):
                    freq_entry = freqs[-1][0]
                    if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
                        print(f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id=1 value={freq_entry['cur_freq']} {ts}")

                # === Emit power values
                if power:
                    for key, val in power[-1].items():
                        print(f"power,type={key},host={HOSTNAME},gpu_id=1 value={val} {ts}")

                dev2 = devs_state[-2]
                dev_stats2 = dev2.get("dev_stats", {})
                eng_usage2 = dev_stats2.get("eng_usage", {})
                freqs2 = dev_stats2.get("freqs", [])
                power2 = dev_stats2.get("power", [])

                # === Emit engine usage
                for eng, vals in eng_usage2.items():
                    if vals:
                        print(f"engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id=0 usage={vals[-1]} {ts}")

                # === Emit frequency
                if freqs2 and isinstance(freqs2[-1], list):
                    freq_entry2 = freqs2[-1][0]
                    if isinstance(freq_entry2, dict) and "cur_freq" in freq_entry2:
                        print(f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id=0 value={freq_entry2['cur_freq']} {ts}")

                # === Emit power values
                if power2:
                    for key, val in power2[-1].items():
                        print(f"power,type={key},host={HOSTNAME},gpu_id=0 value={val} {ts}")
            else:
                # Use the last device state
                dev = devs_state[-1]
                dev_stats = dev.get("dev_stats", {})
                eng_usage = dev_stats.get("eng_usage", {})
                freqs = dev_stats.get("freqs", [])
                power = dev_stats.get("power", [])

                ts = current_ts_ns  # Same timestamp for simplicity

                # === Emit engine usage
                for eng, vals in eng_usage.items():
                    if vals:
                        print(f"engine_usage,engine={eng},type={eng},host={HOSTNAME},gpu_id=0 usage={vals[-1]} {ts}")

                # === Emit frequency
                if freqs and isinstance(freqs[-1], list):
                    freq_entry = freqs[-1][0]
                    if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
                        print(f"gpu_frequency,type=cur_freq,host={HOSTNAME},gpu_id=0 value={freq_entry['cur_freq']} {ts}")

                # === Emit power values
                if power:
                    for key, val in power[-1].items():
                        print(f"power,type={key},host={HOSTNAME},gpu_id=0 value={val} {ts}")

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
