# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration utilities for the Video Search and Summarization application.

This module provides functions for reading VSS-specific configuration
and profile details from YAML config files.

Functions:
  - get_enabled_vss_apis(config)                 : returns which VSS APIs are enabled
  - get_video_summary_profile_details(...)        : full profile details for video summary API
  - get_video_search_profile_details(...)         : full profile details for video search API
"""

from common.config import get_api_config, get_profile_details


def get_enabled_vss_apis(config):
    """
    Return which Video Search and Summarization APIs are enabled.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        tuple: (video_summary_enabled, video_search_enabled)
    """
    video_summary_enabled = get_api_config(config, 'video_summary').get("enabled", False)
    video_search_enabled = get_api_config(config, 'video_search').get("enabled", False)
    return video_summary_enabled, video_search_enabled


def get_video_summary_profile_details(profile_path, config, warmup=False):
    """
    Retrieve video summary API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to use the warmup profile.

    Returns:
        tuple: (video_profile, upload_endpoint, summary_endpoint, states_endpoint,
                telemetry_endpoint, filename, filepath, payload)
    """
    video_summary_details = get_api_config(config, 'video_summary')

    # Extract endpoints safely
    endpoints = video_summary_details.get("endpoints", {})
    upload_endpoint = endpoints.get("upload")
    summary_endpoint = endpoints.get("summary")
    states_endpoint = endpoints.get("states")
    telemetry_endpoint = endpoints.get("telemetry")

    # Extract profile name and load profile-specific details
    if warmup:
        video_profile = "video_summary_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    else:
        video_profile = video_summary_details.get("input_profile", '')
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)

    # Extract file information
    file_details = profile_details.get('files', [])
    if not file_details:
        raise ValueError("No files defined in the video summary profile")

    filename = file_details[0]["name"]
    filepath = file_details[0]["path"]

    # Extract payload configuration
    payload = profile_details.get('payload', {})

    return video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload


def get_video_search_profile_details(profile_path, config, warmup=False):
    """
    Retrieve video search API profile details.

    Args:
        profile_path: Path to the profiles YAML file.
        config: Pre-loaded configuration dict.
        warmup: Whether to use the warmup profile.

    Returns:
        tuple: (video_profile, upload_endpoint, search_endpoint, embed_endpoint,
                telemetry_endpoint, file_details, queries)
    """
    video_search_details = get_api_config(config, 'video_search')

    # Extract endpoints safely
    endpoints = video_search_details.get("endpoints", {})
    upload_endpoint = endpoints.get("upload")
    search_endpoint = endpoints.get("search")
    embed_endpoint = endpoints.get("embedding")
    telemetry_endpoint = endpoints.get("telemetry")

    # Extract profile name and load profile-specific details
    if warmup:
        video_profile = "video_search_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    else:
        video_profile = video_search_details.get("input_profile", '')
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)

    # Extract file details and queries
    file_details = profile_details.get('files')
    queries = profile_details.get('queries')

    return video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries
