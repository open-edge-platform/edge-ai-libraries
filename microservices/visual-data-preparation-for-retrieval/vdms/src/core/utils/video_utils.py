# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Video Utilities Module

This module provides video processing utilities for the VDMS microservice.
Supports both SDK mode (direct integration) and API mode (HTTP-based) processing.

Functions:
- get_video_from_minio(): Download video from MinIO storage
- get_video_fps_and_frames(): Get video frame rate and total frame count
- process_video_with_frame_extraction(): Extract frames from video with optional object detection
- process_video_with_enhanced_detection(): Enhanced video processing with object detection

Usage:
    from src.core.utils.video_utils import get_video_from_minio, process_video_with_frame_extraction
    
    # Download video
    video_data, filename = get_video_from_minio(bucket, video_id)
    
    # Process video with frame extraction
    frame_info_list, manifest_path = process_video_with_frame_extraction(video_path)
"""

import io
import pathlib
import time
from typing import List, Optional, Tuple

import cv2
import torch
from decord import VideoReader, cpu
from torchvision.transforms import ToPILImage

from src.common import DataPrepException, Strings, logger
from .common_utils import get_minio_client, FrameInfo
from .config_utils import get_config
from .file_utils import create_temp_directory

# Initialize torchvision transform
toPIL = ToPILImage()


def get_video_from_minio(
    bucket_name: str, video_id: str, video_name: Optional[str] = None
) -> Tuple[io.BytesIO, str]:
    """Get video data from Minio storage.

    Args:
        bucket_name (str): The bucket containing the video
        video_id (str): The directory (video_id) containing the video
        video_name (Optional[str], optional): Specific video filename. If None, first video found is used.

    Returns:
        Tuple[io.BytesIO, str]: Tuple containing the video data and the video filename

    Raises:
        DataPrepException: If video not found or other Minio error occurs
    """
    try:
        minio_client = get_minio_client()

        # Determine the object name
        object_name = None
        if video_name:
            # If video_name is provided, use it directly
            object_name = f"{video_id}/{video_name}"
        else:
            # Otherwise, find the first video in the directory
            object_name = minio_client.get_video_in_directory(bucket_name, video_id)

        if not object_name:
            logger.error(f"No video found in directory {video_id}")
            raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)

        # Get the video data
        data = minio_client.download_video_stream(bucket_name, object_name)
        if not data:
            logger.error(f"Failed to download video {object_name}")
            raise DataPrepException(status_code=404, msg=Strings.minio_file_not_found)

        # Extract just the filename part
        filename = pathlib.Path(object_name).name

        return data, filename
    except DataPrepException as ex:
        # Re-raise DataPrepException directly
        raise ex
    except Exception as ex:
        logger.error(f"Error getting video from Minio: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_error)


def get_video_fps_and_frames(video_local_path: pathlib.Path) -> tuple[float, int]:
    """
    Open the video file and get fps and total frames in video

    Args:
        video_local_path (Path) : Path of the video file

    Returns:
        fps, frames (tuple) : A tuple containing float fps and total num of frames (int)
            in the video.
    """
    cap = cv2.VideoCapture(str(video_local_path))
    if not cap.isOpened():
        raise Exception(Strings.video_open_error)

    fps: float = cap.get(cv2.CAP_PROP_FPS)
    total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    return fps, total_frames


def process_video_with_frame_extraction(
    video_path: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    temp_dir: Optional[str] = None,
    detector=None
) -> Tuple[List[FrameInfo], str, dict]:
    """
    Extract frames from video using frame interval approach.
    This is the core function for the new frame-based processing strategy.
    
    Args:
        video_path: Path to the video file
        frame_interval: Extract every Nth frame. If None, uses config default.
        enable_object_detection: Whether to detect and crop objects. If None, uses config default.
        detection_confidence: Confidence threshold for object detection. If None, uses config default.
        temp_dir: Optional temporary directory path
        detector: Optional YOLOXDetector instance for object detection
        
    Returns:
        Tuple of (frame_info_list, manifest_path, metrics)
        
    Raises:
        Exception: If video processing fails
    """
    try:
        # Get config defaults if parameters not provided
        config = get_config()
        
        if frame_interval is None:
            frame_interval = config.get("frame_interval", 15)
        if enable_object_detection is None:
            enable_object_detection = config.get("enable_object_detection", True)
        if detection_confidence is None:
            detection_confidence = config.get("detection_confidence", 0.85)
        
        logger.info(f"Processing video with frame extraction: {video_path}")
        logger.debug(f"Frame interval: {frame_interval}, Object detection: {enable_object_detection}")
        
        # Create temporary directory if not provided
        if temp_dir is None:
            temp_dir = create_temp_directory()
        
        # Use decord for video processing (same as embedding service)
        vr = VideoReader(video_path, ctx=cpu(0))
        fps = vr.get_avg_fps()
        total_frames = len(vr)
        
        logger.debug(f"Video FPS: {fps}, Total frames: {total_frames}")
        
        # Calculate frame indices (every Nth frame)
        frame_indices = list(range(0, total_frames, frame_interval))
        logger.debug(f"Extracting {len(frame_indices)} frames with interval {frame_interval}")
        
        frame_info_list = []
        
        # Extract all frames first for batch processing optimization
        extracted_frames = []
        frame_metadata = []
        extraction_start = time.perf_counter()
        
        logger.info(f"Extracting {len(frame_indices)} frames for processing...")
        for i, frame_idx in enumerate(frame_indices):
            try:
                # Seek to frame and get it
                vr.seek(frame_idx)
                frame_tensor = vr.next()
                logger.debug(f"Processing frame {i}: frame_idx={frame_idx}, tensor_shape={frame_tensor.shape}")
            except Exception as e:
                logger.error(f"Failed to extract frame {frame_idx}: {e}")
                continue
            timestamp = frame_idx / fps
            
            # Handle different tensor types from decord VideoReader
            try:
                if hasattr(frame_tensor, 'asnumpy'):
                    # It's a decord NDArray - convert to numpy first
                    frame_numpy = frame_tensor.asnumpy()
                    frame_torch = torch.from_numpy(frame_numpy)
                elif hasattr(frame_tensor, 'numpy'):
                    # It's a PyTorch tensor - convert to numpy first
                    frame_numpy = frame_tensor.numpy()
                    frame_torch = torch.from_numpy(frame_numpy)
                elif hasattr(frame_tensor, 'detach'):
                    # It's a PyTorch tensor with gradients - detach first
                    frame_torch = frame_tensor.detach()
                else:
                    # Assume it's already a PyTorch tensor or numpy array
                    if isinstance(frame_tensor, torch.Tensor):
                        frame_torch = frame_tensor
                    else:
                        frame_torch = torch.from_numpy(frame_tensor)
                
                # Convert to PIL Image (ensure correct dimension order: H,W,C -> C,H,W)
                if len(frame_torch.shape) == 3 and frame_torch.shape[-1] == 3:
                    # Format is H,W,C (height, width, channels) - need to permute to C,H,W
                    frame_pil = toPIL(frame_torch.permute(2, 0, 1))
                else:
                    # Assume it's already in correct format
                    frame_pil = toPIL(frame_torch)
                    
            except Exception as tensor_error:
                logger.error(f"Failed to convert frame tensor for frame {frame_idx}: {tensor_error}")
                logger.error(f"Frame tensor type: {type(frame_tensor)}, shape: {getattr(frame_tensor, 'shape', 'unknown')}")
                continue
            
            # Save full frame
            full_frame_filename = f"frame_{frame_idx:06d}.jpg"
            full_frame_path = pathlib.Path(temp_dir) / full_frame_filename
            frame_pil.save(full_frame_path, quality=90, optimize=True)
            
            # Store frame for batch processing
            extracted_frames.append(frame_pil)
            frame_metadata.append({
                'frame_idx': frame_idx,
                'timestamp': timestamp,
                'full_frame_path': full_frame_path,
                'full_frame_filename': full_frame_filename
            })
        
        logger.info(f"Successfully extracted {len(extracted_frames)} frames")
        frame_extraction_seconds = time.perf_counter() - extraction_start
        detection_seconds = 0.0
        
        # Process object detection in optimized batches
        if enable_object_detection and detector is not None:
            detection_batch_size = 32  # Configurable batch size for object detection
            logger.info(f"Processing object detection in batches of {detection_batch_size}")
            detection_timer = time.perf_counter()
            
            # Process frames in batches for optimal performance
            for batch_start in range(0, len(extracted_frames), detection_batch_size):
                batch_end = min(batch_start + detection_batch_size, len(extracted_frames))
                batch_frames = extracted_frames[batch_start:batch_end]
                batch_metadata = frame_metadata[batch_start:batch_end]
                
                logger.debug(f"Processing detection batch {batch_start//detection_batch_size + 1}: frames {batch_start}-{batch_end-1}")
                
                try:
                    # Process each frame in the batch (detector can be optimized for batch processing in the future)
                    for frame_pil, meta in zip(batch_frames, batch_metadata):
                        frame_idx = meta['frame_idx']
                        timestamp = meta['timestamp']
                        full_frame_path = meta['full_frame_path']
                        
                        try:
                            # Get detected crops
                            crops = detector.extract_crops(frame_pil)
                            detection_metadata = detector.get_detection_metadata(frame_pil)
                            
                            logger.debug(f"Frame {frame_idx}: {len(crops)} objects detected")
                            
                            # Always add the full frame first (matching SDK mode behavior)
                            full_frame_info = FrameInfo(
                                frame_number=frame_idx,
                                timestamp=timestamp,
                                image_path=str(full_frame_path),
                                frame_type="full_frame"
                            )
                            frame_info_list.append(full_frame_info)
                            
                            # Additionally add detected crops if any
                            if len(crops) > 0:
                                for j, (crop, det_meta) in enumerate(zip(crops, detection_metadata)):
                                    crop_filename = f"frame_{frame_idx:06d}_crop_{j:03d}.jpg"
                                    crop_path = pathlib.Path(temp_dir) / crop_filename
                                    crop.save(crop_path, quality=90, optimize=True)
                                    
                                    crop_info = FrameInfo(
                                        frame_number=frame_idx,
                                        timestamp=timestamp,
                                        image_path=str(crop_path),
                                        frame_type="detected_crop",
                                        crop_index=j,
                                        detection_confidence=det_meta['confidence'],
                                        crop_bbox=tuple(det_meta['bbox']),
                                        detected_label=det_meta.get('class_name'),
                                        merged_boxes_count=det_meta.get('merged_boxes_count'),
                                        context_expansion_applied=det_meta.get('context_expansion_applied')
                                    )
                                    frame_info_list.append(crop_info)
                                
                        except Exception as e:
                            logger.warning(f"Object detection failed for frame {frame_idx}: {e}")
                            # Fallback to full frame if detection fails
                            frame_info = FrameInfo(
                                frame_number=frame_idx,
                                timestamp=timestamp,
                                image_path=str(full_frame_path),
                                frame_type="full_frame"
                            )
                            frame_info_list.append(frame_info)
                            
                except Exception as batch_e:
                    logger.error(f"Batch detection processing failed: {batch_e}")
                    # Fallback: add all frames as full frames
                    for meta in batch_metadata:
                        frame_info = FrameInfo(
                            frame_number=meta['frame_idx'],
                            timestamp=meta['timestamp'],
                            image_path=str(meta['full_frame_path']),
                            frame_type="full_frame"
                        )
                        frame_info_list.append(frame_info)
            detection_seconds = time.perf_counter() - detection_timer
        else:
            # No object detection - add all as full frames
            logger.info("Object detection disabled - processing all frames as full frames")
            for meta in frame_metadata:
                frame_info = FrameInfo(
                    frame_number=meta['frame_idx'],
                    timestamp=meta['timestamp'],
                    image_path=str(meta['full_frame_path']),
                    frame_type="full_frame"
                )
                frame_info_list.append(frame_info)
            
        # Create frames manifest - import locally to avoid circular imports
        from .metadata_utils import create_frames_manifest
        manifest_path = create_frames_manifest(frame_info_list, temp_dir)
        
        logger.info(f"Frame extraction complete: {len(frame_info_list)} frames extracted")
        metrics = {
            'frame_extraction_seconds': frame_extraction_seconds,
            'detection_seconds': detection_seconds,
            'frames_extracted': len(frame_metadata),
            'items_after_detection': len(frame_info_list),
        }
        return frame_info_list, manifest_path, metrics
        
    except Exception as e:
        logger.error(f"Error in frame extraction: {e}")
        raise Exception(f"Failed to extract frames from video: {e}")


def process_video_with_enhanced_detection(
    video_path: pathlib.Path,
    frame_interval: int = None,
    object_detection_config = None
) -> Tuple[List[FrameInfo], str, dict]:
    """
    Enhanced video processing with frame-based extraction and optional object detection.
    
    Args:
        video_path: Path to the video file
        frame_interval: Number of frames between extractions. If None, uses config default.
        object_detection_config: Configuration for object detection
        
    Returns:
        Tuple[List[FrameInfo], str, dict]: frames, manifest path, and timing metrics
        
    Raises:
        Exception: If video processing fails
    """
    try:
        # Get config defaults if parameters not provided
        config = get_config()
        
        if frame_interval is None:
            frame_interval = config.get("frame_interval", 15)
        
        # Create detector if object detection is enabled
        detector = None
        enable_object_detection = object_detection_config and object_detection_config.enabled
        detection_confidence = (
            object_detection_config.confidence_threshold
            if object_detection_config and hasattr(object_detection_config, "confidence_threshold")
            else config.get("object_detection", {}).get("confidence_threshold", 0.85)
        )
        
        logger.info(f"Object detection configuration: enabled={enable_object_detection}, "
                   f"confidence_threshold={detection_confidence}")
        
        if enable_object_detection:
            logger.info("Object detection is enabled - attempting to create detector...")
            # Import here to avoid circular imports
            from .common_utils import create_detector_instance
            # Pass None to use the effective config instead of a minimal config
            detector = create_detector_instance(None)
            
            if detector is None:
                error_msg = (
                    "Object detection is REQUIRED but detector is unavailable! "
                    "This could be due to: "
                    "1) Object detection disabled in configuration, "
                    "2) Missing OpenVINO dependencies, "
                    "3) Model download/extraction failure, "
                    "4) Virtual environment not properly activated. "
                    "Check the logs above for specific error details."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                logger.info("Object detector successfully created and ready")
        else:
            logger.info("Object detection is disabled - proceeding with frame-only extraction")
        
        # Process video with frame extraction and optional object detection
        frame_info_list, manifest_path, metrics = process_video_with_frame_extraction(
            video_path=str(video_path),
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
            detector=detector
        )
        
        logger.info(f"Enhanced video processing complete: {len(frame_info_list)} items extracted")
        
        return frame_info_list, manifest_path, metrics
        
    except Exception as e:
        logger.error(f"Enhanced video processing failed: {e}")
        raise Exception(f"Failed to process video with enhanced detection: {e}")