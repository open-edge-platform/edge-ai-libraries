# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resources and prompts: context a client can read without spending a turn.
"""

from __future__ import annotations

import json
import shlex
from datetime import datetime, timezone
from typing import Any, Awaitable, Iterable

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from .clients import VssError
from .tools import Deps
from .tools.discovery import get_deployment_info, list_tags, list_videos

#: Search phrasings that work against this retrieval stack, and the ones that
#: do not. Static because it describes the *system*, not the deployment: it is
#: as true of an empty library as a full one.
SEARCH_PATTERNS = {
    "works_well": [
        "Visible things: 'a person in a yellow hard hat', 'a forklift near a "
        "pallet'. Retrieval matches appearance.",
        "One idea per query. Two unrelated things score worse than either "
        "alone -- search twice instead.",
        "Time as arguments, never words in the query: start and end as "
        "ISO-8601 UTC timestamps you compute from server_time_utc.",
        "Place as a tag, never words in the query: tags=['Camera 2'].",
    ],
    "works_badly": [
        "Negation. 'a room with nobody in it' retrieves rooms with people; "
        "there is no NOT in embedding search.",
        "Counting. 'three people' cannot be distinguished from 'people'.",
        "Proper nouns and text on signs. Nothing here reads text.",
        "Anything not visible in a frame: intent, ownership, what happened "
        "before the clip starts.",
    ],
}


#: Appended to every live resource description: the body is a snapshot.
_SNAPSHOT_NOTE = (
    " This is a snapshot taken at read time (see as_of); call {tool} for the "
    "current state, and always after uploading or indexing."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _snapshot(
    coroutine: Awaitable[dict[str, Any]],
    refresh_with: str,
    drop: Iterable[str] = (),
) -> str:
    """Await a tool body and serialise it as a dated, compact JSON snapshot."""

    try:
        body = await coroutine
    except VssError as exc:
        raise ResourceError(str(exc)) from exc
    excluded = set(drop)
    snapshot = {"as_of": _utc_now(), "refresh_with": refresh_with}
    snapshot.update({k: v for k, v in body.items() if k not in excluded})
    return json.dumps(snapshot, separators=(",", ":"))


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the resources and prompts on ``mcp``."""

    # -- Resources -------------------------------------------------------

    @mcp.resource(
        "vss://deployment",
        name="Deployment",
        description=(
            "Which VSS features are on and how much of the library is indexed. "
            "Read this before assuming search or summarization is available. "
            "It omits server_time_utc: for time ranges, call "
            "vss_get_deployment_info when you need the clock."
            + _SNAPSHOT_NOTE.format(tool="vss_get_deployment_info")
        ),
        mime_type="application/json",
    )
    async def deployment() -> str:
        return await _snapshot(
            get_deployment_info(deps),
            "vss_get_deployment_info",
            drop=("server_time_utc",),
        )

    @mcp.resource(
        "vss://videos",
        name="Video library",
        description=(
            "The 50 newest videos, with their indexing status. indexed=null "
            "means unknown, not unindexed. Only indexed videos can be found "
            "by search."
            + _SNAPSHOT_NOTE.format(tool="vss_list_videos")
        ),
        mime_type="application/json",
    )
    async def videos() -> str:
        return await _snapshot(list_videos(deps), "vss_list_videos")

    @mcp.resource(
        "vss://tags",
        name="Tags in use",
        description=(
            "The tags videos are labelled with. A tag filter must come from "
            "this list: VSS answers an unknown tag with no results rather than "
            "an error, so an invented one reads as an empty place."
            + _SNAPSHOT_NOTE.format(tool="vss_list_tags")
        ),
        mime_type="application/json",
    )
    async def tags() -> str:
        return await _snapshot(list_tags(deps), "vss_list_tags")

    if deps.features.search:

        @mcp.resource(
            "vss://search-patterns",
            name="How to search this system",
            description=(
                "Query shapes that work against embedding retrieval, and the "
                "ones that quietly do not -- negation, counting, and text on "
                "signs."
            ),
            mime_type="application/json",
        )
        async def search_patterns() -> str:
            return json.dumps(SEARCH_PATTERNS, separators=(",", ":"))

    _register_prompts(mcp, deps)


def _numbered(steps: list[str]) -> list[str]:
    """Number the steps; lines starting with a space continue the one above."""

    lines, n = [], 0
    for step in steps:
        if step.startswith(" "):
            lines.append(step)
        else:
            n += 1
            lines.append(f"{n}. {step}")
    return lines


def _upload_steps(deps: Deps, tags: str) -> list[str]:
    """How to get a file into VSS; the MCP server itself cannot carry bytes."""

    url = f"{deps.settings.vss_base_url}/videos"
    tag_arg = f" -F {shlex.quote(f'tags={tags}')}" if tags else ""
    return [
        "Upload -- this is a plain HTTP call, not an MCP tool; this server "
        "cannot carry video bytes. Run it yourself if you have a shell, "
        "otherwise give the user the command:",
        f"     curl -s -X POST {url} -F 'video=@<path/to/file.mp4>'{tag_arg}",
        "   The file must be a streamable MP4 (a 422 says it is not; remux with "
        "`ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`). Tags are "
        "one comma-separated field. The response is {\"videoId\": \"...\"}; "
        "keep that id. If this URL is unreachable, vss_get_deployment_info "
        "reports the current upload target.",
    ]


def _register_prompts(mcp: FastMCP, deps: Deps) -> None:
    """Register the workflow prompts this deployment can actually carry out.

    Each prompt is a numbered script naming only tools that are registered for
    the same features, so a summary-only deployment is never told to search.
    """

    if deps.features.search:
        _register_search_prompts(mcp, deps)
    if deps.features.summary:
        _register_summary_prompts(mcp, deps)


def _register_search_prompts(mcp: FastMCP, deps: Deps) -> None:
    @mcp.prompt(
        name="search_videos",
        description=(
            "Search the video library by description, with the camera and "
            "time window passed as filters rather than query words."
        ),
    )
    def search_videos(looking_for: str, where: str = "", when: str = "") -> str:
        """Search for something, putting each constraint where it belongs.

        Args:
            looking_for: What to find, described as it would look.
            where: A camera or place, if the user named one.
            when: A time window in plain words, e.g. "the last 2 hours".
        """

        steps = []
        if where:
            steps.append(
                f"Place: the user said {where!r}. Call vss_list_tags and pick "
                "the matching tag for `tags`. If none matches, tell the user "
                "and list the real tags instead of searching without it."
            )
        if when:
            steps.append(
                f"Time: the user said {when!r}. Call vss_get_deployment_info, "
                "read server_time_utc, and compute `start` and `end` as "
                "ISO-8601 UTC. Both are required together."
            )
        steps += [
            "Search: call vss_search_video with `query` set to a short visual "
            "description of the thing itself -- no place, time, counts or "
            "negation. To search by a picture, pass `image` instead of `query`.",
            "Report: give each hit's `url` exactly as returned, with start_s and "
            "end_s as separate text. Similarity is not proof; say what a clip "
            "shows only if you have checked it. If nothing is found, say so and "
            "suggest a rephrasing -- and remember only indexed videos can match "
            "(vss_list_videos shows `indexed`).",
        ]
        return "\n".join([f"Find moments matching: {looking_for}", ""] + _numbered(steps))

    @mcp.prompt(
        name="upload_and_index_videos",
        description=(
            "Upload video files to VSS over its HTTP API, then index each one "
            "with vss_index_video so it can be searched."
        ),
    )
    def upload_and_index_videos(files: str = "", tags: str = "") -> str:
        """Make new footage searchable.

        Args:
            files: The video files to add, if known.
            tags: Comma-separated tags to label them with, e.g. a camera name.
        """

        target = f"Make these videos searchable: {files}" if files else (
            "Make the user's new videos searchable."
        )
        steps = _upload_steps(deps, tags) + [
            "Index: call vss_index_video with each returned videoId, one call "
            "per video. It waits up to its wait budget; indexed=true means the "
            "video is searchable now, indexed=false means indexing continues "
            "in the background -- check later with vss_list_videos.",
            "Report each video separately: its videoId, and whether it is "
            "searchable yet. Do not call the batch done while any is still "
            "running. In vss_list_videos, indexed=null means unknown, not "
            "failed; do not re-index because of it.",
        ]
        return "\n".join([target, ""] + _numbered(steps))


def _register_summary_prompts(mcp: FastMCP, deps: Deps) -> None:
    @mcp.prompt(
        name="summarize_video",
        description=(
            "Summarize one video as a captioned timeline and an overall "
            "summary, uploading it first if it is not in the library yet."
        ),
    )
    def summarize_video(video: str, focus: str = "", overall: str = "") -> str:
        """Summarize a video, from finding it to reporting the timeline.

        Args:
            video: The video's name, id, or a description of it.
            focus: What the summary should pay attention to, if anything.
            overall: Set to "no" if the user wants only the timeline, without
                the overall prose summary VSS produces by default.
        """

        timeline_only = overall.strip().lower() in {"no", "false", "0", "n"}
        steps = [
            f"Find the video: call vss_resolve_video with hint {video!r}. If it "
            "returns several candidates, ask the user which one. If it returns "
            "none, the video has to be uploaded first:",
        ]
        steps += ["  " + line for line in _upload_steps(deps, "")]
        summarize = (
            "Summarize: call vss_summarize_video with the video_id"
            + (f" and focus={focus!r}" if focus else "")
            + (
                " and final_summary=false, because the user wants only the "
                "timeline (this is faster)."
                if timeline_only
                else ". Keep the default final_summary=true, which also "
                "produces one overall summary, as VSS does."
            )
        )
        steps += [
            summarize,
            "If completed=false the wait budget ran out, not the job. Show the "
            "captions so far, then call vss_get_video_timeline with the "
            "returned state_id to fetch the rest.",
            "Report the overall summary, if any, then the timeline as times "
            "and what happens, in order. Do not add events the captions do "
            "not mention.",
        ]
        return "\n".join([f"Summarize the video: {video}", ""] + _numbered(steps))
