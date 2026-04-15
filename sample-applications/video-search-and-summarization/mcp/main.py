"""Convenience entrypoint for running the MCP REST proxy server."""

from src.main import create_mcp, get_mcp, main

__all__ = ["create_mcp", "get_mcp", "main"]


if __name__ == "__main__":
    main()
