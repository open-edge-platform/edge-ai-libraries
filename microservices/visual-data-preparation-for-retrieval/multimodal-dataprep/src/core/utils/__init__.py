# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Core Utilities Module

This module contains utility functions organized by functionality area.
All utilities support both SDK mode (direct integration) and API mode (HTTP-based) processing.

Sub-modules:
- video_utils: Video processing and frame extraction utilities
- config_utils: Configuration loading and validation utilities
- file_utils: File operations and temporary directory management
- metadata_utils: Metadata generation and storage utilities  
- common_utils: General purpose utility functions

Usage:
    from src.core.utils import video_utils, config_utils
    from src.core.utils.video_utils import get_video_from_minio
    from src.core.utils.config_utils import get_config
    
    # Or import specific functions for backward compatibility
    from src.core.utils import get_video_from_minio, get_config
"""

# Import all utility modules for organized access
from . import video_utils
from . import config_utils  
from . import file_utils
from . import metadata_utils
from . import common_utils

# Import key functions for backward compatibility
# This allows existing code to import directly from utils package

# Configuration utilities
from .config_utils import (
    get_config,
    read_config,
    clear_config_cache
)

# Common utilities  
from .common_utils import (
    sanitize_input,
    get_minio_client,
    create_detector_instance
)

# File utilities
from .file_utils import (
    save_video_to_temp,
    create_temp_directory,
    cleanup_temp_directory,
    save_metadata_at_temp
)

# Video utilities
from .video_utils import (
    get_video_from_minio,
    get_video_fps_and_frames,
    process_video_with_frame_extraction,
    process_video_with_enhanced_detection
)

# Metadata utilities
from .metadata_utils import (
    FrameInfo,
    create_frames_manifest,
    create_enhanced_frame_metadata,
    store_enhanced_video_metadata,
    extract_enhanced_video_metadata
)

__all__ = [
    # Sub-modules
    'video_utils',
    'config_utils', 
    'file_utils',
    'metadata_utils',
    'common_utils',
    
    # Configuration functions
    'get_config',
    'read_config', 
    'clear_config_cache',
    
    # Common functions
    'sanitize_input',
    'get_minio_client',
    'create_detector_instance',
    
    # File functions
    'save_video_to_temp',
    'create_temp_directory',
    'cleanup_temp_directory', 
    'save_metadata_at_temp',
    
    # Video functions
    'get_video_from_minio',
    'get_video_fps_and_frames',
    'process_video_with_frame_extraction',
    'process_video_with_enhanced_detection',
    
    # Metadata functions and classes
    'FrameInfo',
    'create_frames_manifest',
    'create_enhanced_frame_metadata',
    'store_enhanced_video_metadata',
    'extract_enhanced_video_metadata'
]