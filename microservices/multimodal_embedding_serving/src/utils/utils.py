# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
import tempfile
import uuid
from io import BytesIO
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


def should_bypass_proxy(url: str, no_proxy: str) -> bool:
    """
    Determines if the given URL should bypass the proxy based on the no_proxy setting.

    Args:
        url (str): The URL to check.
        no_proxy (str): The no_proxy setting.

    Returns:
        bool: True if the URL should bypass the proxy, False otherwise.
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
    Downloads an image from a given URL.

    Args:
        image_url (str): URL of the image to download.

    Returns:
        Image.Image: Downloaded image.

    Raises:
        RuntimeError: If there is an error during the download process.
    """
    try:
        logger.debug(f"Downloading image from URL: {image_url}")
        if settings.no_proxy_env and should_bypass_proxy(
            image_url, settings.no_proxy_env
        ):
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
        else:
            async with httpx.AsyncClient(
                proxies=proxies if proxies else None
            ) as client:
                response = await client.get(image_url)
        response.raise_for_status()
        logger.info(f"Image downloaded successfully from URL: {image_url}")
        image = Image.open(BytesIO(response.content))
        return np.array(image)
    except httpx.RequestError as e:
        logger.error(f"Error downloading image: {e}")
        raise RuntimeError(f"{ErrorMessages.DOWNLOAD_FILE_ERROR}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred while downloading image: {e}")
        raise RuntimeError(f"Unexpected error occurred while downloading image: {e}")


def decode_base64_image(image_base64: str) -> Image.Image:
    """
    Decodes a base64 encoded image.

    Args:
        image_base64 (str): Base64 encoded image string.

    Returns:
        Image.Image: Decoded image.

    Raises:
        RuntimeError: If there is an error during the decoding process.
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
    Deletes a file given its path.

    Args:
        file_path (str): Path of the file to delete.

    Raises:
        RuntimeError: If there is an error during the deletion process.
    """
    try:
        logger.debug(f"Deleting file: {file_path}")
        os.remove(file_path)
        logger.info(f"File {file_path} deleted successfully.")
    except FileNotFoundError:
        logger.warning(f"File {file_path} not found.")
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise RuntimeError(f"{ErrorMessages.DELETE_FILE_ERROR}: {e}")


async def download_video(video_url: str) -> str:
    """
    Downloads a video from a given URL.

    Args:
        video_url (str): URL of the video to download.

    Returns:
        str: Path to the downloaded video.

    Raises:
        RuntimeError: If there is an error during the download process.
    """
    try:
        logger.debug(f"Downloading video from URL: {video_url}")
        async with httpx.AsyncClient(proxies=proxies if proxies else None) as client:
            async with client.stream("GET", video_url) as response:
                response.raise_for_status()
                # Get filename from URL (without extension)
                parsed_url = urlparse(video_url)
                filename = os.path.basename(parsed_url.path)
                filename_without_ext = os.path.splitext(filename)[0] if filename else "video"
                # Create unique filename without extension
                unique_filename = f"{uuid.uuid4().hex}_{filename_without_ext}"
                temp_dir = tempfile.gettempdir()
                video_path = os.path.join(temp_dir, "videoQnA", unique_filename)
                os.makedirs(os.path.dirname(video_path), exist_ok=True)
                # Write video data to file
                with open(video_path, "wb") as video_file:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        video_file.write(chunk)
        logger.info(f"Video downloaded successfully from URL: {video_url}")
        return video_path
    except httpx.RequestError as e:
        logger.error(f"Error downloading video: {e}")
        raise RuntimeError(f"{ErrorMessages.DOWNLOAD_FILE_ERROR}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred while downloading video: {e}")
        raise RuntimeError(f"Unexpected error occurred while downloading video: {e}")


def decode_base64_video(video_base64: str) -> str:
    """
    Decodes a base64 encoded video.

    Args:
        video_base64 (str): Base64 encoded video string.

    Returns:
        str: Path to the decoded video.

    Raises:
        RuntimeError: If there is an error during the decoding process.
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
        # Get the default temporary directory based on the OS
        temp_dir = tempfile.gettempdir()
        video_path = os.path.join(temp_dir, "videoQnA", unique_filename)
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
    Extracts frames from a video with multiple extraction modes.

    Args:
        video_path (str): Path to the video file.
        segment_config (dict, optional): Configuration for video segmentation. Defaults to None.
            Supported parameters:
            - startOffsetSec: Starting offset in seconds
            - clip_duration: Duration of clip to extract frames from (-1 for full video)
            - frame_indexes: Array of specific frame indices to extract (highest priority)
            - fps: Frames per second for uniform sampling (medium priority, can be float, including <1)
            - num_frames: Number of frames to extract using uniform sampling (lowest priority)

    Returns:
        list: List of extracted video frames.

    Raises:
        RuntimeError: If there is an error during the frame extraction process.
    """
    try:
        logger.debug(f"Extracting frames from video: {video_path}")
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
        
        logger.debug(
            f"video_path: {video_path} start_offset_sec: {start_offset_sec}, clip_duration: {clip_duration}, "
            f"num_frames: {num_frames}, extraction_fps: {extraction_fps}, frame_indexes: {frame_indexes}"
        )

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
                logger.warning(f"No valid frame indices found within segment bounds [{start_idx}, {end_idx})")
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
            f"{len(video_frames)} Frames extracted successfully from video: {video_path}"
        )
        return video_frames
    except Exception as e:
        logger.error(f"Error extracting video frames: {e}")
        raise RuntimeError(f"{ErrorMessages.EXTRACT_VIDEO_FRAMES_ERROR}: {e}")
