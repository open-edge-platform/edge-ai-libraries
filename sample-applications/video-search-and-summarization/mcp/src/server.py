# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FastMCP server factory."""

from __future__ import annotations

import logging

import httpx
from fastmcp import FastMCP

from .core import Settings, configure_logging, get_settings
from .filters import load_filter_config
from .openapi import (
    build_component_fn,
    build_mcp_names,
    build_route_map_fn,
    fetch_openapi_spec,
)

logger = logging.getLogger(__name__)


def create_mcp(settings: Settings | None = None) -> FastMCP:
    """Build a :class:`FastMCP` server from the configured spec and JSON filter.

    The factory performs four steps in order:

    1. Resolve runtime settings and configure logging.
    2. Load and validate the JSON filter file.
    3. Download the live OpenAPI spec and decide on a backend base URL.
    4. Hand the spec, an :class:`httpx.AsyncClient`, and the filter-derived
       hooks to :func:`FastMCP.from_openapi`.

    Args:
        settings: Optional pre-built :class:`Settings`. When ``None`` (the
            default), settings are read from the environment via
            :func:`get_settings`.

    Returns:
        A fully wired :class:`FastMCP` instance ready for ``run()``.

    Raises:
        ValueError: If required environment variables or filter rules are
            missing or malformed, or if the spec cannot be fetched.
    """

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    logger.info("Loading filter configuration from %s", resolved_settings.filter_config_path)
    filter_config = load_filter_config(resolved_settings.filter_config_path)
    logger.info(
        "Filter loaded: server_name=%s, prefix=%s, declared_apis=%d",
        filter_config.server_name,
        filter_config.prefix,
        len(filter_config.apis),
    )

    spec = fetch_openapi_spec(
        resolved_settings.spec_url, resolved_settings.request_timeout_seconds
    )

    client = httpx.AsyncClient(
        base_url=resolved_settings.api_base_url,
        timeout=resolved_settings.request_timeout_seconds,
    )
    logger.info(
        "HTTP client configured (base_url=%s, timeout=%.1fs)",
        resolved_settings.api_base_url,
        resolved_settings.request_timeout_seconds,
    )

    mcp_names = build_mcp_names(spec, filter_config)
    route_map_fn = build_route_map_fn(filter_config)
    component_fn = build_component_fn(filter_config)

    mcp = FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name=filter_config.server_name,
        mcp_names=mcp_names,
        route_map_fn=route_map_fn,
        mcp_component_fn=component_fn,
    )

    counters = getattr(route_map_fn, "counters", {})
    logger.info(
        "MCP server '%s' assembled: %d tool(s), %d resource(s), %d resource template(s), %d excluded route(s)",
        filter_config.server_name,
        counters.get("tool", 0),
        counters.get("resource", 0),
        counters.get("resource_template", 0),
        counters.get("excluded", 0),
    )
    return mcp


_mcp_singleton: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Return the lazily initialised MCP server, creating it on first call.

    Returns:
        The process-wide :class:`FastMCP` instance.
    """

    global _mcp_singleton
    if _mcp_singleton is None:
        _mcp_singleton = create_mcp()
    return _mcp_singleton
