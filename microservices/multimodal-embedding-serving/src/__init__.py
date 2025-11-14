# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Multimodal Embedding Serving Package

This package provides a comprehensive solution for serving multimodal embedding models
that can process both text and visual inputs. It supports multiple state-of-the-art
architectures including CLIP, MobileCLIP, SigLIP, and BLIP2.

Key features:
- Multiple model architecture support with unified interface
- Text and image embedding generation
- Video frame processing and embedding
- OpenVINO optimization for improved performance  
- REST API for embedding generation
- Flexible input formats (URLs, base64, local files)
- Configurable model parameters and device selection

The package is designed for production deployment scenarios requiring efficient
multimodal embedding generation with high throughput and low latency.
"""

from .wrapper import EmbeddingModel

__all__ = [
    "EmbeddingModel"
]