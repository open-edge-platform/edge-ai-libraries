# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration utilities for the ChatQnA Modular application.

This module provides functions for reading ChatQnA-specific configuration
and profile details from YAML config files.

Functions:
  - get_enabled_chatqna_apis(config)     : returns which ChatQnA APIs are enabled
  - get_chatqna_profile_details(...)     : full profile details for ChatQnA chat API
  - get_document_profile_details(...)    : full profile details for document API
"""

from common.config import get_api_config, get_profile_details


def get_enabled_chatqna_apis(config):
    """
    Return which ChatQnA APIs (stream-log and document) are enabled.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        tuple: (stream_log_api_enabled, document_api_enabled)
    """
    stream_log_api_enabled = get_api_config(config, 'stream_log').get("enabled", False)
    document_api_enabled = get_api_config(config, 'document').get("enabled", False)
    return stream_log_api_enabled, document_api_enabled


def get_chatqna_profile_details(profile_path, config, warmup=False):
    """
    Retrieve chat/stream-log profile details for ChatQnA applications.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to load the warmup profile instead of the run profile.

    Returns:
        tuple: (profile, chat_endpoint, doc_endpoint, prompt, filename,
                filepath, service_name, max_tokens)
    """
    stream_log_details = get_api_config(config, 'stream_log')

    # Extract endpoints safely
    endpoints = stream_log_details.get("endpoints", {})
    doc_endpoint = endpoints.get("document")
    chat_endpoint = endpoints.get("chat")

    # Extract service configuration
    service_name = stream_log_details.get("service_name", {})
    profile = stream_log_details.get("input_profile", {})

    # Load profile-specific details
    if warmup:
        profile_details = get_profile_details(profile_path=profile_path, profile_name='chatqna_warmup_profile')
    else:
        profile_details = get_profile_details(profile_path=profile_path, profile_name=profile)

    prompt = profile_details.get("prompt")
    max_tokens = profile_details.get("max_tokens", "1024")

    # Extract file information
    file_details = profile_details.get('files', [])
    if not file_details:
        raise ValueError("No files defined in the profile")

    filename = file_details[0]["name"]
    filepath = file_details[0]["path"]

    return profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens


def get_document_profile_details(profile_path, config):
    """
    Retrieve document API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.

    Returns:
        tuple: (document_profile, document_endpoint, file_details)
    """
    document_details = get_api_config(config, 'document')

    # Extract profile name and load profile-specific details
    document_profile = document_details.get("input_profile", "")
    document_profile_details = get_profile_details(
        profile_path=profile_path,
        profile_name=document_profile,
    )

    # Extract endpoint URL safely with nested get
    document_endpoint = document_details.get("endpoints", {}).get("document")

    # Extract file details with proper default
    file_details = document_profile_details.get('files', [])

    return document_profile, document_endpoint, file_details
