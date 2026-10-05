# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Search tools."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from mcp.types import ResourceLink, TextContent
from pydantic import TypeAdapter

from ..clients import VssError, is_image_reference, resolve_image_input
from ..projections import (
    attach_video_names,
    cap_payload,
    slim_search_hit,
    slim_video,
    unwrap_search_results,
)
from ..schemas import Hit, SearchList, SearchResult, SearchSummary, StoredSearch
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


async def _project_hits(
    deps: Deps,
    raw_results: Any,
    limit: int,
    videos: list[dict[str, Any]] | None = None,
) -> list[Hit]:
    """Slim, rank and name the hits of a search, best first."""

    hits = [
        hit
        for hit in (
            slim_search_hit(item, deps.settings.vss_datastore_url)
            for item in unwrap_search_results(raw_results)
        )
        if hit.get("video_id")
    ]
    hits.sort(key=lambda hit: hit.get("score") or 0, reverse=True)
    hits = hits[: max(1, min(limit, MAX_LIMIT))]
    if any(not hit.get("video_name") for hit in hits):
        attach_video_names(hits, await _video_names(deps, videos))
    return hits


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
    for key in ("query", "image_search", "watch", "created_at", "updated_at"):
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
    local path (read from disk). Tag words are matched to existing tags
    before searching, because VSS answers an unknown tag with an empty result rather than an error.

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
    matched, unmatched = match_tags(tags or [], counts)
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

    hits = await _project_hits(deps, stored.get("results") or [], limit, videos)

    # `count` is set before capping so the budget accounts for it; it can only
    # shrink afterwards.
    payload: dict[str, Any] = {"count": len(hits), "results": hits}
    payload.update(_status(stored))
    if matched:
        payload["tags"] = matched
    if unmatched:
        payload["unknown_tags"] = unmatched
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


async def list_searches(deps: Deps, *, limit: int = DEFAULT_LIST_LIMIT) -> SearchList:
    """Return persisted search queries, newest first, without their hits."""

    searches = [
        _summarize_search(stored) for stored in await deps.client.list_searches()
    ]
    searches = [item for item in searches if item.get("query_id")]
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


async def watch_search(deps: Deps, query_id: str, watch: bool) -> SearchSummary:
    """Watch or unwatch a persisted search query.

    Raises:
        VssError: If no query has that id.
    """

    stored = await _require_search(deps, query_id)
    await deps.client.set_search_watch(stored["queryId"], bool(watch))
    stored = await deps.client.get_search(stored["queryId"]) or {
        **stored,
        "watch": bool(watch),
    }
    return _summarize_search(stored)


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
    ) -> ToolResult:
        """Find moments across all indexed videos matching a description or an image.

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
            tags: Only search videos carrying these tags.
            start: Range start, ISO-8601 UTC. Requires end.
            end: Range end, ISO-8601 UTC. Requires start.
            limit: Maximum results to return.
            wait_seconds: How long to wait for results before returning
                the query_id with status "running".

        Results are best first; each hit's url plays its video, with
        start_s/end_s bounding the moment and seek_s where to start. Each
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
    async def vss_list_searches(limit: int = DEFAULT_LIST_LIMIT) -> SearchList:
        """List saved searches (VSS search history), newest first, without
        their hits. Use vss_get_search for a search's results.

        Args:
            limit: Maximum searches to return.
        """

        return await list_searches(deps, limit=limit)

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

    @mcp.tool(annotations=IDEMPOTENT_WORK)
    async def vss_watch_search(query_id: str, watch: bool = True) -> SearchSummary:
        """Watch or unwatch a saved search. VSS re-runs watched searches
        automatically whenever new videos are indexed, and notifies the VSS
        UI of new matches.

        Args:
            query_id: The saved search's query_id.
            watch: true to watch, false to stop watching.
        """

        return await watch_search(deps, query_id, watch)
