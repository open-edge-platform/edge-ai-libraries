# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
import traceback
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import UploadFile

from audio_analyzer.core.settings import settings
from audio_analyzer.utils.logger import logger


async def save_upload_file(file: UploadFile, upload_dir: Optional[Path] = None) -> Path:
    """
    Save an uploaded file to disk.
    
    Args:
        file: The uploaded file
        upload_dir: Directory to save the file to (uses settings.UPLOAD_DIR if not provided)
        
    Returns:
        Path to the saved file
    """
    logger.info(f"Saving uploaded file: {file.filename}")
    
    # Use default upload directory if not provided
    if upload_dir is None:
        upload_dir = Path(settings.UPLOAD_DIR)
        logger.debug(f"Using default upload directory: {upload_dir}")
    
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured upload directory exists: {upload_dir}")
    except Exception as e:
        logger.error(f"Failed to create upload directory {upload_dir}: {e}")
        logger.debug(f"Error details: {traceback.format_exc()}")
        raise RuntimeError(f"Failed to create upload directory: {e}")
    
    # Create a unique filename with timestamp
    timestamp = int(time.time())
    safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
    file_path = upload_dir / safe_filename
    logger.debug(f"Generated safe filename: {safe_filename}")
    
    # Save the file
    try:
        logger.debug(f"Writing file content to: {file_path}")
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)
        logger.info(f"File saved successfully: {file_path}")
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.debug(f"File size: {file_size_mb:.2f} MB")
        
        return file_path
    except Exception as e:
        error_msg = f"Failed to save uploaded file: {e}"
        logger.error(error_msg)
        logger.debug(f"Error details: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e


def get_file_duration(file_path: Path) -> float:
    """
    Get the duration of a media file in seconds.
    
    Args:
        file_path: Path to the media file
        
    Returns:
        Duration in seconds
    """
    logger.debug(f"Getting duration of file: {file_path}")
    
    try:
        from moviepy import VideoFileClip
        
        with VideoFileClip(str(file_path)) as clip:
            duration = clip.duration
            logger.debug(f"File duration: {duration:.2f} seconds")
            return duration
    except Exception as e:
        logger.error(f"Error getting file duration: {e}")
        logger.debug(f"Error details: {traceback.format_exc()}")
        return 0.0


def is_video_file(file_name: str) -> bool:
    """
    Check if a file is a video based on its extension.
    
    Args:
        file_name: Name of the file
        
    Returns:
        True if the file is a video, False otherwise
    """
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.mpg', '.mpeg'}
    extension = Path(file_name).suffix.lower()
    is_video = extension in video_extensions
    
    logger.debug(f"Checking file type: {file_name} with extension {extension} - Is video: {is_video}")
    return is_video