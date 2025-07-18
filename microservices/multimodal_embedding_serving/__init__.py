# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Multimodal Embedding Serving Microservice

This package provides multimodal embedding capabilities for text, images, and videos
using various models including CLIP, MobileCLIP, SigLIP, and BLIP2.

Main exports:
- EmbeddingModel: High-level wrapper for embedding functionality
- ModelFactory: Factory for creating model handlers
- get_model_handler: Convenience function for getting model handlers
"""

from .src import EmbeddingModel
from .src.models import ModelFactory, get_model_handler, list_available_models

__version__ = "1.0.0"

__all__ = [
    "EmbeddingModel",
    "ModelFactory", 
    "get_model_handler",
    "list_available_models",
]
