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
from typing import Annotated, Any, Literal
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
    observed_epoch,
    parse_iso,
    parse_iso_epoch,
    slim_search_hit,
    slim_video,
)
from ..schemas import (
    FrameLocator,
    Hit,
    MediaFrame,
    SearchList,
    SearchResult,
    SearchSummary,
    StoppedWatch,
    StoredSearch,
    WatchResult,
)
from ._deps import (
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
    raw_results: list[dict[str, Any]],
    videos: list[dict[str, Any]] | None = None,
    *,
    video_ids: set[str] | None = None,
) -> list[tuple[float, Hit]]:
    """Slim and name every hit, paired with its :func:`_hit_epoch`.

    ``video_ids`` keeps only hits from those videos or cameras.
    """

    pairs = []
    for item in raw_results:
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
    raw_results: list[dict[str, Any]],
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


#: Accepted values of the ``sort`` argument.
SORT_ORDERS = ("relevance", "newest", "oldest")


def check_sort(value: str | None) -> str:
    """Validate a ``sort`` argument; ``None`` means relevance.

    Raises:
        VssError: If it is not one of :data:`SORT_ORDERS`.
    """

    order = (value or "relevance").strip().lower()
    if order not in SORT_ORDERS:
        raise VssError(f"sort must be one of {', '.join(SORT_ORDERS)}.")
    return order


def sort_hits(hits: list[Hit], order: str) -> list[Hit]:
    """Reorder the already ranked ``hits`` by ``observed_at``.

    ``relevance`` keeps them as they are. The sort is stable and hits with
    no ``observed_at`` go last, so ties and undated hits stay best first.
    """

    if order == "relevance":
        return hits
    dated = [hit for hit in hits if parse_iso_epoch(hit.get("observed_at"))]
    undated = [hit for hit in hits if not parse_iso_epoch(hit.get("observed_at"))]
    dated.sort(
        key=lambda hit: parse_iso_epoch(hit["observed_at"]) or 0.0,
        reverse=order == "newest",
    )
    return dated + undated


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
        "result_count": len(stored.get("results") or []),
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
    deps: Deps, stored: dict[str, Any], limit: int, sort: str = "relevance"
) -> StoredSearch:
    """Project a persisted search query and its hits, capped in size."""

    hits = sort_hits(
        await _project_hits(deps, stored.get("results") or [], limit), sort
    )
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
    if sort != "relevance":
        payload["sort"] = sort
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
    from_hit: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
    wait_seconds: float | None = None,
    stream_ids: list[str] | None = None,
    min_peak_score: float | None = None,
    sort: str | None = None,
) -> SearchResult:
    """Back :func:`vss_search_video` (see its docstring for the contract).

    ``image`` is forwarded as ``imageUrl`` so Pipeline Manager loads it from
    its own object store; this server never handles the bytes. Tag words are
    matched to existing tags first because VSS answers an unknown tag with an
    empty result rather than an error.

    Raises:
        VssError: If not exactly one of ``query``/``image``/``from_hit`` is given,
            ``image`` is not a recognised reference, the time range is
            invalid, or the search failed.
    """

    query = (query or "").strip() or None
    image = (image or "").strip() or None
    given = [name for name, value in (("query", query), ("image", image), ("from_hit", from_hit)) if value]
    if len(given) > 1:
        raise VssError(
            f"Provide only one of query, image or from_hit, not {' and '.join(given)}."
        )
    if not given:
        raise VssError(
            "Provide a query describing what to look for, an image to search "
            "by, or from_hit to find more like an earlier hit."
        )
    if from_hit and not deps.features.image_search_enabled:
        raise VssError(
            "This deployment cannot search by image (it has no frame-embedding "
            "index). Describe the target with query instead."
        )

    image_url = _require_image_reference(image) if image else None
    image_data_url = await _seed_image_from_hit(deps, from_hit) if from_hit else None
    time_filter = build_time_filter(start, end)
    min_peak_score = check_min_peak_score(min_peak_score)
    sort = check_sort(sort)

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
        image=image_data_url,
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

    hits = sort_hits(
        await _project_hits(deps, stored.get("results") or [], limit, video_ids=wanted),
        sort,
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
    if sort != "relevance":
        payload["sort"] = sort
    return payload


async def get_search(
    deps: Deps,
    query_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
    sort: str | None = None,
) -> StoredSearch:
    """Return a persisted search query and its latest hits.

    Raises:
        VssError: If no query has that id or ``sort`` is invalid.
    """

    sort = check_sort(sort)
    return await _stored_search_payload(
        deps, await _require_search(deps, query_id), limit, sort
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
    sort: str | None = None,
) -> StoredSearch:
    """Re-run a persisted search query, optionally over a new time range
    or with a new minimum peak score, and return its fresh hits.

    Raises:
        VssError: If no query has that id, the time range, score or sort
            is invalid, or the search failed.
    """

    time_filter = build_time_filter(start, end)
    min_peak_score = check_min_peak_score(min_peak_score)
    sort = check_sort(sort)
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
    return await _stored_search_payload(deps, refreshed, limit, sort)


#: Cursor format: ``w2.<query id>.<newest sighting, epoch ms>.<expiry, epoch ms>``.
#: Query ids are ``[A-Za-z0-9_-]``, so they never contain the separator.
_CURSOR_RE = re.compile(r"^w2\.([A-Za-z0-9_-]{1,128})\.(\d{1,16})\.(\d{1,16})$")

#: Most sightings one watch call reports. A poll that waits for news rarely
#: sees more; the rest are still in last_seen and the search's results.
MAX_SIGHTINGS = 10

#: How long a watch poll waits for a new sighting by default, and at most.
#: Kept under common MCP client call timeouts.
DEFAULT_WATCH_WAIT_SECONDS = 30.0
MAX_WATCH_WAIT_SECONDS = 120.0

#: Upper bound on the delay between re-reads of a watched search's results.
WATCH_REREAD_SECONDS = 2.0

#: How long a watch runs by default, and at most, in minutes. A watch the
#: agent forgets to stop would otherwise keep VSS re-running it indefinitely.
DEFAULT_DURATION_MINUTES = 30.0
MAX_DURATION_MINUTES = 24 * 60

#: Rolling window a watch searches when its search has none: each refresh
#: then ranks recent footage, so new sightings are not crowded out by old ones.
DEFAULT_WINDOW_MINUTES = 5


def encode_cursor(query_id: str, newest: float, expires: float) -> str:
    """Encode the tracker state the agent hands back on its next call."""

    return f"w2.{query_id}.{max(0, int(newest * 1000))}.{int(expires * 1000)}"


def decode_cursor(cursor: str) -> tuple[str, float, float]:
    """Return ``(query id, newest sighting epoch, expiry epoch)``.

    Raises:
        VssError: If the cursor was not produced by this server.
    """

    match = _CURSOR_RE.match((cursor or "").strip())
    if not match:
        raise VssError(
            "cursor is not one this server issued. Pass next_cursor from the "
            "previous vss_watch_search result unchanged, or omit it to start "
            "over."
        )
    return match.group(1), int(match.group(2)) / 1000, int(match.group(3)) / 1000


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


def _rolling_window(stored: dict[str, Any]) -> tuple[int, str] | None:
    """The search's relative time window as ``(value, unit)``, if it has one."""

    selection = stored.get("timeFilter")
    if not isinstance(selection, dict):
        return None
    value, unit = selection.get("value"), selection.get("unit")
    if isinstance(value, int) and not isinstance(value, bool) and unit:
        return value, str(unit)
    return None


def _schedule_auto_stop(deps: Deps, query_id: str, expires: float) -> None:
    """Unwatch ``query_id`` at ``expires`` even if the agent never polls
    again. Replaces any timer already set for it.

    The timer lives in this process: a restart drops it, and the next poll
    (whose cursor carries the expiry) sets it again or stops the watch.
    """

    timers = deps.watch_timers
    previous = timers.pop(query_id, None)
    if previous is not None:
        previous.cancel()

    async def stop_at_expiry() -> None:
        await asyncio.sleep(max(0.0, expires - time.time()))
        try:
            await deps.client.set_search_watch(query_id, False)
            logger.info("watch %s expired; stopped watching", query_id)
        except VssError as exc:
            # Nobody is waiting on this call; the next poll retries the stop.
            logger.warning("watch %s expired but could not be stopped: %s", query_id, exc)
        finally:
            if timers.get(query_id) is task:
                del timers[query_id]

    task = asyncio.create_task(stop_at_expiry(), name=f"vss-watch-expiry-{query_id}")
    timers[query_id] = task


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
    newest: float | None,
) -> tuple[list[tuple[float, dict[str, Any]]], list[tuple[float, dict[str, Any]]]]:
    """Return ``(all, fresh)`` sightings in ``stored``; fresh ones are newer
    than ``newest`` (all of them when it is ``None``), newest first."""

    pairs = await _project_pairs(deps, stored.get("results") or [], video_ids=wanted)
    fresh = sorted(
        ((epoch, hit) for epoch, hit in pairs if newest is None or epoch > newest),
        key=lambda item: item[0],
        reverse=True,
    )
    return pairs, fresh


async def _ensure_watched(deps: Deps, stored: dict[str, Any]) -> dict[str, Any]:
    """Watch the search, first giving it a rolling window if it has none.
    A search already watched with a window is left as it is, so polling
    changes nothing. Returns the search as it is now."""

    qid = stored["queryId"]
    if _rolling_window(stored) is None:
        # Re-running saves the window as a relative selection, which VSS then
        # slides forward on every refresh.
        await deps.client.refetch_search(
            qid,
            time_filter={
                "value": DEFAULT_WINDOW_MINUTES,
                "unit": "minutes",
                "source": "relative",
            },
        )
        stored = await _require_search(deps, qid)
    if not stored.get("watch"):
        await deps.client.set_search_watch(qid, True)
        stored = {**stored, "watch": True}
    return stored


async def _wait_for_sightings(
    deps: Deps,
    stored: dict[str, Any],
    wanted: set[str] | None,
    since: float,
    budget: float,
    ctx: Context | None,
) -> tuple[dict[str, Any], list, list]:
    """Re-read the search, which VSS's auto-refresh updates, until a sighting
    newer than ``since`` arrives or ``budget`` seconds pass."""

    pairs, fresh = await _sightings(deps, stored, wanted, since)
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
        stored = await deps.client.get_search(stored["queryId"]) or stored
        pairs, fresh = await _sightings(deps, stored, wanted, since)
    return stored, pairs, fresh


async def watch_search(
    deps: Deps,
    query_id: str,
    *,
    cursor: str | None = None,
    duration_minutes: float = DEFAULT_DURATION_MINUTES,
    stream_ids: list[str] | None = None,
    wait_seconds: float = DEFAULT_WATCH_WAIT_SECONDS,
    ctx: Context | None = None,
) -> WatchResult:
    """Back :func:`vss_watch_search`, which validates the argument ranges
    (see its docstring for the contract).

    The newest reported sighting and the expiry travel in ``cursor``. A timer
    in this process also unwatches the search at the expiry, in case the
    agent stops calling.

    Raises:
        VssError: On an unknown query id, a cursor from another search, or a
            backend failure.
    """

    query_id = (query_id or "").strip()
    now = time.time()
    if cursor:
        cursor_qid, newest, expires = decode_cursor(cursor)
        if cursor_qid != query_id:
            raise VssError(
                f"cursor belongs to search {cursor_qid!r}, not {query_id!r}. "
                "Pass the next_cursor this search's last call returned, or "
                "omit cursor to start over."
            )
    else:
        # Only a call without a cursor sets the expiry, so an agent that
        # repeats duration_minutes on every poll does not keep extending it.
        newest, expires = 0.0, now + duration_minutes * 60

    if now >= expires:
        stopped = await stop_watch(deps, query_id)
        expired: WatchResult = {
            "query_id": stopped["query_id"],
            "watch": False,
            "remaining_seconds": 0,
            "sightings": [],
            "last_seen": [],
            "next_cursor": None,
        }
        if "query" in stopped:
            expired["query"] = stopped["query"]
        return expired

    stored = await _ensure_watched(deps, await _require_search(deps, query_id))
    qid = stored["queryId"]
    if not cursor or qid not in deps.watch_timers:
        _schedule_auto_stop(deps, qid, expires)

    # Unreadable: assume VSS's default, which is on.
    refresh = await read_refresh_config(deps)
    refresh_on = refresh[0] if refresh else True
    wanted = _id_filter(stream_ids)
    if cursor and refresh_on:
        budget = min(wait_seconds, deps.settings.default_wait_seconds, expires - now)
        stored, pairs, fresh = await _wait_for_sightings(
            deps, stored, wanted, newest, budget, ctx
        )
        now = time.time()
    else:
        # Without a cursor every hit is new; without auto-refresh nothing
        # new can arrive. Either way, waiting cannot help.
        pairs, fresh = await _sightings(deps, stored, wanted, newest if cursor else None)

    newest_now = max([newest] + [epoch for epoch, _ in fresh])
    payload: dict[str, Any] = {
        "query_id": qid,
        "watch": True,
        "remaining_seconds": max(0, int(expires - now)),
        "sightings": [hit for _, hit in fresh[:MAX_SIGHTINGS]],
        "last_seen": _last_seen(pairs),
        "next_cursor": encode_cursor(qid, newest_now, expires),
    }
    logger.info(
        "watch %s %s: new=%d cameras_seen=%d",
        qid,
        "poll" if cursor else "start",
        len(fresh),
        len(payload["last_seen"]),
    )
    if stored.get("query"):
        payload["query"] = stored["query"]
    window = _rolling_window(stored)
    if window and window[1] == "minutes":
        payload["window_minutes"] = window[0]
    if stored.get("minPeakScore"):
        payload["min_peak_score"] = stored["minPeakScore"]
    if stored.get("errorMessage"):
        payload["error"] = stored["errorMessage"]
    elif not refresh_on:
        payload["error"] = (
            "VSS auto-refresh is disabled on this deployment, so no new "
            "sightings will arrive; re-run the search with vss_get_search "
            "refresh=true instead."
        )
    return payload


async def stop_watch(deps: Deps, query_id: str) -> StoppedWatch:
    """Back :func:`vss_stop_watch`.

    Raises:
        VssError: On an unknown query id or a backend failure.
    """

    stored = await _require_search(deps, query_id)
    qid = stored["queryId"]
    timer = deps.watch_timers.pop(qid, None)
    if timer is not None:
        timer.cancel()
    was_watching = bool(stored.get("watch"))
    if was_watching:
        await deps.client.set_search_watch(qid, False)
    logger.info("watch %s stop: was_watching=%s", qid, was_watching)
    payload: dict[str, Any] = {
        "query_id": qid,
        "watch": False,
        "was_watching": was_watching,
    }
    if stored.get("query"):
        payload["query"] = stored["query"]
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
        # Only live-camera hits carry a media_path, always with its bucket.
        # Without it the backend looks in the uploads bucket and returns 404.
        raise VssError(
            "media_path needs bucket_name: pass both from the hit's `frame` "
            "object, unchanged."
        )
    if media_path:
        params["media_path"] = media_path
    if bucket_name:
        params["bucket_name"] = bucket_name

    try:
        payload = await deps.client.get_frame(params)
    except VssError as exc:
        if exc.status_code == 404 and not media_path:
            # A camera's video_id covers hundreds of segments, so with no
            # media_path the backend cannot find the frame and says only
            # "no video found".
            raise VssError(
                f"{exc} If this is a live-camera hit, pass `media_path` and "
                "`bucket_name` from the hit's `frame` object, unchanged: "
                "video_id and timestamp alone do not say which 10 s segment "
                "holds the frame.",
                status_code=404,
            ) from exc
        raise
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
        from_hit: FrameLocator | None = None,
        tags: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        wait_seconds: float | None = None,
        stream_ids: list[str] | None = None,
        min_peak_score: float | None = None,
        sort: Literal["relevance", "newest", "oldest"] = "relevance",
    ) -> ToolResult:
        """Find moments across all indexed videos and live cameras matching
        a description or an image.

        The search is saved in VSS's search history, like one run from the
        VSS UI, and its query_id can be passed to vss_get_search, or to
        vss_watch_search to keep watching for new sightings.

        Args:
            query: What to look for, e.g. "a man in green pants". Provide
                exactly one of query, image or from_hit.
            image: What to search by instead of text: the image URI
                returned by uploading the image directly to VSS first via
                ``POST /search/images`` on the Pipeline Manager gateway
                (its imageUrl, imagePath, or imageId), e.g.
                http://<vss-host>:12345/datastore/video-summary/search-images/<id>.jpg
                -- VSS loads the bytes from its object store, so no image
                data passes through this call. Only supported in
                deployments with frame-embedding search enabled.
            from_hit: An earlier hit's `frame` object, unchanged, to find
                more like it: searches by that hit's detected crop, i.e. for
                the same-looking person or object. Frame-embedding
                deployments only.
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
            sort: "relevance" (default) keeps the best hits first;
                "newest"/"oldest" reorders the returned hits by observed_at
                into a timeline. Only the top `limit` hits are reordered,
                so it does not find older or newer moments that ranked
                lower; hits without observed_at go last.

        Results are best first unless sorted; each hit's url plays its video, with
        start_s/end_s bounding the moment and seek_s where to start; a
        hit's frame, when present, locates its best-matching frame for
        vss_get_media_frame. A live-camera hit has source "live" and its
        stream_id. observed_at (UTC) dates a hit: time_source "live" is when
        the camera captured it, "upload" is the video's upload time plus the
        frame's offset, not when the footage was recorded. Group hits by
        stream_id/video_id to see them per camera or video. Each
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
            from_hit=dict(from_hit) if from_hit else None,
            tags=tags,
            start=start,
            end=end,
            limit=limit,
            wait_seconds=wait_seconds,
            stream_ids=stream_ids,
            min_peak_score=min_peak_score,
            sort=sort,
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
        sort: Literal["relevance", "newest", "oldest"] = "relevance",
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
            sort: "relevance" (default), or "newest"/"oldest" to reorder
                the returned hits by observed_at, as in vss_search_video.
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
                sort=sort,
            )
        else:
            payload = await get_search(deps, query_id, limit=limit, sort=sort)
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

    @mcp.tool(annotations=IDEMPOTENT_WORK)
    async def vss_watch_search(
        ctx: Context,
        query_id: str,
        cursor: str | None = None,
        # Nullable because some clients (MCP Inspector among them) send null
        # for an optional field left empty; null means the default.
        duration_minutes: Annotated[
            float | None, Field(gt=0, le=MAX_DURATION_MINUTES)
        ] = DEFAULT_DURATION_MINUTES,
        stream_ids: list[str] | None = None,
        wait_seconds: Annotated[
            float | None, Field(ge=0, le=MAX_WATCH_WAIT_SECONDS)
        ] = DEFAULT_WATCH_WAIT_SECONDS,
    ) -> WatchResult:
        """Watch a search live and get its new sightings: track a person,
        vehicle, bag, ... as it appears on cameras or in new videos.

        First run the search with vss_search_video (by query, image, or
        from_hit to follow one hit's object), or take a query_id from
        vss_list_searches -- a search started in the VSS UI works too. Then:

            vss_watch_search(query_id)                      # starts; returns next_cursor
            vss_watch_search(query_id, cursor=next_cursor)  # repeat while watch is true
            vss_stop_watch(query_id)                        # when the user says stop

        The first call (no cursor) watches the search and returns its
        current sightings at once. Each later call waits up to wait_seconds
        for a new sighting, so call again straight away; an empty result
        just means nothing new yet. sightings are only the hits new since
        the cursor, newest first; last_seen is the latest per camera/video.

        Each refresh searches the search's rolling window (window_minutes;
        5 if it had none). To change the window or min_peak_score, run a
        new search. The watch stops by itself after duration_minutes, even
        if you stop calling; the call after that returns watch=false. To
        keep going, call again without cursor.

        Similarity is not identity: verify a sighting with
        vss_get_media_frame before telling the user it is the same object.

        Args:
            query_id: The search to watch. Required.
            cursor: next_cursor from the previous call, unchanged. Omit on
                the first call.
            duration_minutes: How long to watch. Read only on a call
                without cursor.
            stream_ids: Only report sightings from these cameras.
            wait_seconds: How long a call with cursor waits for a new
                sighting; 0 returns at once.
        """

        return await watch_search(
            deps,
            query_id,
            cursor=cursor,
            duration_minutes=(
                DEFAULT_DURATION_MINUTES if duration_minutes is None else duration_minutes
            ),
            stream_ids=stream_ids,
            wait_seconds=(
                DEFAULT_WATCH_WAIT_SECONDS if wait_seconds is None else wait_seconds
            ),
            ctx=ctx,
        )

    @mcp.tool(annotations=IDEMPOTENT_WORK)
    async def vss_stop_watch(query_id: str) -> StoppedWatch:
        """Stop watching a search, e.g. when the user says stop tracking.

        VSS stops re-running it; the search and its results stay in history
        (vss_get_search). Stopping a search that is not watched is fine.
        A watch also stops by itself when its duration runs out.

        Args:
            query_id: The watched search. Required.
        """

        return await stop_watch(deps, query_id)

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
        same person or object before saying so.

        Uploaded video: video_id and timestamp are enough, and any
        timestamp works, e.g. to look at a moment from a summary timeline.

        Live camera: video_id and timestamp are NOT enough. A camera's
        video_id is its stream id and covers all of its recorded segments,
        so the frame is only found with the hit's media_path AND
        bucket_name as well. Leaving media_path out fails with "No video
        found" or returns a frame from a different segment. Only a search
        hit's `frame` object has these, so search first.

        Args:
            video_id: frame.video_id of the hit (a video id, or a live
                camera's stream id).
            timestamp: frame.timestamp of the hit, in seconds, copied
                unrounded. For a live hit this is the offset into the
                media_path segment, not a wall-clock time. Not seek_s or
                start_s, which address the clip, not the matched frame.
            media_path: frame.media_path; optional for uploaded videos,
                but required for live-camera hits (the 10 s segment
                holding the frame).
            bucket_name: frame.bucket_name; required with media_path, so
                required for live-camera hits.
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
