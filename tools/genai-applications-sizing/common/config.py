# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Configuration reading and profile management utilities.

This module provides generic functions for reading YAML configuration files
and extracting common settings and profile details.

Function naming conventions:
  - get_api_config(config, api_name) : generic single-section accessor
  - get_global_config(config)        : global section accessor
  - get_profile_details(...)         : profile lookup from profiles YAML
  - get_global_details(config)       : global settings + directory setup
"""

import os
import yaml


def read_yaml_config(config_path):
    """
    Read configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        dict: Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
        ValueError: If the file is empty, not a regular file, has an invalid
            extension, or does not parse to a mapping.
        PermissionError: If the file cannot be read due to insufficient permissions.
        yaml.YAMLError: If the file contains invalid YAML syntax.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    if not os.path.isfile(config_path):
        raise ValueError(f"Path is not a regular file: {config_path}")

    if not os.access(config_path, os.R_OK):
        raise PermissionError(f"Permission denied reading configuration file: {config_path}")

    if os.path.getsize(config_path) == 0:
        raise ValueError(f"Configuration file is empty: {config_path}")

    _, ext = os.path.splitext(config_path)
    if ext.lower() not in ('.yaml', '.yml'):
        raise ValueError(f"Configuration file must have a .yaml or .yml extension: {config_path}")

    with open(config_path, 'r') as file:
        raw = file.read()

    config = yaml.safe_load(raw)

    if config is None:
        raise ValueError(f"Configuration file parsed to an empty document: {config_path}")

    if not isinstance(config, dict):
        raise ValueError(
            f"Configuration file must contain a YAML mapping at the top level, "
            f"got {type(config).__name__}: {config_path}"
        )

    return config


def get_global_config(config):
    """
    Retrieve the global configuration section.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        dict: Global configuration settings.
    """
    return config.get('global', {})


def get_api_config(config, api_name):
    """
    Retrieve configuration for a named API from the apis section.

    Args:
        config: Pre-loaded configuration dict.
        api_name: Key identifying the API (e.g. ``'stream_log'``,
            ``'document'``, ``'video_summary'``, ``'video_search'``,
            ``'live_caption'``).

    Returns:
        dict: API configuration sub-dictionary, or ``{}`` if absent.
    """
    return config.get('apis', {}).get(api_name, {})


def get_profile_details(profile_path='profiles/profiles.yaml', profile_name='stream_log_small_text'):
    """
    Retrieve profile details from a YAML file.

    Args:
        profile_path: Path to the profiles YAML file.
        profile_name: Name of the profile to retrieve.

    Returns:
        dict: Profile configuration details.

    Raises:
        FileNotFoundError: If the profile file doesn't exist.
        ValueError: If the file is empty, not a regular file, has an invalid
            extension, does not parse to a mapping, is missing the top-level
            ``profiles`` key, or the requested profile name is not found.
        PermissionError: If the file cannot be read due to insufficient permissions.
        yaml.YAMLError: If the file contains invalid YAML syntax.
    """
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Profile file not found: {profile_path}")

    if not os.path.isfile(profile_path):
        raise ValueError(f"Path is not a regular file: {profile_path}")

    if not os.access(profile_path, os.R_OK):
        raise PermissionError(f"Permission denied reading profile file: {profile_path}")

    if os.path.getsize(profile_path) == 0:
        raise ValueError(f"Profile file is empty: {profile_path}")

    _, ext = os.path.splitext(profile_path)
    if ext.lower() not in ('.yaml', '.yml'):
        raise ValueError(f"Profile file must have a .yaml or .yml extension: {profile_path}")

    with open(profile_path, 'r') as file:
        raw = file.read()

    profiles_doc = yaml.safe_load(raw)

    if profiles_doc is None:
        raise ValueError(f"Profile file parsed to an empty document: {profile_path}")

    if not isinstance(profiles_doc, dict):
        raise ValueError(
            f"Profile file must contain a YAML mapping at the top level, "
            f"got {type(profiles_doc).__name__}: {profile_path}"
        )

    profiles = profiles_doc.get('profiles')
    if profiles is None:
        raise ValueError(f"Profile file is missing the top-level 'profiles' key: {profile_path}")

    if not isinstance(profiles, dict):
        raise ValueError(
            f"'profiles' section must be a mapping, "
            f"got {type(profiles).__name__}: {profile_path}"
        )

    if profile_name not in profiles:
        available = ', '.join(sorted(profiles.keys())) or '<none>'
        raise ValueError(
            f"Profile '{profile_name}' not found in {profile_path}. "
            f"Available profiles: {available}"
        )

    return profiles[profile_name]


# ==============================================================================
# Global Details
# ==============================================================================

def get_global_details(config):
    """
    Retrieve global configuration details and initialise the report directory.

    Args:
        config: Pre-loaded configuration dict.

    Returns:
        tuple: (report_dir, perf_tool_repo, profile_path)
    """
    from common.utils import setup_report_permissions

    global_details = get_global_config(config=config)

    # Extract configuration values with defaults
    report_dir = global_details.get('report_dir', 'reports')
    perf_tool_repo = global_details.get('perf_tool_repo', '')
    profile_path = global_details.get('input_profiles_path', 'profiles/profiles.yaml')

    # Ensure report directory exists and set up permissions
    os.makedirs(report_dir, exist_ok=True)
    setup_report_permissions(report_dir)

    return report_dir, perf_tool_repo, profile_path
