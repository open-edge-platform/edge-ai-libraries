# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Object Detection Module

This module provides object detection functionality using YOLOX models with OpenVINO backend.
It supports both SDK mode (direct integration) and API mode (HTTP-based) processing.

Main Components:
- YOLOXDetector: Main detector class for object detection
- YOLOX utilities: Preprocessing and postprocessing functions
- Model configurations: Detection model settings and parameters

Usage:
    from src.core.object_detection import YOLOXDetector, create_detector
    
    # Create detector instance
    detector = create_detector(config)
    
    # Perform detection
    results = detector.detect(image)
"""

from .detector import YOLOXDetector, create_detector
from . import yolox_utils

__all__ = [
    'YOLOXDetector',
    'create_detector', 
    'yolox_utils'
]