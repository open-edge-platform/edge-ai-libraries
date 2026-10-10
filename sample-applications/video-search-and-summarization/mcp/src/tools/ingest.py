# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Ingest tools: making an uploaded video searchable."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from ..features import Features
from ..projections import indexed_status
from ..schemas import IndexResult
from ._deps import IDEMPOTENT_WORK, Deps, require_video, run_summary


def choose_index_strategy(features: Features, strategy: str = "auto") -> str:
    """Decide how a video is made searchable in this deployment.

    When a frame-embedding index is deployed (``image_search_enabled``, true
    in dual and search-only mode), the standalone embedding endpoint is the
    fast, independent path and is preferred. Otherwise (unified mode, where
    the frame-embedding endpoint targets the wrong model) summarizing indexes
    as a side effect: each chunk caption is embedded with its time bounds.
    ``Settings.index_strategy`` may force ``summary`` or ``embeddings``.
    """

    if strategy in {"summary", "embeddings"}:
        return strategy
    if features.image_search_enabled:
        return "embeddings"
    return "summary" if features.summary else "embeddings"


async def index_video(
    deps: Deps,
    video_id: str,
    wait_seconds: float | None = None,
    ctx: Context | None = None,
) -> IndexResult:
    """Make a video findable by search, by whichever path this deployment needs.

    Raises:
        VssError: If the video does not exist.
    """

    video = await require_video(deps, video_id)
    result: IndexResult = {
        "video_id": video_id,
        "indexed": True,
        "strategy": None,
        "state_id": None,
    }
    if indexed_status(video):
        return result

    result["strategy"] = choose_index_strategy(
        deps.features, deps.settings.index_strategy
    )
    if result["strategy"] == "embeddings":
        await deps.client.create_search_embeddings(video_id)
        return result

    # Indexing needs only the chunk captions; skip the slower final summary
    # and audio transcription.
    result["state_id"], _, result["indexed"] = await run_summary(
        deps,
        video,
        final_summary=False,
        audio=False,
        wait_seconds=wait_seconds,
        ctx=ctx,
    )
    return result


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the ingest tools on ``mcp`` where search is on.

    Indexing means "make findable by search", which is meaningless where
    search is off.
    """

    if not deps.features.search:
        return

    @mcp.tool(annotations=IDEMPOTENT_WORK)
    async def vss_index_video(
        ctx: Context, video_id: str, wait_seconds: float | None = None
    ) -> IndexResult:
        """Make a video searchable. Run this after uploading.

        To index several videos, call this once per video. strategy is null
        when the video was already indexed. indexed=false means indexing is
        still running in the background; read the video's indexed flag from
        vss_list_videos later.

        Args:
            video_id: Video to index.
            wait_seconds: How long to wait before returning a progress
                handle.
        """

        return await index_video(
            deps, video_id, wait_seconds=wait_seconds, ctx=ctx
        )
