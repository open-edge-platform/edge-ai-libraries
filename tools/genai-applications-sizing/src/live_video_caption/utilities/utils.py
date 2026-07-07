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
from src.live_video_caption.locust_files import live_caption
from src.live_video_caption.utilities.config import get_lvc_profile_details, get_lvc_rag_profile_details


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


"""LVC RAG Application functions"""
def run_live_caption_rag_warmup(warmup_time, ip, profile_path, config):
    """
    Run warmup requests to prime the live caption pipeline.
    
    Args:
        warmup_time: Duration in seconds to keep the warmup running.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        config: Pre-loaded configuration dict.
    """
    lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload, chat_endpoint, chat_payload = get_lvc_rag_profile_details(profile_path, config, warmup=True)
    url = f"http://{ip}:{runs_endpoint}"
    chat_url = f"http://{ip}:{chat_endpoint}"
    
    print(f"Sending warmup requests to LVC RAG APIs...")
    warmup_start = time.time()

    run_payload = payload[0].get("run") 
    response = requests.post(url, headers={'Content-Type': 'application/json'}, data=run_payload)
    if response.status_code == 200:
        run_id = response.json().get("runId")
        print(f"Warmup request started with runId: {run_id}")
        print(f"Waiting for {warmup_time} seconds to complete warmup requests...")
        while (time.time() - warmup_start) < warmup_time:
            if chat_url and chat_payload:
                chat_response = requests.post(chat_url, headers={'Content-Type': 'application/json'}, data=chat_payload[0].get("chat"), stream=True)
                if chat_response.status_code != 200:
                    print(f"Chat warmup request failed: status={chat_response.status_code}")
                else:
                    for chunk in chat_response.iter_lines():
                        pass
            time.sleep(1)  # Sleep for a second before sending the next request

        stop_all_run_request(url, [run_id])
        print("Warmup requests completed.")
    else:
        print(f"Warmup request failed: status={response.status_code}")


def run_live_caption_rag_hw_sizing(users, total_requests, ip, profile_path, report_dir, warmup_time, config):
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
    from src.live_video_caption.locust_files import live_caption_rag
    lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload, chat_endpoint, chat_payload = get_lvc_rag_profile_details(profile_path, config)
    print(f"Hardware sizing started for the '{lvc_profile}' profile...")

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{live_caption_rag.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", "1",
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--runs_endpoint={runs_endpoint}",
        f"--metadata_endpoint={metadata_endpoint}",
        f"--chat_endpoint={chat_endpoint}",
        f"--caption_duration={caption_duration}",
        f"--payload={payload}",
        f"--chat_payload={chat_payload}",
        f"--report_dir={report_dir}",
        f"--warmup_time={warmup_time}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)