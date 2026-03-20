# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration reading and profile management utilities.

This module provides functions for reading YAML configuration files
and extracting API-specific settings and profile details.
"""

import os
import yaml


def read_yaml_config(config_path='config.yaml'):
    """
    Read configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file.
        
    Returns:
        dict: Parsed configuration dictionary.
        
    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)


def get_global_config(config=None, config_path='config.yaml'):
    """
    Retrieve global configuration section.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Global configuration settings.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('global', {})


def get_stream_log_config(config=None, config_path='config.yaml'):
    """
    Retrieve stream log API configuration.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Stream log API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('stream_log', {})


def get_document_config(config=None, config_path='config.yaml'):
    """
    Retrieve document API configuration.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Document API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('document', {})


def get_profile_details(profile_path='input_profiles.yaml', profile_name='stream_log_small_text'):
    """
    Retrieve profile details from a YAML file.
    
    Args:
        profile_path: Path to the profiles YAML file.
        profile_name: Name of the profile to retrieve.
        
    Returns:
        dict: Profile configuration details.
        
    Raises:
        FileNotFoundError: If the profile file doesn't exist.
    """
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Profile file not found: {profile_path}")
    with open(profile_path, 'r') as file:
        profiles = yaml.safe_load(file)
        return profiles.get('profiles', {}).get(profile_name, {})


def get_enabled_apis(input_file):
    """
    Determine which APIs are enabled based on the configuration file.
    
    Args:
        input_file: Path to the input configuration file.
        
    Returns:
        tuple: (stream_log_api_enabled, document_api_enabled)
    """
    config = read_yaml_config(input_file)
    stream_log_api_enabled = config.get('apis', {}).get('stream_log', {}).get("enabled", False)
    document_api_enabled = config.get('apis', {}).get('document', {}).get("enabled", False)
    return stream_log_api_enabled, document_api_enabled


def get_stream_api_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieve stream API profile details from configuration and profile files.
    
    Args:
        profile_path: Path to the profiles YAML file.
        input_file: Path to the input configuration file.
        warmup: Boolean flag indicating if warmup mode is enabled.
        
    Returns:
        tuple: (profile, chat_endpoint, doc_endpoint, prompt, filename, 
                filepath, service_name, max_tokens)
    """
    # Load configuration and extract stream log API details
    config = read_yaml_config(input_file)
    stream_log_api_details = get_stream_log_config(config=config)
    
    # Extract endpoints safely
    endpoints = stream_log_api_details.get("endpoints", {})
    doc_endpoint = endpoints.get("document")
    chat_endpoint = endpoints.get("chat")
    
    # Extract service configuration
    service_name = stream_log_api_details.get("service_name", {})
    profile = stream_log_api_details.get("input_profile", {})
    
    # Load profile-specific details
    if warmup:
        stream_log_profile_details = get_profile_details(profile_path=profile_path, profile_name='chatqna_warmup_profile')
    else:
        stream_log_profile_details = get_profile_details(profile_path=profile_path, profile_name=profile)
        
    prompt = stream_log_profile_details.get("prompt")
    max_tokens = stream_log_profile_details.get("max_tokens", "1024")
    
    # Extract file information
    file_details = stream_log_profile_details.get('files', [])
    if not file_details:
        raise ValueError("No files defined in the profile")
    
    filename = file_details[0]["name"]
    filepath = file_details[0]["path"]
    
    return profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens


def get_document_api_profile_details(profile_path, input_file):
    """
    Retrieve document API profile details from configuration and profile files.
    
    Args:
        profile_path: Path to the profiles YAML file.
        input_file: Path to the input configuration file.
        
    Returns:
        tuple: (document_profile, document_endpoint, file_details)
    """
    # Load configuration and extract document API details
    config = read_yaml_config(input_file)
    document_api_details = get_document_config(config=config)
    
    # Extract profile name and load profile-specific details
    document_profile = document_api_details.get("input_profile", "")
    document_profile_details = get_profile_details(
        profile_path=profile_path, 
        profile_name=document_profile
    )
    
    # Extract endpoint URL safely with nested get
    document_endpoint = document_api_details.get("endpoints", {}).get("document")
    
    # Extract file details with proper default
    file_details = document_profile_details.get('files', [])
    
    return document_profile, document_endpoint, file_details


# ==============================================================================
# Video API Configuration
# ==============================================================================

def get_video_summary_config(config=None, config_path='config.yaml'):
    """
    Retrieve video summary API configuration from the YAML config file.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Video summary API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('video_summary', {})


def get_video_search_config(config=None, config_path='config.yaml'):
    """
    Retrieve video search API configuration from the YAML config file.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Video search API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('video_search', {})


def get_enabled_video_apis(input_file):
    """
    Determine which video-related APIs are enabled based on the configuration file.
    
    Args:
        input_file: Path to the input configuration file.
        
    Returns:
        tuple: (video_summary_enabled, video_search_enabled)
    """
    config = read_yaml_config(input_file)
    video_summary_enabled = get_video_summary_config(config=config).get("enabled", False)
    video_search_enabled = get_video_search_config(config=config).get("enabled", False)
    return video_summary_enabled, video_search_enabled


def get_video_summary_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieve video summary API profile details from configuration and profile files.
    
    Args:
        profile_path: Path to the profiles YAML file.
        input_file: Path to the input configuration file.
        warmup: Whether to use warmup profile.
        
    Returns:
        tuple: (video_profile, upload_endpoint, summary_endpoint, states_endpoint,
                telemetry_endpoint, filename, filepath, payload)
    """
    # Load configuration and extract video summary API details
    config = read_yaml_config(input_file)
    video_summary_details = get_video_summary_config(config=config)
    
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


def get_video_search_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieve video search API profile details from configuration and profile files.
    
    Args:
        profile_path: Path to the profiles YAML file.
        input_file: Path to the input configuration file.
        warmup: Whether to use warmup profile.
        
    Returns:
        tuple: (video_profile, upload_endpoint, search_endpoint, embed_endpoint,
                telemetry_endpoint, file_details, queries)
    """
    # Load configuration and extract video search API details
    config = read_yaml_config(input_file)
    video_search_details = get_video_search_config(config=config)
    
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


# ==============================================================================
# Live Caption API Configuration
# ==============================================================================

def get_live_caption_config(config=None, config_path='config.yaml'):
    """
    Retrieve live caption API configuration from the YAML config file.
    
    Args:
        config: Pre-loaded configuration dict (optional).
        config_path: Path to config file if config not provided.
        
    Returns:
        dict: Live caption API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('live_caption', {})


def get_enabled_live_caption_apis(input_file):
    """
    Determine if live caption API is enabled based on the configuration file.
    
    Args:
        input_file: Path to the input configuration file.
        
    Returns:
        bool: True if live caption API is enabled.
    """
    config = read_yaml_config(input_file)
    return get_live_caption_config(config=config).get("enabled", False)


def get_live_caption_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieve live caption API profile details from configuration and profile files.
    
    Args:
        profile_path: Path to the profiles YAML file.
        input_file: Path to the input configuration file.
        warmup: Whether to use warmup profile.
        
    Returns:
        tuple: (lvc_profile, runs_endpoint, metadata_endpoint, caption_duration, payload)
    """
    # Load configuration and extract live caption API details
    config = read_yaml_config(input_file)
    live_caption_details = get_live_caption_config(config=config)
    
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


def get_global_details(input_file):
    """
    Retrieve global configuration details from the input configuration file.
    
    This function sets up the report directory with proper permissions.
    
    Args:
        input_file: Path to the input configuration file.
        
    Returns:
        tuple: (report_dir, perf_tool_repo, profile_path)
    """
    from common.utils import setup_report_permissions
    
    config = read_yaml_config(input_file)
    global_details = get_global_config(config=config)
    
    # Extract configuration values with defaults
    report_dir = global_details.get('report_dir', 'reports')
    perf_tool_repo = global_details.get('perf_tool_repo', '')
    profile_path = global_details.get('input_profiles_path', 'input_profiles.yaml')
    
    # Ensure report directory exists and set up permissions
    import os
    os.makedirs(report_dir, exist_ok=True)
    setup_report_permissions(report_dir)
    
    return report_dir, perf_tool_repo, profile_path
