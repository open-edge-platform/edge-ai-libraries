# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared dependencies and helpers for the tool layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from mcp.types import ToolAnnotations

from ..clients import VssClient, VssError
from ..core import Settings
from ..features import ALL_FEATURES, Features

#: MCP tool hints. Clients use ``readOnlyHint`` to run a tool without asking
#: for confirmation; everything talks only to this VSS deployment, so no tool
#: is open-world. Only removing a camera is destructive, and even that keeps
#: the camera's recorded media and embeddings.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
STARTS_WORK = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, openWorldHint=False
)
IDEMPOTENT_WORK = STARTS_WORK.model_copy(update={"idempotentHint": True})
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


@dataclass(frozen=True, slots=True)
class Deps:
    """Objects every tool needs.

    ``features`` is resolved once at startup and decides which tools are
    registered. It defaults to everything on for callers constructing this by
    hand; the server always passes the detected set.
    """

    client: VssClient
    settings: Settings
    features: Features = ALL_FEATURES


#: Watch auto-refresh interval assumed when the config cannot be read;
#: Pipeline Manager's own default.
DEFAULT_REFRESH_SECONDS = 10.0


async def read_refresh_config(deps: Deps) -> tuple[bool, float] | None:
    """Whether VSS auto-refreshes watched searches, and how often (seconds).

    The one reading of ``GET /search/refresh-config``, whose ``intervalMs``
    Pipeline Manager clamps to 1 s - 1 h. ``None`` when the config cannot be
    read, leaving the caller to decide what an unknown setting means.
    """

    try:
        config = await deps.client.get_refresh_config()
    except VssError as exc:
        logging.getLogger(__name__).warning(
            "Could not read the watch refresh config: %s", exc
        )
        return None
    return config["enabled"], config["intervalMs"] / 1000


async def require_video(deps: Deps, video_id: str) -> dict[str, Any]:
    """Return the video row for ``video_id``, or raise a usable error."""

    video = await deps.client.get_video(video_id)
    if not video:
        raise VssError(
            f"No video with id {video_id}. Use vss_resolve_video or vss_list_videos to "
            "find the right id."
        )
    return video
