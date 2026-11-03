# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""What a pool shows to retrieval, and the provenance each record carries.

A pool is retrieved through its *serving* bindings only -- `AssetPool.serving`,
recomputed whenever a binding changes state. A source that is preparing has
half the pool at best, and a deprecated or disabled one is kept for its data,
not for answering; neither is mixed into a pool's results.

Every result also says which source produced it. With several models per pool
that is the only way to tell an image hit from a video hit, and `source_id`
used to be stamped with the *pool* id on the way out of the API.
"""

from typing import Any, Iterable, Sequence

from assetlib.sources.profile import now

#: Metadata a record carries about where it came from. Kept out of what a
#: model embeds or an LLM reads -- it describes the record, not its content.
PROVENANCE_KEYS = ("source_id", "source_name", "profile_hash", "indexed_at")


def serving_projections(pool) -> Sequence[Any]:
    return pool.serving


def _metadata_of(result: Any):
    node = getattr(result, "node", result)
    metadata = getattr(node, "metadata", None)
    return node, metadata if isinstance(metadata, dict) else None


def stamp_results(results: Iterable[Any], source: Any) -> list:
    """Name the source on each retrieved record, whatever it was indexed with.

    Done at retrieval rather than trusted from the stored row, so records
    written before rows carried provenance are attributed correctly too.
    """
    stamped = []
    for result in results:
        _, metadata = _metadata_of(result)
        if metadata is not None:
            metadata["source_id"] = source.source_id
            metadata["source_name"] = source.name
            profile_hash = (source.profile or {}).get("profile_hash")
            if profile_hash:
                metadata["profile_hash"] = profile_hash
        stamped.append(result)
    return stamped


def stamp_nodes(nodes: Iterable[Any], source: Any) -> None:
    """Record provenance on nodes about to be written, invisibly to the model."""
    indexed_at = now()
    for node in nodes:
        _, metadata = _metadata_of(node)
        if metadata is None:
            continue
        metadata["source_id"] = source.source_id
        metadata["source_name"] = source.name
        metadata["profile_hash"] = (source.profile or {}).get("profile_hash", "")
        metadata["indexed_at"] = indexed_at
        for attribute in ("excluded_embed_metadata_keys", "excluded_llm_metadata_keys"):
            excluded = list(getattr(node, attribute, None) or [])
            excluded.extend(key for key in PROVENANCE_KEYS if key not in excluded)
            try:
                setattr(node, attribute, excluded)
            except (AttributeError, ValueError):
                pass


__all__ = ["PROVENANCE_KEYS", "serving_projections", "stamp_nodes", "stamp_results"]
