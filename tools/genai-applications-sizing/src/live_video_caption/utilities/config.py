# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration utilities for the Live Video Caption application.

This module provides functions for reading LVC-specific configuration
and profile details from YAML config files.

Functions:
  - is_live_caption_enabled(config)     : returns whether the LVC API is enabled
  - is_live_caption_rag_enabled(config) : returns whether the LVC RAG API is enabled
  - get_lvc_profile_details(...)        : full profile details for the live caption (or RAG) API
"""

from common.config import get_api_config, get_profile_details


def is_live_caption_enabled(config):
    """
    Return whether the Live Video Caption API is enabled.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        tuple: (live_caption_enabled, live_caption_rag_enabled)
    """
    live_caption_enabled = get_api_config(config, 'live_caption').get("enabled", False)
    live_caption_rag_enabled = get_api_config(config, 'live_caption_rag').get("enabled", False)
    return live_caption_enabled, live_caption_rag_enabled


def get_lvc_profile_details(profile_path, config, warmup=False):
    """
    Retrieve Live Video Caption (or RAG) API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to use the warmup profile.

    Returns:
        tuple: When rag=False — (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload)
               When rag=True  — (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload, chat_endpoint, chat_payload)
    """
    
    live_caption_details = get_api_config(config, 'live_caption')

    # Extract endpoints safely
    endpoints = live_caption_details.get("endpoints", {})
    runs_endpoint = endpoints.get("runs")
    metadata_endpoint = endpoints.get("metadata")
    caption_duration = live_caption_details.get("captioning_time", 120)

    # Extract profile name and load profile-specific details
    if warmup:
        lvc_profile = "live_caption_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile)
    else:
        lvc_profile = live_caption_details.get("input_profile", "")
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile)

    payload = profile_details.get("payloads")
    return lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload


def get_lvc_rag_profile_details(profile_path, config, warmup=False):
    """
    Retrieve Live Video Caption (or RAG) API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to use the warmup profile.

    Returns:
        tuple: When rag=False — (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload)
               When rag=True  — (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload, chat_endpoint, chat_payload)
    """
    
    live_caption_details = get_api_config(config, 'live_caption_rag')

    # Extract endpoints safely
    endpoints = live_caption_details.get("endpoints", {})
    runs_endpoint = endpoints.get("runs")
    metadata_endpoint = endpoints.get("metadata")
    chat_endpoint = endpoints.get("chat")
    caption_duration = live_caption_details.get("captioning_time", 120)
    input_profile = live_caption_details.get("input_profile", "")

    # Extract profile name and load profile-specific details
    if warmup:
        lvc_profile = "live_caption_rag_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile)   
    else:
        lvc_profile = input_profile
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile) 

    payload = profile_details.get("payloads")
    chat_payload = profile_details.get("chat_payloads")
    return lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload, chat_endpoint, chat_payload