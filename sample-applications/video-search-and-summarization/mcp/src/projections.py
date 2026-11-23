# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Projections from VSS wire payloads to agent-sized results.

Pipeline Manager's responses are shaped for the React UI: ``GET /summary/{id}``
runs to 80-120 KB for a five-minute video, and a single search hit is 1.5-3 KB,
mostly scoring telemetry.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

#: Upper bound on a listing tool's result, in bytes, so several results fit a
#: small model's context alongside the conversation. Search hits and summaries
#: are content the agent asked for and are never capped.
MAX_RESULT_BYTES = 8_000

#: Video-row columns that record whether a video is in the search index:
#: frame embeddings and summary-text embeddings respectively.
_INDEX_FLAGS = ("searchEmbeddings", "textEmbeddings")

#: A live segment's object name is the epoch second its recording started,
#: e.g. ``segments/1791446440.mp4``.
_SEGMENT_EPOCH_RE = re.compile(r"(?:^|/)(\d{9,11})(?:\.\d+)?\.mp4$")

#: ``user:pass@`` in a stream URL.
_URL_CREDENTIALS_RE = re.compile(r"(?i)\b(rtsps?://)[^/@\s]+@")


def redact_url(text: str | None) -> str | None:
    """Replace credentials in any RTSP URL inside ``text`` with ``***``.

    Dataprep already redacts the URLs it returns; this is the belt to that
    brace, applied to everything stream-related that leaves this server.
    """

    if not text:
        return text
    return _URL_CREDENTIALS_RE.sub(r"\1***@", text)


def is_number(value: Any, *, integer: bool = False) -> bool:
    """Whether ``value`` is a real number (an ``int`` if ``integer``).

    ``bool`` is excluded: it subclasses ``int``, so ``True`` would otherwise
    pass as ``1``.
    """

    kinds = int if integer else (int, float)
    return isinstance(value, kinds) and not isinstance(value, bool)


def iso_utc(epoch: float | int | None) -> str | None:
    """Render epoch seconds as ISO-8601 UTC with millisecond precision."""

    if not is_number(epoch) or epoch <= 0:
        return None
    moment = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_iso() -> str:
    """The current time as :func:`iso_utc` renders it."""

    return iso_utc(time.time()) or ""


def parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp as an aware UTC datetime, treating a
    naive value as UTC; ``None`` if it is not one."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_iso_epoch(value: Any) -> float | None:
    """Parse an ISO-8601 timestamp to epoch seconds, treating naive as UTC."""

    moment = parse_iso(value)
    return moment.timestamp() if moment else None


def observed_epoch(metadata: dict[str, Any]) -> float | None:
    """Wall-clock epoch seconds of a live hit's peak frame, or ``None``.

    A live frame is addressed as ``media_path`` (a segment named after the
    epoch second its recording started) plus ``timestamp`` seconds into it.
    The segment row's ``created_at`` is the fallback when the name does not
    carry the epoch. Uploaded videos have no wall-clock time and yield
    ``None``.
    """

    info = metadata.get("best_frame_info")
    if not isinstance(info, dict) or not info.get("is_live"):
        return None
    offset = info.get("timestamp")
    if not is_number(offset):
        offset = 0.0
    match = _SEGMENT_EPOCH_RE.search(str(info.get("media_path") or ""))
    if match:
        return int(match.group(1)) + float(offset)
    created = parse_iso_epoch(
        (metadata.get("video_metadata") or {}).get("created_at")
        or metadata.get("created_at")
    )
    return created + float(offset) if created is not None else None


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


#: Which index flag means "searchable" for each concrete strategy from
#: :func:`choose_index_strategy` -- frame mode and unified mode write to, and
#: query, different collections (``video_frame_embeddings`` vs
#: ``video_summary_embeddings``), so only one flag is meaningful once a
#: strategy is known.
_STRATEGY_INDEX_FLAG = {"embeddings": "searchEmbeddings", "summary": "textEmbeddings"}


def indexed_status(entity: dict[str, Any], *, strategy: str | None = None) -> bool | None:
    """Read whether a video is searchable from its own row.

    Args:
        strategy: The deployment's resolved indexing strategy, ``"embeddings"``
            or ``"summary"`` (see ``choose_index_strategy``). When given, only
            the flag that strategy actually writes and queries is checked, so
            a video indexed under a different, previously active strategy is
            not mistaken for searchable now. ``None`` falls back to treating
            either flag as sufficient, for callers with no resolved strategy
            (e.g. summary-only deployments, where indexing is off entirely).

    Returns:
        ``True`` if the relevant flag is set, ``False`` if it is explicitly
        unset, ``None`` when the backend reports neither -- unknown, not
        unindexed.
    """

    keys = (
        (_STRATEGY_INDEX_FLAG[strategy],)
        if strategy in _STRATEGY_INDEX_FLAG
        else _INDEX_FLAGS
    )
    flags = [entity.get(key) for key in keys]
    if any(flag is True for flag in flags):
        return True
    if any(flag is False for flag in flags):
        return False
    return None


def slim_video(
    entity: dict[str, Any],
    *,
    include_indexed: bool = True,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Project a ``VideoEntity`` down to the fields an agent can act on.

    ``name`` comes from ``dataStore.fileName``: ``POST /videos`` ignores the
    caller's name, so the ``name`` column holds multer's random hex.

    Args:
        include_indexed: Whether to report the ``indexed`` flag. Pass
            ``False`` in summary-only deployments, where there is no search
            index at all, so the flag would be meaningless rather than
            merely unknown.
        strategy: Forwarded to :func:`indexed_status`.
    """

    data_store = entity.get("dataStore") or {}
    video = {
        "video_id": entity.get("videoId"),
        "name": data_store.get("fileName") or entity.get("name"),
        "tags": list(entity.get("tags") or []),
        "created_at": entity.get("createdAt"),
    }
    if include_indexed:
        video["indexed"] = indexed_status(entity, strategy=strategy)
    return video


def _tag_list(value: Any) -> list[str]:
    """Tags as a list: VSS stores them as a list or a comma-separated string."""

    items = value if isinstance(value, list) else str(value or "").split(",")
    return [str(tag).strip() for tag in items if str(tag).strip()]


def slim_search_hit(
    raw: dict[str, Any], datastore_base_url: str | None = None
) -> dict[str, Any]:
    """Project one search result (aggregated or legacy flat shape) to the
    fields that carry meaning; missing or non-numeric values are dropped.

    ``url`` comes from the backend's ``videoPlaybackUrl``, prefixed with
    ``datastore_base_url`` when set. The metadata's ``video_url`` points at an
    internal hostname, so it is only a fallback for older backends.
    ``best_frame_info`` becomes ``frame``, the locator ``vss_get_media_frame``
    takes, plus the detected object's ``label``. ``tags`` are the camera tags
    VSS indexed the segment with, for recorded videos and live cameras alike
    (a live stream's footage carries the stream's tags).
    """

    metadata = raw.get("metadata") or {}
    data_store = (raw.get("video") or {}).get("dataStore") or {}
    best_frame = metadata.get("best_frame_info")

    seek = metadata.get("seek_timestamp", metadata.get("timestamp"))
    start = metadata.get("segment_start", seek)
    end = metadata.get("segment_end", seek)

    def _round(value: Any, places: int) -> float | None:
        if not is_number(value):
            return None
        return round(value, places)

    playback_path = raw.get("videoPlaybackUrl")
    if playback_path and datastore_base_url:
        url = f"{datastore_base_url.rstrip('/')}{playback_path}"
    else:
        url = playback_path or metadata.get("video_url") or metadata.get(
            "video_rel_url"
        )
        # Live segments carry a gateway-relative path under the datastore.
        if (
            url
            and not playback_path
            and str(url).startswith("/")
            and datastore_base_url
        ):
            url = f"{datastore_base_url.rstrip('/')}{url}"

    is_live = isinstance(best_frame, dict) and bool(best_frame.get("is_live"))
    breakdown = metadata.get("score_breakdown") or {}

    # Pipeline Manager stamps observedAt (capture time for live hits, upload
    # time plus offset for videos); older backends only let live hits be dated.
    observed_at = iso_utc(parse_iso_epoch(raw.get("observedAt")))
    time_source = raw.get("timeSource") if observed_at else None
    if not observed_at:
        observed_at = iso_utc(observed_epoch(metadata))
        time_source = "live" if observed_at else None
    if time_source not in ("live", "upload"):
        time_source = None

    tags = _tag_list(metadata.get("tags")) or _tag_list(
        (metadata.get("video_metadata") or {}).get("tags")
    )

    hit = {
        "video_id": metadata.get("video_id"),
        "tags": tags or None,
        "video_name": data_store.get("fileName")
        or (metadata.get("video_metadata") or {}).get("file_name"),
        "source": "live" if is_live else "video",
        "stream_id": metadata.get("video_id") if is_live else None,
        "observed_at": observed_at,
        "time_source": time_source,
        "start_s": _round(start, 1),
        "end_s": _round(end, 1),
        "seek_s": _round(seek, 1),
        "score": _round(metadata.get("relevance_score"), 3),
        "raw_score": _round(
            breakdown.get("raw_score") if isinstance(breakdown, dict) else None, 4
        ),
        "url": url,
        "frame": slim_best_frame(best_frame),
        "label": best_frame.get("detected_label") if isinstance(best_frame, dict) else None,
    }
    return {key: value for key, value in hit.items() if value not in (None, "")}


def _bbox_string(bbox: Any) -> str | None:
    """Render a crop box, as a 4-number list or ``"x1,y1,x2,y2"``, as the
    string ``GET /frames`` takes; ``None`` if malformed."""

    if isinstance(bbox, str):
        parts = [part.strip() for part in bbox.split(",")]
        if len(parts) == 4 and all(re.fullmatch(r"-?\d+(?:\.\d+)?", p) for p in parts):
            return ",".join(str(int(float(part))) for part in parts)
        return None
    if (
        isinstance(bbox, (list, tuple))
        and len(bbox) == 4
        and all(is_number(value) for value in bbox)
    ):
        return ",".join(str(int(value)) for value in bbox)
    return None


def slim_best_frame(info: Any) -> dict[str, Any] | None:
    """Project ``best_frame_info`` to the locator ``GET /frames`` takes.

    The peak-scoring frame's ``timestamp`` is kept unrounded: it addresses a
    single frame, unlike the segment-level ``seek_s``. ``crop_bbox`` is
    rendered as the ``"x1,y1,x2,y2"`` string the endpoint expects. Returns
    ``None`` when the hit carries no usable locator.
    """

    if not isinstance(info, dict):
        return None
    video_id = info.get("video_id")
    timestamp = info.get("timestamp")
    if (
        not video_id
        or not is_number(timestamp)
        or timestamp < 0
    ):
        return None

    frame: dict[str, Any] = {"video_id": str(video_id), "timestamp": timestamp}
    for key in ("bucket_name", "media_path"):
        if info.get(key):
            frame[key] = str(info[key])
    bbox = _bbox_string(info.get("crop_bbox"))
    if info.get("is_detected_crop") and bbox:
        frame["crop_bbox"] = bbox
    return frame


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
            {"start_s": start_s, "end_s": end_s, "caption": caption}
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
    include_timeline: bool = True,
) -> dict[str, Any]:
    """Project a ``UIState`` to a :class:`~.schemas.Timeline`, never
    shortening captions or summaries.

    ``completed`` follows the rollup when ``final_summary`` is set, else the
    timeline; the rollup ``summary`` appears only once done.
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
    }
    if include_timeline:
        result["timeline"] = build_timeline(ui_state)

    if final_summary and result["completed"]:
        result["summary"] = (ui_state.get("summary") or "").strip()

    transcript_summary = (ui_state.get("audioTranscriptSummary") or "").strip()
    if transcript_summary:
        result["audio_summary"] = transcript_summary

    return result



#: Stream stats an agent can act on; the rest is ingestion telemetry.
_STREAM_STATS = (
    "frames_processed",
    "embeddings_created",
    "segments_stored",
    "reconnect_count",
)


def slim_stream(info: dict[str, Any]) -> dict[str, Any]:
    """Project a dataprep ``LiveStreamInfo`` to what an agent acts on.

    Epoch timestamps become ISO-8601 UTC; the URL and any error are redacted.
    """

    stats = info.get("stats") or {}
    slim_stats: dict[str, Any] = {
        key: stats[key]
        for key in _STREAM_STATS
        if is_number(stats.get(key))
    }
    uptime = stats.get("uptime_seconds")
    if is_number(uptime):
        slim_stats["uptime_s"] = round(uptime, 1)
    last_frame = iso_utc(stats.get("last_frame_ts"))
    if last_frame:
        slim_stats["last_frame_at"] = last_frame

    stream = {
        "stream_id": info.get("stream_id"),
        # Pipeline Manager defaults the name to the URL, credentials included.
        "name": redact_url(info.get("stream_name")),
        "url": redact_url(info.get("stream_url")),
        "state": info.get("state"),
        "description": info.get("description"),
        "sensor_id": info.get("sensor_id"),
        "tags": list(info.get("tags") or []),
        "frame_interval": info.get("frame_interval"),
        "object_detection": info.get("enable_object_detection"),
        "stats": slim_stats,
        "error": redact_url(info.get("last_error")),
        "created_at": iso_utc(info.get("created_ts")),
    }
    return {
        key: value
        for key, value in stream.items()
        if value not in (None, "") or key in {"tags", "stats"}
    }
