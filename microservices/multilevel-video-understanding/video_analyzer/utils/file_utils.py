# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import ipaddress
import socket
import traceback
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import requests
import tempfile
import pathlib
from fastapi import HTTPException, status
from decord import VideoReader, cpu
from video_analyzer.core.settings import settings
from video_analyzer.schemas.summarization import ErrorResponse

from video_analyzer.utils.logger import logger


_PRIVATE_NETS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
    )
)


def _is_public_host(host: str) -> bool:
    if not host or host.lower() == "localhost":
        return False
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError:
            return False
        if any(ip in network for network in _PRIVATE_NETS):
            return False
    return bool(addresses)


def validate_remote_url(raw_url: str) -> str:
    """Return a normalized public HTTP(S) URL suitable for a single fetch."""
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not _is_public_host(parsed.hostname or ""):
        raise ValueError("URL host is not allowed")
    return urlunparse((parsed.scheme.lower(), parsed.netloc, parsed.path, "", parsed.query, ""))


def validate_local_path(raw_path: str) -> str:
    """Resolve a service-visible media path within configured input roots."""
    requested_path = os.path.abspath(os.path.expanduser(raw_path))
    for configured_root in settings.VIDEO_ALLOWED_PATHS:
        root = Path(configured_root).expanduser().resolve()
        relative_path = os.path.relpath(requested_path, root)
        if relative_path != os.pardir and not relative_path.startswith(os.pardir + os.sep):
            path = (root / relative_path).resolve()
            if path.is_relative_to(root):
                break
    else:
        raise ValueError("Local path is outside the configured video input paths")
    if not path.is_file():
        raise FileNotFoundError("Local file not found")
    return str(path)


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
    Robust video loading function supporting local files, HTTP, and HTTPS URLs.

    decord's VideoReader cannot reliably open HTTP/HTTPS URLs directly
    (FFmpeg filter graph creation fails), so remote videos are downloaded
    to a temporary file first.
    """
    scheme = urlparse(url).scheme.lower()

    # Local files: open directly with decord
    if scheme in ("", "file"):
        local_path = urlparse(url).path if scheme == "file" else url
        return VideoReader(local_path, ctx=ctx, width=width, height=height, num_threads=num_threads)

    # HTTP / HTTPS: download to temp file first
    if scheme in ("http", "https"):
        validated_url = validate_remote_url(url)
        logger.info("Downloading video from approved remote host")
        response = requests.get(validated_url, stream=True, allow_redirects=False,
                    verify=(verify_ssl if scheme == "https" else True), timeout=60)
        response.raise_for_status()

        suffix = ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_path = temp_file.name

        logger.info("Downloaded to temp file: %s", temp_path)
        vr = VideoReader(temp_path, ctx=ctx, width=width, height=height, num_threads=num_threads)
        os.unlink(temp_path)
        return vr

    raise ValueError(f"Unsupported URL scheme: {scheme}")

def download_to_temp(video_path: str) -> str | None:
    """Download a remote (HTTP/HTTPS) video to a local temp file.

    Returns the temp file path, or None if video_path is already local.
    Caller is responsible for deleting the temp file after use.
    """
    scheme = urlparse(video_path).scheme.lower()
    if scheme not in ("http", "https"):
        return None

    validated_url = validate_remote_url(video_path)
    logger.info("Downloading video from approved remote host")
    response = requests.get(validated_url, stream=True, allow_redirects=False, timeout=60)
    response.raise_for_status()

    suffix = os.path.splitext(urlparse(video_path).path)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
        temp_path = f.name

    logger.info("Downloaded to: %s", temp_path)
    return temp_path


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
        try:
            return validate_local_path(local_path)
        except (ValueError, FileNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message="Local file not found",
                    details=f"{local_path}"
                ).model_dump()
            )
    if scheme in ("http", "https"):
        # Simple syntax / extension check
        ext = pathlib.Path(parsed.path).suffix.lower()
        video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".mpeg", ".mpg"}
        if not parsed.netloc or not _is_public_host(parsed.hostname or ""):
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
        return urlunparse((scheme, parsed.netloc, parsed.path, "", parsed.query, ""))

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ErrorResponse(
            error_message="Unsupported URI scheme",
            details=f"{scheme}"
        ).model_dump()
    )
