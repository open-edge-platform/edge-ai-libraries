# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import traceback
from pathlib import Path
import os
from urllib.parse import urlparse
import requests
import tempfile
import pathlib
from fastapi import HTTPException, status
from decord import VideoReader, cpu
from video_analyzer.schemas.summarization import ErrorResponse

from video_analyzer.utils.logger import logger


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
        logger.error(f"Error details: {traceback.format_exc()}")
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

def robust_video_reader(url, ctx=cpu(0), width=-1, height=-1, num_threads=0, verify_ssl=True):
    """
    Robust video loading functions, supporting HTTPS.
    """
    # For local file and HTTP files, directly use decord
    if not urlparse(url).scheme in ['https']:
        return VideoReader(url, ctx=ctx, width=width, height=height, num_threads=num_threads)
    
    # For HTTPS URL, download first
    response = requests.get(url, stream=True, verify=verify_ssl, timeout=30)
    response.raise_for_status()
    
    # Create temporary files
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_path = temp_file.name
    
    vr = VideoReader(temp_path, ctx=ctx, width=width, height=height, num_threads=num_threads)
    
    # Clean up temporary files
    os.unlink(temp_path)
    
    return vr

def validate_video_path(raw: str) -> str:
    """
    Validate video path format:
    - local path (relative/absolute)
    - file://
    - http:// / https:// (only syntax check, no network request)
    """
    if not raw or not isinstance(raw, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_message="Invalid video path",
                details="Empty video path"
            ).model_dump()
        )
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()

    if scheme in ("", "file"):
        local_path = parsed.path if scheme == "file" else raw
        local_path = os.path.abspath(os.path.expanduser(local_path))
        if not os.path.isfile(local_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message="Local file not found",
                    details=f"{local_path}"
                ).model_dump()
            )
        return local_path

    if scheme in ("http", "https"):
        # Simple syntax / extension check
        ext = pathlib.Path(parsed.path).suffix.lower()
        video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".mpeg", ".mpg"}
        if not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message="Invalid URL",
                    details="Missing host part"
                ).model_dump()
            )
        if ext and ext not in video_exts:
            # Allow missing extension (stream endpoints), reject wrong extension
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message="Unsupported video extension",
                    details=f"{ext}"
                ).model_dump()
            )
        return raw

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ErrorResponse(
            error_message="Unsupported URI scheme",
            details=f"{scheme}"
        ).model_dump()
    )
