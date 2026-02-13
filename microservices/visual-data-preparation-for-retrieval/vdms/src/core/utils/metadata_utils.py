# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Metadata Utilities Module

This module provides metadata generation and management utilities for the VDMS microservice.
Supports both SDK mode (direct integration) and API mode (HTTP-based) processing.

Classes:
- FrameInfo: Named tuple for frame information

Functions:
- create_frames_manifest(): Create JSON manifest for extracted frames
- create_enhanced_frame_metadata(): Create enhanced metadata for a single frame
- store_enhanced_video_metadata(): Store enhanced video metadata with frame processing
- extract_enhanced_video_metadata(): Generate enhanced metadata for video processing

Usage:
    from src.core.utils.metadata_utils import FrameInfo, create_frames_manifest
    
    # Create frame info
    frame_info = FrameInfo(
        frame_number=30,
        timestamp=1.0,
        image_path="/path/to/frame.jpg",
        frame_type="full_frame"
    )
    
    # Create manifest
    manifest_path = create_frames_manifest([frame_info], temp_dir)
"""

import datetime
import json
import pathlib
import time
from typing import Dict, List, Optional, Tuple, NamedTuple

from tzlocal import get_localzone

from src.common import logger, settings
from src.common.schema import FrameExtractionModeEnum, ObjectDetectionConfig
from .config_utils import get_config
from .file_utils import save_metadata_at_temp
from .common_utils import FrameInfo


# Frame extraction data structures are now in common_utils.py to avoid circular imports


def create_frames_manifest(frame_info_list: List[FrameInfo], temp_dir: str, video_path: str = None) -> str:
    """
    Create a JSON manifest file for the extracted frames.
    This manifest will be used by the embedding service for batch processing.
    
    Args:
        frame_info_list: List of frame information
        temp_dir: Directory to save the manifest
        video_path: Path to the video file (for batch processing)
        
    Returns:
        Path to the created manifest file
    """
    try:
        # Convert FrameInfo namedtuples to dictionaries
        frames_data = []
        for frame_info in frame_info_list:
            frame_dict = {
                "frame_number": frame_info.frame_number,
                "timestamp": frame_info.timestamp,
                "image_path": frame_info.image_path,
                "type": frame_info.frame_type
            }
            
            # Add optional fields if present
            if frame_info.crop_index is not None:
                frame_dict["crop_index"] = frame_info.crop_index
            if frame_info.detection_confidence is not None:
                frame_dict["detection_confidence"] = frame_info.detection_confidence
            if frame_info.crop_bbox is not None:
                frame_dict["crop_bbox"] = list(frame_info.crop_bbox)
            if frame_info.detected_label is not None:
                frame_dict["detected_label"] = frame_info.detected_label
            if frame_info.merged_boxes_count is not None:
                frame_dict["merged_boxes_count"] = frame_info.merged_boxes_count
            if frame_info.context_expansion_applied is not None:
                frame_dict["context_expansion_applied"] = frame_info.context_expansion_applied
            
            frames_data.append(frame_dict)
        
        # For video-based processing, optimize frame extraction to avoid duplicates
        if video_path:
            # Extract unique frame numbers and create mapping
            unique_frames_data = []
            frame_to_metadata_map = {}
            seen_frame_numbers = set()
            
            for frame_info in frame_info_list:
                frame_num = frame_info.frame_number
                
                # Create frame dictionary
                frame_dict = {
                    "frame_number": frame_info.frame_number,
                    "timestamp": frame_info.timestamp,
                    "image_path": frame_info.image_path,
                    "type": frame_info.frame_type
                }
                
                # Add optional fields if present
                if frame_info.crop_index is not None:
                    frame_dict["crop_index"] = frame_info.crop_index
                if frame_info.detection_confidence is not None:
                    frame_dict["detection_confidence"] = frame_info.detection_confidence
                if frame_info.crop_bbox is not None:
                    frame_dict["crop_bbox"] = list(frame_info.crop_bbox)
                if frame_info.detected_label is not None:
                    frame_dict["detected_label"] = frame_info.detected_label
                if frame_info.merged_boxes_count is not None:
                    frame_dict["merged_boxes_count"] = frame_info.merged_boxes_count
                if frame_info.context_expansion_applied is not None:
                    frame_dict["context_expansion_applied"] = frame_info.context_expansion_applied
                
                frames_data.append(frame_dict)
                
                # For unique frame extraction, only add each frame number once
                if frame_num not in seen_frame_numbers:
                    # Add only the base frame info for video extraction (no crop-specific data)
                    unique_frame_dict = {
                        "frame_number": frame_info.frame_number,
                        "timestamp": frame_info.timestamp,
                        "image_path": frame_info.image_path,
                        "type": "full_frame"  # Always use full_frame for video extraction
                    }
                    unique_frames_data.append(unique_frame_dict)
                    seen_frame_numbers.add(frame_num)
                    frame_to_metadata_map[frame_num] = []
                
                # Add metadata for this frame/crop
                frame_to_metadata_map[frame_num].append(frame_dict)
            
            # Create optimized manifest structure
            # Use unique_frames_data for the main "frames" array that multimodal service will use
            manifest = {
                "frames": unique_frames_data,  # Deduplicated frames for video extraction
                "all_frame_metadata": frames_data,  # Complete metadata for all frames/crops
                "frame_metadata_map": frame_to_metadata_map,  # Map frames to their metadata
                "total_frames": len(unique_frames_data),  # Number of frames to extract
                "total_metadata_entries": len(frames_data),  # Total metadata entries (including crops)
                "extraction_timestamp": datetime.datetime.now().isoformat(),
                "video_path": video_path
            }
            
            logger.info(f"Added video_path to manifest: {video_path}")
            logger.info(f"Video processing optimization: {len(frames_data)} total entries, {len(unique_frames_data)} unique frames to extract")
        else:
            # Create traditional manifest structure for image-based processing
            manifest = {
                "frames": frames_data,
                "total_frames": len(frames_data),
                "extraction_timestamp": datetime.datetime.now().isoformat()
            }
        
        # Save manifest file
        manifest_path = pathlib.Path(temp_dir) / "frames_manifest.json"
        logger.info(f"Creating manifest at: {manifest_path}")
        
        # Ensure directory exists
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Frames manifest created successfully: {manifest_path}")
        
        # Verify file was created
        if manifest_path.exists():
            file_size = manifest_path.stat().st_size
            logger.info(f"Manifest file size: {file_size} bytes")
        else:
            logger.error(f"Manifest file was not created at {manifest_path}")
            raise Exception(f"Failed to create manifest file at {manifest_path}")
            
        return str(manifest_path)
        
    except Exception as e:
        logger.error(f"Error creating frames manifest: {e}")
        raise Exception(f"Failed to create frames manifest: {e}")


def create_enhanced_frame_metadata(
    video_metadata: dict,
    frame_info: FrameInfo,
    frame_interval: int,
    enable_object_detection: bool
) -> dict:
    """
    Create enhanced metadata for a single frame that preserves all video context
    while adding frame-specific information.
    
    Args:
        video_metadata: Original video metadata dictionary
        frame_info: Frame-specific information
        frame_interval: Frame extraction interval used
        enable_object_detection: Whether object detection was enabled
        
    Returns:
        Enhanced metadata dictionary for the frame
    """
    # Start with all original video metadata
    enhanced_metadata = video_metadata.copy()
    
    # Add frame-specific metadata
    enhanced_metadata.update({
        "frame_number": frame_info.frame_number,
        "timestamp": frame_info.timestamp,
        "frame_interval": frame_interval,
        "embedding_type": "frame",
        "is_detected_crop": frame_info.frame_type == "detected_crop",
        "enable_object_detection": enable_object_detection,
        "processing_timestamp": datetime.datetime.now().isoformat()
    })
    
    # Add detection-specific metadata if applicable
    if frame_info.frame_type == "detected_crop":
        enhanced_metadata.update({
            "crop_index": frame_info.crop_index,
            "detection_confidence": frame_info.detection_confidence,
            "crop_bbox": list(frame_info.crop_bbox) if frame_info.crop_bbox else None,
            "detected_label": frame_info.detected_label,
            "merged_boxes_count": frame_info.merged_boxes_count,
            "context_expansion_applied": frame_info.context_expansion_applied,
        })
    else:
        enhanced_metadata.update({
            "crop_index": None,
            "detection_confidence": None,
            "crop_bbox": None,
            "detected_label": None,
            "merged_boxes_count": None,
            "context_expansion_applied": None,
        })
    
    return enhanced_metadata


def store_enhanced_video_metadata(
    bucket_name: str,
    video_id: str,
    video_filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    tags: List[str] | str = [],
) -> Tuple[pathlib.Path, dict]:
    """
    Store enhanced video metadata with frame-based processing and object detection support

    Args:
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory containing the video
        video_filename (str): Video filename
        temp_video_path (pathlib.Path): Temporary path to the video file
        metadata_temp_path (str): Path to store metadata
        frame_interval (int): Number of frames between extractions. If None, uses config default.
        enable_object_detection (bool): Whether to enable object detection. If None, uses config default.
        detection_confidence (float): Confidence threshold for object detection. If None, uses config default.
        tags (List[str] | str): Tags for the video

    Returns:
        Tuple containing metadata file path and processing summary
    """
    # Get config defaults if parameters not provided
    config = get_config()
    
    if frame_interval is None:
        frame_interval = config.get("frame_interval", 15)
    if enable_object_detection is None:
        enable_object_detection = config.get("enable_object_detection", True)
    if detection_confidence is None:
        detection_confidence = config.get("detection_confidence", 0.85)
    
    metadata, processing_summary = extract_enhanced_video_metadata(
        temp_video_path=temp_video_path,
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=video_filename,
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        tags=tags,
    )
    metadata_file_path: pathlib.Path = save_metadata_at_temp(metadata_temp_path, metadata)

    processing_summary["metadata_file_path"] = str(metadata_file_path)
    return metadata_file_path, processing_summary


def extract_enhanced_video_metadata(
    temp_video_path: pathlib.Path,
    bucket_name: str,
    video_id: str,
    video_filename: str,
    frame_interval: int = None,
    enable_object_detection: bool = None,
    detection_confidence: float = None,
    tags: List[str] | str = [],
) -> Tuple[Dict, Dict]:
    """
    Generates enhanced metadata for a video with frame-based processing and optional object detection.

    Args:
        temp_video_path (pathlib.Path): Path to the video file on disk
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory (video_id) containing the video
        video_filename (str): Name of the video file
        frame_interval (int): Number of frames between extractions. If None, uses config default.
        enable_object_detection (bool): Whether to enable object detection. If None, uses config default.
        detection_confidence (float): Confidence threshold for object detection. If None, uses config default.
        tags (List[str] | str): Tags for the video

    Returns:
        Tuple containing the metadata dictionary and processing summary metrics
    """
    # Get config defaults if parameters not provided
    config = get_config()
    
    if frame_interval is None:
        frame_interval = config.get("frame_interval", 15)
    if enable_object_detection is None:
        enable_object_detection = config.get("enable_object_detection", True)
    if detection_confidence is None:
        detection_confidence = config.get("detection_confidence", 0.85)
    
    metadata = {}
    processing_metrics: Dict[str, float] = {}
    logger.info("Extracting enhanced video metadata with frame-based processing...")

    # Generate clean timestamp once 
    date_time = datetime.datetime.now()
    local_timezone = get_localzone()
    current_time_local = date_time.replace(tzinfo=datetime.timezone.utc).astimezone(local_timezone)
    iso_date_time = current_time_local.isoformat()

    # Construct the path to the video in Minio
    video_minio_path = f"{video_id}/{video_filename}"
    video_rel_url = f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
    video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"

    # Import video utility functions locally to avoid circular imports
    from .video_utils import get_video_fps_and_frames, process_video_with_enhanced_detection
    
    fps, total_frames = get_video_fps_and_frames(temp_video_path)
    video_duration_seconds: Optional[float] = None
    if fps and fps > 0:
        try:
            video_duration_seconds = float(total_frames) / float(fps)
        except ZeroDivisionError:
            video_duration_seconds = None

    # If tags is a list, convert it to a comma-separated string
    if isinstance(tags, List):
        tags: str = ",".join(tags) if tags else ""

    # Process video with frame-based extraction
    if enable_object_detection:
        logger.info("Processing video with enhanced frame extraction and object detection")
        
        # Create object detection config for the enhanced detection pipeline
        object_detection_config = ObjectDetectionConfig(
            enabled=settings.ENABLE_OBJECT_DETECTION,
            confidence_threshold=detection_confidence,
            extraction_mode=FrameExtractionModeEnum.object_detection
        )
        
        # Use the enhanced detection pipeline
        frame_info_list, actual_manifest_path, extraction_metrics = process_video_with_enhanced_detection(
            temp_video_path,
            frame_interval=frame_interval,
            object_detection_config=object_detection_config,
        )
        processing_metrics = dict(extraction_metrics)
        
        # Generate metadata for each extracted frame/crop
        for idx, frame_info in enumerate(frame_info_list):
            keyname = f"{video_id}_{idx}"
            
            # Calculate interval info based on frame number
            interval_num = frame_info.frame_number // frame_interval
            start_time = frame_info.timestamp
            
            metadata[keyname] = {
                "timestamp": start_time,
                "video_id": video_id,
                "video": video_filename,
                "interval_num": interval_num,
                "frame_number": frame_info.frame_number,
                "frame_type": frame_info.frame_type,
                "image_path": frame_info.image_path,
                "created_at": iso_date_time,
                "fps": int(fps),
                "total_frames": total_frames,
                "video_duration": video_duration_seconds,
                "video_duration_seconds": video_duration_seconds,
                "video_temp_path": str(temp_video_path),
                "video_remote_path": video_minio_path,
                "bucket_name": bucket_name,
                "video_url": video_url,
                "video_rel_url": video_rel_url,
                "tags": tags,
                "object_detection_enabled": True,
                "extraction_mode": object_detection_config.extraction_mode.value,
                "frame_interval": frame_interval,
            }
            
            # Add object detection specific metadata if this is a crop
            if frame_info.frame_type == "detected_crop":
                metadata[keyname].update({
                    "crop_index": frame_info.crop_index,
                    "detection_confidence": frame_info.detection_confidence,
                    "crop_bbox": frame_info.crop_bbox,
                    "detected_label": frame_info.detected_label,
                    "merged_boxes_count": frame_info.merged_boxes_count,
                    "context_expansion_applied": frame_info.context_expansion_applied,
                })
        
        # Add manifest path to the first metadata entry for reference  
        if metadata:
            first_key = next(iter(metadata))
            metadata[first_key]["frames_manifest_path"] = str(actual_manifest_path)
        processing_metrics["manifest_path"] = str(actual_manifest_path)
        processing_metrics["items_after_detection"] = len(frame_info_list)
            
    else:
        # Process with basic frame-based extraction (no object detection)
        logger.info("Processing video with basic frame-based extraction")
        
        extraction_start = time.perf_counter()
        # Create frame info list for batch processing
        frame_info_list = []
        
        # Calculate frame extraction points based on frame_interval
        frame_count = 0
        for frame_number in range(0, total_frames, frame_interval):
            keyname = f"{video_id}_{frame_count}"
            timestamp = frame_number / fps
            
            # Create FrameInfo for this frame (for batch processing)
            frame_info = FrameInfo(
                frame_number=frame_number,
                timestamp=timestamp,
                image_path=None,  # No individual frame images for video-based processing
                frame_type="full_frame",  # API expects 'full_frame' or 'detected_crop'
                crop_index=None,
                detection_confidence=None,
                crop_bbox=None,
                detected_label=None,
                merged_boxes_count=None,
                context_expansion_applied=None
            )
            frame_info_list.append(frame_info)
            
            metadata[keyname] = {
                "timestamp": timestamp,
                "video_id": video_id,
                "video": video_filename,
                "interval_num": frame_count,
                "frame_number": frame_number,
                "frame_type": "full_frame",  # API expects 'full_frame' or 'detected_crop'
                "created_at": iso_date_time,
                "fps": int(fps),
                "total_frames": total_frames,
                "video_duration": video_duration_seconds,
                "video_duration_seconds": video_duration_seconds,
                "video_temp_path": str(temp_video_path),
                "video_remote_path": video_minio_path,
                "bucket_name": bucket_name,
                "video_url": video_url,
                "video_rel_url": video_rel_url,
                "tags": tags,
                "object_detection_enabled": False,
                "extraction_mode": "frame_based",
                "frame_interval": frame_interval,
            }

            frame_count += 1

        frame_extraction_seconds = time.perf_counter() - extraction_start

        # Create frames manifest for batch processing (even without object detection)
        logger.info(f"Creating frames manifest for {len(frame_info_list)} frames...")
        manifest_path = create_frames_manifest(frame_info_list, str(temp_video_path.parent), str(temp_video_path))
        
        # Add manifest path to the first metadata entry for reference
        if metadata:
            first_key = next(iter(metadata))
            metadata[first_key]["frames_manifest_path"] = str(manifest_path)
            logger.info(f"Frames manifest created at: {manifest_path}")

        processing_metrics = {
            "frame_extraction_seconds": frame_extraction_seconds,
            "detection_seconds": 0.0,
            "frames_extracted": frame_count,
            "items_after_detection": frame_count,
            "manifest_path": str(manifest_path),
        }

    metadata_sample = metadata[next(iter(metadata))] if metadata else {}
    processing_summary = {
        **processing_metrics,
        "fps": float(fps) if fps else None,
        "total_frames": total_frames,
        "video_duration_seconds": video_duration_seconds,
        "frame_interval": frame_interval,
        "object_detection_enabled": enable_object_detection,
        "detection_confidence": detection_confidence,
        "metadata_sample": metadata_sample,
        "video_url": video_url,
        "video_rel_url": video_rel_url,
    }

    return metadata, processing_summary