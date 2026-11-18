# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model handlers for different multimodal embedding models.

This module contains the implementation of various multimodal embedding model handlers
including CLIP, MobileCLIP, SigLIP, BLIP2, Qwen text and GME.
"""

from .clip_handler import CLIPHandler
from .cn_clip_handler import CNClipHandler
from .mobileclip_handler import MobileCLIPHandler
from .siglip_handler import SigLIPHandler
from .siglip_transformers_handler import SigLIPTransformersHandler
from .blip2_handler import BLIP2Handler
from .qwen_handler import QwenEmbeddingHandler
from .gme_handler import GMEHandler

__all__ = [
    "CLIPHandler",
    "CNClipHandler",
    "MobileCLIPHandler", 
    "SigLIPHandler",
    "SigLIPTransformersHandler",
    "BLIP2Handler",
    "QwenEmbeddingHandler",
    "GMEHandler",
]