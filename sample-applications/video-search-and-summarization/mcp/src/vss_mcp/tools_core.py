"""Core tool registration for the VSS MCP server."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import CallToolResult
from pydantic import Field

from .lifecycle import AppContext
from .registry import RegistryContext


def register_core_tools(mcp: FastMCP, registry: RegistryContext) -> None:
    """Register always-on tools."""

    @mcp.tool(
        name="vss_get_app_config",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_get_app_config(
        ctx: Context[ServerSession, AppContext],
        response_format: Annotated[
            str,
            Field(
                description="Tool response format: 'markdown' for humans or 'json' for machines.",
                pattern="^(markdown|json)$",
            ),
        ] = "markdown",
    ) -> CallToolResult:
        """Fetch the VSS application configuration from GET /app/config."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path="/app/config",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_get_app_features",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_get_app_features(
        ctx: Context[ServerSession, AppContext],
        response_format: Annotated[
            str,
            Field(
                description="Tool response format: 'markdown' for humans or 'json' for machines.",
                pattern="^(markdown|json)$",
            ),
        ] = "markdown",
    ) -> CallToolResult:
        """Fetch the VSS feature flags from GET /app/features."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path="/app/features",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_list_tags",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_list_tags(
        ctx: Context[ServerSession, AppContext],
        limit: Annotated[
            int,
            Field(description="Forwarded to the backend as the limit query parameter.", ge=1, le=100),
        ] = 20,
        offset: Annotated[
            int,
            Field(description="Forwarded to the backend as the offset query parameter.", ge=0),
        ] = 0,
        query_params: Annotated[
            dict[str, str] | None,
            Field(description="Optional additional query parameters to pass through to VSS."),
        ] = None,
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """List tags from GET /tags with optional pagination-style query parameters."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path="/tags",
            query_params=registry.pagination_params(limit, offset, query_params),
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_delete_tag",
        annotations=registry.tool_annotations(read_only=False, destructive=True, idempotent=False),
    )
    async def vss_delete_tag(
        ctx: Context[ServerSession, AppContext],
        tag_id: Annotated[
            str,
            Field(description="Identifier of the tag to delete from VSS.", min_length=1),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Delete a tag through DELETE /tags/{tagId}."""

        return await registry.request_tool(
            ctx,
            method="DELETE",
            path=f"/tags/{tag_id}",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_get_video",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_get_video(
        ctx: Context[ServerSession, AppContext],
        video_id: Annotated[
            str,
            Field(description="Identifier of the video to retrieve.", min_length=1),
        ],
        include_binary_content: Annotated[
            bool,
            Field(
                description=(
                    "When true and the backend responds with binary content, include "
                    "base64 in the structured result."
                )
            ),
        ] = False,
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Fetch a video or video metadata from GET /videos/{videoId}."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path=f"/videos/{video_id}",
            include_binary_content=include_binary_content,
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_list_videos",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_list_videos(
        ctx: Context[ServerSession, AppContext],
        limit: Annotated[
            int,
            Field(description="Forwarded to the backend as the limit query parameter.", ge=1, le=100),
        ] = 20,
        offset: Annotated[
            int,
            Field(description="Forwarded to the backend as the offset query parameter.", ge=0),
        ] = 0,
        query_params: Annotated[
            dict[str, str] | None,
            Field(description="Optional additional query parameters to pass through to VSS."),
        ] = None,
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """List uploaded videos from GET /videos."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path="/videos",
            query_params=registry.pagination_params(limit, offset, query_params),
            response_format=response_format,
        )
