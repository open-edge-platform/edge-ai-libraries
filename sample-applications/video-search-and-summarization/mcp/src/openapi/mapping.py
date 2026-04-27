# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Translate filter rules into the callables expected by ``FastMCP.from_openapi``.

``FastMCP.from_openapi`` accepts three pluggable knobs that decide how each
HTTP route in the spec is surfaced over MCP:

* ``mcp_names``   — rename components from their OpenAPI ``operationId`` to a
  filter-controlled tool name (``<prefix>_<tool_name>``).
* ``route_map_fn`` — classify each route as ``TOOL``, ``RESOURCE``,
  ``RESOURCE_TEMPLATE`` or ``EXCLUDE``.
* ``mcp_component_fn`` — post-process the registered MCP component (today, to
  prepend a per-API description override).

This module builds those callables from a :class:`ProxyFilterConfig`.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastmcp.server.providers.openapi import MCPType
from fastmcp.utilities.openapi import HTTPRoute

from ..filters import (
    ProxyFilterConfig,
    api_config_for,
    configured_resource_name,
    configured_tool_name,
    resource_is_enabled,
    tool_is_enabled,
)

logger = logging.getLogger(__name__)

_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def build_mcp_names(
    spec: dict[str, Any], filter_config: ProxyFilterConfig
) -> dict[str, str]:
    """Map OpenAPI ``operationId`` values to filter-controlled MCP names.

    FastMCP defaults to ``operationId`` as the component name. Operations the
    filter exposes as tools are renamed to ``<prefix>_<tool_name>`` so the
    final names are deterministic and human-readable for MCP clients.

    Args:
        spec: The parsed OpenAPI / Swagger document.
        filter_config: Per-operation exposure rules.

    Returns:
        A ``{operationId: final_mcp_name}`` mapping. Operations without an
        ``operationId`` or without an explicit ``tool_name`` are omitted (they
        keep whatever default name FastMCP chooses).
    """

    mapping: dict[str, str] = {}
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            upper_method = method.upper()
            if upper_method not in _HTTP_METHODS:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                continue

            custom_name = configured_tool_name(filter_config, upper_method, path)
            if custom_name is None:
                custom_name = configured_resource_name(filter_config, upper_method, path)
            if custom_name is not None:
                mapping[operation_id] = custom_name

    logger.info("Renaming %d operationId(s) to filter-controlled names", len(mapping))
    if logger.isEnabledFor(logging.DEBUG):
        for source, target in mapping.items():
            logger.debug("  %s -> %s", source, target)
    return mapping


def build_route_map_fn(
    filter_config: ProxyFilterConfig,
) -> Callable[[HTTPRoute, MCPType], MCPType | None]:
    """Build the ``route_map_fn`` that classifies each spec route.

    For every route FastMCP discovers, the returned callable consults the JSON
    filter and decides whether to expose it as a tool, a resource, a resource
    template, or to exclude it altogether.

    Args:
        filter_config: Per-operation exposure rules from the JSON filter.

    Returns:
        A callable suitable for the ``route_map_fn`` parameter of
        :func:`FastMCP.from_openapi`.
    """

    counters: dict[str, int] = {"tool": 0, "resource": 0, "resource_template": 0, "excluded": 0}

    def route_map_fn(route: HTTPRoute, _default_type: MCPType) -> MCPType | None:
        method = route.method.upper()
        path = route.path
        api_cfg = api_config_for(filter_config, method, path)

        if api_cfg is None:
            counters["excluded"] += 1
            logger.debug("[exclude] %s %s — not listed in filter", method, path)
            return MCPType.EXCLUDE

        if api_cfg.expose == "disabled":
            counters["excluded"] += 1
            logger.debug("[exclude] %s %s — disabled in filter", method, path)
            return MCPType.EXCLUDE

        if tool_is_enabled(filter_config, method, path):
            counters["tool"] += 1
            logger.info("[tool]     %-6s %s", method, path)
            return MCPType.TOOL

        if resource_is_enabled(filter_config, method, path):
            if "{" in path:
                counters["resource_template"] += 1
                logger.info("[template] %-6s %s", method, path)
                return MCPType.RESOURCE_TEMPLATE
            counters["resource"] += 1
            logger.info("[resource] %-6s %s", method, path)
            return MCPType.RESOURCE

        counters["excluded"] += 1
        logger.debug("[exclude] %s %s — no exposure rule matched", method, path)
        return MCPType.EXCLUDE

    # Stash counters on the function for post-build summary logging.
    route_map_fn.counters = counters  # type: ignore[attr-defined]
    return route_map_fn


def build_component_fn(
    filter_config: ProxyFilterConfig,
) -> Callable[[HTTPRoute, Any], None]:
    """Build the ``mcp_component_fn`` that applies description overrides.

    When an entry in the JSON filter sets ``"description"``, that text is
    prepended to whatever description FastMCP generated from the spec, so the
    operator's wording leads the rendered tool/resource description.

    Args:
        filter_config: Per-operation exposure rules from the JSON filter.

    Returns:
        A callable suitable for the ``mcp_component_fn`` parameter of
        :func:`FastMCP.from_openapi`.
    """

    def component_fn(route: HTTPRoute, component: Any) -> None:
        api_cfg = api_config_for(filter_config, route.method.upper(), route.path)
        if api_cfg is None or not api_cfg.description:
            return

        existing = getattr(component, "description", None) or ""
        separator = "\n\n" if existing else ""
        component.description = f"{api_cfg.description}{separator}{existing}".strip()
        logger.debug(
            "Applied description override to %s %s", route.method.upper(), route.path
        )

    return component_fn
