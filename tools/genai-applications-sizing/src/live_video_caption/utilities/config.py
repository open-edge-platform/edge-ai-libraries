# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration utilities for the Live Video Caption application.

This module provides functions for reading LVC-specific configuration
and profile details from YAML config files.

Functions:
  - is_live_caption_enabled(config)  : returns whether the LVC API is enabled
  - get_lvc_profile_details(...)     : full profile details for the live caption API
"""

from common.config import get_api_config, get_profile_details


def is_live_caption_enabled(config):
    """
    Return whether the Live Video Caption API is enabled.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        bool: True if the live caption API is enabled.
    """
    return get_api_config(config, 'live_caption').get("enabled", False)


def get_lvc_profile_details(profile_path, config, warmup=False):
    """
    Retrieve Live Video Caption API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to use the warmup profile.

    Returns:
        tuple: (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload)
    """
    live_caption_details = get_api_config(config, 'live_caption')

    # Extract endpoints safely
    endpoints = live_caption_details.get("endpoints", {})
    runs_endpoint = endpoints.get("runs")
    metadata_endpoint = endpoints.get("metadata")
    caption_duration = live_caption_details.get("captioning_time", 10)

    # Extract profile name and load profile-specific details
    if warmup:
        lvc_profile = "live_caption_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile)
    else:
        lvc_profile = live_caption_details.get("input_profile", '')
        profile_details = get_profile_details(profile_path=profile_path, profile_name=lvc_profile)

    payload = profile_details.get("payloads")
    return lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload