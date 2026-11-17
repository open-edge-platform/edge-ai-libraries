# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/rate_limit.py
Description: frame-rate / data-rate throttling helpers shared by the batch encoder
runner and the REST sample clients under tests/sample_clients/.
"""
import math
import time


def sleep_to_enforce_fps(frame_started_at: float, fps: float) -> float:
    """Sleep long enough to enforce target FPS; returns sleep duration in ms."""
    if fps is None or not math.isfinite(fps) or fps <= 0:
        return 0.0

    target_frame_seconds = 1.0 / fps
    elapsed = time.perf_counter() - frame_started_at
    remaining = target_frame_seconds - elapsed
    if remaining <= 0:
        return 0.0

    time.sleep(remaining)
    return remaining * 1000.0


def sleep_to_enforce_data_rate(
    frame_started_at: float,
    payload_bytes: int,
    target_mbps: float,
) -> float:
    """Sleep to enforce target data rate (Mbps); returns sleep duration in ms.

    Args:
        frame_started_at: perf_counter() timestamp when frame processing started.
        payload_bytes: Size of encoded payload in bytes.
        target_mbps: Target data rate in Mbps (megabits per second).

    Returns:
        Sleep duration in milliseconds (0.0 if no sleep needed).
    """
    if target_mbps is None or not math.isfinite(target_mbps) or target_mbps <= 0:
        return 0.0

    # Convert megabits to bits: 1 Mbps = 1e6 bits/sec
    target_bits_per_sec = target_mbps * 1e6
    payload_bits = payload_bytes * 8

    # Time needed to transmit payload at target rate
    target_seconds = payload_bits / target_bits_per_sec

    elapsed = time.perf_counter() - frame_started_at
    remaining = target_seconds - elapsed
    if remaining <= 0:
        return 0.0

    time.sleep(remaining)
    return remaining * 1000.0
