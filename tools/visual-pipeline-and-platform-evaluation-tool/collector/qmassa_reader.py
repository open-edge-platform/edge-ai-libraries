#!/usr/bin/env python3

import json
import time
import shutil

# Configurable paths
log_file = "/app/qmassa_log.json"
temp_copy = "/tmp/qmassa_copy.json"
index_tracker = "/tmp/last_state_index.txt"
debug_log = "/tmp/qmassa_reader_trace.log"
hostname = "gundaara-desk"

# Load last seen sample index and timestamp
def load_last_state():
    try:
        with open(index_tracker, "r") as f:
            parts = f.read().strip().split()
            return int(parts[0]), int(parts[1])
    except:
        return -1, int(time.time() * 1e9)

# Save current sample index and timestamp
def save_last_state(index, timestamp):
    with open(index_tracker, "w") as f:
        f.write(f"{index} {timestamp}")

try:
    # Copy log safely
    shutil.copy(log_file, temp_copy)
    with open(temp_copy, "r") as f:
        data = json.load(f)

    states = data.get("states", [])
    if not states:
        exit(0)

    last_state = states[-1]
    devs_state = last_state.get("devs_state", [])
    if not devs_state:
        exit(0)

    dev_stats = devs_state[0].get("dev_stats", {})
    eng_usage = dev_stats.get("eng_usage", {})
    freqs = dev_stats.get("freqs", [])
    power = dev_stats.get("power", [])

    # Total samples available
    total_samples = max(len(freqs), *(len(v) for v in eng_usage.values()), len(power))

    last_seen, last_ts_ns = load_last_state()
    now_ts_ns = int(time.time() * 1e9)
    delta_ns = now_ts_ns - last_ts_ns
    new_samples = total_samples - last_seen - 1

    if new_samples <= 0:
        exit(0)

    per_sample_ns = delta_ns // new_samples if new_samples > 0 else 1

    for idx in range(last_seen + 1, total_samples):
        ts = last_ts_ns + (idx - (last_seen + 1)) * per_sample_ns

        # Engine usage
        for eng, vals in eng_usage.items():
            if idx < len(vals):
                print(f"engine_usage,engine={eng},type={eng},host={hostname} usage={vals[idx]} {ts}")

        # Frequency
        if idx < len(freqs):
            freq_entry = freqs[idx]
            if freq_entry and isinstance(freq_entry[0], dict):
                cur_freq = freq_entry[0].get("cur_freq")
                if cur_freq is not None:
                    print(f"gpu_frequency,type=cur_freq,host={hostname} value={cur_freq} {ts}")

        # Power
        if idx < len(power):
            for key, value in power[idx].items():
                print(f"power,type={key},host={hostname} value={value} {ts}")

    save_last_state(total_samples - 1, now_ts_ns)

except Exception as e:
    with open(debug_log, "a") as log:
        log.write(f"[{time.ctime()}] ERROR: {e}\n")
