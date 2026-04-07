"""Bootstrap the VSS MCP server and assemble feature-gated registrations."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .feature_flags import (
    build_server_instructions,
    build_upload_api_guide,
    resolve_feature_flags,
)
from .lifecycle import build_lifespan
from .logging_config import configure_logging
from .prompts import register_prompts
from .registry import RegistryContext
from .resources import register_core_resources, register_summary_resources
from .tools_core import register_core_tools
from .tools_search import register_search_tools
from .tools_summary import register_summary_tools


settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)
feature_flags = resolve_feature_flags(settings, logger)
registry = RegistryContext(settings=settings)
upload_api_guide = build_upload_api_guide(settings, feature_flags)

mcp = FastMCP(
    name="vss_mcp",
    instructions=build_server_instructions(settings, feature_flags),
    host=settings.mcp_host,
    port=settings.mcp_port,
    streamable_http_path=settings.mcp_path,
    stateless_http=settings.stateless_http,
    log_level=settings.log_level,
    json_response=True,
    lifespan=build_lifespan(settings, logger),
)

register_core_resources(mcp, registry, upload_api_guide)
register_prompts(mcp, upload_api_guide)
register_core_tools(mcp, registry)

if feature_flags.summary_enabled:
    register_summary_resources(mcp, registry)
    register_summary_tools(mcp, registry)

if feature_flags.search_enabled:
    register_search_tools(mcp, registry)


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
