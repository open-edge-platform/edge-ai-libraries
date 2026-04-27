# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Process entrypoint for the spec-driven MCP REST proxy.

Parses runtime settings, asks :mod:`src.server` to assemble the
:class:`FastMCP` instance, and runs it with the streamable-HTTP transport.
"""

from __future__ import annotations

import logging

from .core import get_settings
from .server import create_mcp, get_mcp

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the MCP server with the streamable HTTP transport.

    Reads :class:`Settings` from the environment, builds the server lazily via
    :func:`get_mcp`, and blocks serving HTTP traffic until interrupted.
    """

    settings = get_settings()
    server = get_mcp()
    logger.info(
        "Starting MCP server on http://%s:%d%s (stateless_http=%s, log_level=%s)",
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
        settings.stateless_http,
        settings.log_level,
    )
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
        stateless_http=settings.stateless_http,
        log_level=settings.log_level,
    )


__all__ = ["create_mcp", "get_mcp", "main"]


if __name__ == "__main__":
    main()
