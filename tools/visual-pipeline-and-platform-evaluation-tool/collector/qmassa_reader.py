#!/usr/bin/env python3

import json
import time
import os
import shutil

# Configurable paths
log_file = "/app/qmassa_log.json"
temp_copy = "/tmp/qmassa_copy.json"
index_tracker = "/tmp/last_state_index.txt"
debug_log = "/tmp/qmassa_reader_trace.log"
hostname = "gundaara-desk"

# Load the last index and timestamp (ns)
def load_last_state():
    try:
        with open(index_tracker, "r") as f:
            parts = f.read().strip().split()
            return int(parts[0]), int(parts[1])
    except:
        return -1, int(time.time() * 1e9)  # First run fallback

# Save the current index and timestamp (ns)
def save_last_state(index, timestamp):
    with open(index_tracker, "w") as f:
        f.write(f"{index} {timestamp}")

try:
    shutil.copy(log_file, temp_copy)

    with open(temp_copy, "r") as file:
        data = json.load(file)

    states = data.get("states", [])
    if not states:
        exit(0)

    last_seen, last_ts_ns = load_last_state()
    current_max = len(states) - 1

    if current_max <= last_seen:
        exit(0)

    now_ts_ns = int(time.time() * 1e9)
    total_states = current_max - last_seen
    total_delta = now_ts_ns - last_ts_ns
    interval_per_state = total_delta // total_states if total_states > 0 else 1

    for i in range(last_seen + 1, current_max + 1):
        state = states[i]
        devs_state = state.get("devs_state", [])
        if not devs_state:
            continue

        dev_stats = devs_state[0].get("dev_stats", {})
        eng_stats = dev_stats.get("eng_usage", {})
        power_stats = dev_stats.get("power", {})

        state_ts_ns = last_ts_ns + (i - (last_seen + 1)) * interval_per_state

        # Emit each engine usage sample with spaced timestamps
        for engine, values in eng_stats.items():
            if values:
                num_samples = len(values)
                per_sample_delta = interval_per_state // num_samples if num_samples > 0 else 1

                for idx, val in enumerate(values):
                    sample_ts_ns = state_ts_ns + idx * per_sample_delta
                    print(f"engine_usage,engine={engine},type={engine},host={hostname} usage={val} {sample_ts_ns}")

        # Emit latest power values with state's base timestamp
        if power_stats:
            latest_power = power_stats[-1]
            for key, value in latest_power.items():
                print(f"power,type={key},host={hostname} value={value} {state_ts_ns}")

    # Save last seen index and time
    save_last_state(current_max, now_ts_ns)

except Exception as e:
    with open(debug_log, "a") as log:
        log.write(f"[{time.ctime()}] ERROR: {e}\n")
