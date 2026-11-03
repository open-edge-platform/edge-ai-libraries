# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The background half of ingest: describing a clip, long after it was stored.

Embedding a clip is fast and happens inside the normal pool sync. Describing
one means a vision-language model reading the whole thing, which takes minutes,
so it cannot sit inside the request that stored the asset. This module is that
work, and the shape of it is dictated by one thing: **it must be safe to run
twice.**

Three decisions follow from that.

**The caption block's id is a domain coordinate**, `<asset_id>:caption`, not
anything derived from a request. A retry addresses the same block and replaces
it, rather than appending a second description of the same clip.

**Job state lives on the content stream**, in `caption_status` -- the record is
already written per asset, already read on every sync, and already the thing a
rebuild would replay from. A separate store would be a second source of truth
to keep in step with the first.

**The stream is re-read inside the lock, immediately before merging.** The job
starts minutes after the asset was stored, and the same file may have been
re-ingested in between; merging into the stream as it was at submission time
would quietly revert that ingest.
"""

import os
import threading
from typing import Any, Dict, List, Optional, Sequence, Set

from assetlib.content import asset_key
from core.content import (
    ROLE_L2_CAPTION,
    TEXT,
    ROLE_SHORT_VIDEO,
    ContentBlock,
    ContentStream,
    media_block,
    role_of,
)
from core.multimodal.video_summary_client import VideoSummaryClient, VideoSummaryError

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

#: Media roles a caption is written for. An image is embedded but not
#: described -- a visual embedding already carries what it looks like, and a
#: generated sentence about it would mostly restate that less precisely.
CAPTIONED_ROLES = frozenset({ROLE_SHORT_VIDEO})

# One lock per asset: two ingests of the same file must not interleave their
# read-modify-write of the same content record. Keyed by asset so unrelated
# assets still caption concurrently.
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def asset_lock(asset_id: str) -> threading.Lock:
    """The lock every background job holds while it rewrites this asset's stream."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(asset_id, threading.Lock())


def caption_block_id(asset_id: str) -> str:
    """Where this asset's description lives, whoever wrote it and whenever."""
    return f"{asset_id}:caption"


#: Why an undescribed clip will stay that way, when nothing is configured to describe it.
NOT_CONFIGURED = (
    "video summary service is not configured (ENGINE_VIDEO_SUMMARY_BASE_URL)"
)


def needs_caption(stream: ContentStream) -> bool:
    """Whether this asset has a clip waiting to be described by a configured service."""
    return VideoSummaryClient().configured and _media_block(stream) is not None


def _media_block(stream: ContentStream) -> Optional[ContentBlock]:
    """The clip to describe, if this stream has one of a captioned role."""
    block = media_block(stream)
    if block is not None and role_of(block) in CAPTIONED_ROLES:
        return block
    return None


def caption_status(stream: ContentStream) -> Dict[str, Any]:
    """What the caption job has made of this asset so far.

    About captioning only. Whether the asset gets a *vector* is a separate
    pipeline with its own answer (`coverage.embedding_coverage`); reporting
    "unsupported" here for a recording that simply is not described would have
    read as though it were not searchable either.
    """
    block = media_block(stream)
    role = role_of(block) if block else ""
    status = str(stream.metadata.get("caption_status") or "")
    error = str(stream.metadata.get("caption_error") or "") or None
    if not status:
        status = STATUS_PENDING if role in CAPTIONED_ROLES else STATUS_SKIPPED
        if status == STATUS_PENDING and not VideoSummaryClient().configured:
            # No job was queued, so "pending" would wait forever. Worked out
            # now rather than stored: a clip ingested after the service is
            # configured is described as usual.
            status, error = STATUS_SKIPPED, NOT_CONFIGURED
    return {
        "role": role,
        "caption_status": status,
        "error": error,
        "updated_at": stream.metadata.get("caption_updated_at"),
    }


def caption_asset(
    library: Any,
    asset_id: str,
    client: Optional[VideoSummaryClient] = None,
    now: Optional[float] = None,
) -> str:
    """Describe this asset's clip and fold the result into its content stream.

    Returns the resulting status. Idempotent: an asset already captioned, or
    one with nothing to caption, is left alone.
    """
    client = client or VideoSummaryClient()
    asset = library.assets.get(asset_id)
    if asset is None:
        return STATUS_SKIPPED
    if not client.configured:
        # Nothing to call. Deliberately not recorded as a failure: the clip is
        # embedded and findable, and turning the service on later should let
        # the job run normally rather than meeting a terminal state.
        return STATUS_SKIPPED

    with asset_lock(asset_id):
        # Re-read rather than trust the stream this job was queued against.
        stream = reload_stream(library, asset)
        block = _media_block(stream)
        if block is None:
            return STATUS_SKIPPED
        if stream.metadata.get("caption_status") == STATUS_COMPLETED:
            return STATUS_COMPLETED

        try:
            suffix = os.path.splitext(stream.metadata.get("file_name") or "")[1] or ".mp4"
            with asset.media_path(block.media_key, suffix) as path:
                text = client.caption(path)
        except VideoSummaryError as error:
            return _record(library, asset, stream, STATUS_FAILED, str(error), now)
        except Exception as error:  # noqa: BLE001 - reported on the asset, not raised
            return _record(
                library, asset, stream, STATUS_FAILED,
                f"{type(error).__name__}: {error}", now,
            )

        changed = _merge_caption(stream, asset_id, text, block.block_id)
        return _record(library, asset, stream, STATUS_COMPLETED, "", now, changed)


def sources_taking(library: Any, asset: Any, blocks: Sequence[ContentBlock]) -> Set[str]:
    """The sources, in the asset's pools, whose records would hold one of `blocks`.

    A multimodal source takes a block its model `covers`; a graph source
    extracts knowledge from every text block of an asset it accepts. A text
    source never takes derived blocks. Unavailable and frozen sources are
    judged by their persisted profiles, without loading a model, so they catch
    up when re-enabled or brought back by a rollback.
    """
    from core.indexer import GraphIndexer, MultimodalIndexer, accepts_asset, accepts_block  # noqa: PLC0415
    from core.multimodal.routing import effective_configuration

    taking: Set[str] = set()
    for pool in library.asset_pools.values():
        if asset.asset_id not in pool.asset_ids:
            continue
        for projection in pool.projections:
            if isinstance(projection, MultimodalIndexer):
                takes = projection.accepts(asset) and any(
                    projection.covers(block) for block in blocks
                )
            elif isinstance(projection, GraphIndexer):
                takes = projection.accepts(asset) and any(
                    block.kind == TEXT for block in blocks
                )
            else:
                takes = False
            if takes:
                taking.add(projection.source.source_id)
        for source_id, source in {
            **pool.unavailable_sources,
            **pool.frozen_sources,
        }.items():
            roles = (source.profile or {}).get("supported_roles") or ()
            options = effective_configuration(source)
            if accepts_asset(asset, options) and any(
                role_of(block) in roles and accepts_block(block, options)
                for block in blocks
            ):
                taking.add(source_id)
    return taking


def note_derived(library: Any, asset: Any, blocks: Sequence[ContentBlock]) -> bool:
    """Re-open the asset only in the sources whose records `blocks` change.

    `blocks` are the derived blocks just written and any they replaced. A
    caption that no source takes is stored and nothing is re-embedded: marking
    the asset changed everywhere would have re-encoded its clip for an
    identical vector. Returns whether anything was re-opened.
    """
    taking = sources_taking(library, asset, blocks)
    if taking:
        library.note_assets_changed([asset.asset_id], taking)
    return bool(taking)


def reload_stream(library: Any, asset: Any) -> ContentStream:
    """This asset's stream as it is on disk right now."""
    if asset.content_source_id and asset.content_key:
        source = library.source_for(asset.content_source_id)
        return ContentStream.from_record(
            library.content_store.get_record(source, asset.content_key)
        )
    return asset.content


def _merge_caption(
    stream: ContentStream, asset_id: str, text: str, source_block_id: str
) -> List[ContentBlock]:
    """Put the description in the stream, replacing any earlier one.

    Returns the blocks this changed: the new caption and the one it replaced.
    """
    block_id = caption_block_id(asset_id)
    caption = ContentBlock(
        block_id=block_id,
        kind=TEXT,
        text=text,
        reading_order=0,
        metadata={"role": ROLE_L2_CAPTION, "source_block_id": source_block_id},
    )
    replaced = [block for block in stream.blocks if block.block_id == block_id]
    kept: List[ContentBlock] = [
        block for block in stream.blocks if block.block_id != block_id
    ]
    kept.append(caption)
    for order, block in enumerate(kept):
        block.reading_order = order
    stream.blocks = kept
    return replaced + [caption]


def _record(
    library: Any,
    asset: Any,
    stream: ContentStream,
    status: str,
    error: str,
    now: Optional[float],
    changed: Sequence[ContentBlock] = (),
) -> str:
    """Persist the stream and let the sources that take `changed` know.

    The write happens even on failure, so the reason is visible on the asset
    rather than only in a log. What was already materialized stays: a clip
    whose description failed keeps the vector it got at sync time.
    """
    import time  # noqa: PLC0415

    stream.metadata["caption_status"] = status
    stream.metadata["caption_updated_at"] = now if now is not None else time.time()
    if error:
        stream.metadata["caption_error"] = error
    else:
        stream.metadata.pop("caption_error", None)

    source = library.content_source(asset.content_source_id or None)
    key = asset.content_key or asset_key(asset.asset_id)
    library.content_store.put_record(source, key, stream.to_record())
    asset.cached = stream
    if status == STATUS_COMPLETED:
        # Only a changed caption changes what a projection should hold, and
        # only for a source that takes it. A failure left the blocks as they
        # were, and marking the asset stale would re-embed them for nothing.
        note_derived(library, asset, changed)
    return status


__all__ = [
    "CAPTIONED_ROLES",
    "NOT_CONFIGURED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SKIPPED",
    "asset_lock",
    "caption_asset",
    "caption_block_id",
    "caption_status",
    "needs_caption",
    "note_derived",
    "reload_stream",
    "sources_taking",
]
