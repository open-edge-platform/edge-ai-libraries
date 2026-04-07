"""Search tool registration for the VSS MCP server."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import CallToolResult
from pydantic import Field

from .lifecycle import AppContext
from .registry import RegistryContext


def register_search_tools(mcp: FastMCP, registry: RegistryContext) -> None:
    """Register search-specific tools."""

    @mcp.tool(
        name="vss_create_video_search_embeddings",
        annotations=registry.tool_annotations(read_only=False, destructive=False, idempotent=False),
    )
    async def vss_create_video_search_embeddings(
        ctx: Context[ServerSession, AppContext],
        video_id: Annotated[
            str,
            Field(description="Identifier of the video that should receive embeddings.", min_length=1),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Trigger search-embedding generation through POST /videos/search-embeddings/{videoId}."""

        return await registry.request_tool(
            ctx,
            method="POST",
            path=f"/videos/search-embeddings/{video_id}",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_execute_search_query",
        annotations=registry.tool_annotations(read_only=False, destructive=False, idempotent=False),
    )
    async def vss_execute_search_query(
        ctx: Context[ServerSession, AppContext],
        body: Annotated[
            dict[str, Any],
            Field(description="JSON payload forwarded to POST /search/query."),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Execute an immediate VSS search through POST /search/query."""

        return await registry.request_tool(
            ctx,
            method="POST",
            path="/search/query",
            json_body=body,
            response_format=response_format,
        )
