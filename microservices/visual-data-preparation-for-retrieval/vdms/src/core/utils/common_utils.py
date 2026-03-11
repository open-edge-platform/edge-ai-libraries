# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Common utility functions extracted from util.py

This module contains general-purpose utility functions that are used across
the VDMS DataPrep microservice.
"""

import logging
from typing import NamedTuple, Optional, Tuple
from minio import Minio

from src.common import DataPrepException, Strings, logger, settings
from src.core.minio_client import MinioClient
from src.core.object_detection.detector import YOLOXDetector
from .config_utils import get_config


# Frame extraction data structures
class FrameInfo(NamedTuple):
    """Information about an extracted frame."""

    frame_number: int
    timestamp: float
    image_path: str
    frame_type: str  # "full_frame" or "detected_crop"
    crop_index: Optional[int] = None
    detection_confidence: Optional[float] = None
    crop_bbox: Optional[Tuple[int, int, int, int]] = None
    detected_label: Optional[str] = None
    merged_boxes_count: Optional[int] = None
    context_expansion_applied: Optional[bool] = None


def sanitize_input(input: str) -> str | None:
    """Takes an string input and strips whitespaces. Returns None if
    string is empty else returns the string.
    
    Args:
        input: Input string to sanitize
        
    Returns:
        Sanitized string or None if empty
    """
    input = str.strip(input)
    if len(input) == 0:
        return None

    return input


def get_minio_client() -> MinioClient:
    """Get a configured Minio client instance.

    Returns:
        MinioClient: A configured Minio client

    Raises:
        Exception: If Minio client configuration is missing
    """
    if (
        not settings.MINIO_ENDPOINT
        or not settings.MINIO_ACCESS_KEY
        or not settings.MINIO_SECRET_KEY
    ):
        logger.error("Minio configuration is incomplete")
        raise Exception(Strings.minio_conn_error)

    try:
        return MinioClient(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    except Exception as e:
        logger.error(f"Failed to create Minio client: {e}")
        raise Exception(Strings.minio_conn_error)


def create_detector_instance(config: Optional[dict] = None, enable_object_detection: Optional[bool] = None, detection_confidence: Optional[float] = None):
    """
    Create a detector instance based on configuration with API parameter override.
    
    Args:
        config: Configuration dictionary. If None, loads from effective config.
        enable_object_detection: Override for object detection enabled state from API
        detection_confidence: Override for detection confidence from API
        
    Returns:
        YOLOXDetector instance or None if detection is disabled or unavailable
    """
    try:
        # Import detector here to avoid circular imports and handle missing dependencies
        from src.core.object_detection import create_detector
        
        logger.info("Attempting to create detector instance...")
        logger.debug(f"Detector config passed: {config}")
        logger.debug(f"API overrides: enable_object_detection={enable_object_detection}, detection_confidence={detection_confidence}")
        
        # Get effective config to check object detection settings
        effective_config = get_config()
        detection_config = effective_config.get('object_detection', {}).copy()
        
        # Override with API parameters if provided
        if enable_object_detection is not None:
            detection_config['enabled'] = enable_object_detection
            logger.info(f"Overriding object detection enabled with API value: {enable_object_detection}")
        
        if detection_confidence is not None:
            detection_config['confidence_threshold'] = detection_confidence
            logger.info(f"Overriding detection confidence with API value: {detection_confidence}")
        
        # Use the same device as processing components for consistency across all components
        sdk_device = settings.DEVICE
        detection_config['device'] = sdk_device
        logger.info(f"Using processing device for object detection: {sdk_device}")
        
        logger.info(f"Object detection configuration: enabled={detection_config.get('enabled', False)}, "
                   f"device={detection_config.get('device', 'CPU')}, "
                   f"confidence_threshold={detection_config.get('confidence_threshold', 0.85)}")
        
        # Create custom config with overrides
        detector_config = {
            'object_detection': detection_config
        }
        
        detector = create_detector(detector_config)
        
        if detector is None:
            logger.error("create_detector returned None - object detection is likely disabled in configuration")
            return None
            
        logger.info("Detector instance created successfully")
        return detector
        
    except ImportError as e:
        logger.error(f"Detector module not available - ImportError: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create detector instance: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None