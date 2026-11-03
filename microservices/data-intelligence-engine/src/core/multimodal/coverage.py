# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Will this media asset be embedded, and how far has that got?

The answer is worked out from what is configured now. It is not stored on the
asset, because it is not a property of the asset: a three-hour recording has no
embedding today and has one the day a source with a suitable model is added,
and the file did not change in between. Writing "unsupported" into the content
at ingest would be wrong from the next configuration change onward and would
need every asset re-ingested to correct.

Three different situations all look identical from outside -- nothing is found
-- and a user needs to tell them apart:

- **no_source**: no source in the asset's pools can embed this kind of media.
  Either the engine has no model for the role at all, or it has one and nobody
  has configured a source with it. The reason says which, since the fix differs.
- **pending / failed**: a source covers it and is working, or broke.
- **unassigned**: it is in no pool, so nothing was ever going to embed it.

An audio file is a case of its own: no model embeds sound, so it is embedded
through its transcript, and what is asked is who embeds `l2_transcript`. Until
the transcript exists there is nothing for that source to hold, so the report
follows the transcription job first (`transcription.py`).
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

from assetlib.sources import binding
from core.content import (
    IMAGE,
    ROLE_AUDIO,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    ROLE_L3_WIKI,
    TEXT,
    ContentBlock,
    ContentStream,
    media_block,
    role_of,
)
from core.embedding import FusedEmbedding
from core.indexer import MultimodalIndexer, VectorIndexer, accepts_asset, accepts_block
from core.multimodal import captioning, registry, transcription
from core.multimodal.routing import effective_configuration

NOT_APPLICABLE = "not_applicable"
UNASSIGNED = "unassigned"
NO_SOURCE = "no_source"
PENDING = "pending"
READY = "ready"
FAILED = "failed"

# When several sources cover one asset the report is the least settled of them:
# a clip is only findable everywhere once every covering source has it.
_SEVERITY = {READY: 0, PENDING: 1, NO_SOURCE: 2, FAILED: 3}


@dataclass(frozen=True)
class EmbeddingCoverage:
    status: str
    reason: str = ""


def embedding_coverage(library: Any, asset_id: str, stream: ContentStream) -> EmbeddingCoverage:
    media = media_block(stream)
    if media is None:
        return EmbeddingCoverage(NOT_APPLICABLE)
    block = _embedded_as(media)
    role = role_of(block)

    pools = [pool for pool in library.asset_pools.values() if asset_id in pool.asset_ids]
    if not pools:
        return EmbeddingCoverage(UNASSIGNED, "the asset is in no pool")

    # Use the registered asset's origin-derived file type without reloading its
    # content. Older callers/fakes only supply the stream and no asset registry.
    asset = getattr(library, "assets", {}).get(asset_id)
    if asset is None:
        asset = SimpleNamespace(asset_id=asset_id, content=stream)
    covering: List[Tuple[Any, Any, ContentBlock]] = [
        (pool, projection, candidate)
        for pool in pools
        for projection in pool.projections
        if _active(pool, projection.source.source_id, projection.source)
        and isinstance(projection, VectorIndexer)
        and projection.accepts(asset)
        for candidate in _representations(stream, projection.configuration)
        if _covers(projection, candidate)
    ]
    broken = _broken_source(pools, asset, block, role, stream)
    if not covering:
        if broken is not None:
            return broken
        return EmbeddingCoverage(NO_SOURCE, _why_uncovered(role, role_of(media)))

    if broken is not None:
        return broken
    worst = EmbeddingCoverage(READY)
    for pool, projection, candidate in covering:
        state = _state(pool, projection, asset_id)
        found = (
            state if state.status == FAILED
            else _representation_pending(stream, candidate) or state
        )
        if _SEVERITY[found.status] > _SEVERITY[worst.status]:
            worst = found
    return worst


def _representations(stream: ContentStream, options: Any) -> List[ContentBlock]:
    """Original media and selected derived representations, including pending ones.

    A caption-only source must be visible before enrichment produces its text,
    but an ordinary image/video source must not implicitly wait for a caption.
    """
    media = media_block(stream)
    candidates = [_embedded_as(media)]
    selected = set(options.get('block_roles') or ())
    for role in (ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI):
        existing = [
            block for block in stream.blocks
            if role_of(block) == role and block.text.strip()
        ]
        candidates.extend(existing)
        if role in selected and not existing:
            candidates.append(ContentBlock(
                f'{media.block_id}:{role}', kind=TEXT, text='-', metadata={'role': role},
            ))
    return candidates


def _representation_pending(stream: ContentStream, block: ContentBlock) -> Optional[EmbeddingCoverage]:
    role = role_of(block)
    if role not in {ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}:
        return None
    if any(role_of(b) == role and b.text.strip() for b in stream.blocks):
        # Filters select existing content; they never require a generator. An
        # externally supplied caption/transcript remains indexable even when
        # automatic enrichment is disabled or its latest attempt failed.
        return None
    if role == ROLE_L2_TRANSCRIPT:
        return _transcript_pending(stream)
    if role == ROLE_L3_WIKI:
        return EmbeddingCoverage(PENDING, 'waiting for its l3_wiki content')
    if role != ROLE_L2_CAPTION:
        return None
    found = captioning.caption_status(stream)
    if found['caption_status'] == captioning.STATUS_FAILED:
        return EmbeddingCoverage(FAILED, f"captioning failed: {found['error'] or 'unknown error'}")
    if found['caption_status'] == captioning.STATUS_SKIPPED:
        return EmbeddingCoverage(NO_SOURCE, found['error'] or 'caption generation was skipped')
    return EmbeddingCoverage(PENDING, 'waiting for its caption')


def _active(pool: Any, source_id: str, source: Any) -> bool:
    return (
        source_id not in getattr(pool, "frozen_sources", {})
        and not binding.is_frozen(source, pool.source_statuses.get(source_id))
    )


def _covers(projection: Any, block: ContentBlock) -> bool:
    if isinstance(projection, MultimodalIndexer):
        return projection.covers(block)
    # Main's document/text GME path also embeds standalone images by their
    # pixels. A caption-only text fallback is not media embedding coverage.
    return (
        block.kind == IMAGE
        and bool(block.media_key)
        and isinstance(getattr(projection, "_embedding_model", None), FusedEmbedding)
        and accepts_block(block, projection.configuration)
    )


def _embedded_as(media: ContentBlock) -> ContentBlock:
    """The block whose coverage decides this media's.

    A recording is embedded through its transcript, so a representative
    transcript block stands in for it.
    """
    if role_of(media) == ROLE_AUDIO:
        return ContentBlock(
            f"{media.block_id}:transcript", kind=TEXT, text="-",
            metadata={"role": ROLE_L2_TRANSCRIPT},
        )
    return media


def _transcript_pending(stream: ContentStream) -> Optional[EmbeddingCoverage]:
    """Why a covered recording has no vector yet, if its transcript is the reason."""
    found = transcription.transcript_status(stream)
    status = found["transcript_status"]
    if status == transcription.STATUS_COMPLETED:
        return None
    if status == transcription.STATUS_FAILED:
        return EmbeddingCoverage(
            FAILED, f"transcription failed: {found['transcript_error'] or 'unknown error'}"
        )
    if status == transcription.STATUS_SKIPPED:
        return EmbeddingCoverage(
            NO_SOURCE, transcription.ASR_DISABLED
        )
    return EmbeddingCoverage(PENDING, "waiting for its transcript")


def _broken_source(
    pools: List[Any], asset: Any, block: ContentBlock, role: str,
    stream: Optional[ContentStream] = None,
) -> Optional[EmbeddingCoverage]:
    """A source that would cover this block but could not be loaded.

    Such a source has no projection, so the check above never sees it, and
    reporting "no source" would send the reader off to add one that is already
    there. The pool recorded why it failed, which is the thing worth showing.
    """
    for pool in pools:
        for source_id, source in getattr(pool, "unavailable_sources", {}).items():
            if not _active(pool, source_id, source):
                continue
            profile = source.profile or {}
            roles = profile.get("supported_roles") or ()
            options = effective_configuration(source)
            # An unloaded text source has no runtime to inspect. Only its fixed
            # profile, not today's default backend, can promise fused images.
            fused_image = (
                block.kind == IMAGE and bool(block.media_key)
                and profile.get("encoder_kind") == "text"
                and profile.get("backend") == "native_openvino_gme"
            )
            candidates = _representations(stream, options) if stream else [block]
            if not accepts_asset(asset, options) or not any(
                (role_of(candidate) in roles or (candidate is block and fused_image))
                and accepts_block(candidate, options) for candidate in candidates
            ):
                continue
            status = pool.source_statuses.get(source_id)
            error = (status.error if status else "") or "the source could not be loaded"
            return EmbeddingCoverage(
                FAILED, f"source {source.name or source_id!r} could not be loaded: {error}"
            )
    return None


def _state(pool: Any, projection: Any, asset_id: str) -> EmbeddingCoverage:
    status = pool.source_statuses.get(projection.source.source_id)
    if status is None:
        return EmbeddingCoverage(PENDING)
    if status.status == "failed":
        return EmbeddingCoverage(FAILED, status.error or "")
    if getattr(status, "serving_state", binding.SERVING) != binding.SERVING:
        return EmbeddingCoverage(PENDING, "the source is not serving yet")
    if not any(item is projection for item in getattr(pool, "serving", (projection,))):
        return EmbeddingCoverage(PENDING, "the source is not serving yet")
    held = asset_id in status.indexed_asset_ids and asset_id not in status.stale_asset_ids
    return EmbeddingCoverage(READY if held else PENDING)


def _why_uncovered(role: str, media_role: str = "") -> str:
    """What is missing, split by what would fix it."""
    if not any(role in model.supported_roles for model in registry.MODELS):
        return f"no embedding model supports {role!r} yet"
    if media_role == ROLE_AUDIO:
        return (
            "audio is embedded through its transcript, and no source in the "
            f"asset's pools embeds {role!r}; add a vector source whose model "
            'embeds transcripts (GME, e.g. asset_types ["audio"])'
        )
    return (
        f"no source in the asset's pools embeds {role!r}; "
        "add a vector source whose model supports it"
    )


__all__ = [
    "FAILED",
    "NOT_APPLICABLE",
    "NO_SOURCE",
    "PENDING",
    "READY",
    "UNASSIGNED",
    "EmbeddingCoverage",
    "embedding_coverage",
]
