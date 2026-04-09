# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utilities for multimodal embedding serving.

This module provides essential utility functions and configurations for the
multimodal embedding serving application. It includes common functionality
for data processing, file handling, configuration management, and error handling.

Key components:
- Settings management and environment configuration  
- Image and video processing utilities
- File download and format conversion functions
- Logging and error message definitions
- Base64 encoding/decoding utilities

The utilities support various input formats including URLs, base64 encoded data,
and local files, enabling flexible data input for embedding generation.
"""

from .common import Settings, ErrorMessages, logger, settings
from .utils import (
    build_safe_temp_path,
    should_bypass_proxy,
    download_image,
    decode_base64_image,
    delete_file,
    download_video,
    decode_base64_video,
    extract_video_frames,
    sanitize_for_log,
    resolve_safe_local_path,
    validate_remote_media_url,
)

__all__ = [
    "Settings",
    "ErrorMessages", 
    "logger",
    "settings",
    "build_safe_temp_path",
    "should_bypass_proxy",
    "download_image",
    "decode_base64_image",
    "delete_file",
    "download_video",
    "decode_base64_video",
    "extract_video_frames",
    "sanitize_for_log",
    "resolve_safe_local_path",
    "validate_remote_media_url",
]