#!/usr/bin/env python3

import json
import time
import shutil
import fcntl
import sys
import os

# === Config (with defaults, overridden via environment) ===
log_file = os.getenv("QMASSA_LOG_FILE", "/app/qmassa_log.json")
temp_copy = os.getenv("QMASSA_TEMP_COPY", "/tmp/qmassa_copy.json")
index_tracker = os.getenv("QMASSA_INDEX_TRACKER", "/tmp/last_state_index.txt")
debug_log = os.getenv("QMASSA_DEBUG_LOG", "/tmp/qmassa_reader_trace.log")
lock_file = os.getenv("QMASSA_LOCK_FILE", "/tmp/qmassa_reader.lock")
hostname = os.getenv("HOSTNAME", "localhost")

# === Helpers ===
def load_last_state():
    try:
        with open(index_tracker, "r") as f:
            parts = f.read().strip().split()
            return int(parts[0]), int(parts[1])
    except:
        return -1, int(time.time() * 1e9)

def save_last_state(index, timestamp):
    with open(index_tracker, "w") as f:
        f.write(f"{index} {timestamp}")

# === Lock to prevent multiple instances ===
with open(lock_file, "w") as lock_fp:
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another instance is running
        sys.exit(0)

    try:
        shutil.copy(log_file, temp_copy)
        with open(temp_copy, "r") as f:
            data = json.load(f)

        states = data.get("states", [])
        if not states:
            exit(0)

        last_seen, last_ts_ns = load_last_state()
        current_ts_ns = int(time.time() * 1e9)

        for i in range(last_seen + 1, len(states)):
            state = states[i]
            devs_state = state.get("devs_state", [])
            if not devs_state:
                continue

            dev_stats = devs_state[0].get("dev_stats", {})
            eng_usage = dev_stats.get("eng_usage", {})
            freqs = dev_stats.get("freqs", [])
            power = dev_stats.get("power", [])

            ts = current_ts_ns  # Same timestamp for simplicity

            # === Emit engine usage
            for eng, vals in eng_usage.items():
                if vals:
                    print(f"engine_usage,engine={eng},type={eng},host={hostname} usage={vals[-1]} {ts}")

            # === Emit frequency
            if freqs and isinstance(freqs[-1], list):
                freq_entry = freqs[-1][0]
                if isinstance(freq_entry, dict) and "cur_freq" in freq_entry:
                    print(f"gpu_frequency,type=cur_freq,host={hostname} value={freq_entry['cur_freq']} {ts}")

            # === Emit power values
            if power:
                for key, val in power[-1].items():
                    print(f"power,type={key},host={hostname} value={val} {ts}")

            # Update last seen
            save_last_state(i, current_ts_ns)

    except Exception as e:
        with open(debug_log, "a") as log:
            log.write(f"[{time.ctime()}] ERROR: {e}\n")
