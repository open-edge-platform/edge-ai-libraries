# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Entrypoint for ``python -m src.mcp``.

Usage:
    python -m src.mcp                              # stdio (default)
    python -m src.mcp --transport http --port 8080  # HTTP (Streamable HTTP)
"""

import argparse
import sys

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Model Download MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the HTTP transport to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the HTTP transport (default: 8080)",
    )
    args = parser.parse_args()

    kwargs: dict = {"transport": args.transport}
    if args.transport == "http":
        kwargs["host"] = args.host
        kwargs["port"] = args.port

    mcp.run(**kwargs)


if __name__ == "__main__":
    main()
