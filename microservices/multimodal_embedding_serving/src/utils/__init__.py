# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utilities for multimodal embedding serving.

This module contains utility functions and common configurations for the
multimodal embedding serving application.
"""

from .common import Settings, ErrorMessages, logger, settings
from .utils import (
    should_bypass_proxy,
    download_image,
    decode_base64_image,
    delete_file,
    download_video,
    decode_base64_video,
    extract_video_frames,
)

__all__ = [
    "Settings",
    "ErrorMessages", 
    "logger",
    "settings",
    "should_bypass_proxy",
    "download_image",
    "decode_base64_image",
    "delete_file",
    "download_video",
    "decode_base64_video",
    "extract_video_frames",
]