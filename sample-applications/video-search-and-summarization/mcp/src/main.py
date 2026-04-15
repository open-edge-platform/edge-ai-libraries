"""Bootstrap the spec-driven MCP REST proxy server."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .client import ProxyApiClient
from .config import get_settings
from .filters import load_filter_config
from .lifecycle import build_lifespan
from .logging_config import configure_logging
from .openapi import load_api_catalog
from .registry import RegistryContext
from .registry import build_server_instructions, register_resources, register_tools


def create_mcp(settings=None) -> FastMCP:
    """Build the FastMCP server from the configured spec and JSON filter."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    catalog = load_api_catalog(resolved_settings)
    filter_config = load_filter_config(resolved_settings.filter_config_path)
    shared_client = ProxyApiClient(resolved_settings, base_url=catalog.base_url)
    registry = RegistryContext(
        settings=resolved_settings,
        catalog=catalog,
        filter_config=filter_config,
        shared_client=shared_client,
    )
    operations = registry.enabled_operations()

    mcp_server = FastMCP(
        name=filter_config.server_name,
        instructions=build_server_instructions(registry, operations),
        host=resolved_settings.mcp_host,
        port=resolved_settings.mcp_port,
        streamable_http_path=resolved_settings.mcp_path,
        stateless_http=resolved_settings.stateless_http,
        log_level=resolved_settings.log_level,
        json_response=True,
        lifespan=build_lifespan(
            resolved_settings,
            catalog,
            filter_config,
            shared_client,
            logging.getLogger(__name__),
        ),
    )
    register_resources(mcp_server, registry, operations)
    register_tools(mcp_server, registry, operations)
    return mcp_server


mcp: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Return the lazily initialized FastMCP server."""

    global mcp
    if mcp is None:
        mcp = create_mcp()
    return mcp


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""

    get_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
