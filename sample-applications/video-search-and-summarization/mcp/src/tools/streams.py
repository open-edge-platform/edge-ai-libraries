# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live stream tools: register, inspect, pause/resume and remove RTSP cameras.

Pipeline Manager proxies ``/streams`` to multimodal-dataprep, which ingests
each camera in the background and writes its frame embeddings into the same
search index as uploaded videos. Credentials in a stream URL are never echoed
back: dataprep redacts its responses and this module redacts again, including
error messages.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastmcp import FastMCP
from typing_extensions import TypedDict, NotRequired

from ..clients import VssError
from ..projections import cap_payload, is_number, redact_url, slim_stream
from ..schemas import (
    Stream,
    StreamAddResult,
    StreamList,
    StreamRemoveResult,
)
from ._deps import DESTRUCTIVE, IDEMPOTENT_WORK, READ_ONLY, STARTS_WORK, Deps

#: Mirrors Pipeline Manager's ``LiveStreamCreateDto`` checks, so a bad request
#: fails here with a sentence instead of a 400 listing validator names.
_RTSP_URL_RE = re.compile(r"^rtsps?://\S+$", re.IGNORECASE)
_SENSOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
MAX_BATCH = 64
MAX_TAGS = 32

StreamState = Literal[
    "pending", "starting", "running", "paused", "reconnecting", "error", "stopped"
]


class StreamSpec(TypedDict):
    """One camera to add, for adding several at once."""

    stream_url: str
    name: NotRequired[str]
    description: NotRequired[str]
    sensor_id: NotRequired[str]
    frame_interval: NotRequired[int]
    object_detection: NotRequired[bool]
    detection_confidence: NotRequired[float]
    tags: NotRequired[list[str]]
    start: NotRequired[bool]


def _redacted_error(exc: VssError) -> VssError:
    """Re-raise a backend error with any stream credentials removed."""

    return VssError(redact_url(str(exc)) or "", status_code=exc.status_code)


def _check_tuning(
    frame_interval: Any, detection_confidence: Any, tags: Any
) -> None:
    if frame_interval is not None and (
        not is_number(frame_interval, integer=True)
        or not 1 <= frame_interval <= 60
    ):
        raise VssError(
            f"frame_interval must be a whole number from 1 to 60, got {frame_interval!r}."
        )
    if detection_confidence is not None and (
        not is_number(detection_confidence)
        or not 0.1 <= detection_confidence <= 1.0
    ):
        raise VssError(
            "detection_confidence must be between 0.1 and 1.0, got "
            f"{detection_confidence!r}."
        )
    if tags is not None and (
        not isinstance(tags, list)
        or len(tags) > MAX_TAGS
        or not all(isinstance(tag, str) and tag.strip() for tag in tags)
    ):
        raise VssError(f"tags must be a list of up to {MAX_TAGS} non-empty strings.")


def build_stream_body(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate one camera spec and shape it as ``LiveStreamCreateDto``.

    Raises:
        VssError: On a non-RTSP URL or an out-of-range setting.
    """

    url = (spec.get("stream_url") or "").strip()
    if not _RTSP_URL_RE.match(url):
        raise VssError(
            f"stream_url must start with rtsp:// or rtsps://, got "
            f"{redact_url(url)!r}."
        )
    sensor_id = (spec.get("sensor_id") or "").strip() or None
    if sensor_id and not _SENSOR_ID_RE.match(sensor_id):
        raise VssError(
            "sensor_id must start with a letter or digit and contain only "
            "letters, digits, '.', '_', ':' or '-'."
        )
    _check_tuning(
        spec.get("frame_interval"), spec.get("detection_confidence"), spec.get("tags")
    )

    body: dict[str, Any] = {"stream_url": url}
    optional = {
        "stream_name": (spec.get("name") or "").strip() or None,
        "description": (spec.get("description") or "").strip() or None,
        "sensor_id": sensor_id,
        "frame_interval": spec.get("frame_interval"),
        "enable_object_detection": spec.get("object_detection"),
        "detection_confidence": spec.get("detection_confidence"),
        "tags": [tag.strip() for tag in spec["tags"]] if spec.get("tags") else None,
        "start": spec.get("start"),
    }
    body.update({key: value for key, value in optional.items() if value is not None})
    return body


async def list_streams(
    deps: Deps,
    *,
    state: str | None = None,
    tags: list[str] | None = None,
    limit: int = 50,
) -> StreamList:
    """Return registered cameras, newest first."""

    try:
        raw = await deps.client.list_streams(state=state, tags=tags)
    except VssError as exc:
        raise _redacted_error(exc) from exc
    streams = [slim_stream(item) for item in raw]
    streams = [stream for stream in streams if stream.get("stream_id")]
    streams.sort(key=lambda stream: stream.get("created_at") or "", reverse=True)
    payload: dict[str, Any] = {
        "total": len(streams),
        "count": 0,
        "streams": streams[: max(1, limit)],
    }
    payload = cap_payload(payload, "streams")
    payload["count"] = len(payload["streams"])
    return payload


async def require_stream(deps: Deps, stream_id: str) -> dict[str, Any]:
    """Return the raw stream ``stream_id``, or raise a usable error."""

    stream_id = (stream_id or "").strip()
    try:
        raw = await deps.client.get_stream(stream_id) if stream_id else None
    except VssError as exc:
        raise _redacted_error(exc) from exc
    if not raw:
        raise _no_stream(stream_id)
    return raw


def _no_stream(stream_id: str) -> VssError:
    return VssError(
        f"No live stream with id {stream_id!r}. Use vss_list_streams to "
        "find the right id."
    )


async def get_stream(deps: Deps, stream_id: str) -> Stream:
    return slim_stream(await require_stream(deps, stream_id))


async def add_streams(deps: Deps, specs: list[dict[str, Any]]) -> StreamAddResult:
    """Register one or more cameras.

    One camera goes to ``POST /streams`` so its own error comes back as the
    tool error; several go to ``POST /streams/batch``, where each succeeds or
    fails on its own.

    Raises:
        VssError: If any spec is invalid (nothing is registered then), or a
            single registration fails.
    """

    if not specs:
        raise VssError("Give a stream_url, or a non-empty list in streams.")
    if len(specs) > MAX_BATCH:
        raise VssError(f"At most {MAX_BATCH} cameras can be added in one call.")
    bodies = [build_stream_body(spec) for spec in specs]

    try:
        if len(bodies) == 1:
            created = await deps.client.create_stream(bodies[0])
            stream = slim_stream(created)
            return {
                "accepted": 1,
                "rejected": 0,
                "items": [
                    {
                        "stream_url": stream["url"],
                        "accepted": True,
                        "stream_id": stream["stream_id"],
                    }
                ],
                "streams": [stream],
            }
        outcome = await deps.client.create_streams(bodies)
    except VssError as exc:
        raise _redacted_error(exc) from exc

    items = []
    for item in outcome["items"]:
        entry: dict[str, Any] = {
            "stream_url": redact_url(item["identifier"]),
            "accepted": item["status"] == "success",
        }
        if item.get("stream_id"):
            entry["stream_id"] = item["stream_id"]
        if item.get("message"):
            entry["message"] = redact_url(item["message"])
        items.append(entry)

    streams: list[dict[str, Any]] = []
    for entry in items:
        if entry["accepted"] and entry.get("stream_id"):
            try:
                raw = await deps.client.get_stream(entry["stream_id"])
            except VssError:
                raw = None
            if raw:
                streams.append(slim_stream(raw))
    return {
        "accepted": outcome["accepted"],
        "rejected": outcome["rejected"],
        "items": items,
        "streams": streams,
    }


async def update_stream(
    deps: Deps,
    stream_id: str,
    *,
    state: str | None = None,
    name: str | None = None,
    description: str | None = None,
    frame_interval: int | None = None,
    object_detection: bool | None = None,
    detection_confidence: float | None = None,
    tags: list[str] | None = None,
) -> Stream:
    """Pause, resume or retune a camera.

    Raises:
        VssError: If nothing would change, a value is out of range, or the
            stream does not exist.
    """

    if state is not None and state not in {"running", "paused"}:
        raise VssError(
            "state can only be set to 'paused' or 'running' (resume); the "
            "other states are managed by VSS."
        )
    _check_tuning(frame_interval, detection_confidence, tags)
    body = {
        key: value
        for key, value in {
            "state": state,
            "stream_name": (name or "").strip() or None,
            "description": description,
            "frame_interval": frame_interval,
            "enable_object_detection": object_detection,
            "detection_confidence": detection_confidence,
            "tags": [tag.strip() for tag in tags] if tags is not None else None,
        }.items()
        if value is not None
    }
    if not body:
        raise VssError(
            "Nothing to change: give state, name, description, frame_interval, "
            "object_detection, detection_confidence or tags. A camera's URL "
            "cannot be changed; remove it and add it again instead."
        )
    stream_id = (stream_id or "").strip()
    try:
        updated = await deps.client.update_stream(stream_id, body)
    except VssError as exc:
        if exc.status_code == 404:
            raise _no_stream(stream_id) from exc
        raise _redacted_error(exc) from exc
    return slim_stream(updated)


async def remove_streams(deps: Deps, stream_ids: list[str]) -> StreamRemoveResult:
    """Stop and deregister cameras, keeping their media and embeddings.

    Purging is never requested: past hits from a removed camera stay
    searchable and playable until the deployment's retention prunes them.
    """

    ids = [sid.strip() for sid in stream_ids if isinstance(sid, str) and sid.strip()]
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise VssError("Give at least one stream_id to remove.")
    if len(ids) > MAX_BATCH:
        raise VssError(f"At most {MAX_BATCH} cameras can be removed in one call.")

    try:
        outcome = await deps.client.delete_streams(ids)
    except VssError as exc:
        raise _redacted_error(exc) from exc
    items: list[dict[str, Any]] = []
    for item in outcome["items"]:
        entry: dict[str, Any] = {
            "stream_id": item["stream_id"],
            "removed": item["status"] == "success",
        }
        if not entry["removed"]:
            entry["message"] = redact_url(item.get("message")) or ""
        items.append(entry)
    if len(ids) == 1 and not items[0]["removed"]:
        raise VssError(
            f"Could not remove stream {ids[0]!r}: {items[0]['message']} Use "
            "vss_list_streams to find the right id."
        )
    return {"removed": outcome["accepted"], "items": items}


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the live stream tools, if this deployment ingests cameras."""

    if not deps.features.live_streams:
        return

    @mcp.tool(annotations=READ_ONLY)
    async def vss_list_streams(
        state: StreamState | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> StreamList:
        """List live RTSP cameras registered with VSS, with their state and
        ingestion stats. A camera's stream_id is the video_id (and
        stream_id) of its search hits.

        Args:
            state: Only cameras in this state, e.g. "running" or "error".
            tags: Only cameras carrying all of these tags.
            limit: Maximum cameras to return.
        """

        return await list_streams(deps, state=state, tags=tags, limit=limit)

    @mcp.tool(annotations=READ_ONLY)
    async def vss_get_stream(stream_id: str) -> Stream:
        """Return one live camera: its state, settings, last error, and
        stats (frames processed, embeddings created, last frame time).
        Use it to check a camera is ingesting before searching it.

        Args:
            stream_id: The camera's stream_id.
        """

        return await get_stream(deps, stream_id)

    @mcp.tool(annotations=STARTS_WORK)
    async def vss_add_stream(
        stream_url: str | None = None,
        name: str | None = None,
        description: str | None = None,
        sensor_id: str | None = None,
        frame_interval: int | None = None,
        object_detection: bool | None = None,
        detection_confidence: float | None = None,
        tags: list[str] | None = None,
        start: bool = True,
        streams: list[StreamSpec] | None = None,
    ) -> StreamAddResult:
        """Add a live RTSP camera to VSS. It is ingested continuously in the
        background and becomes searchable with vss_search_video within
        about 10-30 s; its hits have source "live".

        Give stream_url (and optional settings) for one camera, or streams
        for several at once -- not both. Each camera in streams succeeds or
        fails on its own. Credentials in the URL are accepted but never
        returned. Check the result with vss_get_stream: "running" with
        rising embeddings means it is being indexed.

        Args:
            stream_url: rtsp:// or rtsps:// URL of the camera.
            name: Friendly label for the camera.
            description: Free-text description.
            sensor_id: Stable id of the physical camera, recorded on every
                embedding; defaults to the generated stream_id.
            frame_interval: Embed every Nth frame, 1-60. Lower is denser
                and costs more compute.
            object_detection: Also embed detected-object crops, which makes
                people and vehicles easier to find.
            detection_confidence: Minimum detector score for a crop, 0.1-1.0.
            tags: Tags applied to every embedding; usable as search tags.
            start: false registers the camera paused.
            streams: Several cameras, each with the fields above.
        """

        if streams and stream_url:
            raise VssError("Give either stream_url or streams, not both.")
        if streams:
            specs = [dict(spec) for spec in streams]
        else:
            specs = [
                {
                    "stream_url": stream_url,
                    "name": name,
                    "description": description,
                    "sensor_id": sensor_id,
                    "frame_interval": frame_interval,
                    "object_detection": object_detection,
                    "detection_confidence": detection_confidence,
                    "tags": tags,
                    "start": start,
                }
            ] if stream_url else []
        return await add_streams(deps, specs)

    @mcp.tool(annotations=IDEMPOTENT_WORK)
    async def vss_update_stream(
        stream_id: str,
        state: Literal["running", "paused"] | None = None,
        name: str | None = None,
        description: str | None = None,
        frame_interval: int | None = None,
        object_detection: bool | None = None,
        detection_confidence: float | None = None,
        tags: list[str] | None = None,
    ) -> Stream:
        """Pause, resume or retune a live camera. Pausing stops ingestion
        but keeps the camera registered; "running" resumes it. Only the
        fields given change. The URL cannot be changed: remove the camera
        and add it again.

        Args:
            stream_id: The camera's stream_id.
            state: "paused" to pause, "running" to resume.
            name: New friendly label.
            description: New description.
            frame_interval: Embed every Nth frame, 1-60.
            object_detection: Turn detected-object crops on or off.
            detection_confidence: Minimum detector score, 0.1-1.0.
            tags: Replaces the camera's tags.
        """

        return await update_stream(
            deps,
            stream_id,
            state=state,
            name=name,
            description=description,
            frame_interval=frame_interval,
            object_detection=object_detection,
            detection_confidence=detection_confidence,
            tags=tags,
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    async def vss_remove_stream(
        stream_id: str | None = None,
        stream_ids: list[str] | None = None,
    ) -> StreamRemoveResult:
        """Stop and remove live cameras from VSS. Ingestion stops and the
        camera is deregistered. Its recorded clips and embeddings are kept,
        so earlier hits stay searchable and playable. To stop temporarily,
        use vss_update_stream with state "paused" instead.

        Args:
            stream_id: The camera to remove.
            stream_ids: Several cameras to remove; each succeeds or fails
                on its own.
        """

        ids = list(stream_ids or [])
        if stream_id:
            ids.insert(0, stream_id)
        return await remove_streams(deps, ids)
