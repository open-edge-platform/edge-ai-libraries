# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Multimodal Embedding Serving Microservice

This package provides a comprehensive multimodal embedding solution that supports
text, image, and video processing using state-of-the-art models. It offers a
unified interface for generating embeddings from diverse input modalities.

Supported Models:
- CLIP: Contrastive Language-Image Pre-training models for general multimodal tasks
- MobileCLIP: Mobile-optimized CLIP variants for edge deployment
- SigLIP: Sigmoid-based CLIP models with improved training efficiency
- BLIP2: Advanced vision-language models with Q-Former architecture
- CN-CLIP: Chinese language specialized CLIP models

Key Features:
- Unified API for multiple model architectures
- OpenVINO optimization for production deployment
- REST API for embedding generation services
- Support for various input formats (URLs, base64, local files)
- Video frame extraction and processing
- Configurable model parameters and device selection
- Comprehensive error handling and logging

Main exports:
- EmbeddingModel: High-level wrapper for embedding functionality
- ModelFactory: Factory pattern implementation for model creation
- get_model_handler: Convenience function for model instantiation
- list_available_models: Function to discover available models

The package is designed for production environments requiring efficient multimodal
embedding generation with high throughput and low latency requirements.
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
