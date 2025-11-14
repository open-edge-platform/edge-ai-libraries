# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Sample utilities for multimodal embedding serving.

This module provides utilities for creating sample data required for model
testing, validation, and OpenVINO conversion processes. It generates standard
test inputs with known properties that ensure reliable model conversion and
validation workflows.

The sample utilities support the model conversion pipeline by providing
consistent test data that can be used across different model architectures
and conversion scenarios.
"""

from .create_sample import create_sample_image

__all__ = [
    "create_sample_image",
]
