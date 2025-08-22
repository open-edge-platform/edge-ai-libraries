# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model utilities for multimodal embedding serving.

This module provides specialized utilities for model management, particularly
focused on OpenVINO model conversion and loading operations. It supports the
conversion pipeline from PyTorch models to optimized OpenVINO representations.

Key functionality:
- Automated OpenVINO model conversion with caching
- Model loading and compilation for target devices
- Conversion validation and error handling
- Memory management during conversion processes

The utilities ensure efficient model deployment by providing seamless conversion
from research models to production-optimized formats suitable for inference.
"""

from .openvino_utils import check_and_convert_openvino_models, load_openvino_models

__all__ = [
    "check_and_convert_openvino_models",
    "load_openvino_models",
]