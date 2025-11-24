# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Import from simplified_embedding_helper to support both API and SDK modes
from .simplified_embedding_helper import (
    _client_cache,
    generate_video_embedding,
    generate_video_embedding_from_content,
    generate_text_embedding,
)
from .sdk_embedding_helper import generate_video_embedding_sdk
from .sdk_client import SDKVDMSClient

__all__ = [
    "_client_cache",
    "generate_text_embedding",
    "generate_video_embedding", 
    "generate_video_embedding_from_content",
    "generate_video_embedding_sdk",
    "SDKVDMSClient",
]
