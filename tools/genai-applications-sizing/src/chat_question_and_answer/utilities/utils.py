# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from gevent import monkey
monkey.patch_all()
import json
import subprocess
from common.utils import get_document_api_profile_details, get_stream_api_profile_details, upload_document_before_conversation, delete_existing_docs


def run_document_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir):
    """
    Runs Locust tests for the Document API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
    """
    from src.chat_question_and_answer.locust_files import document

    doc_profile, document_endpoint, file_details = get_document_api_profile_details(profile_path, input_file)
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



def run_chat_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir):
    """
    Runs Locust tests for the Chat API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        spawn_rate (int): Rate at which users are spawned.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
    """
    from src.chat_question_and_answer.locust_files import chat
    profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens = get_stream_api_profile_details(
        profile_path, input_file
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