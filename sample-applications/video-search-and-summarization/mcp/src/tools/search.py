# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Search tools."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, ResourceLink, TextContent
from pydantic import TypeAdapter

from ..clients import VssError, is_image_reference, resolve_image_input
from ..projections import (
    redact_url,
    attach_video_names,
    cap_payload,
    iso_utc,
    observed_epoch,
    parse_iso_epoch,
    slim_search_hit,
    slim_video,
    unwrap_search_results,
)
from ..schemas import (
    FrameLocator,
    Hit,
    MediaFrame,
    SearchList,
    SearchResult,
    SearchSummary,
    StoredSearch,
    WatchResult,
)
from ._deps import IDEMPOTENT_WORK, READ_ONLY, STARTS_WORK, Deps
from .discovery import match_tags, tag_counts

logger = logging.getLogger(__name__)

#: Default number of hits. A handful of well-scored segments beats a long tail.
DEFAULT_LIMIT = 5
MAX_LIMIT = 25

#: Tags offered back when a tag filter matched nothing.
MAX_AVAILABLE_TAGS = 50

#: How long a search waits for its persisted query to finish by default. A
#: search normally takes about a second, so this stays well under the budget
#: for summaries.
DEFAULT_SEARCH_WAIT_SECONDS = 60.0

#: Upper bound on the delay between polls of a running search query.
SEARCH_POLL_INTERVAL_SECONDS = 1.0

#: Default and maximum number of persisted queries listed.
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

SEARCH_RESULT_SCHEMA = TypeAdapter(SearchResult).json_schema()
STORED_SEARCH_SCHEMA = TypeAdapter(StoredSearch).json_schema()
MEDIA_FRAME_SCHEMA = TypeAdapter(MediaFrame).json_schema()

#: A pixel box ``x1,y1,x2,y2``, as ``GET /frames`` validates it.
_CROP_BBOX_RE = re.compile(r"^\d+,\d+,\d+,\d+$")

#: JPEG quality for returned frames: smaller than the backend's 90, still
#: plenty for a vision model to read.
DEFAULT_FRAME_QUALITY = 80

#: Bucket live-camera segments are stored in when the camera's own record
#: is gone (dataprep's ``LIVE_STREAM_BUCKET`` default).
DEFAULT_LIVE_STREAM_BUCKET = "live-streams"


def _parse_iso(name: str, value: str) -> datetime:
    """Parse one ISO-8601 bound as UTC, treating a naive value as UTC."""

    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise VssError(
            f"{name}={value!r} is not an ISO-8601 timestamp, e.g. "
            "2026-08-04T14:00:00Z."
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def build_time_filter(start: str | None, end: str | None) -> dict[str, Any] | None:
    """Validate an absolute range and shape it as ``timeFilter``, or ``None``.

    Strict, because Pipeline Manager silently drops a malformed filter and
    returns plausible-looking unfiltered hits.

    Raises:
        VssError: If only one bound is given, either is not ISO-8601, or
            ``start`` is after ``end``.
    """

    start = (start or "").strip()
    end = (end or "").strip()
    if not start and not end:
        return None
    if not (start and end):
        raise VssError("Give both start and end as ISO-8601 timestamps, or neither.")
    start_at = _parse_iso("start", start)
    end_at = _parse_iso("end", end)
    if start_at > end_at:
        raise VssError("start must not be after end.")
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    return {
        "start": start_at.strftime(fmt),
        "end": end_at.strftime(fmt),
        "source": "absolute",
    }


async def _video_names(deps: Deps, videos: list[dict[str, Any]] | None) -> dict[str, str]:
    """Return names by video id, fetching the library only if not already held.

    Failure is tolerated: hits then simply arrive unnamed.
    """

    if videos is None:
        try:
            videos = await deps.client.list_videos()
        except VssError as exc:
            logger.warning("Could not list videos to name search hits: %s", exc)
            return {}
    slims = (slim_video(video) for video in videos)
    return {slim["video_id"]: slim["name"] for slim in slims if slim["video_id"]}


async def _stream_names(deps: Deps) -> dict[str, str]:
    """Return camera names by stream id; empty if streams cannot be listed."""

    if not deps.features.live_streams:
        return {}
    try:
        streams = await deps.client.list_streams()
    except VssError as exc:
        logger.warning("Could not list streams to name live hits: %s", exc)
        return {}
    return {
        str(item["stream_id"]): redact_url(str(item.get("stream_name") or item["stream_id"]))
        for item in streams
        if item.get("stream_id")
    }


def _hit_epoch(raw: dict[str, Any]) -> float:
    """When a hit happened, for ordering sightings: the wall-clock time of a
    live frame, else when its video was added (so a newly indexed video
    counts as new). ``0`` when unknown."""

    metadata = raw.get("metadata") or {}
    observed = observed_epoch(metadata)
    if observed is not None:
        return observed
    video = raw.get("video") or {}
    for value in (
        video.get("createdAt"),
        metadata.get("created_at"),
        (metadata.get("video_metadata") or {}).get("created_at"),
    ):
        parsed = parse_iso_epoch(value)
        if parsed is not None:
            return parsed
    return 0.0


async def _project_pairs(
    deps: Deps,
    raw_results: Any,
    videos: list[dict[str, Any]] | None = None,
    *,
    video_ids: set[str] | None = None,
) -> list[tuple[float, Hit]]:
    """Slim and name every hit, paired with its :func:`_hit_epoch`.

    ``video_ids`` keeps only hits from those videos or cameras.
    """

    pairs = []
    for item in unwrap_search_results(raw_results):
        hit = slim_search_hit(item, deps.settings.vss_datastore_url)
        if not hit.get("video_id"):
            continue
        if video_ids is not None and hit["video_id"] not in video_ids:
            continue
        pairs.append((_hit_epoch(item), hit))
    hits = [hit for _, hit in pairs]
    if any(not hit.get("video_name") and hit.get("source") != "live" for hit in hits):
        attach_video_names(
            [hit for hit in hits if hit.get("source") != "live"],
            await _video_names(deps, videos),
        )
    if any(not hit.get("video_name") and hit.get("source") == "live" for hit in hits):
        attach_video_names(
            [hit for hit in hits if hit.get("source") == "live"],
            await _stream_names(deps),
        )
    return pairs


async def _project_hits(
    deps: Deps,
    raw_results: Any,
    limit: int,
    videos: list[dict[str, Any]] | None = None,
    *,
    video_ids: set[str] | None = None,
) -> list[Hit]:
    """Slim, rank and name the hits of a search, best first."""

    hits = [
        hit
        for _, hit in await _project_pairs(
            deps, raw_results, videos, video_ids=video_ids
        )
    ]
    hits.sort(key=lambda hit: hit.get("score") or 0, reverse=True)
    return hits[: max(1, min(limit, MAX_LIMIT))]


def _status(stored: dict[str, Any]) -> dict[str, Any]:
    """The query id, status and any error of a persisted search."""

    result: dict[str, Any] = {"query_id": stored.get("queryId")}
    if stored.get("queryStatus"):
        result["status"] = stored["queryStatus"]
    if stored.get("errorMessage"):
        result["error"] = stored["errorMessage"]
    return result


def _time_range(time_filter: dict[str, Any] | None) -> dict[str, str] | None:
    if time_filter and time_filter.get("start") and time_filter.get("end"):
        return {"start": time_filter["start"], "end": time_filter["end"]}
    return None


def _summarize_search(stored: dict[str, Any]) -> SearchSummary:
    """Project a persisted search query without its hits or query image."""

    summary: dict[str, Any] = {
        "query_id": stored.get("queryId"),
        "query": stored.get("query") or None,
        "image_search": bool(stored.get("image")),
        "tags": stored.get("tags") or [],
        "status": stored.get("queryStatus"),
        "watch": bool(stored.get("watch")),
        "result_count": len(unwrap_search_results(stored.get("results") or [])),
        "created_at": stored.get("createdAt"),
        "updated_at": stored.get("updatedAt"),
        "last_refreshed": stored.get("lastRefreshedAt"),
        "error": stored.get("errorMessage"),
    }
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "") or key in {"status"}
    }


async def _stored_search_payload(
    deps: Deps, stored: dict[str, Any], limit: int
) -> StoredSearch:
    """Project a persisted search query and its hits, capped in size."""

    hits = await _project_hits(deps, stored.get("results") or [], limit)
    summary = _summarize_search(stored)
    payload: dict[str, Any] = {"count": len(hits), "results": hits}
    payload.update(_status(stored))
    for key in (
        "query",
        "image_search",
        "watch",
        "created_at",
        "updated_at",
        "last_refreshed",
    ):
        if key in summary:
            payload[key] = summary[key]
    if stored.get("tags"):
        payload["tags"] = stored["tags"]
    time_range = _time_range(stored.get("timeFilter"))
    if time_range:
        payload["time_range"] = time_range
    payload = cap_payload(payload, "results")
    payload["count"] = len(payload["results"])
    return payload


def _id_filter(ids: list[str] | None) -> set[str] | None:
    """The set of video/stream ids to keep, or ``None`` to keep every hit."""

    if ids is None:
        return None
    wanted = {str(value).strip() for value in ids if str(value).strip()}
    return wanted or None


async def _stream_tag_counts(deps: Deps) -> dict[str, int]:
    """Tags carried by live cameras, which label their embeddings like a
    video's tags do; empty when there are none or they cannot be listed."""

    if not deps.features.live_streams:
        return {}
    try:
        streams = await deps.client.list_streams()
    except VssError as exc:
        logger.warning("Could not list streams for their tags: %s", exc)
        return {}
    counts: dict[str, int] = {}
    for stream in streams:
        for tag in stream.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                counts[tag] = counts.get(tag, 0) + 1
    return counts


async def _require_search(deps: Deps, query_id: str) -> dict[str, Any]:
    """Return the persisted search ``query_id``, or raise a usable error."""

    query_id = (query_id or "").strip()
    stored = await deps.client.get_search(query_id) if query_id else None
    if not stored:
        raise VssError(
            f"No search query with id {query_id!r}. Use vss_list_searches to "
            "find the right id."
        )
    return stored


def _poll_interval(deps: Deps) -> float:
    return min(deps.settings.poll_interval_seconds, SEARCH_POLL_INTERVAL_SECONDS)


def _wait_budget(deps: Deps, wait_seconds: float | None) -> float:
    if wait_seconds is not None and wait_seconds >= 0:
        return wait_seconds
    return min(DEFAULT_SEARCH_WAIT_SECONDS, deps.settings.default_wait_seconds)


def _raise_if_failed(stored: dict[str, Any]) -> None:
    if stored.get("queryStatus") == "error":
        raise VssError(
            f"Search {stored.get('queryId')} failed: "
            f"{stored.get('errorMessage') or 'VSS reported an error.'}"
        )


async def search_video(
    deps: Deps,
    query: str | None = None,
    *,
    image: str | None = None,
    tags: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
    wait_seconds: float | None = None,
    stream_ids: list[str] | None = None,
) -> SearchResult:
    """Search indexed videos for moments matching a description or an image.

    The search is created as a persisted VSS query (``POST /search``), the
    same as one run from the UI, so it appears in the search history and can
    be re-run or watched later. Its results are polled until ready or until
    the wait budget expires, in which case ``status`` is ``running`` and the
    hits can be fetched later by ``query_id``.

    ``image`` is a data URL (forwarded unchanged), a reference to an image
    uploaded with ``POST /search/images`` (its URL, path or id; forwarded as
    ``imageUrl`` so Pipeline Manager loads it from the object store), or a
    local path (read from disk). Tag words are matched to existing tags --
    of videos, and of live cameras where they exist -- before searching,
    because VSS answers an unknown tag with an empty result rather than an
    error. ``stream_ids`` keeps only hits from those cameras (or videos);
    it filters the ranked results, so a narrow camera set can come back
    with fewer hits than ``limit``.

    Raises:
        VssError: If neither or both of ``query``/``image`` are given, the
            image is unusable, the time range is invalid, or the search
            failed.
    """

    query = (query or "").strip() or None
    image = (image or "").strip() or None
    if query and image:
        raise VssError("Provide either a query or an image, not both.")
    if not query and not image:
        raise VssError(
            "Provide a query describing what to look for, or an image to search by."
        )

    image_url = image if image and is_image_reference(image) else None
    image_data_url = (
        resolve_image_input(image) if image and not image_url else None
    )
    time_filter = build_time_filter(start, end)

    videos = await deps.client.list_videos() if tags else None
    counts = tag_counts(videos or [])
    if tags:
        for tag, cameras in (await _stream_tag_counts(deps)).items():
            counts[tag] = counts.get(tag, 0) + cameras
    matched, unmatched = match_tags(tags or [], counts)
    wanted = _id_filter(stream_ids)
    if unmatched and not matched:
        # Searching without the filter would answer a broader question than
        # the one asked, so nothing is searched.
        return {
            "count": 0,
            "results": [],
            "unknown_tags": unmatched,
            "available_tags": list(counts)[:MAX_AVAILABLE_TAGS],
            "truncated": False,
            "omitted": 0,
        }

    created = await deps.client.create_search(
        query,
        image=image_data_url,
        image_url=image_url,
        tags=matched or None,
        time_filter=time_filter,
    )
    stored, _ = await deps.client.poll_search(
        created["queryId"],
        wait_seconds=_wait_budget(deps, wait_seconds),
        poll_interval_seconds=_poll_interval(deps),
    )
    stored = stored or created
    _raise_if_failed(stored)

    hits = await _project_hits(
        deps, stored.get("results") or [], limit, videos, video_ids=wanted
    )

    # `count` is set before capping so the budget accounts for it; it can only
    # shrink afterwards.
    payload: dict[str, Any] = {"count": len(hits), "results": hits}
    payload.update(_status(stored))
    if matched:
        payload["tags"] = matched
    if unmatched:
        payload["unknown_tags"] = unmatched
    if wanted is not None:
        payload["stream_ids"] = sorted(wanted)
    time_range = _time_range(time_filter)
    if time_range:
        payload["time_range"] = time_range
    payload = cap_payload(payload, "results")
    payload["count"] = len(payload["results"])
    return payload


async def get_search(
    deps: Deps, query_id: str, *, limit: int = DEFAULT_LIMIT
) -> StoredSearch:
    """Return a persisted search query and its latest hits.

    Raises:
        VssError: If no query has that id.
    """

    return await _stored_search_payload(
        deps, await _require_search(deps, query_id), limit
    )


async def list_searches(
    deps: Deps, *, limit: int = DEFAULT_LIST_LIMIT, watched_only: bool = False
) -> SearchList:
    """Return persisted search queries, newest first, without their hits."""

    searches = [
        _summarize_search(stored) for stored in await deps.client.list_searches()
    ]
    searches = [
        item
        for item in searches
        if item.get("query_id") and (item.get("watch") or not watched_only)
    ]
    searches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    total = len(searches)
    payload: dict[str, Any] = {
        "total": total,
        "count": 0,
        "searches": searches[: max(1, min(limit, MAX_LIST_LIMIT))],
    }
    payload["count"] = len(payload["searches"])
    payload = cap_payload(payload, "searches")
    payload["count"] = len(payload["searches"])
    return payload


async def refetch_search(
    deps: Deps,
    query_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
    wait_seconds: float | None = None,
) -> StoredSearch:
    """Re-run a persisted search query, optionally over a new time range,
    and return its fresh hits.

    Raises:
        VssError: If no query has that id, the time range is invalid, or the
            search failed.
    """

    time_filter = build_time_filter(start, end)
    stored = await _require_search(deps, query_id)
    await deps.client.refetch_search(stored["queryId"], time_filter)
    refreshed, _ = await deps.client.poll_search(
        stored["queryId"],
        wait_seconds=_wait_budget(deps, wait_seconds),
        poll_interval_seconds=_poll_interval(deps),
    )
    refreshed = refreshed or stored
    _raise_if_failed(refreshed)
    return await _stored_search_payload(deps, refreshed, limit)


#: Cursor format: ``w1.<newest sighting, epoch ms>.<expiry, epoch ms or 0>``.
_CURSOR_RE = re.compile(r"^w1\.(\d{1,16})\.(\d{1,16})$")

#: Default and maximum sightings returned per watch call.
DEFAULT_SIGHTINGS = 10

#: Fallback for ``poll_after_seconds`` when the refresh config is unreadable;
#: Pipeline Manager's own default.
DEFAULT_REFRESH_SECONDS = 10.0

#: Longest rolling window and tracking duration accepted, in minutes.
MAX_WINDOW_MINUTES = 7 * 24 * 60
MAX_DURATION_MINUTES = 24 * 60


def encode_cursor(newest: float, expires: float | None) -> str:
    """Encode the tracker state the agent hands back on its next call."""

    return f"w1.{max(0, int(newest * 1000))}.{int((expires or 0) * 1000)}"


def decode_cursor(cursor: str) -> tuple[float, float | None]:
    """Return ``(newest sighting epoch, expiry epoch or None)``.

    Raises:
        VssError: If the cursor was not produced by this server.
    """

    match = _CURSOR_RE.match((cursor or "").strip())
    if not match:
        raise VssError(
            "cursor is not one this server issued. Pass next_cursor from the "
            "previous vss_watch_search result unchanged, or omit it to get "
            "every current sighting."
        )
    expires = int(match.group(2)) / 1000
    return int(match.group(1)) / 1000, expires or None


async def _refresh_interval(deps: Deps) -> tuple[bool, float]:
    """Whether VSS auto-refreshes watched searches, and how often (seconds)."""

    try:
        config = await deps.client.get_refresh_config()
    except VssError as exc:
        logger.warning("Could not read the watch refresh config: %s", exc)
        return True, DEFAULT_REFRESH_SECONDS
    interval = config.get("intervalMs")
    seconds = (
        interval / 1000
        if isinstance(interval, (int, float)) and not isinstance(interval, bool) and interval > 0
        else DEFAULT_REFRESH_SECONDS
    )
    return config.get("enabled", True) is not False, seconds


async def _seed_image_from_hit(deps: Deps, from_hit: dict[str, Any]) -> str:
    """Fetch a hit's peak frame (its detected crop when it has one) as a
    data URL to search by.

    Raises:
        VssError: If the locator is unusable or the frame cannot be read.
    """

    if not isinstance(from_hit, dict):
        raise VssError("from_hit must be a search hit's `frame` object.")
    meta, data = await get_media_frame(
        deps,
        str(from_hit.get("video_id") or ""),
        from_hit.get("timestamp"),  # type: ignore[arg-type]
        media_path=from_hit.get("media_path"),
        bucket_name=from_hit.get("bucket_name"),
        crop_bbox=from_hit.get("crop_bbox"),
        quality=90,
    )
    return f"data:{meta['mime']};base64,{data}"


async def _start_watch(
    deps: Deps,
    *,
    query: str | None,
    image: str | None,
    from_hit: dict[str, Any] | None,
    tags: list[str] | None,
    window_minutes: int | None,
) -> dict[str, Any]:
    """Create a persisted search for the target and wait for its first
    results. Returns the stored query (not yet watched)."""

    query = (query or "").strip() or None
    image = (image or "").strip() or None
    given = [name for name, value in (("query", query), ("image", image), ("from_hit", from_hit)) if value]
    if len(given) != 1:
        raise VssError(
            "To start watching, give exactly one of query, image or from_hit; "
            "to poll or stop an existing watch, give its query_id."
        )
    if (image or from_hit) and not deps.features.image_search_enabled:
        raise VssError(
            "This deployment cannot search by image (it has no frame-embedding "
            "index). Describe the target with query instead."
        )

    image_url = image if image and is_image_reference(image) else None
    image_data_url = resolve_image_input(image) if image and not image_url else None
    if from_hit:
        image_data_url = await _seed_image_from_hit(deps, from_hit)

    time_filter = None
    if window_minutes is not None:
        if (
            isinstance(window_minutes, bool)
            or not isinstance(window_minutes, int)
            or not 1 <= window_minutes <= MAX_WINDOW_MINUTES
        ):
            raise VssError(
                f"window_minutes must be a whole number from 1 to {MAX_WINDOW_MINUTES}."
            )
        time_filter = {"value": window_minutes, "unit": "minutes", "source": "relative"}

    created = await deps.client.create_search(
        query,
        image=image_data_url,
        image_url=image_url,
        tags=[tag.strip() for tag in tags if tag.strip()] if tags else None,
        time_filter=time_filter,
    )
    stored, _ = await deps.client.poll_search(
        created["queryId"],
        wait_seconds=_wait_budget(deps, None),
        poll_interval_seconds=_poll_interval(deps),
    )
    return stored or created


async def watch_search(
    deps: Deps,
    query_id: str | None = None,
    watch: bool = True,
    *,
    query: str | None = None,
    image: str | None = None,
    from_hit: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    stream_ids: list[str] | None = None,
    window_minutes: int | None = None,
    duration_minutes: float | None = None,
    cursor: str | None = None,
    min_raw_score: float | None = None,
    limit: int = DEFAULT_SIGHTINGS,
) -> WatchResult:
    """Start, poll or stop a watched search, reporting sightings as a tracker.

    The server keeps no state between calls: the newest sighting already
    reported and the expiry travel in ``cursor``. Pipeline Manager re-runs a
    watched search on its own cadence when new embeddings arrive, so polling
    only reads the stored results -- unless auto-refresh is disabled, when
    the poll re-runs the search itself.

    Raises:
        VssError: On invalid arguments, an unknown query id, or a backend
            failure while starting.
    """

    if duration_minutes is not None and (
        isinstance(duration_minutes, bool)
        or not isinstance(duration_minutes, (int, float))
        or not 0 < duration_minutes <= MAX_DURATION_MINUTES
    ):
        raise VssError(
            f"duration_minutes must be more than 0 and at most {MAX_DURATION_MINUTES}."
        )
    newest, expires = decode_cursor(cursor) if cursor else (0.0, None)
    now = time.time()
    if duration_minutes is not None:
        expires = now + duration_minutes * 60

    if query_id:
        if query or image or from_hit or window_minutes is not None:
            raise VssError(
                "query, image, from_hit and window_minutes only apply when "
                "starting a watch; omit query_id to start a new one."
            )
        stored = await _require_search(deps, query_id)
    elif not watch:
        raise VssError("query_id is required to stop watching.")
    else:
        stored = await _start_watch(
            deps,
            query=query,
            image=image,
            from_hit=from_hit,
            tags=tags,
            window_minutes=window_minutes,
        )
    qid = stored["queryId"]

    expired = bool(watch and expires is not None and now >= expires)
    want_watch = bool(watch) and not expired
    refresh_on, interval = await _refresh_interval(deps)
    if want_watch and not refresh_on and query_id and stored.get("queryStatus") != "running":
        # Nothing re-runs watched searches; do it on the agent's behalf.
        await deps.client.refetch_search(qid)
        stored = await deps.client.get_search(qid) or stored
    if bool(stored.get("watch")) != want_watch:
        await deps.client.set_search_watch(qid, want_watch)
        stored = {**stored, "watch": want_watch}

    wanted = _id_filter(stream_ids)
    pairs = await _project_pairs(deps, stored.get("results") or [], video_ids=wanted)
    if min_raw_score is not None:
        pairs = [
            (epoch, hit)
            for epoch, hit in pairs
            if hit.get("raw_score") is None or hit["raw_score"] >= min_raw_score
        ]

    last_seen: dict[str, tuple[float, dict[str, Any]]] = {}
    for epoch, hit in pairs:
        key = hit["video_id"]
        if key not in last_seen or epoch > last_seen[key][0]:
            last_seen[key] = (epoch, hit)
    seen = [
        {
            key: value
            for key, value in {
                "video_id": hit["video_id"],
                "name": hit.get("video_name"),
                "source": hit.get("source") or "video",
                "observed_at": hit.get("observed_at"),
                "raw_score": hit.get("raw_score"),
                "url": hit.get("url"),
            }.items()
            if value is not None
        }
        for _, hit in sorted(last_seen.values(), key=lambda item: item[0], reverse=True)
    ]

    fresh = sorted(
        ((epoch, hit) for epoch, hit in pairs if not cursor or epoch > newest),
        key=lambda item: item[0],
        reverse=True,
    )
    newest_now = max([newest] + [epoch for epoch, _ in fresh])
    fresh = fresh[: max(1, min(limit, MAX_LIMIT))]

    payload: dict[str, Any] = {
        "query_id": qid,
        "watch": want_watch,
        "status": stored.get("queryStatus"),
        "image_search": bool(stored.get("image")),
        "server_time_utc": iso_utc(now),
        "expired": expired,
        "new_count": len(fresh),
        "sightings": [hit for _, hit in fresh],
        "last_seen": seen,
        "next_cursor": encode_cursor(newest_now, expires) if want_watch else None,
        "poll_after_seconds": interval,
    }
    logger.info(
        "watch %s %s: watch=%s expired=%s new=%d cameras_seen=%d",
        qid,
        "start" if not query_id else ("poll" if watch else "stop"),
        want_watch,
        expired,
        len(fresh),
        len(seen),
    )
    if stored.get("query"):
        payload["query"] = stored["query"]
    selection = stored.get("timeFilter") or {}
    if isinstance(selection, dict) and selection.get("unit") == "minutes" and isinstance(
        selection.get("value"), int
    ):
        payload["window_minutes"] = selection["value"]
    if wanted is not None:
        payload["stream_ids"] = sorted(wanted)
    if stored.get("lastRefreshedAt"):
        payload["last_refreshed"] = stored["lastRefreshedAt"]
    if expires is not None:
        payload["expires_at"] = iso_utc(expires)
        if want_watch:
            payload["remaining_seconds"] = max(0, int(expires - now))
    if stored.get("errorMessage"):
        payload["error"] = stored["errorMessage"]
    elif want_watch and not refresh_on:
        payload["error"] = (
            "VSS auto-refresh is disabled on this deployment; each poll "
            "re-runs the search instead."
        )
    payload = cap_payload(payload, "sightings")
    payload["new_count"] = len(payload["sightings"])
    return payload


async def get_media_frame(
    deps: Deps,
    video_id: str,
    timestamp: float,
    *,
    media_path: str | None = None,
    bucket_name: str | None = None,
    crop_bbox: str | None = None,
    quality: int = DEFAULT_FRAME_QUALITY,
) -> tuple[MediaFrame, str]:
    """Fetch one stored frame; returns its metadata and base64 JPEG data.

    A ``crop_bbox`` returns just that region; without one, the whole frame.

    Raises:
        VssError: If an argument is invalid, or VSS cannot produce the frame.
    """

    video_id = (video_id or "").strip()
    if not video_id:
        raise VssError(
            "video_id is required: pass the `frame.video_id` of a search hit."
        )
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or timestamp < 0
    ):
        raise VssError(
            f"timestamp must be a non-negative number of seconds, got {timestamp!r}."
        )
    if isinstance(quality, bool) or not isinstance(quality, int) or not 1 <= quality <= 100:
        raise VssError(f"quality must be a whole number from 1 to 100, got {quality!r}.")
    crop_bbox = (crop_bbox or "").replace(" ", "") or None
    if crop_bbox and not _CROP_BBOX_RE.match(crop_bbox):
        raise VssError(
            f"crop_bbox must be four whole numbers 'x1,y1,x2,y2', got {crop_bbox!r}."
        )

    params: dict[str, Any] = {
        "video_id": video_id,
        "timestamp": timestamp,
        "quality": quality,
        "variant": "crop" if crop_bbox else "full",
    }
    if crop_bbox:
        params["crop_bbox"] = crop_bbox
    media_path = (media_path or "").strip() or None
    bucket_name = (bucket_name or "").strip() or None
    if media_path and not bucket_name:
        # Only live-camera hits carry a media_path. Without their bucket the
        # backend looks in the uploads bucket and returns 404.
        bucket_name = await _live_stream_bucket(deps, video_id)
    if media_path:
        params["media_path"] = media_path
    if bucket_name:
        params["bucket_name"] = bucket_name

    payload = await deps.client.get_frame(params)
    frame = payload.get("frame") or {}
    meta: dict[str, Any] = {
        "video_id": frame.get("video_id") or video_id,
        "requested_timestamp": frame.get("requested_timestamp", timestamp),
        "actual_timestamp": frame.get("actual_timestamp"),
        "media_path": frame.get("media_path"),
        "variant": frame.get("variant") or params["variant"],
        "cropped": bool(frame.get("cropped")),
        "width": frame.get("width") or 0,
        "height": frame.get("height") or 0,
        "mime": payload.get("mime") or "image/jpeg",
    }
    return meta, payload["image_base64"]


async def _live_stream_bucket(deps: Deps, stream_id: str) -> str:
    """Bucket holding a live camera's segments: the camera's own, or the
    default when the camera has been removed or cannot be looked up."""

    try:
        stream = await deps.client.get_stream(stream_id)
    except VssError as exc:
        logger.debug("Stream lookup for %s failed: %s", stream_id, exc)
        stream = None
    bucket = (stream or {}).get("bucket_name")
    return bucket if isinstance(bucket, str) and bucket.strip() else DEFAULT_LIVE_STREAM_BUCKET


def _is_absolute_http(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not any(char.isspace() or ord(char) < 32 for char in url)
    )


def clip_links(hits: list[Hit]) -> list[ResourceLink]:
    """One MCP ``resource_link`` per distinct absolute clip URL, in hit order.

    Relative URLs (no datastore base configured) are not valid resource URIs
    and stay in ``structuredContent`` only.
    """

    links: dict[str, ResourceLink] = {}
    for hit in hits:
        url = hit.get("url")
        if not url or url in links or not _is_absolute_http(url):
            continue
        links[url] = ResourceLink(
            type="resource_link",
            uri=url,
            name=hit.get("video_name") or hit["video_id"],
            mimeType="video/mp4",
        )
    return list(links.values())


def search_tool_result(payload: SearchResult) -> ToolResult:
    """Serialise ``payload`` for MCP: the JSON as text, mirroring
    ``structuredContent`` for clients without output schemas, then the clip
    links."""

    text = TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))
    return ToolResult(
        content=[text, *clip_links(payload["results"])],
        structured_content=payload,
    )


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the search tools on ``mcp``, if this deployment can search."""

    if not deps.features.search:
        return

    @mcp.tool(annotations=STARTS_WORK, output_schema=SEARCH_RESULT_SCHEMA)
    async def vss_search_video(
        query: str | None = None,
        image: str | None = None,
        tags: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        wait_seconds: float | None = None,
        stream_ids: list[str] | None = None,
    ) -> ToolResult:
        """Find moments across all indexed videos and live cameras matching
        a description or an image.

        The search is saved in VSS's search history, like one run from the
        VSS UI, and its query_id can be passed to vss_get_search,
        vss_refetch_search and vss_watch_search.

        Args:
            query: What to look for, e.g. "a man in green pants". Provide
                exactly one of query or image.
            image: What to search by instead of text. Preferred: the
                image URI returned by VSS's POST /search/images upload
                (its imageUrl, imagePath, or imageId), e.g.
                http://<vss-host>:12345/datastore/video-summary/search-images/<id>.jpg
                -- VSS loads the bytes from its object store, so nothing
                large passes through this call. Otherwise a
                data:<mime-type>;base64,<data> URL, e.g.
                data:image/jpeg;base64,/9j/4AAQ.... If you (the agent) have
                the image's raw bytes -- from an attachment, a downloaded
                file, or a frame you extracted -- base64-encode them
                yourself and send the resulting data URL directly; it is
                forwarded to the backend unchanged, with no filesystem
                access required. A path to a local image file readable by
                this server (e.g. a still frame already on its disk) is
                also accepted, but a data URL is the reliable choice when
                you hold the image yourself. Only supported in deployments
                with frame-embedding search enabled.
            tags: Only search videos and cameras carrying these tags.
            start: Range start, ISO-8601 UTC. Requires end.
            end: Range end, ISO-8601 UTC. Requires start.
            limit: Maximum results to return.
            wait_seconds: How long to wait for results before returning
                the query_id with status "running".
            stream_ids: Only keep hits from these cameras (or video ids).
                Applied to the ranked results, so it can return fewer than
                limit; tag the cameras to narrow the search itself.

        Results are best first; each hit's url plays its video, with
        start_s/end_s bounding the moment and seek_s where to start; a
        hit's frame, when present, locates its best-matching frame for
        vss_get_media_frame. A live-camera hit has source "live", its
        stream_id, and observed_at (when it happened, UTC). Each
        clip is also returned as a resource_link. status "running" means
        the results were not ready in time: call vss_get_search with
        query_id later. unknown_tags lists tag words matching no existing
        tag; if no tag matched, nothing was searched and available_tags
        lists the real ones.
        """

        payload = await search_video(
            deps,
            query,
            image=image,
            tags=tags,
            start=start,
            end=end,
            limit=limit,
            wait_seconds=wait_seconds,
            stream_ids=stream_ids,
        )
        return search_tool_result(payload)

    @mcp.tool(annotations=READ_ONLY, output_schema=STORED_SEARCH_SCHEMA)
    async def vss_get_search(query_id: str, limit: int = DEFAULT_LIMIT) -> ToolResult:
        """Return a saved search and its latest results.

        Use it to collect results of a vss_search_video call that returned
        status "running", or to reopen a search from vss_list_searches.

        Args:
            query_id: The saved search's query_id.
            limit: Maximum results to return.
        """

        return search_tool_result(await get_search(deps, query_id, limit=limit))

    @mcp.tool(annotations=READ_ONLY)
    async def vss_list_searches(
        limit: int = DEFAULT_LIST_LIMIT, watched_only: bool = False
    ) -> SearchList:
        """List saved searches (VSS search history), newest first, without
        their hits. Use vss_get_search for a search's results.

        Args:
            limit: Maximum searches to return.
            watched_only: Only searches being watched (tracked), e.g. to
                find a watch to poll or stop.
        """

        return await list_searches(deps, limit=limit, watched_only=watched_only)

    @mcp.tool(annotations=IDEMPOTENT_WORK, output_schema=STORED_SEARCH_SCHEMA)
    async def vss_refetch_search(
        query_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        wait_seconds: float | None = None,
    ) -> ToolResult:
        """Re-run a saved search, e.g. after more videos were indexed, and
        return its fresh results. The saved results are replaced.

        Args:
            query_id: The saved search's query_id.
            start: New range start, ISO-8601 UTC. Requires end.
            end: New range end, ISO-8601 UTC. Requires start.
            limit: Maximum results to return.
            wait_seconds: How long to wait for results.
        """

        payload = await refetch_search(
            deps,
            query_id,
            start=start,
            end=end,
            limit=limit,
            wait_seconds=wait_seconds,
        )
        return search_tool_result(payload)

    @mcp.tool(annotations=STARTS_WORK)
    async def vss_watch_search(
        query_id: str | None = None,
        watch: bool = True,
        query: str | None = None,
        image: str | None = None,
        from_hit: FrameLocator | None = None,
        tags: list[str] | None = None,
        stream_ids: list[str] | None = None,
        window_minutes: int | None = None,
        duration_minutes: float | None = None,
        cursor: str | None = None,
        min_raw_score: float | None = None,
        limit: int = DEFAULT_SIGHTINGS,
    ) -> WatchResult:
        """Track an object (person, vehicle, bag, ...) live: watch a search and poll it for new
        sightings. VSS re-runs a watched search by itself (about every
        poll_after_seconds) whenever new video or camera footage is indexed.

        Start: give exactly one of query (a visual description), image, or
        from_hit (a hit's `frame` object -- searches by that hit's detected
        crop, i.e. for that same-looking person/object). Usually also
        window_minutes (e.g. 5) so each refresh ranks only recent footage,
        and duration_minutes when the user gave a time limit ("for 10
        minutes"). Or give query_id to start watching an existing search.

        Poll: call again with query_id and the previous next_cursor, waiting
        poll_after_seconds between calls. sightings are only the hits new
        since that cursor, newest first; last_seen is the latest sighting
        per camera/video. Keep polling while watch is true.

        Stop: watch=false with query_id, or automatically on the first poll
        after duration_minutes (expired=true). The search stays in history.

        Similarity is not identity: verify a sighting with
        vss_get_media_frame before telling the user it is the same object.

        Args:
            query_id: An existing search to watch, poll or stop.
            watch: false to stop watching.
            query: What to track, e.g. "man in a red jacket" (start only).
            image: Image to track, as for vss_search_video (start only).
            from_hit: A search hit's frame object, unchanged (start only).
            tags: Only footage carrying these tags (start only).
            stream_ids: Only report sightings from these cameras.
            window_minutes: Rolling window of recent footage each refresh
                searches, in minutes (start only).
            duration_minutes: Stop watching after this many minutes.
            cursor: next_cursor from the previous call.
            min_raw_score: Drop sightings whose raw_score is below this.
            limit: Maximum sightings per call.
        """

        return await watch_search(
            deps,
            query_id,
            watch,
            query=query,
            image=image,
            from_hit=dict(from_hit) if from_hit else None,
            tags=tags,
            stream_ids=stream_ids,
            window_minutes=window_minutes,
            duration_minutes=duration_minutes,
            cursor=cursor,
            min_raw_score=min_raw_score,
            limit=limit,
        )

    @mcp.tool(annotations=READ_ONLY, output_schema=MEDIA_FRAME_SCHEMA)
    async def vss_get_media_frame(
        video_id: str,
        timestamp: float,
        media_path: str | None = None,
        bucket_name: str | None = None,
        crop_bbox: str | None = None,
        quality: int = DEFAULT_FRAME_QUALITY,
    ) -> ToolResult:
        """Return the image of one stored video frame, e.g. the exact frame
        a search hit matched, to look at or verify it.

        Copy the fields of a search hit's `frame` object unchanged. Omit
        crop_bbox to get the whole frame instead of the detected object.

        Args:
            video_id: frame.video_id of the hit (a video or live stream id).
            timestamp: frame.timestamp of the hit, in seconds. Not seek_s.
            media_path: frame.media_path; required for live-stream hits.
            bucket_name: frame.bucket_name, when present. Worked out from
                the camera for live-stream hits if omitted.
            crop_bbox: frame.crop_bbox, "x1,y1,x2,y2", to return only that
                region.
            quality: JPEG quality, 1-100.
        """

        meta, image_base64 = await get_media_frame(
            deps,
            video_id,
            timestamp,
            media_path=media_path,
            bucket_name=bucket_name,
            crop_bbox=crop_bbox,
            quality=quality,
        )
        return ToolResult(
            content=[
                ImageContent(type="image", data=image_base64, mimeType=meta["mime"]),
                TextContent(type="text", text=json.dumps(meta, separators=(",", ":"))),
            ],
            structured_content=meta,
        )
