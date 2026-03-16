# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for multimodal embedding serving.

This module provides essential utility functions for handling various input types
including images and videos from different sources (URLs, base64, local files).

Key functionality:
- Image downloading and processing from URLs
- Base64 decoding for images and videos  
- Video frame extraction and processing
- File management operations
- Error handling and validation

The utilities support the main application by handling data preprocessing
and format conversions required for embedding generation.
"""

import base64
import ipaddress
import os
import re
import socket
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import decord
import httpx
import numpy as np
from decord import VideoReader, cpu
from PIL import Image
from torchvision.transforms import ToPILImage
from .common import ErrorMessages, logger, settings

decord.bridge.set_bridge("torch")
toPIL = ToPILImage()

# Only include proxies if they are defined
proxies = {}
if settings.http_proxy:
    proxies["http://"] = settings.http_proxy
if settings.https_proxy:
    proxies["https://"] = settings.https_proxy
# if settings.no_proxy_env:
#     proxies["no_proxy"] = settings.no_proxy_env


_SAFE_LOG_PATTERN = re.compile(r"[\r\n\t\x00-\x1f\x7f]+")
_VIDEO_TMP_DIR = Path(tempfile.gettempdir()) / "videoQnA"
_MAX_REMOTE_REDIRECTS = 3


def sanitize_for_log(value, max_len: int = 1024) -> str:
    """Return a compact, single-line representation for safe logging."""
    text = "" if value is None else str(value)
    text = _SAFE_LOG_PATTERN.sub(" ", text)
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _sanitize_filename_component(name: str) -> str:
    """Sanitize a user-influenced filename component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name or "")
    cleaned = cleaned.strip("._")
    return cleaned or "video"


def _is_private_or_local_host(hostname: str) -> bool:
    """Check whether hostname resolves to private/local addresses."""
    host = (hostname or "").strip().lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass

    try:
        for entry in socket.getaddrinfo(host, None):
            resolved_ip = ipaddress.ip_address(entry[4][0])
            if (
                resolved_ip.is_private
                or resolved_ip.is_loopback
                or resolved_ip.is_link_local
                or resolved_ip.is_multicast
                or resolved_ip.is_reserved
                or resolved_ip.is_unspecified
            ):
                return True
    except socket.gaierror:
        return False
    return False


def validate_remote_media_url(url: str) -> str:
    """Validate untrusted media URL to mitigate SSRF."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    if _is_private_or_local_host(parsed.hostname):
        raise ValueError("Local/private network URLs are not allowed")
    return url


def resolve_safe_local_path(file_path: str, allowed_root: Path = _VIDEO_TMP_DIR) -> str:
    """Resolve and validate a local path under an allowed root."""
    resolved_root = allowed_root.expanduser().resolve()
    candidate_path = Path(file_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = resolved_root / candidate_path
    resolved_path = candidate_path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path outside allowed directory: {resolved_path}")
    return str(resolved_path)


def build_safe_temp_path(file_name: str, allowed_root: Path = _VIDEO_TMP_DIR) -> str:
    """Build an internal temp path under the allowed root."""
    resolved_root = allowed_root.expanduser().resolve()
    candidate_path = (resolved_root / Path(file_name).name).resolve(strict=False)
    candidate_path.relative_to(resolved_root)
    return str(candidate_path)


def _get_remote_media_client_kwargs(url: str) -> tuple[str, dict]:
    """Return a validated URL and client kwargs for remote media requests."""
    validated_url = validate_remote_media_url(url)
    client_kwargs = {"follow_redirects": False}
    if not (
        settings.no_proxy_env
        and should_bypass_proxy(validated_url, settings.no_proxy_env)
    ):
        client_kwargs["proxies"] = proxies if proxies else None
    return validated_url, client_kwargs


def _resolve_redirect_url(current_url: str, location: str) -> str:
    """Resolve and validate a redirect target against the current URL."""
    if not location:
        raise RuntimeError("Redirect response missing Location header")
    return validate_remote_media_url(str(httpx.URL(current_url).join(location)))


async def _get_remote_media_response(url: str) -> tuple[httpx.Response, str]:
    """Fetch a remote media URL while validating every redirect target."""
    current_url, client_kwargs = _get_remote_media_client_kwargs(url)
    async with httpx.AsyncClient(**client_kwargs) as client:
        for _ in range(_MAX_REMOTE_REDIRECTS + 1):
            request = client.build_request("GET", validate_remote_media_url(current_url))
            response = await client.send(request)
            if response.has_redirect_location:
                redirect_url = _resolve_redirect_url(
                    current_url, response.headers.get("location")
                )
                await response.aclose()
                current_url = redirect_url
                continue
            response.raise_for_status()
            return response, current_url
    raise RuntimeError("Too many redirects while downloading remote media")


def should_bypass_proxy(url: str, no_proxy: str) -> bool:
    """
    Determines if the given URL should bypass the proxy based on no_proxy setting.

    Checks if the hostname of the provided URL matches any domain specified
    in the no_proxy configuration, allowing for direct connections to those
    domains without going through the proxy server.

    Args:
        url: The URL to check for proxy bypass
        no_proxy: Comma-separated list of domains that should bypass proxy

    Returns:
        True if the URL should bypass the proxy, False otherwise
        
    Note:
        The function performs suffix matching, so 'example.com' will match
        both 'example.com' and 'subdomain.example.com'.
    """
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if not hostname:
        return False

    no_proxy_list = no_proxy.split(",")
    for domain in no_proxy_list:
        if hostname.endswith(domain):
            return True
    return False


async def download_image(image_url: str) -> Image.Image:
    """
    Downloads an image from a given URL with proxy support.

    Downloads an image from the specified URL, handling proxy configuration
    and no_proxy settings. The function automatically determines whether to
    use proxy settings based on the URL and configuration.

    Args:
        image_url: URL of the image to download

    Returns:
        Downloaded image as a numpy array that can be converted to PIL Image

    Raises:
        RuntimeError: If there is an error during the download process,
            including network errors, invalid URLs, or HTTP errors

    Note:
        The function respects proxy settings from the application configuration
        and handles both proxied and direct connections as appropriate.
    """
    try:
        logger.debug("Downloading image from remote URL")
        response, _ = await _get_remote_media_response(image_url)
        logger.info("Image downloaded successfully from remote URL")
        image = Image.open(BytesIO(response.content))
        return np.array(image)
    except httpx.RequestError as e:
        logger.error("Error downloading image: %s", sanitize_for_log(e))
        raise RuntimeError(f"{ErrorMessages.DOWNLOAD_FILE_ERROR}: {e}")
    except Exception as e:
        logger.error(
            "Unexpected error occurred while downloading image: %s",
            sanitize_for_log(e),
        )
        raise RuntimeError(f"Unexpected error occurred while downloading image: {e}")


def decode_base64_image(image_base64: str) -> Image.Image:
    """
    Decodes a base64 encoded image string to PIL Image.

    Handles base64 decoding of image data, supporting both data URL format
    (with MIME type prefix) and plain base64 strings. The function automatically
    detects and handles the format appropriately.

    Args:
        image_base64: Base64 encoded image string, optionally with data URL prefix
            (e.g., "data:image/jpeg;base64,...")

    Returns:
        Decoded PIL Image object ready for processing

    Raises:
        RuntimeError: If there is an error during the decoding process,
            including invalid base64 data or unsupported image formats

    Note:
        The function supports common image formats (JPEG, PNG, GIF, etc.)
        and automatically strips data URL prefixes if present.
    """
    try:
        logger.debug("Decoding base64 image")
        if "," in image_base64:
            image_data = base64.b64decode(image_base64.split(",")[1])
        else:
            image_data = base64.b64decode(image_base64)
        logger.info("Image decoded successfully")
        return Image.open(BytesIO(image_data))
    except (IndexError, ValueError, base64.binascii.Error) as e:
        logger.error(f"Error decoding base64 image: {e}")
        raise RuntimeError(f"{ErrorMessages.DECODE_BASE64_IMAGE_ERROR}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error decoding base64 image: {e}")
        raise RuntimeError(f"Unexpected error decoding base64 image: {e}")


def delete_file(file_path: str):
    """
    Deletes a file from the filesystem with error handling.

    Safely removes a file from the specified path, handling common error
    conditions and providing appropriate logging. The function gracefully
    handles cases where the file doesn't exist.

    Args:
        file_path: Path of the file to delete

    Raises:
        RuntimeError: If there is an error during the deletion process
            (excluding FileNotFoundError which is handled gracefully)

    Note:
        If the file doesn't exist, a warning is logged but no exception
        is raised, making this function safe for cleanup operations.
    """
    try:
        safe_path = resolve_safe_local_path(file_path)
        logger.debug("Deleting file: %s", sanitize_for_log(safe_path))
        os.remove(safe_path)
        logger.info("File deleted successfully: %s", sanitize_for_log(safe_path))
    except FileNotFoundError:
        logger.warning("File not found: %s", sanitize_for_log(file_path))
    except ValueError as e:
        logger.error("Invalid file path for delete operation: %s", sanitize_for_log(e))
        raise RuntimeError(f"{ErrorMessages.DELETE_FILE_ERROR}: {e}")
    except Exception as e:
        logger.error("Error deleting file: %s", sanitize_for_log(e))
        raise RuntimeError(f"{ErrorMessages.DELETE_FILE_ERROR}: {e}")


async def download_video(video_url: str) -> str:
    """
    Downloads a video from a given URL with proxy support.

    Downloads a video file from the specified URL to a temporary location,
    handling proxy configuration and providing comprehensive error handling.
    The video is saved with a unique filename to avoid conflicts.

    Args:
        video_url: URL of the video to download

    Returns:
        Path to the downloaded video file as a string

    Raises:
        RuntimeError: If there is an error during the download process,
            including network errors, invalid URLs, or HTTP errors

    Note:
        The downloaded video file should be cleaned up by the caller
        using the delete_file() function when no longer needed.
    """
    try:
        logger.debug("Downloading video from remote URL")
        current_url, client_kwargs = _get_remote_media_client_kwargs(video_url)
        async with httpx.AsyncClient(**client_kwargs) as client:
            for _ in range(_MAX_REMOTE_REDIRECTS + 1):
                request = client.build_request("GET", validate_remote_media_url(current_url))
                response = await client.send(request, stream=True)
                if response.has_redirect_location:
                    current_url = _resolve_redirect_url(
                        current_url, response.headers.get("location")
                    )
                    await response.aclose()
                    continue

                response.raise_for_status()
                parsed_url = urlparse(current_url)
                filename = os.path.basename(parsed_url.path)
                filename_without_ext = (
                    os.path.splitext(filename)[0] if filename else "video"
                )
                filename_without_ext = _sanitize_filename_component(filename_without_ext)
                unique_filename = f"{uuid.uuid4().hex}_{filename_without_ext}"
                _VIDEO_TMP_DIR.mkdir(parents=True, exist_ok=True)
                video_path = build_safe_temp_path(unique_filename)
                os.makedirs(os.path.dirname(video_path), exist_ok=True)
                with open(video_path, "wb") as video_file:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        video_file.write(chunk)
                await response.aclose()
                logger.info("Video downloaded successfully from remote URL")
                return video_path

        raise RuntimeError("Too many redirects while downloading remote media")
    except httpx.RequestError as e:
        logger.error("Error downloading video: %s", sanitize_for_log(e))
        raise RuntimeError(f"{ErrorMessages.DOWNLOAD_FILE_ERROR}: {e}")
    except Exception as e:
        logger.error(
            "Unexpected error occurred while downloading video: %s",
            sanitize_for_log(e),
        )
        raise RuntimeError(f"Unexpected error occurred while downloading video: {e}")


def decode_base64_video(video_base64: str) -> str:
    """
    Decodes a base64 encoded video string and saves it to a temporary file.

    Handles base64 decoding of video data, supporting both data URL format
    (with MIME type prefix) and plain base64 strings. The decoded video is
    saved to a unique temporary file location.

    Args:
        video_base64: Base64 encoded video string, optionally with data URL prefix
            (e.g., "data:video/mp4;base64,...")

    Returns:
        Path to the decoded video file as a string

    Raises:
        RuntimeError: If there is an error during the decoding process,
            including invalid base64 data or file I/O errors

    Note:
        The decoded video file should be cleaned up by the caller
        using the delete_file() function when no longer needed.
    """
    try:
        logger.debug("Decoding base64 video")
        # Decode the video data
        if "," in video_base64:
            video_data = base64.b64decode(video_base64.split(",")[1])
        else:
            video_data = base64.b64decode(video_base64)
        # Create filename without extension
        unique_filename = f"base64DecodedVideo_{uuid.uuid4().hex}"
        _VIDEO_TMP_DIR.mkdir(parents=True, exist_ok=True)
        video_path = build_safe_temp_path(unique_filename)
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        with open(video_path, "wb") as video_file:
            video_file.write(video_data)
        logger.info("Video decoded successfully")
        return video_path
    except Exception as e:
        logger.error(f"Error decoding base64 video: {e}")
        raise RuntimeError(f"{ErrorMessages.DECODE_BASE64_VIDEO_ERROR}: {e}")


def extract_video_frames(video_path: str, segment_config: dict = None) -> list:
    """
    Extracts frames from a video with configurable extraction modes.

    Supports multiple frame extraction strategies with flexible configuration
    options. The function can extract specific frames by index, sample at
    a given frame rate, or uniformly sample a specified number of frames.

    Args:
        video_path: Path to the video file to process
        segment_config: Configuration dictionary for video segmentation with options:
            - startOffsetSec: Starting offset in seconds (default: 0)
            - clip_duration: Duration of clip to extract from (-1 for full video)
            - frame_indexes: Array of specific frame indices (highest priority)
            - fps: Frames per second for uniform sampling (can be fractional)
            - num_frames: Number of frames for uniform sampling (lowest priority)

    Returns:
        List of extracted video frames as PIL Image objects

    Raises:
        RuntimeError: If there is an error during the frame extraction process,
            including invalid video files or unsupported formats

    Note:
        Priority order: frame_indexes > fps > num_frames. If multiple extraction
        methods are specified, the highest priority method will be used.
    """
    try:
        logger.debug("Extracting frames from video input")
        if segment_config is None:
            segment_config = {}

        start_offset_sec = segment_config.get(
            "startOffsetSec", settings.DEFAULT_START_OFFSET_SEC
        )
        clip_duration = segment_config.get(
            "clip_duration", settings.DEFAULT_CLIP_DURATION
        )
        num_frames = segment_config.get("num_frames", settings.DEFAULT_NUM_FRAMES)
        extraction_fps = segment_config.get("extraction_fps")
        frame_indexes = segment_config.get("frame_indexes")
        
        logger.debug("Video frame extraction configuration prepared")

        vr = VideoReader(video_path, ctx=cpu(0))
        vlen = len(vr)
        video_fps = vr.get_avg_fps()
        start_idx = int(video_fps * start_offset_sec)
        end_idx = (
            min(vlen, start_idx + int(video_fps * clip_duration))
            if clip_duration != -1
            else vlen
        )
        logger.debug(f"Video FPS: {video_fps}, Total frames: {vlen}")
        # Priority 1: frame_indexes - specific frame indices (highest priority)
        if frame_indexes is not None:
            if not isinstance(frame_indexes, (list, tuple, np.ndarray)):
                raise ValueError("frame_indexes must be a list, tuple, or numpy array")
            
            # Convert to numpy array and ensure valid indices
            frame_indexes = np.array(frame_indexes, dtype=int)
            
            # Filter indices to be within the video segment bounds
            valid_indices = frame_indexes[(frame_indexes >= start_idx) & (frame_indexes <= end_idx)]
            
            if len(valid_indices) == 0:
                logger.warning(
                    "No valid frame indices found within segment bounds [%s, %s)",
                    start_idx,
                    end_idx,
                )
                # Fall back to default uniform sampling
                frame_idx = np.linspace(
                    start_idx, end_idx, num=settings.DEFAULT_NUM_FRAMES, endpoint=False, dtype=int
                )
            else:
                frame_idx = valid_indices
            
            logger.debug(f"Using frame_indexes with {len(frame_idx)} valid indices")
        
        # Priority 2: fps - uniform sampling at specified rate
        elif extraction_fps is not None:
            if not isinstance(extraction_fps, (int, float)) or extraction_fps <= 0:
                raise ValueError("fps must be a positive number")
            
            # Calculate frame interval based on user fps (float to preserve precision)
            frame_interval = float(video_fps) / float(extraction_fps)
            
            # Generate frame indices at the specified fps rate
            frame_indices = []
            current_frame = float(start_idx)
            
            while current_frame <= end_idx:
                frame_indices.append(int(current_frame))
                current_frame += frame_interval
            
            frame_idx = np.array(frame_indices, dtype=int)
            logger.debug(f"Using fps={extraction_fps} for sampling, generated {len(frame_idx)} frames")
        
        # Priority 3: num_frames - use explicit value if provided, otherwise use default
        # Default: use DEFAULT_NUM_FRAMES for uniform sampling (lowest priority)
        else:
            frame_idx = np.linspace(
                start_idx, end_idx, num=num_frames, endpoint=False, dtype=int
            )
            logger.debug(f"Using default num_frames={num_frames} for uniform sampling")

        video_frames = []

        # read images
        temp_frms = vr.get_batch(frame_idx.astype(int).tolist())
        for idx in range(temp_frms.shape[0]):
            im = temp_frms[idx]  # H W C
            video_frames.append(toPIL(im.permute(2, 0, 1)))
        logger.info(
            "%s Frames extracted successfully from video: %s",
            len(video_frames),
            sanitize_for_log(video_path),
        )
        return video_frames
    except Exception as e:
        logger.error("Error extracting video frames: %s", sanitize_for_log(e))
        raise RuntimeError(f"{ErrorMessages.EXTRACT_VIDEO_FRAMES_ERROR}: {e}")
