# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model utilities for multimodal embedding serving.

This module contains utility functions for OpenVINO model conversion and loading.
"""

from .openvino_utils import check_and_convert_openvino_models, load_openvino_models

__all__ = [
    "check_and_convert_openvino_models",
    "load_openvino_models",
]