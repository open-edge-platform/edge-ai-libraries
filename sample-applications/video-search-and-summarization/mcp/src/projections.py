# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Projections from VSS wire payloads to agent-sized results.

Pipeline Manager's responses are shaped for the React UI: ``GET /summary/{id}``
runs to 80-120 KB for a five-minute video, and a single search hit is 1.5-3 KB,
mostly scoring telemetry.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

#: Upper bound on any single tool result, in bytes, so several results fit a
#: small model's context alongside the conversation.
MAX_RESULT_BYTES = 8_000

#: Longest caption text returned inside a timeline entry before truncation.
MAX_CAPTION_CHARS = 600

#: Video-row columns that record whether a video is in the search index:
#: frame embeddings and summary-text embeddings respectively.
_INDEX_FLAGS = ("searchEmbeddings", "textEmbeddings")


def truncate(text: str | None, limit: int = MAX_CAPTION_CHARS) -> str:
    """Shorten ``text`` to ``limit`` characters, marking the cut."""

    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}... [truncated]"


def _payload_size(payload: Any) -> int:
    """Return the UTF-8 byte length of ``payload`` serialized as JSON."""

    return len(json.dumps(payload, default=str).encode("utf-8"))


def cap_payload(
    payload: dict[str, Any], list_key: str, *, max_bytes: int = MAX_RESULT_BYTES
) -> dict[str, Any]:
    """Drop trailing ``payload[list_key]`` items until it fits ``max_bytes``.

    Always sets ``truncated`` and ``omitted`` (see :class:`~.schemas.Capped`),
    so the shape does not depend on size. ``payload`` is not mutated.
    """

    items = list(payload.get(list_key) or [])
    total = len(items)

    def build(keep: int) -> dict[str, Any]:
        return {
            **payload,
            list_key: items[:keep],
            "truncated": keep < total,
            "omitted": total - keep,
        }

    if _payload_size(build(total)) <= max_bytes:
        return build(total)

    # Size grows monotonically with retained items: binary search the prefix.
    low, high = 0, total
    while low < high:
        midpoint = (low + high + 1) // 2
        if _payload_size(build(midpoint)) <= max_bytes:
            low = midpoint
        else:
            high = midpoint - 1
    return build(low)


def indexed_status(entity: dict[str, Any]) -> bool | None:
    """Read whether a video is searchable from its own row.

    Returns:
        ``True`` if any index flag is set, ``False`` if one is explicitly
        unset, ``None`` when the backend reports neither -- unknown, not
        unindexed.
    """

    flags = [entity.get(key) for key in _INDEX_FLAGS]
    if any(flag is True for flag in flags):
        return True
    if any(flag is False for flag in flags):
        return False
    return None


def slim_video(entity: dict[str, Any], *, include_indexed: bool = True) -> dict[str, Any]:
    """Project a ``VideoEntity`` down to the fields an agent can act on.

    ``name`` comes from ``dataStore.fileName``: ``POST /videos`` ignores the
    caller's name, so the ``name`` column holds multer's random hex.

    Args:
        include_indexed: Whether to report the ``indexed`` flag. Pass
            ``False`` in summary-only deployments, where there is no search
            index at all, so the flag would be meaningless rather than
            merely unknown.
    """

    data_store = entity.get("dataStore") or {}
    video = {
        "video_id": entity.get("videoId"),
        "name": data_store.get("fileName") or entity.get("name"),
        "tags": list(entity.get("tags") or []),
        "created_at": entity.get("createdAt"),
    }
    if include_indexed:
        video["indexed"] = indexed_status(entity)
    return video


def slim_search_hit(
    raw: dict[str, Any], datastore_base_url: str | None = None
) -> dict[str, Any]:
    """Project one search result to the fields that carry meaning.

    Scoring internals, per-frame scores and templated ``page_content`` are
    dropped. Both the aggregated shape and the legacy flat shape (no segment
    bounds) are handled.

    ``url`` is built from the backend's ``videoPlaybackUrl`` join, prefixed with
    ``datastore_base_url`` (kept relative when that is absent). The metadata's
    ``video_url``/``video_rel_url`` point at an internal hostname and are only
    a fallback for backends that predate the join. Missing and non-numeric
    values are dropped rather than sent as ``null`` or ``""``.
    """

    metadata = raw.get("metadata") or {}
    data_store = (raw.get("video") or {}).get("dataStore") or {}

    seek = metadata.get("seek_timestamp", metadata.get("timestamp"))
    start = metadata.get("segment_start", seek)
    end = metadata.get("segment_end", seek)

    def _round(value: Any, places: int) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return round(value, places)

    playback_path = raw.get("videoPlaybackUrl")
    if playback_path and datastore_base_url:
        url = f"{datastore_base_url.rstrip('/')}{playback_path}"
    else:
        url = playback_path or metadata.get("video_url") or metadata.get(
            "video_rel_url"
        )

    hit = {
        "video_id": metadata.get("video_id"),
        "video_name": data_store.get("fileName")
        or (metadata.get("video_metadata") or {}).get("file_name"),
        "start_s": _round(start, 1),
        "end_s": _round(end, 1),
        "seek_s": _round(seek, 1),
        "score": _round(metadata.get("relevance_score"), 3),
        "url": url,
    }
    return {key: value for key, value in hit.items() if value not in (None, "")}


def attach_video_names(
    hits: list[dict[str, Any]], names_by_id: dict[str, str]
) -> list[dict[str, Any]]:
    """Fill in a missing ``video_name`` on hits from a video-id lookup."""

    for hit in hits:
        name = names_by_id.get(hit.get("video_id") or "")
        if name and not hit.get("video_name"):
            hit["video_name"] = name
    return hits


def _frame_bounds(
    frame_summary: dict[str, Any],
    frames_by_id: dict[str, dict[str, Any]],
) -> tuple[float | None, float | None]:
    """Resolve a frame summary's ``(start_s, end_s)`` from the UI frame list.

    ``UIFrame.videoTimeStamp`` is the only place a caption's position is
    exposed; ``FrameSummary`` carries frame ids only.
    """

    ids = frame_summary.get("frames") or [
        value
        for value in (frame_summary.get("startFrame"), frame_summary.get("endFrame"))
        if value
    ]
    stamps = [
        frames_by_id[str(frame_id)].get("videoTimeStamp")
        for frame_id in ids
        if str(frame_id) in frames_by_id
    ]
    stamps = [value for value in stamps if isinstance(value, (int, float))]
    if not stamps:
        return None, None
    return round(min(stamps), 1), round(max(stamps), 1)


def build_timeline(ui_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Project ``frameSummaries`` into ``{start_s, end_s, caption}`` entries
    ordered by start time, skipping entries with no caption yet."""

    frames_by_id = {
        str(frame.get("frameId")): frame for frame in ui_state.get("frames") or []
    }

    entries: list[dict[str, Any]] = []
    for frame_summary in ui_state.get("frameSummaries") or []:
        caption = (frame_summary.get("summary") or "").strip()
        if not caption:
            continue
        start_s, end_s = _frame_bounds(frame_summary, frames_by_id)
        entries.append(
            {"start_s": start_s, "end_s": end_s, "caption": truncate(caption)}
        )

    entries.sort(key=lambda item: (item["start_s"] is None, item["start_s"] or 0))
    return entries


def caption_progress(ui_state: dict[str, Any]) -> dict[str, int]:
    """Return ``complete``/``in_progress``/``ready``/``total`` caption counts."""

    counts = ui_state.get("frameSummaryStatus") or {}
    complete = int(counts.get("complete", 0) or 0)
    in_progress = int(counts.get("inProgress", 0) or 0)
    ready = int(counts.get("ready", 0) or 0)
    na = int(counts.get("na", 0) or 0)
    return {
        "complete": complete,
        "in_progress": in_progress,
        "ready": ready,
        "total": complete + in_progress + ready + na,
    }


def is_timeline_done(ui_state: dict[str, Any]) -> bool:
    """Report whether chunk-level captioning has finished.

    Deliberately not ``videoSummaryStatus == "complete"``: with
    ``produceFinalSummary: false`` that status stays ``"na"`` forever.
    """

    if ui_state.get("videoChunkingStatus") != "complete":
        return False
    progress = caption_progress(ui_state)
    return (
        progress["complete"] > 0
        and progress["in_progress"] == 0
        and progress["ready"] == 0
    )


def is_final_summary_done(ui_state: dict[str, Any]) -> bool:
    """Report whether the map-reduce rollup has finished."""

    return ui_state.get("videoSummaryStatus") == "complete"


def slim_summary(
    ui_state: dict[str, Any],
    *,
    final_summary: bool = False,
) -> dict[str, Any]:
    """Project a ``UIState`` to a :class:`~.schemas.Timeline`, capped in size.

    Drops per-frame entries, chunks, prompt templates and inference config.
    ``completed`` follows the rollup when ``final_summary`` is set and the
    timeline otherwise; the rollup ``summary`` is only included once done.
    """

    progress = caption_progress(ui_state)
    done = is_final_summary_done if final_summary else is_timeline_done
    result: dict[str, Any] = {
        "video_id": ui_state.get("videoId"),
        "state_id": ui_state.get("stateId"),
        "title": ui_state.get("title"),
        "completed": done(ui_state),
        "captioned": progress["complete"],
        "total_chunks": progress["total"],
        "timeline": build_timeline(ui_state),
    }

    if final_summary and result["completed"]:
        result["summary"] = ui_state.get("summary") or ""

    transcript_summary = ui_state.get("audioTranscriptSummary")
    if transcript_summary:
        result["audio_summary"] = truncate(transcript_summary, 1_500)

    return cap_payload(result, "timeline")


def unwrap_search_results(payload: Any) -> list[dict[str, Any]]:
    """Flatten ``POST /search/query``'s ``results[].results[]`` envelope.

    Unrecognised shapes yield an empty list rather than raising, because the
    backend also emits a bare list on some fallback paths.
    """

    if isinstance(payload, dict):
        blocks: Iterable[Any] = payload.get("results") or []
    elif isinstance(payload, list):
        blocks = payload
    else:
        return []

    hits: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("results"), list):
            hits.extend(item for item in block["results"] if isinstance(item, dict))
        elif isinstance(block, dict):
            hits.append(block)
    return hits
