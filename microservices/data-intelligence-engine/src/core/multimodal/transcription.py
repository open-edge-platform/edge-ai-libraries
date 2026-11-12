# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from typing import Any, Dict, List, Optional, Protocol, Sequence

import config
from assetlib.content import asset_key
from core.content import (
    ROLE_AUDIO,
    ROLE_L2_TRANSCRIPT,
    TEXT,
    ContentBlock,
    ContentStream,
    media_block,
    role_of,
)
from core.multimodal.captioning import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SKIPPED,
    asset_lock,
    note_derived,
    reload_stream,
)

#: Media roles whose speech is transcribed.
TRANSCRIBED_ROLES = frozenset({ROLE_AUDIO})


ASR_DISABLED = "speech recognition is disabled (ENGINE_ASR_ENABLED=false)"


class Transcriber(Protocol):
    def transcribe(self, path: str) -> Sequence[Any]:
        """Segments with `start_s`, `end_s` and `text`, in time order."""


def transcript_block_prefix(asset_id: str) -> str:
    return f"{asset_id}:transcript:"


def needs_transcript(stream: ContentStream) -> bool:
    """Whether this asset has a recording waiting to be transcribed."""
    return config.ASR_ENABLED and _media_block(stream) is not None


def _media_block(stream: ContentStream) -> Optional[ContentBlock]:
    block = media_block(stream)
    if block is not None and role_of(block) in TRANSCRIBED_ROLES:
        return block
    return None


def transcript_status(stream: ContentStream) -> Dict[str, Any]:
    """Transcription status, error, timestamp and segment count for this asset."""
    block = media_block(stream)
    role = role_of(block) if block else ""
    status = str(stream.metadata.get("transcript_status") or "")
    error = str(stream.metadata.get("transcript_error") or "") or None
    if not status:
        status = STATUS_PENDING if role in TRANSCRIBED_ROLES else STATUS_SKIPPED
        if status == STATUS_PENDING and not config.ASR_ENABLED:
            status, error = STATUS_SKIPPED, ASR_DISABLED
    prefix = transcript_block_prefix(stream.asset_id)
    return {
        "transcript_status": status,
        "transcript_error": error,
        "transcript_updated_at": stream.metadata.get("transcript_updated_at"),
        "transcript_segments": sum(
            1 for block in stream.blocks if block.block_id.startswith(prefix)
        ),
    }


def transcribe_asset(
    library: Any,
    asset_id: str,
    transcriber: Optional[Transcriber] = None,
    now: Optional[float] = None,
) -> str:
    """Transcribe this asset's recording into its stream (idempotent) and return the status."""
    asset = library.assets.get(asset_id)
    if asset is None or not config.ASR_ENABLED:
        return STATUS_SKIPPED

    with asset_lock(asset_id):
        stream = reload_stream(library, asset)
        block = _media_block(stream)
        if block is None:
            return STATUS_SKIPPED
        if stream.metadata.get("transcript_status") == STATUS_COMPLETED:
            return STATUS_COMPLETED

        try:
            if transcriber is None:
                from core.multimodal.asr import get_transcriber  # noqa: PLC0415

                transcriber = get_transcriber()
            suffix = os.path.splitext(stream.metadata.get("file_name") or "")[1] or ".wav"
            with asset.media_path(block.media_key, suffix) as path:
                segments = list(transcriber.transcribe(path))
        except Exception as error:  # noqa: BLE001
            return _record(
                library, asset, stream, STATUS_FAILED,
                f"{type(error).__name__}: {error}", now,
            )

        changed = _merge_transcript(stream, asset_id, segments, block.block_id)
        return _record(library, asset, stream, STATUS_COMPLETED, "", now, changed)


def _merge_transcript(
    stream: ContentStream,
    asset_id: str,
    segments: Sequence[Any],
    source_block_id: str,
) -> List[ContentBlock]:
    """Replace the stream's transcript blocks; return both replaced and added blocks."""
    prefix = transcript_block_prefix(asset_id)
    replaced = [block for block in stream.blocks if block.block_id.startswith(prefix)]
    kept: List[ContentBlock] = [
        block for block in stream.blocks if not block.block_id.startswith(prefix)
    ]
    added: List[ContentBlock] = []
    for number, segment in enumerate(
        segment for segment in segments if str(segment.text).strip()
    ):
        added.append(
            ContentBlock(
                block_id=f"{prefix}{number}",
                kind=TEXT,
                text=str(segment.text).strip(),
                metadata={
                    "role": ROLE_L2_TRANSCRIPT,
                    "source_block_id": source_block_id,
                    "t_start_ms": int(round(float(segment.start_s) * 1000)),
                    "t_end_ms": int(round(float(segment.end_s) * 1000)),
                },
            )
        )
    kept.extend(added)
    for order, block in enumerate(kept):
        block.reading_order = order
    stream.blocks = kept
    return replaced + added


def _record(
    library: Any,
    asset: Any,
    stream: ContentStream,
    status: str,
    error: str,
    now: Optional[float],
    changed: Sequence[ContentBlock] = (),
) -> str:
    """Persist the stream and, on success, notify sources of `changed` blocks."""
    stream.metadata["transcript_status"] = status
    stream.metadata["transcript_updated_at"] = now if now is not None else time.time()
    if error:
        stream.metadata["transcript_error"] = error
    else:
        stream.metadata.pop("transcript_error", None)

    source = library.content_source(asset.content_source_id or None)
    key = asset.content_key or asset_key(asset.asset_id)
    library.content_store.put_record(source, key, stream.to_record())
    asset.cached = stream
    if status == STATUS_COMPLETED:
        note_derived(library, asset, changed)
    return status


__all__ = [
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SKIPPED",
    "TRANSCRIBED_ROLES",
    "Transcriber",
    "needs_transcript",
    "transcribe_asset",
    "transcript_block_prefix",
    "transcript_status",
]
