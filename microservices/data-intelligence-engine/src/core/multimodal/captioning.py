# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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

#: Media roles a caption is written for.
CAPTIONED_ROLES = frozenset({ROLE_SHORT_VIDEO})

# Per-asset locks serializing read-modify-write of an asset's content record.
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def asset_lock(asset_id: str) -> threading.Lock:
    """The lock every background job holds while it rewrites this asset's stream."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(asset_id, threading.Lock())


def caption_block_id(asset_id: str) -> str:
    """Stable caption block id, so a retry replaces rather than appends."""
    return f"{asset_id}:caption"


NOT_CONFIGURED = (
    "video summary service is not configured (ENGINE_VIDEO_SUMMARY_BASE_URL)"
)


def needs_caption(stream: ContentStream) -> bool:
    """Whether this asset has a clip waiting to be described by a configured service."""
    return VideoSummaryClient().configured and _media_block(stream) is not None


def _media_block(stream: ContentStream) -> Optional[ContentBlock]:
    block = media_block(stream)
    if block is not None and role_of(block) in CAPTIONED_ROLES:
        return block
    return None


def caption_status(stream: ContentStream) -> Dict[str, Any]:
    """Caption job status for this asset (captioning only, not embedding)."""
    block = media_block(stream)
    role = role_of(block) if block else ""
    status = str(stream.metadata.get("caption_status") or "")
    error = str(stream.metadata.get("caption_error") or "") or None
    if not status:
        status = STATUS_PENDING if role in CAPTIONED_ROLES else STATUS_SKIPPED
        if status == STATUS_PENDING and not VideoSummaryClient().configured:
            # No job was queued; derived rather than stored.
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
    """Describe this asset's clip and fold the result into its content stream; idempotent."""
    client = client or VideoSummaryClient()
    asset = library.assets.get(asset_id)
    if asset is None:
        return STATUS_SKIPPED
    if not client.configured:
        # Not recorded, so enabling the service later lets the job run normally.
        return STATUS_SKIPPED

    with asset_lock(asset_id):
        # Re-read: the asset may have been re-ingested since the job was queued.
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
        except Exception as error:  # noqa: BLE001
            return _record(
                library, asset, stream, STATUS_FAILED,
                f"{type(error).__name__}: {error}", now,
            )

        changed = _merge_caption(stream, asset_id, text, block.block_id)
        return _record(library, asset, stream, STATUS_COMPLETED, "", now, changed)


def sources_taking(library: Any, asset: Any, blocks: Sequence[ContentBlock]) -> Set[str]:
    """The sources, in the asset's pools, whose records would hold one of `blocks`.

    Unavailable and frozen sources are judged by their persisted profiles.
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
    """Re-open the asset only in the sources whose records `blocks` change; returns whether any were."""
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
    """Put the caption in the stream, returning the new block and any it replaced."""
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
    """Persist the stream (also on failure) and re-open sources that take `changed`."""
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
