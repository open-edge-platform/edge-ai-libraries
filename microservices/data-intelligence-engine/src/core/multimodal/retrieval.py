# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Resolve media projections and format candidates from the shared retrieval factory."""

import math
from typing import Any, Callable

from llama_index.core.schema import NodeWithScore
from core.file_asset_library import nodes_to_chunks
from schemas import RetrievedChunk
from core.content import ROLE_DOC_IMAGE, ROLE_IMAGE, ROLE_L1_SEGMENT, ROLE_L2_TRANSCRIPT, ROLE_SHORT_VIDEO


_REPRESENTATIONS = {
    "video": "video_clip",
    "image": "image_dense",
    "audio": "transcript_dense",
}
_TARGET_ROLES = {
    "video": {ROLE_L1_SEGMENT, ROLE_SHORT_VIDEO},
    "image": {ROLE_IMAGE, ROLE_DOC_IMAGE},
    "audio": {ROLE_L2_TRANSCRIPT},
}


class InvalidRetrievalScore(ValueError):
    """The backend returned a score that cannot be ranked."""


def _projection_target(projection: Any) -> str:
    configuration = projection.source.configuration
    explicit = configuration.get("target_media")
    if explicit:
        return str(explicit)
    # A source taking exactly one media kind serves that target.
    kinds = {str(kind).lower() for kind in configuration.get("block_kinds") or ()}
    media = kinds & {"audio", "image", "video"}
    return media.pop() if len(media) == 1 else ""


def targeted_projections(
    asset_library: Any, target: str, asset_pool_ids=(), *, pools=None,
) -> list[tuple[Any, Any]]:
    """Serving vector projections that can embed this target's units; empty `asset_pool_ids` means all pools."""
    selected_pools = asset_library._select_asset_pools(asset_pool_ids) if pools is None else pools
    return [
        (pool, projection)
        for pool in selected_pools
        for projection in pool.serving
        if getattr(projection, "kind", None) == "vector"
        and getattr(projection.source, "enabled", True)
        and (projection.source.profile or {}).get("encoder_kind") == "multimodal"
        and _projection_target(projection) in ("", target)
        and bool(set((projection.source.profile or {}).get("supported_roles") or ()) & _TARGET_ROLES[target])
        and bool(set(projection.source.configuration.get("block_roles") or _TARGET_ROLES[target]) & _TARGET_ROLES[target])
    ]


def media_nodes_to_chunks(
    nodes: list[NodeWithScore],
    library: Any,
    pool: Any,
    projection: Any,
    target: str,
    top_k: int,
    excluded: set[str],
    accept: Callable[[RetrievedChunk], bool] | None = None,
) -> list[RetrievedChunk]:
    """Validate and present media candidates without executing retrieval."""
    describe = getattr(library, "_show_description", None)
    if callable(describe):
        nodes = [node.model_copy(deep=True) for node in nodes]
        for scored in nodes:
            describe(scored.node)
    for node in nodes:
        score = node.score
        try:
            valid = score is not None and math.isfinite(float(score))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise InvalidRetrievalScore(f"invalid retrieval score for {target}")
    chunks = []
    for chunk in nodes_to_chunks(
        nodes,
        library=library.name,
        pool_id=pool.asset_pool_id,
    ):
        chunk.metadata.update({
            "library": library.name,
            "pool_id": pool.asset_pool_id,
            "asset_pool_id": pool.asset_pool_id,
            "vector_source_id": projection.source.source_id,
            "target_media": target,
            "representation": _REPRESENTATIONS[target],
        })
        chunk.metadata["source_id"] = projection.source.source_id
        chunks.append(chunk)
    chunks.sort(key=lambda chunk: chunk.score, reverse=True)
    for rank, chunk in enumerate(chunks, 1):
        chunk.metadata["source_rank"] = rank
    return [
        chunk for chunk in chunks
        if chunk.id not in excluded and (accept is None or accept(chunk))
    ][:top_k]


__all__ = ["media_nodes_to_chunks", "targeted_projections"]
