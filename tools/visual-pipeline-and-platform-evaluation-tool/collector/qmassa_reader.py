#!/usr/bin/env python3

import json
import time
import shutil
import fcntl
import sys
import os

# === Constants ===
LOG_FILE = "/app/qmassa_log.json"
TEMP_COPY = "/tmp/qmassa_copy.json"
INDEX_TRACKER = "/tmp/last_state_index.txt"
DEBUG_LOG = "/tmp/qmassa_reader_trace.log"
LOCK_FILE = "/tmp/qmassa_reader.lock"
HOSTNAME = os.uname()[1]

# === Helpers ===
def load_last_state():
    try:
        with open(INDEX_TRACKER, "r") as f:
            parts = f.read().strip().split()
            return int(parts[0]), int(parts[1])
    except:
        return -1, int(time.time() * 1e9)

def save_last_state(index, timestamp):
    with open(INDEX_TRACKER, "w") as f:
        f.write(f"{index} {timestamp}")

# === Lock to prevent multiple instances ===
with open(LOCK_FILE, "w") as lock_fp:
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another instance is running
        sys.exit(0)

    try:
        shutil.copy(LOG_FILE, TEMP_COPY)
        with open(TEMP_COPY, "r") as f:
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
            # Update last seen
            save_last_state(i, current_ts_ns)

    except Exception as e:
        with open(DEBUG_LOG, "a") as log:
            log.write(f"[{time.ctime()}] ERROR: {e}\n")
