# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File Utilities Module

This module provides file operation utilities for the VDMS microservice.
Supports both SDK mode (direct integration) and API mode (HTTP-based) processing.

Functions:
- save_video_to_temp(): Save video data to temporary file
- create_temp_directory(): Create unique temporary directory
- cleanup_temp_directory(): Clean up temporary directories
- save_metadata_at_temp(): Save metadata to temporary JSON file

Usage:
    from src.core.utils.file_utils import create_temp_directory, cleanup_temp_directory
    
    # Create temporary directory
    temp_dir = create_temp_directory()
    
    # Save video to temporary location
    video_path = save_video_to_temp(video_data, "video.mp4", temp_dir)
    
    # Clean up when done
    cleanup_temp_directory(temp_dir)
"""

import io
import json
import pathlib
import shutil
import uuid
from typing import Dict, Any

from src.common import logger, settings
from .config_utils import get_config


def save_video_to_temp(data: io.BytesIO, filename: str, temp_dir: str) -> pathlib.Path:
    """Save the video data to a temporary directory.

    Args:
        data (io.BytesIO): The video data
        filename (str): The filename to use
        temp_dir (str): The directory path string where videofile needs to be temporarily saved

    Returns:
        pathlib.Path: Path to the saved file
    """
    temp_file = pathlib.Path(temp_dir) / filename
    temp_file.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_file, "wb") as file:
        file.write(data.read())

    return temp_file


def create_temp_directory(base_path: str = None) -> str:
    """
    Create a unique temporary directory for frame extraction.
    
    Args:
        base_path: Base path for temporary directories. If None, uses config default.
        
    Returns:
        Path to the created temporary directory
    """
    if base_path is None:
        config = get_config()
        base_path = config.get("frames_temp_dir", "/tmp/dataprep/vdms_frames")
    
    unique_id = uuid.uuid4().hex
    temp_dir = pathlib.Path(base_path) / f"frames_{unique_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def cleanup_temp_directory(temp_dir: str) -> None:
    """
    Clean up temporary directory and all its contents.
    
    Args:
        temp_dir: Path to the temporary directory to clean up
    """
    try:
        temp_path = pathlib.Path(temp_dir)
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary directory {temp_dir}: {e}")


def save_metadata_at_temp(metadata_temp_path: str, metadata: dict) -> pathlib.Path:
    """
    Dumps the metadata dictionary in json format in a temporary file.

    Args:
        metadata_temp_path (str) : Temporary path where metadata json needs to be saved
        metadata (dict) :  the metadata content as python dict

    Returns:
        metadata_file (Path) : Path of the metadata file location
    """
    metadata_path = pathlib.Path(metadata_temp_path)
    metadata_path.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_path / settings.METADATA_FILENAME

    logger.info("Saving video metadata to a temporary file...")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    logger.info("Metadata saved!")
    return metadata_file