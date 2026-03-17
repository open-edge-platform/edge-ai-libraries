# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import time
import requests
from common.utils import get_live_caption_profile_details, stop_all_run_request


def run_live_caption_warmup(url, payload, warmup_time):
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


def run_live_caption_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir, warmup_time):
    """
    Runs Locust tests for the Live Caption API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
        warmup_time (int): Duration in seconds for warmup requests.
    """
    from src.live_video_caption.locust_files import live_caption
    lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload = get_live_caption_profile_details(profile_path, input_file)
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
