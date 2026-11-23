# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import functools
from typing import ClassVar, Optional

import config
from inference.meta import InferenceMeta


@functools.lru_cache(maxsize=None)
def _remote_embedding_class():
    # Lazy so the llama-index OpenAI package stays optional.
    from llama_index.embeddings.openai import OpenAIEmbedding

    class RemoteOpenAIEmbedding(InferenceMeta, OpenAIEmbedding):
        BACKEND: ClassVar[str] = config.REMOTE_OPENAI_COMPATIBLE
        RUNTIME: ClassVar[str] = ""
        SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = False

    return RemoteOpenAIEmbedding


def remote_openai_embedding(**options):
    """An `OpenAIEmbedding(**options)` that reports its backend."""
    return _remote_embedding_class()(**options)
