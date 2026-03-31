# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for Live Video Caption profiling.

This module provides helper functions for running warmup requests
and Locust-based hardware sizing tests for the Live Caption API.
"""

import subprocess
import time

import requests

from common.video import stop_all_run_request
from src.live_video_caption.utilities.config import get_lvc_profile_details


def run_live_caption_warmup(url, payload, warmup_time):
    """
    Run warmup requests to prime the live caption pipeline.
    
    Args:
        url: The API endpoint URL for starting caption runs.
        payload: JSON payload for the caption request.
        warmup_time: Duration in seconds to keep the warmup running.
    """
    response = requests.post(url, headers={'Content-Type': 'application/json'}, data=payload)
    if response.status_code == 200:
        run_id = response.json().get("runId")
        print(f"Warmup request started with runId: {run_id}")
        print(f"Waiting for {warmup_time} seconds to complete warmup requests...")
        time.sleep(warmup_time)        
        stop_all_run_request(url, [run_id])
        print("Warmup requests completed.")
    else:
        print(f"Warmup request failed: status={response.status_code}")


def run_live_caption_hw_sizing(users, total_requests, ip, profile_path, report_dir, warmup_time, config):
    """
    Run Locust tests for the Live Caption API hardware sizing.

    Args:
        users: Number of concurrent users for the test.
        total_requests: Total number of requests.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        report_dir: Directory to save the test reports.
        warmup_time: Duration in seconds for warmup requests.
        config: Pre-loaded configuration dict.
    """
    from src.live_video_caption.locust_files import live_caption
    lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload = get_lvc_profile_details(profile_path, config)
    print(f"Hardware sizing started for the '{lvc_profile}' profile...")

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{live_caption.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", "1",
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--runs_endpoint={runs_endpoint}",
        f"--metadata_endpoint={metadata_endpoint}",
        f"--caption_duration={caption_duration}",
        f"--payload={payload}",
        f"--report_dir={report_dir}",
        f"--warmup_time={warmup_time}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)