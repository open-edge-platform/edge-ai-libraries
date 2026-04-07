"""Summary tool registration for the VSS MCP server."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import CallToolResult
from pydantic import Field

from .lifecycle import AppContext
from .registry import RegistryContext


def register_summary_tools(mcp: FastMCP, registry: RegistryContext) -> None:
    """Register summary-specific tools."""

    @mcp.tool(
        name="vss_list_summaries",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_list_summaries(
        ctx: Context[ServerSession, AppContext],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """List summary states from GET /summary."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path="/summary",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_get_summary",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_get_summary(
        ctx: Context[ServerSession, AppContext],
        state_id: Annotated[
            str,
            Field(description="Identifier of the summary state.", min_length=1),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Fetch a summary state from GET /summary/{stateId}."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path=f"/summary/{state_id}",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_get_summary_raw",
        annotations=registry.tool_annotations(read_only=True, destructive=False, idempotent=True),
    )
    async def vss_get_summary_raw(
        ctx: Context[ServerSession, AppContext],
        state_id: Annotated[
            str,
            Field(description="Identifier of the summary state.", min_length=1),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Fetch raw summary state data from GET /summary/{stateId}/raw."""

        return await registry.request_tool(
            ctx,
            method="GET",
            path=f"/summary/{state_id}/raw",
            response_format=response_format,
        )

    @mcp.tool(
        name="vss_start_summary_pipeline",
        annotations=registry.tool_annotations(read_only=False, destructive=False, idempotent=False),
    )
    async def vss_start_summary_pipeline(
        ctx: Context[ServerSession, AppContext],
        body: Annotated[
            dict[str, Any],
            Field(description="JSON payload forwarded to POST /summary."),
        ],
        response_format: Annotated[
            str,
            Field(description="Tool response format.", pattern="^(markdown|json)$"),
        ] = "markdown",
    ) -> CallToolResult:
        """Start the VSS summary pipeline through POST /summary."""

        return await registry.request_tool(
            ctx,
            method="POST",
            path="/summary",
            json_body=body,
            response_format=response_format,
        )
