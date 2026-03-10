# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from gevent import monkey
monkey.patch_all()
import subprocess
from transformers import LlamaTokenizerFast
from common.utils import get_document_api_profile_details, get_stream_api_profile_details, upload_document_before_conversation


def get_token_length(text):
    """
    Calculates the token length of a given text using the LlamaTokenizerFast.

    Args:
        text (str): The input text to tokenize.

    Returns:
        int: The number of tokens in the input text. Returns 0 if an error occurs.
    """
    try:
        # Load the tokenizer
        tokenizer = LlamaTokenizerFast.from_pretrained(
            "hf-internal-testing/llama-tokenizer", legacy=False
        )
        
        # Encode the text and calculate token length
        token_length = len(tokenizer.encode(text))
        return token_length
    except Exception as e:
        # Log the error and return 0
        print(f"Token length calculation failed with error: {e}")
        return 0


def run_stream_log_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir):
    """
    Runs Locust tests for the Stream Log API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        input_file (str): Path to the input YAML configuration file.
        report_dir (str): Directory to save the test reports.
    """
    # Import stream_log here to avoid circular imports
    from src.chat_question_and_answer_core.locust_files import stream_log
    

    profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, max_tokens, service_name = get_stream_api_profile_details(
        profile_path, input_file
    )
    print(f"Hardware sizing started for the '{profile}' profile...")

    # Upload document before starting the conversation
    doc_url = f"http://{ip}:{doc_endpoint}"
    upload_document_before_conversation(doc_url, filename, filepath)

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{stream_log.__file__}",
        "--headless",
        "--users",  str(users),
        "--spawn-rate", str(spawn_rate),
        "-i",  str(total_requests),
        "--host", f"http://{ip}",
        f"--chat_endpoint={chat_endpoint}",
        f"--report_dir={report_dir}",
        "--prompt", f"{prompt}",
    #    "--max_tokens", f"{max_tokens}",
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)


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
    # Import document here to avoid circular imports
    from src.chat_question_and_answer_core.locust_files import document
    
    doc_profile, document_endpoint, file_details = get_document_api_profile_details(profile_path, input_file)
    print(f"Hardware sizing started for the '{doc_profile}' profile...")

    # Construct and execute the Locust command
    cmd = [
        "locust",
        "-f", f"{document.__file__}",
        "--headless",
        "--users",  str(users),
        "--spawn-rate", str(spawn_rate),
        "-i", str(total_requests),
        "--host", f"http://{ip}",
        f"--doc_endpoint={document_endpoint}",
        f"--report_dir={report_dir}",
        f"--file_details={file_details}",
        "--only-summary",
        "--loglevel",  "CRITICAL",
    ]
    subprocess.run(cmd, check=True)