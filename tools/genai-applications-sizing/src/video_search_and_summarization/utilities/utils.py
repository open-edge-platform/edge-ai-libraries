# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for Video Search and Summarization profiling.

This module provides helper functions for running warmup requests and
Locust-based hardware sizing tests against the Video Summary and Search APIs.
"""

import subprocess
import time

import requests
from common.video import wait_for_video_summary_complete, wait_for_search_to_complete,upload_video_file, embedding_video_file
from common.utils import safe_parse_string_to_dict
from src.video_search_and_summarization.utilities.config import (
    get_video_summary_profile_details,
    get_video_search_profile_details,
)


def run_video_summary_warmup(warmup_time, ip, profile_path, config):
    """
    Run warmup requests for video summary API to prime the system.
    
    Uploads a video and runs summarization to ensure the model and pipeline
    are loaded and ready for performance testing.
    
    Args:
        warmup_time: Duration in seconds for warmup requests.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        config: Pre-loaded configuration dict.
    """
    video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload = get_video_summary_profile_details(
        profile_path, config, warmup=True
    )
       
    host = f"http://{ip}"
    upload_url = f"{host}:{upload_endpoint}"
    states_url = f"{host}:{states_endpoint}"
    
    print(f"Sending warmup requests to video summary API...")
    warmup_start = time.time()
    
    # Run warmup requests until warmup_time is exceeded
    while (time.time() - warmup_start) < warmup_time:
        try:
            # Upload video
            video_id = upload_video_file(upload_url, filename, filepath)
            if video_id is None:
                print(f"Warmup: Video upload failed, skipping this iteration")
                continue
            
            # Parse payload and add video_id
            payload_dict = safe_parse_string_to_dict(payload)
            payload_dict["videoId"] = video_id
            #final_payload = json.dumps(payload_dict)
            
            # Start summary
            headers = {'Content-Type': 'application/json'}
            response = requests.post(f"{host}:{summary_endpoint}", headers=headers, json=payload_dict)
            
            if response.status_code == 201:
                summary_id = response.json().get("summaryPipelineId")
                if summary_id:
                    url = f"{states_url}/{summary_id}"
                    video_summary_complete, response = wait_for_video_summary_complete(url)
            print(f"Completed warmup requests.! \n")
            
        except Exception as e:
            print(f"Warmup request failed: {e}")
            continue
    

def run_video_search_warmup(warmup_time, ip, profile_path, config):
    """
    Runs warmup requests for video search API to ensure the system is ready.
    
    Args:
        warmup_time (int): Duration in seconds for which warmup requests should run.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        config: Pre-loaded configuration dict.
    """
    video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries = get_video_search_profile_details(
        profile_path, config, warmup=True
    )
    
    
    host = f"http://{ip}"
    upload_url = f"{host}:{upload_endpoint}"
    embedding_url = f"{host}:{embed_endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    # First, upload and create embeddings for all videos (one-time setup)
    video_ids = []
    
    print(f"Sending warmup requests to video search API...")
    # Run search warmup requests until warmup_time is exceeded
    warmup_start = time.time()
    
    while (time.time() - warmup_start) < warmup_time:
        try:
            for file_detail in file_details:
                filename = file_detail.get("name")
                if not filename:
                    continue
                
                filepath = file_detail["path"]
                
                video_id = upload_video_file(upload_url, filename, filepath)
                if video_id:
                    embedding_status = embedding_video_file(embedding_url, video_id)
                    if embedding_status == 201:
                        video_ids.append(video_id)                    
            response = requests.post(f"{host}:{search_endpoint}", headers=headers, json=queries[0])
            print(f"Completed warmup requests.! \n")
        except Exception as e:
            print(f"Warmup search request failed: {e}")
            continue
    



def run_video_summary_hw_sizing(users, total_requests, ip, profile_path, report_dir, config):
    """
    Runs Locust tests for the Video Summary API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        report_dir (str): Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    from src.video_search_and_summarization.locust_files import video_summary
    video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload = get_video_summary_profile_details(
        profile_path, config
    )
    print(f"Hardware sizing started for the '{video_profile}' profile...")

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{video_summary.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", "1",
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--state_endpoint={states_endpoint}",
        f"--upload_endpoint={upload_endpoint}",
        f"--summary_endpoint={summary_endpoint}",
        f"--telemetry_endpoint={telemetry_endpoint}",
        f"--filename={filename}",
        f"--filepath={filepath}",
        f"--payload={payload}",
        f"--report_dir={report_dir}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)


def run_video_search_hw_sizing(users, total_requests, ip, profile_path, report_dir, config):
    """
    Runs Locust tests for the Video Search API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        report_dir (str): Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    from src.video_search_and_summarization.locust_files import video_search
    video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries = get_video_search_profile_details(
    profile_path, config )
    print(f"Hardware sizing started for the '{video_profile}' profile...")

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{video_search.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", "1",
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--embedding_endpoint={embed_endpoint}",
        f"--upload_endpoint={upload_endpoint}",
        f"--search_endpoint={search_endpoint}",
        f"--telemetry_endpoint={telemetry_endpoint}",
        f"--file_details={file_details}",
        f"--queries={queries}",
        f"--report_dir={report_dir}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)