# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from gevent import monkey
monkey.patch_all()
import subprocess
import time
import requests
import json
from common.utils import get_video_summary_profile_details, get_video_search_profile_details, upload_video_file, wait_for_video_summary_complete, embedding_video_file, safe_parse_string_to_dict


def run_video_summary_warmup(warmup_time, ip, profile_path, input_file):
    """
    Runs warmup requests for video summary API to ensure the system is ready.
    
    Args:
        warmup_time (int): Duration in seconds for which warmup requests should run.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
    """
    video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload = get_video_summary_profile_details(
        profile_path, input_file, warmup=True
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
    

def run_video_search_warmup(warmup_time, ip, profile_path, input_file):
    """
    Runs warmup requests for video search API to ensure the system is ready.
    
    Args:
        warmup_time (int): Duration in seconds for which warmup requests should run.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
    """
    video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries = get_video_search_profile_details(
        profile_path, input_file, warmup=True
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
    



def run_video_summary_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir):
    """
    Runs Locust tests for the Video Summary API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
    """
    from src.video_search_and_summarization.locust_files import video_summary
    video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload = get_video_summary_profile_details(
        profile_path, input_file
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


def run_video_search_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir):
    """
    Runs Locust tests for the Video Search API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
    """
    from src.video_search_and_summarization.locust_files import video_search
    video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries = get_video_search_profile_details(
    profile_path, input_file )
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