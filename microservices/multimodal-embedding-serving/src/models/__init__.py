# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Models module for multimodal embedding serving.

This module provides a factory pattern implementation for creating
and managing different multimodal embedding models.
"""

from .base import BaseEmbeddingModel
from .registry import ModelFactory, get_model_handler, register_model_handler
from .config import get_model_config, list_available_models, get_default_model
from .wrapper import EmbeddingModel

# Import handlers for registration
from .clip_handler import CLIPHandler
from .mobileclip_handler import MobileCLIPHandler
from .siglip_handler import SigLIPHandler
from .blip2_handler import BLIP2Handler

# Expose main API
__all__ = [
    "BaseEmbeddingModel",
    "ModelFactory", 
    "get_model_handler",
    "register_model_handler",
    "get_model_config",
    "list_available_models",
    "get_default_model",
    "EmbeddingModel",
    "CLIPHandler",
    "MobileCLIPHandler", 
    "SigLIPHandler",
    "BLIP2Handler",
]
