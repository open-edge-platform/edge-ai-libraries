# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Discovery tools: what this deployment can do, and what is in the library."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from fastmcp import FastMCP

from ..projections import cap_payload, slim_video
from ..schemas import DeploymentInfo, Resolution, TagList, VideoList
from ._deps import READ_ONLY, Deps

#: Candidates returned by :func:`resolve_videos`. A model asked to choose
#: between more than a handful is being asked to guess.
RESOLVE_CANDIDATES = 5

_TOKEN = re.compile(r"[a-z0-9]+")


async def get_deployment_info(deps: Deps) -> DeploymentInfo:
    """Report enabled features, library size, indexing counts and how to upload.

    Uploading is not an MCP tool (see :mod:`.ingest`), so this is how an agent
    learns where to POST a file instead. Indexing counts are omitted entirely
    when search is off (summary-only deployments), since there is no search
    index to report on.
    """

    videos = await deps.client.list_videos()
    info: DeploymentInfo = {
        "summary_enabled": deps.features.summary,
        "search_enabled": deps.features.search,
        "videos_total": len(videos),
        "server_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "upload": {
            "url": f"{deps.settings.vss_base_url}/videos",
            "method": "POST",
            "content_type": "multipart/form-data",
            "file_field": "video",
            "tags_field": "tags",
        },
    }
    if deps.features.search:
        statuses = [
            slim_video(video)["indexed"] for video in videos
        ]
        info["videos_indexed"] = statuses.count(True)
        info["videos_index_unknown"] = statuses.count(None)
    return info


async def list_videos(
    deps: Deps, tag: str | None = None, limit: int = 50
) -> VideoList:
    """List videos newest first, optionally only those carrying ``tag``.

    Each entry's ``indexed`` is ``True``/``False`` as the backend reports it,
    or ``None`` when unknown. The field is absent entirely in summary-only
    deployments, which have no search index.
    """

    videos = [
        slim_video(video, include_indexed=deps.features.search)
        for video in await deps.client.list_videos()
    ]
    if tag:
        needle = tag.strip().lower()
        videos = [v for v in videos if needle in {t.lower() for t in v["tags"]}]

    videos.sort(key=lambda video: video.get("created_at") or "", reverse=True)
    return cap_payload(
        {"total": len(videos), "videos": videos[: max(1, limit)]}, "videos"
    )


def tag_counts(videos: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count how many videos carry each tag, most used first."""

    counts = Counter(
        tag for video in videos for tag in dict.fromkeys(video.get("tags") or [])
    )
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def match_tags(
    wanted: Iterable[str], existing: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Match requested tag words against the tags that actually exist.

    Operators say "Camera 2"; the tag might be "camera-2". Matching is
    case-insensitive, then punctuation-insensitive, then by containment -- in
    that order, so an exact tag is never beaten by a longer one containing it.

    Returns:
        ``(matched, unmatched)``: real tag values, and the words that matched
        nothing. Callers must report the second rather than silently dropping
        or keeping the filter.
    """

    existing = list(existing)

    def normalise(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    matched: list[str] = []
    unmatched: list[str] = []
    for word in wanted:
        needle = (word or "").strip()
        if not needle:
            continue
        found = (
            next((t for t in existing if t.lower() == needle.lower()), None)
            or next((t for t in existing if normalise(t) == normalise(needle)), None)
            or next((t for t in existing if normalise(needle) in normalise(t)), None)
        )
        if found is None:
            unmatched.append(needle)
        elif found not in matched:
            matched.append(found)
    return matched, unmatched


async def list_tags(deps: Deps) -> TagList:
    """Return the tags in use, most used first, with how many videos carry each.

    A tag filter must come from this vocabulary: VSS answers an unknown tag
    with an empty result rather than an error.
    """

    counts = tag_counts(await deps.client.list_videos())
    tags = [{"tag": tag, "videos": count} for tag, count in counts.items()]
    return cap_payload({"count": len(tags), "tags": tags}, "tags")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def resolve_videos(videos: list[dict[str, Any]], hint: str) -> list[dict[str, Any]]:
    """Find slim videos matching a free-text hint, best match first.

    Passes run in decreasing confidence -- exact id, exact filename, substring,
    then token overlap with name and tags -- and each result names its pass in
    ``match``.
    """

    needle = hint.strip().lower()
    if not needle:
        return videos[:RESOLVE_CANDIDATES]

    def name(video: dict[str, Any]) -> str:
        return (video.get("name") or "").lower()

    passes = (
        ("exact_id", lambda v: (v.get("video_id") or "").lower() == needle),
        ("exact_name", lambda v: name(v) == needle),
        ("substring", lambda v: needle in name(v)),
    )
    for kind, test in passes:
        found = [v for v in videos if test(v)]
        if found:
            return [{**v, "match": kind} for v in found[:RESOLVE_CANDIDATES]]

    needle_tokens = _tokens(needle)
    scored = sorted(
        (
            (len(needle_tokens & _tokens(f"{name(v)} {' '.join(v['tags'])}")), v)
            for v in videos
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [{**v, "match": "fuzzy"} for n, v in scored if n][:RESOLVE_CANDIDATES]


async def resolve_video(deps: Deps, hint: str) -> Resolution:
    """Find the video a user means from an id, filename or loose description."""

    videos = [
        slim_video(video, include_indexed=deps.features.search)
        for video in await deps.client.list_videos()
    ]
    candidates = resolve_videos(videos, hint)
    return cap_payload(
        {"unambiguous": len(candidates) == 1, "candidates": candidates},
        "candidates",
    )


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the discovery tools on ``mcp``."""

    @mcp.tool(annotations=READ_ONLY)
    async def vss_get_deployment_info() -> DeploymentInfo:
        """Report VSS capabilities, indexing counts, server time, and how to upload.

        Call this first when unsure whether search or summarization is
        available. videos_indexed and videos_index_unknown are present only
        when search is enabled; a summary-only deployment has no search
        index, so they are omitted rather than reported as zero/unknown.
        videos_index_unknown counts videos whose indexing status the backend
        does not report; they may or may not be searchable.
        Uploading is not a tool: have the user's own tooling POST the file to
        upload.url as multipart/form-data (file in upload.file_field, optional
        comma-separated tags in upload.tags_field), then call vss_index_video
        with the returned videoId.
        """

        return await get_deployment_info(deps)

    @mcp.tool(annotations=READ_ONLY)
    async def vss_list_videos(tag: str | None = None, limit: int = 50) -> VideoList:
        """List videos in the VSS library, newest first.

        indexed=true means searchable and indexed=false means not indexed.
        indexed=null means unknown, not unindexed; do not recommend indexing
        solely because it is null. The indexed field is absent entirely in a
        summary-only deployment, which has no search index to report on.
        total counts all matches; truncated is true when the list was cut to
        fit the response size budget.

        Args:
            tag: Only return videos carrying this tag.
            limit: Maximum number of videos to return.
        """

        return await list_videos(deps, tag=tag, limit=limit)

    @mcp.tool(annotations=READ_ONLY)
    async def vss_list_tags() -> TagList:
        """List the tags videos are labelled with, most used first.

        Use this before filtering a search by place or camera, so the filter
        uses a tag that exists. An unknown tag returns no results rather than
        an error.
        """

        return await list_tags(deps)

    @mcp.tool(annotations=READ_ONLY)
    async def vss_resolve_video(hint: str) -> Resolution:
        """Find which video a partial name or description refers to.

        Use this whenever the user names a video in words rather than by id,
        for example "the warehouse clip from Friday". Act directly only when
        unambiguous is true; with several candidates, ask the user which one
        they mean; with none, call vss_list_videos.

        Args:
            hint: A video id, a filename, or a loose description.
        """

        return await resolve_video(deps, hint)
