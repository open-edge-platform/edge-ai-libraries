# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Search tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, ResourceLink, TextContent
from pydantic import Field, TypeAdapter

from ..clients import VssError, is_image_reference
from ..projections import (
    redact_url,
    attach_video_names,
    cap_payload,
    is_number,
    iso_utc,
    observed_epoch,
    parse_iso,
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
from ._deps import (
    DEFAULT_REFRESH_SECONDS,
    IDEMPOTENT_WORK,
    READ_ONLY,
    STARTS_WORK,
    Deps,
    read_refresh_config,
)
from .discovery import match_tags

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

    moment = parse_iso(value)
    if moment is None:
        raise VssError(
            f"{name}={value!r} is not an ISO-8601 timestamp, e.g. "
            "2026-08-04T14:00:00Z."
        )
    return moment


def check_min_peak_score(value: float | None) -> float | None:
    """Return ``value`` if it is a valid minimum peak score (0-1), else raise.

    Raises:
        VssError: If ``value`` is outside [0, 1].
    """

    if value is None:
        return None
    if isinstance(value, bool) or not 0 <= value <= 1:
        raise VssError(
            f"min_peak_score={value!r} must be between 0 and 1 (0 turns the "
            "filter off)."
        )
    return float(value)


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
    if stored.get("minPeakScore"):
        payload["min_peak_score"] = stored["minPeakScore"]
    return payload


def _id_filter(ids: list[str] | None) -> set[str] | None:
    """The set of video/stream ids to keep, or ``None`` to keep every hit."""

    if ids is None:
        return None
    wanted = {str(value).strip() for value in ids if str(value).strip()}
    return wanted or None


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


def _require_image_reference(image: str) -> str:
    """Return ``image`` as an ``imageUrl`` reference, or raise.

    Images are uploaded directly to VSS now (``POST /search/images`` on the
    Pipeline Manager gateway), so this server only ever forwards a reference
    to that upload -- it never reads a local file or accepts inline image
    bytes from a caller.

    Raises:
        VssError: If ``image`` is not a recognised reference.
    """

    if is_image_reference(image):
        return image
    raise VssError(
        f"'{image}' is not a recognised image reference. Upload the image "
        "directly to VSS first (POST /search/images on the Pipeline Manager "
        "gateway, e.g. http://<vss-host>:12345/manager/search/images) and "
        "pass the returned imageUrl, imagePath or imageId as image instead."
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
    min_peak_score: float | None = None,
) -> SearchResult:
    """Back :func:`vss_search_video` (see its docstring for the contract).

    ``image`` is forwarded as ``imageUrl`` so Pipeline Manager loads it from
    its own object store; this server never handles the bytes. Tag words are
    matched to existing tags first because VSS answers an unknown tag with an
    empty result rather than an error.

    Raises:
        VssError: If neither or both of ``query``/``image`` are given,
            ``image`` is not a recognised reference, the time range is
            invalid, or the search failed.
    """

    query = (query or "").strip() or None
    image = (image or "").strip() or None
    if query and image:
        raise VssError("Provide either a query or an image, not both.")
    if not query and not image:
        raise VssError(
            "Provide a query describing what to look for, or an image to search by."
        )

    image_url = _require_image_reference(image) if image else None
    time_filter = build_time_filter(start, end)
    min_peak_score = check_min_peak_score(min_peak_score)

    existing = sorted(await deps.client.list_tags()) if tags else []
    matched, unmatched = match_tags(tags or [], existing)
    wanted = _id_filter(stream_ids)
    if unmatched and not matched:
        # Searching without the filter would answer a broader question than
        # the one asked, so nothing is searched.
        return {
            "count": 0,
            "results": [],
            "unknown_tags": unmatched,
            "available_tags": existing[:MAX_AVAILABLE_TAGS],
        }

    created = await deps.client.create_search(
        query,
        image_url=image_url,
        tags=matched or None,
        time_filter=time_filter,
        min_peak_score=min_peak_score,
    )
    stored, _ = await deps.client.poll_search(
        created["queryId"],
        wait_seconds=_wait_budget(deps, wait_seconds),
        poll_interval_seconds=_poll_interval(deps),
    )
    stored = stored or created
    _raise_if_failed(stored)

    hits = await _project_hits(
        deps, stored.get("results") or [], limit, video_ids=wanted
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
    if stored.get("minPeakScore"):
        payload["min_peak_score"] = stored["minPeakScore"]
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
    min_peak_score: float | None = None,
) -> StoredSearch:
    """Re-run a persisted search query, optionally over a new time range
    or with a new minimum peak score, and return its fresh hits.

    Raises:
        VssError: If no query has that id, the time range or score is
            invalid, or the search failed.
    """

    time_filter = build_time_filter(start, end)
    min_peak_score = check_min_peak_score(min_peak_score)
    stored = await _require_search(deps, query_id)
    await deps.client.refetch_search(
        stored["queryId"], time_filter, min_peak_score
    )
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

#: How long a watch poll waits for a new sighting by default, and at most.
#: Kept under common MCP client call timeouts.
DEFAULT_WATCH_WAIT_SECONDS = 30.0
MAX_WATCH_WAIT_SECONDS = 120.0

#: Upper bound on the delay between re-reads of a watched search's results.
WATCH_REREAD_SECONDS = 2.0

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

    image_url = _require_image_reference(image) if image else None
    image_data_url = None
    if from_hit:
        image_data_url = await _seed_image_from_hit(deps, from_hit)

    time_filter = None
    if window_minutes is not None:
        if (
            not is_number(window_minutes, integer=True)
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


def _last_seen(pairs: list[tuple[float, dict[str, Any]]]) -> list[dict[str, Any]]:
    """The latest sighting per camera/video, newest first."""

    latest: dict[str, tuple[float, dict[str, Any]]] = {}
    for epoch, hit in pairs:
        key = hit["video_id"]
        if key not in latest or epoch > latest[key][0]:
            latest[key] = (epoch, hit)
    return [
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
        for _, hit in sorted(latest.values(), key=lambda item: item[0], reverse=True)
    ]


async def _sightings(
    deps: Deps,
    stored: dict[str, Any],
    wanted: set[str] | None,
    min_raw_score: float | None,
    newest: float | None,
) -> tuple[list[tuple[float, dict[str, Any]]], list[tuple[float, dict[str, Any]]]]:
    """Return ``(all, fresh)`` sightings in ``stored``; fresh ones are newer
    than ``newest`` (all of them when it is ``None``), newest first."""

    pairs = await _project_pairs(deps, stored.get("results") or [], video_ids=wanted)
    if min_raw_score is not None:
        pairs = [
            (epoch, hit)
            for epoch, hit in pairs
            if hit.get("raw_score") is None or hit["raw_score"] >= min_raw_score
        ]
    fresh = sorted(
        ((epoch, hit) for epoch, hit in pairs if newest is None or epoch > newest),
        key=lambda item: item[0],
        reverse=True,
    )
    return pairs, fresh


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
    wait_seconds: float | None = None,
    ctx: Context | None = None,
) -> WatchResult:
    """Back :func:`vss_watch_search` (see its docstring for the contract).

    Stateless: the newest reported sighting and the expiry travel in
    ``cursor``. A poll with a cursor holds the call open, re-reading the
    stored results that Pipeline Manager's auto-refresh updates, until a new
    sighting arrives or the wait (capped by the expiry) runs out.

    Raises:
        VssError: On invalid arguments, an unknown query id, or a backend
            failure while starting.
    """

    if duration_minutes is not None and (
        not is_number(duration_minutes)
        or not 0 < duration_minutes <= MAX_DURATION_MINUTES
    ):
        raise VssError(
            f"duration_minutes must be more than 0 and at most {MAX_DURATION_MINUTES}."
        )
    if wait_seconds is not None and (
        not is_number(wait_seconds) or not 0 <= wait_seconds <= MAX_WATCH_WAIT_SECONDS
    ):
        raise VssError(
            f"wait_seconds must be from 0 to {MAX_WATCH_WAIT_SECONDS:g}."
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
    if bool(stored.get("watch")) != want_watch:
        await deps.client.set_search_watch(qid, want_watch)
        stored = {**stored, "watch": want_watch}
    # Unreadable: assume VSS's defaults.
    refresh_on, interval = await read_refresh_config(deps) or (
        True,
        DEFAULT_REFRESH_SECONDS,
    )

    budget = min(
        DEFAULT_WATCH_WAIT_SECONDS if wait_seconds is None else wait_seconds,
        deps.settings.default_wait_seconds,
    )
    if expires is not None:
        budget = min(budget, max(0.0, expires - now))
    # Waiting only helps a poll: without a cursor every hit is already new,
    # and without auto-refresh nothing new can arrive.
    can_wait = bool(want_watch and cursor and refresh_on and budget > 0)

    wanted = _id_filter(stream_ids)
    since = newest if cursor else None
    pairs, fresh = await _sightings(deps, stored, wanted, min_raw_score, since)
    if can_wait and not fresh:
        started = time.monotonic()
        reread = min(deps.settings.poll_interval_seconds, WATCH_REREAD_SECONDS)
        while not fresh and stored.get("queryStatus") != "error":
            remaining = budget - (time.monotonic() - started)
            if remaining <= 0:
                break
            if ctx:
                await ctx.report_progress(
                    round(budget - remaining, 1), budget, "Waiting for new sightings"
                )
            await asyncio.sleep(min(reread, remaining))
            stored = await deps.client.get_search(qid) or stored
            pairs, fresh = await _sightings(deps, stored, wanted, min_raw_score, since)
        now = time.time()

    seen = _last_seen(pairs)
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
        # The next poll waits by itself, so it can follow straight away.
        "poll_after_seconds": 0.0 if refresh_on and budget > 0 else interval,
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
            "VSS auto-refresh is disabled on this deployment, so no new "
            "sightings will arrive; re-run the search with vss_get_search "
            "refresh=true instead."
        )
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
    if not is_number(timestamp) or timestamp < 0:
        raise VssError(
            f"timestamp must be a non-negative number of seconds, got {timestamp!r}."
        )
    if not is_number(quality, integer=True) or not 1 <= quality <= 100:
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
        "url": f"{deps.settings.vss_base_url}/frames?"
        + urlencode({**params, "format": "image"}),
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
        min_peak_score: float | None = None,
    ) -> ToolResult:
        """Find moments across all indexed videos and live cameras matching
        a description or an image.

        The search is saved in VSS's search history, like one run from the
        VSS UI, and its query_id can be passed to vss_get_search and
        vss_watch_search.

        Args:
            query: What to look for, e.g. "a man in green pants". Provide
                exactly one of query or image.
            image: What to search by instead of text: the image URI
                returned by uploading the image directly to VSS first via
                ``POST /search/images`` on the Pipeline Manager gateway
                (its imageUrl, imagePath, or imageId), e.g.
                http://<vss-host>:12345/datastore/video-summary/search-images/<id>.jpg
                -- VSS loads the bytes from its object store, so no image
                data passes through this call. Only supported in
                deployments with frame-embedding search enabled.
            tags: Only search videos and cameras carrying these tags.
            start: Range start, ISO-8601 UTC. Requires end.
            end: Range end, ISO-8601 UTC. Requires start.
            limit: Maximum results to return.
            wait_seconds: How long to wait for results before returning
                the query_id with status "running".
            stream_ids: Only keep hits from these cameras (or video ids).
                Applied to the ranked results, so it can return fewer than
                limit; tag the cameras to narrow the search itself.
            min_peak_score: Drop weak matches: only frames whose similarity
                is at least this (0-1) are ranked, so every hit's best frame
                scores at or above it. 0 turns the filter off; omit to use
                the deployment default (off unless configured). The VSS UI
                starts the filter at 0.2, the score below which it labels a
                hit a weak match; lower it if a search returns nothing.

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
            min_peak_score=min_peak_score,
        )
        return search_tool_result(payload)

    @mcp.tool(annotations=IDEMPOTENT_WORK, output_schema=STORED_SEARCH_SCHEMA)
    async def vss_get_search(
        query_id: str,
        refresh: bool = False,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        wait_seconds: float | None = None,
        min_peak_score: float | None = None,
    ) -> ToolResult:
        """Return a saved search and its results, optionally re-running it
        first.

        Without refresh it only reads: use it to collect the results of a
        vss_search_video call that returned status "running", or to reopen
        a search from vss_list_searches. With refresh=true (implied by
        start/end) VSS re-runs the search, e.g. after more videos were
        indexed, and the saved results are replaced.

        Args:
            query_id: The saved search's query_id.
            refresh: Re-run the search before returning its results.
            start: New range start, ISO-8601 UTC, for the re-run. Requires
                end.
            end: New range end, ISO-8601 UTC, for the re-run. Requires
                start.
            limit: Maximum results to return.
            wait_seconds: How long to wait for re-run results.
            min_peak_score: New minimum peak score (0-1, 0 = off) for the
                re-run; implies refresh and is saved with the search.
        """

        if refresh or start or end or min_peak_score is not None:
            payload = await refetch_search(
                deps,
                query_id,
                start=start,
                end=end,
                limit=limit,
                wait_seconds=wait_seconds,
                min_peak_score=min_peak_score,
            )
        else:
            payload = await get_search(deps, query_id, limit=limit)
        return search_tool_result(payload)

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

    @mcp.tool(annotations=STARTS_WORK)
    async def vss_watch_search(
        ctx: Context,
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
        wait_seconds: float | None = None,
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

        Poll: call again with query_id and the previous next_cursor, after
        poll_after_seconds (0 when the call waits by itself). A poll holds
        until a new sighting arrives or wait_seconds pass, so an empty result
        just means nothing new yet. sightings are only the hits new since
        that cursor, newest first; last_seen is the latest sighting per
        camera/video. Keep polling while watch is true.

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
            wait_seconds: How long a poll waits for a new sighting (default
                30, at most 120; 0 returns at once).
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
            wait_seconds=wait_seconds,
            ctx=ctx,
        )

    @mcp.tool(
        title="Get a search hit's frame image",
        annotations=READ_ONLY,
        output_schema=MEDIA_FRAME_SCHEMA,
    )
    async def vss_get_media_frame(
        video_id: str,
        timestamp: Annotated[float, Field(ge=0)],
        media_path: str | None = None,
        bucket_name: str | None = None,
        crop_bbox: str | None = None,
        quality: Annotated[int, Field(ge=1, le=100)] = DEFAULT_FRAME_QUALITY,
    ) -> ToolResult:
        """Look at the exact frame a search hit matched, to check what it
        really shows before describing it to the user.

        Returns the frame as an image you can see directly (JPEG image
        content), plus metadata with its pixel size and a `url` that serves
        the same JPEG over HTTP. Give that url to the user when they want
        to see the frame; it is the only correct frame link, so never build
        one yourself.

        Pass the fields of a hit's `frame` object unchanged as the
        arguments. With crop_bbox you get just the detected object (the
        hit's `label`); drop crop_bbox to see the whole scene around it.
        Similarity is not identity: use this to confirm a sighting is the
        same person or object before saying so. For an uploaded video,
        any video_id and timestamp also works, e.g. to look at a moment
        from a summary timeline.

        Args:
            video_id: frame.video_id of the hit (a video id, or a live
                camera's stream id).
            timestamp: frame.timestamp of the hit, in seconds, copied
                unrounded. Not seek_s or start_s, which address the clip,
                not the matched frame.
            media_path: frame.media_path; present on, and required for,
                live-camera hits (the 10 s segment holding the frame).
            bucket_name: frame.bucket_name, when present. Worked out from
                the camera for live-camera hits if omitted.
            crop_bbox: frame.crop_bbox, "x1,y1,x2,y2" in pixels, to return
                only that region. Omit for the whole frame.
            quality: JPEG quality, 1-100. Lower it to save context when
                many frames are needed; the default is fine to read.
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
