# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Object Detection Module

Object detection with Hugging Face ``OpenVINO/*`` detection models, loaded
through OpenVINO Model API.

Usage:
    from src.core.object_detection import ObjectDetector, create_detector

    detector = create_detector(config)
    results = detector.detect(image)
"""

from .detector import ObjectDetector, create_detector

__all__ = ["ObjectDetector", "create_detector"]
