# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Core Utilities Module

This module contains utility functions organized by functionality area.
All utilities support in-process embedding generation.

Sub-modules:
- video_utils: Video processing and frame extraction utilities
- config_utils: Configuration loading and validation utilities
- file_utils: File operations and temporary directory management
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
from . import common_utils

# Import key functions for backward compatibility
# This allows existing code to import directly from utils package

# Configuration utilities
from .config_utils import (
    get_config,
)

# Common utilities  
from .common_utils import (
    sanitize_input,
    get_minio_client,
    create_detector_instance
)

# File utilities
from .file_utils import (
    resolve_under_ingest_root,
    to_host_path,
    stream_file_range
)

# Video utilities
from .video_utils import (
    get_video_from_minio,
)

__all__ = [
    # Sub-modules
    'video_utils',
    'config_utils', 
    'file_utils',
    'common_utils',
    
    # Configuration functions
    'get_config',
    
    # Common functions
    'sanitize_input',
    'get_minio_client',
    'create_detector_instance',
    
    # File functions
    'resolve_under_ingest_root',
    'to_host_path',
    'stream_file_range',
    
    # Video functions
    'get_video_from_minio',
]
