# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, FrozenSet, List, Mapping, Optional, Protocol, Sequence, runtime_checkable

from inference.model_cache import ModelCache

Vector = List[float]


@runtime_checkable
class MultimodalEmbedding(Protocol):
    """A multimodal source's embedding model.

    `dimension` is declared, vectors are L2-normalized (IP metric), and text and media share one space.
    """

    dimension: int
    #: Block roles (`core.content.ROLE_*`) this model can embed.
    supported_roles: FrozenSet[str]

    def get_query_embedding(self, text: str) -> Vector:
        """The vector for a query, in the model's shared space."""

    def get_text_embedding_batch(self, texts: Sequence[str]) -> List[Vector]:
        """One vector per corpus text (a caption or transcript)."""

    def get_image_embeddings(self, images: Sequence[Any]) -> List[Vector]:
        """One vector per PIL image."""

    def get_video_embedding(self, frames: Sequence[Any]) -> Vector:
        """Video models only: one vector for one clip, given its sampled frames."""


# Weak cache: a model lives as long as some projection holds it.
_CACHE = ModelCache()


def build_multimodal_embedding(
    record: Mapping[str, Any], options: Optional[Mapping[str, Any]] = None
) -> MultimodalEmbedding:
    """The model a multimodal source's profile recorded, built at most once."""
    from core.multimodal import registry

    options = dict(options or {})
    registry.validate_model_options(options)
    model = registry.model_for_record(record)
    key = (
        record.get("name"),
        record.get("id"),
        options.get("embedding_device") or registry._category_defaults(model.category)["device"],
        tuple(sorted((k, options[k]) for k in registry.MODEL_PARAMS if k in options)),
    )
    return _CACHE.get_or_build(key, lambda: registry.load(record, options))


__all__ = [
    "MultimodalEmbedding",
    "Vector",
    "build_multimodal_embedding",
]
