# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FastMCP server factory."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from .clients import VssClient
from .core import Settings, configure_logging, get_settings
from . import context
from .features import Features, detect_features
from .tools import Deps, register_all

logger = logging.getLogger(__name__)

SERVER_NAME = "vss"

#: Opening line, always true.
_INSTRUCTIONS_HEADER = """\
Tools for the Intel Video Search and Summarization (VSS) system. Tool results
are JSON matching each tool's output schema.

When presenting a clip, give its `url` exactly as returned -- complete path,
query string and fragment, never abbreviated -- with its times as separate
text. Only use returned URLs; do not invent paths.
"""

#: What to do with each capability, and the mistakes each one invites. Only the
#: sections for the enabled features reach the client: instructions describing
#: a tool that is not registered cost context and invite calls that cannot be
#: made.
_INSTRUCTIONS_SUMMARY = """\
Summarization:
  * "What is in this video?" -> resolve_video, then summarize_video.
  * summarize_video returns chunk-level captions as a timeline. Ask for a
    single overall narrative only when the user wants one; it is much slower.
"""

_INSTRUCTIONS_SEARCH = """\
Search:
  * "Find X"                -> search_video, with a time window if one was implied.
  * "Find X in this video"  -> search_video library-wide, then keep only hits
    whose `video_id` matches the video in question. There is no dedicated
    single-video search endpoint.
  * "Add this file"         -> this server cannot upload video bytes. Call
    vss_get_deployment_info for its `upload` target, have the file
    POSTed there by the user's own tooling (outside this server), then call
    vss_index_video with the returned videoId.
  * A video is only findable by search once it has been indexed. list_videos
    reports `indexed` from each video's own status; null means unknown, not
    unindexed. Search normally; do not recommend re-indexing based on
    unknown status.
  * To restrict by time, work out the range yourself and pass start and end
    as ISO-8601 UTC timestamps. vss_get_deployment_info reports
    server_time_utc for resolving phrases like "the last 2 hours".
"""

#: Closing note when a capability is missing. A model that cannot find a search
#: tool otherwise assumes it is holding the wrong name and hunts for it.
_INSTRUCTIONS_LIMITS = """\
Enabled in this deployment: {enabled}. Tools for anything else are not
registered, not hidden -- do not look for them, and say plainly that the
deployment cannot do it when asked.
"""


def build_instructions(features: Features) -> str:
    """Assemble the instructions sent on connect, for enabled features only."""

    parts = [_INSTRUCTIONS_HEADER]
    if features.summary:
        parts.append(_INSTRUCTIONS_SUMMARY)
    if features.search:
        parts.append(_INSTRUCTIONS_SEARCH)
    if not (features.summary and features.search):
        parts.append(_INSTRUCTIONS_LIMITS.format(enabled=features.describe()))
    return "\n".join(parts)


def make_client(settings: Settings) -> VssClient:
    """Return the Pipeline Manager client described by ``settings``.

    The only place the server opens a real HTTP connection pool; tests and
    embedders inject their own client instead.
    """

    return VssClient(
        settings.vss_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def create_mcp(
    settings: Settings,
    features: Features,
    *,
    client: VssClient | None = None,
) -> FastMCP:
    """Build the VSS tool surface for ``features``.

    ``features`` is required because it cannot be guessed; :func:`build_mcp`
    resolves it from the deployment. ``client`` is built from ``settings``
    when omitted.
    """

    deps = Deps(
        client=client or make_client(settings), settings=settings, features=features
    )

    # VssError messages are written for the agent and pass through; anything
    # else is a bug whose details (paths, internal URLs) stay in the log.
    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=build_instructions(features),
        mask_error_details=True,
    )
    register_all(mcp, deps)
    context.register(mcp, deps)

    logger.info(
        "VSS MCP server built (backend=%s, features=[%s])",
        settings.vss_base_url,
        features.describe(),
    )
    return mcp


async def build_mcp(
    settings: Settings | None = None,
    *,
    client: VssClient | None = None,
) -> FastMCP:
    """Ask the deployment what it can do, then build the matching server.

    ``settings`` defaults to the environment and ``client`` to
    :func:`make_client`; pass both to build without a live deployment.

    Raises:
        ValueError: If the environment is missing or invalid.
        VssError: If the deployment cannot be reached. Fatal on purpose: the
            container's restart policy is the retry.
    """

    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    resolved_client = client or make_client(resolved)
    features = await detect_features(resolved_client)
    logger.info("Deployment features: [%s].", features.describe())
    return create_mcp(resolved, features, client=resolved_client)
