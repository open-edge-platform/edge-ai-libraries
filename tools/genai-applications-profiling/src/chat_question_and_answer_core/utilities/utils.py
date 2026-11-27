# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for ChatQnA Core profiling.

This module provides helper functions for running Locust-based hardware
sizing tests against the ChatQnA Core application APIs.
"""

import subprocess
from transformers import LlamaTokenizerFast
from common.utils import upload_document_before_conversation
from src.chat_question_and_answer_core.utilities.config import (
    get_document_profile_details,
    get_chatqna_profile_details,
)

# Module-level cached tokenizer instance
_tokenizer = None


def _get_tokenizer():
    """
    Get or create a cached tokenizer instance.
    
    Uses module-level caching to avoid reloading the tokenizer on every call,
    significantly improving performance for repeated tokenization.
    
    Returns:
        LlamaTokenizerFast: The cached tokenizer instance.
    """
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = LlamaTokenizerFast.from_pretrained(
            "hf-internal-testing/llama-tokenizer", legacy=False
        )
    return _tokenizer


def get_token_length(text):
    """
    Calculate the token length of a given text using LlamaTokenizerFast.

    Uses a cached tokenizer instance for efficient repeated calls.

    Args:
        text: The input text to tokenize.

    Returns:
        int: The number of tokens in the input text. Returns 0 if an error occurs.
    """
    try:
        tokenizer = _get_tokenizer()
        return len(tokenizer.encode(text))
    except Exception as e:
        print(f"Token length calculation failed with error: {e}")
        return 0


def run_stream_log_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, report_dir, config):
    """
    Run Locust tests for the Stream Log API hardware sizing.

    Args:
        users: Number of users for the test.
        total_requests: Total number of requests.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        profile_path: Path to the profile YAML file.
        report_dir: Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    # Import stream_log here to avoid circular imports
    from src.chat_question_and_answer_core.locust_files import stream_log
    
    # Note: get_chatqna_profile_details returns tuple in order:
    # (profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens)
    profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens = get_chatqna_profile_details(
        profile_path, config
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
        "--only-summary",
        "--loglevel", "CRITICAL",
    ]
    subprocess.run(cmd, check=True)


def run_document_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, report_dir, config):
    """
    Runs Locust tests for the Document API hardware sizing.

    Args:
        users (int): Number of users for the test.
        total_requests (int): Total number of requests.
        ip (str): Host IP address where the application is deployed.
        profile_path (str): Path to the profile YAML file.
        report_dir (str): Directory to save the test reports.
        config: Pre-loaded configuration dict.
    """
    from src.chat_question_and_answer_core.locust_files import document
    
    doc_profile, document_endpoint, file_details = get_document_profile_details(profile_path, config)
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