# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Embedding media by what it shows, and describing it by what happens in it.

Two separate things, deliberately kept apart:

- **Embedding** is a projection's business and happens at sync time, exactly
  like text. `MultimodalIndexer` reads a media block, asks a model that can
  *see* for a vector, and stamps it on the node. Nothing is asynchronous about
  it, so a retry re-materializes the same asset the same way and the library's
  delete-then-write already makes that idempotent.
- **Captioning** calls an external vision-language service, takes minutes, and
  therefore runs as a background job that updates the content stream afterwards
  (`captioning.py`). Its state lives on the stream, not in a new store.

Keeping them apart is what lets the slow half fail without costing the fast
half: a clip whose caption never arrives is still findable by what it looks
like.

Retrieval scoping/result formatting and media reranking also live here.
Model-specific inference and reranker inputs live in ``inference.multimodal``.
"""

from core.multimodal.embeddings import (
    MultimodalEmbedding,
    build_multimodal_embedding,
)

__all__ = [
    "MultimodalEmbedding",
    "build_multimodal_embedding",
]
