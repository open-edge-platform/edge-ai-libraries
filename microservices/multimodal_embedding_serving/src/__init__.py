# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Multimodal Embedding Serving Package

This package provides a comprehensive solution for serving multimodal embedding models
including CLIP, MobileCLIP, SigLIP, and BLIP2.
"""

from .wrapper import EmbeddingModel

__all__ = [
    "EmbeddingModel"
]