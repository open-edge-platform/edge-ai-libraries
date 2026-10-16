# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Process entrypoint for the VSS MCP server."""

import asyncio
import logging

from .core import get_settings
from .server import build_mcp

logger = logging.getLogger(__name__)


async def _serve() -> None:
    """Build the server for this deployment and serve it.

    Building and serving share one event loop on purpose. The startup feature
    probe opens a connection through the same HTTP client the tools go on to
    use, and a pool built in a loop that has since closed fails on its first
    reuse.
    """

    settings = get_settings()
    server = await build_mcp(settings)
    logger.info(
        "Starting MCP server on http://%s:%d%s (stateless_http=%s, log_level=%s)",
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
        settings.stateless_http,
        settings.log_level,
    )
    await server.run_async(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
        stateless_http=settings.stateless_http,
        log_level=settings.log_level,
    )


def main() -> None:
    """Run the MCP server with the streamable HTTP transport."""

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
