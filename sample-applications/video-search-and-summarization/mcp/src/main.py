"""Bootstrap the spec-driven MCP REST proxy server using ``FastMCP.from_openapi``.

The heavy lifting — OpenAPI parsing, ``$ref`` resolution, flattening JSON request
bodies into top-level tool parameters, and translating HTTP responses back to
MCP content — is delegated to the third-party :mod:`fastmcp` package. This module
only glues configuration, filter rules, and the HTTP client together.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType
from fastmcp.utilities.openapi import HTTPRoute

from .core import Settings, configure_logging, get_settings
from .filters import (
    ProxyFilterConfig,
    api_config_for,
    configured_tool_name,
    load_filter_config,
    resource_is_enabled,
    tool_is_enabled,
)

logger = logging.getLogger(__name__)


def _fetch_openapi_spec(spec_url: str, timeout: float) -> dict[str, Any]:
    """Fetch and decode the OpenAPI/Swagger document referenced by the settings."""

    response = httpx.get(spec_url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _resolve_target_base_url(
    spec: dict[str, Any], settings: Settings
) -> str:
    """Pick the backend base URL from settings or fall back to the spec."""

    if settings.target_base_url:
        return settings.target_base_url.rstrip("/")

    # OpenAPI 3: first non-empty servers[].url
    servers = spec.get("servers") if isinstance(spec.get("servers"), list) else []
    for server in servers:
        if isinstance(server, dict):
            candidate = str(server.get("url", "")).strip()
            if candidate:
                resolved = urljoin(settings.spec_url, candidate) if settings.spec_url else candidate
                return resolved.rstrip("/")

    # Swagger 2: host + basePath + first scheme
    host = str(spec.get("host", "")).strip()
    if host:
        schemes = spec.get("schemes") if isinstance(spec.get("schemes"), list) else []
        scheme = str(schemes[0]).strip() if schemes else "https"
        base_path = str(spec.get("basePath", "")).strip()
        return f"{scheme}://{host}{base_path}".rstrip("/")

    raise ValueError(
        "API_BASE_URL must be set when the spec does not declare a usable server URL."
    )


def _build_mcp_names(
    spec: dict[str, Any], filter_config: ProxyFilterConfig
) -> dict[str, str]:
    """Return an ``{operationId: final_mcp_name}`` map for renaming tools/resources.

    FastMCP uses each route's ``operationId`` as the default component name. We override
    those so tool names respect the filter config's ``tool_prefix`` + ``tool_name``.
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
            if upper_method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                continue

            custom_name = configured_tool_name(filter_config, upper_method, path)
            if custom_name is not None:
                mapping[operation_id] = custom_name
    return mapping


def _build_route_map_fn(filter_config: ProxyFilterConfig):
    """Return a ``route_map_fn`` that consults the JSON filter for each route."""

    def route_map_fn(route: HTTPRoute, _default_type: MCPType) -> MCPType | None:
        method = route.method.upper()
        path = route.path

        api_cfg = api_config_for(filter_config, method, path)
        if api_cfg is None:
            # Not listed in the filter file — hide it.
            return MCPType.EXCLUDE

        if api_cfg.expose == "disabled":
            return MCPType.EXCLUDE

        if tool_is_enabled(filter_config, method, path):
            return MCPType.TOOL

        if resource_is_enabled(filter_config, method, path):
            # If the path has templated segments, expose as a resource template.
            if "{" in path:
                return MCPType.RESOURCE_TEMPLATE
            return MCPType.RESOURCE

        return MCPType.EXCLUDE

    return route_map_fn


def _build_component_fn(filter_config: ProxyFilterConfig):
    """Return a ``mcp_component_fn`` that applies per-API description overrides."""

    def component_fn(route: HTTPRoute, component) -> None:
        api_cfg = api_config_for(filter_config, route.method.upper(), route.path)
        if api_cfg is None or not api_cfg.description:
            return
        # Prepend the override so it leads the tool/resource description.
        existing = getattr(component, "description", None) or ""
        separator = "\n\n" if existing else ""
        component.description = f"{api_cfg.description}{separator}{existing}".strip()

    return component_fn


def create_mcp(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server from the configured spec and JSON filter."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    filter_config = load_filter_config(resolved_settings.filter_config_path)

    logger.info("Loading OpenAPI spec from %s", resolved_settings.spec_url)
    spec = _fetch_openapi_spec(
        resolved_settings.spec_url, resolved_settings.request_timeout_seconds
    )

    target_base_url = _resolve_target_base_url(spec, resolved_settings)
    logger.info("Proxying REST calls to %s", target_base_url)

    client = httpx.AsyncClient(
        base_url=target_base_url,
        timeout=resolved_settings.request_timeout_seconds,
    )

    mcp_names = _build_mcp_names(spec, filter_config)
    route_map_fn = _build_route_map_fn(filter_config)
    component_fn = _build_component_fn(filter_config)

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name=filter_config.server_name,
        mcp_names=mcp_names,
        route_map_fn=route_map_fn,
        mcp_component_fn=component_fn,
    )


mcp: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Return the lazily initialized FastMCP server."""

    global mcp
    if mcp is None:
        mcp = create_mcp()
    return mcp


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""

    settings = get_settings()
    server = get_mcp()
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
        stateless_http=settings.stateless_http,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
