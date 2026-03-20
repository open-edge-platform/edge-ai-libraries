# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Constants for GenAI application sizing tool.

This module centralizes all magic numbers and configuration constants
used throughout the profiling tool.
"""

# ==============================================================================
# Timeout Values (in seconds)
# ==============================================================================

VIDEO_SUMMARY_TIMEOUT_SECONDS = 3600  # 1 hour timeout for video summary completion
POLLING_INTERVAL_SECONDS = 10         # Interval between status poll requests
PERF_TOOL_STOP_DELAY_SECONDS = 2      # Delay before stopping performance tool
DOCKER_REMOVAL_TIMEOUT_SECONDS = 5    # Timeout for docker container removal

# ==============================================================================
# Frame Extraction Configuration
# ==============================================================================

FRAME_EXTRACTION_RATIO = 15    # Extract 1 frame per N frames for embedding
NORMALIZED_FPS_BASELINE = 30   # Baseline FPS for normalized RTF calculation

# ==============================================================================
# File Permissions
# ==============================================================================

DIRECTORY_PERMISSION = 0o770   # rwxrwx---
UMASK_VALUE = 0o007            # Inverse of 0o770

# ==============================================================================
# Storage Configuration
# ==============================================================================

DEFAULT_BUCKET_NAME = "appuser.gai.ragfiles"

# ==============================================================================
# Default Values
# ==============================================================================

DEFAULT_MAX_TOKENS = "1024"
DEFAULT_CAPTION_DURATION = 120  # seconds
