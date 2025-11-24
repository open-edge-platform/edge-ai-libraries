# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Models module for multimodal embedding serving.

This module provides a factory pattern implementation for creating
and managing different multimodal embedding models.

For model handlers, import from the handlers subpackage:
    from models.handlers import CLIPHandler, MobileCLIPHandler, etc.
"""

from .base import BaseEmbeddingModel
from .registry import ModelFactory, get_model_handler, register_model_handler
from .config import get_model_config, list_available_models

# Expose main API (core functionality only)
__all__ = [
    "BaseEmbeddingModel",
    "ModelFactory",
    "get_model_handler",
    "register_model_handler",
    "get_model_config",
    "list_available_models"
]
