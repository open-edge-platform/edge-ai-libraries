# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model handlers for different multimodal embedding models.

This module contains the implementation of various multimodal embedding model handlers
including CLIP, MobileCLIP, SigLIP, and BLIP2.
"""

from .clip_handler import CLIPHandler
from .cn_clip_handler import CNClipHandler
from .mobileclip_handler import MobileCLIPHandler
from .siglip_handler import SigLIPHandler
from .blip2_handler import BLIP2Handler
from .qwen_handler import QwenEmbeddingHandler

__all__ = [
    "CLIPHandler",
    "CNClipHandler",
    "MobileCLIPHandler", 
    "SigLIPHandler",
    "BLIP2Handler",
    "QwenEmbeddingHandler",
]