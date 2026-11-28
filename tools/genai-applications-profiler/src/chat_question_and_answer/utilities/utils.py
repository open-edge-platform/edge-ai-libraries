# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for ChatQnA Modular profiling.

This module provides helper functions for running Locust-based hardware
sizing tests against the ChatQnA Modular application APIs.
"""

import json
import subprocess
from time import time

import requests

from common.utils import (
    upload_document_before_conversation,
    delete_existing_docs
)
from src.chat_question_and_answer.utilities.config import (
    get_document_profile_details,
    get_chatqna_profile_details,
)

def run_chat_warmup(warmup_time, ip, profile_path, config):
    """
    Run warmup requests for Chat API to prime the system.
    
    Uploads a document and runs a chat conversation to ensure the model and pipeline
    are loaded and ready for performance testing.
    
    Args:
        warmup_time: Duration in seconds for warmup requests.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        config: Pre-loaded configuration dict.
    """
    chat_profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens = get_chatqna_profile_details(
        profile_path, config, warmup=True
    )
    
    host = f"http://{ip}"
    chat_url = f"{host}:{chat_endpoint}"
    
    print(f"Sending warmup requests to chat API...")    
   
    warmup_start = time()
    body = {"conversation_messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens}
    headers = {'Content-Type': 'application/json'}
    while (time() - warmup_start) < warmup_time:
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(chat_url, headers=headers, json=body, stream=True)
            
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    pass
            
        except Exception as e:
            print(f"Warmup request failed: {e}")
            continue
    

def run_document_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, report_dir, config):
    """
    Run Locust tests for the Document API hardware sizing.

    Args:
        users: Number of concurrent users for the test.
        total_requests: Total number of requests.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        report_dir: Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    from src.chat_question_and_answer.locust_files import document

    doc_profile, document_endpoint, file_details = get_document_profile_details(profile_path, config)
    print(f"Hardware sizing started for the '{doc_profile}' profile...")
    doc_url = f"http://{ip}:{document_endpoint}"
    delete_existing_docs(doc_url)
    
    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{document.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", str(spawn_rate),
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--doc_endpoint={document_endpoint}",
        f"--report_dir={report_dir}",
        f"--file_details={file_details}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)


def run_chat_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, report_dir, config):
    """
    Run Locust tests for the Chat API hardware sizing.

    Args:
        users: Number of concurrent users for the test.
        total_requests: Total number of requests.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        report_dir: Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    from src.chat_question_and_answer.locust_files import chat
    
    profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens = get_chatqna_profile_details(
        profile_path, config
    )
    print(f"Hardware sizing started for the '{profile}' profile...")

    # Upload document before starting the conversation
    doc_url = f"http://{ip}:{doc_endpoint}"
    file_details = upload_document_before_conversation(doc_url, filename, filepath)

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{chat.__file__}",
        "--headless",
        "--users", str(users),
        "--spawn-rate", str(spawn_rate),
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--chat_endpoint={chat_endpoint}",
        f"--report_dir={report_dir}",
        "--prompt", f"{prompt}",
        "--max_tokens", f"{max_tokens}",
        "--file_details", json.dumps(file_details),
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)