"""Convenience entrypoint for running the VSS MCP server."""

from vss_mcp.main import main, mcp

__all__ = ["main", "mcp"]


if __name__ == "__main__":
    main()
