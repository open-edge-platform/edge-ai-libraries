"""Prompt registration for the VSS MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP, upload_api_guide: str) -> None:
    """Register prompts exposed by the VSS MCP server."""

    @mcp.prompt(
        name="vss_upload_api_help",
        title="VSS direct upload help",
        description=(
            "Explain how to upload media directly to VSS and which MCP tools to use "
            "after the upload completes."
        ),
    )
    def vss_upload_api_help() -> str:
        """Provide agent-facing guidance for the direct VSS upload workflow."""

        return upload_api_guide
