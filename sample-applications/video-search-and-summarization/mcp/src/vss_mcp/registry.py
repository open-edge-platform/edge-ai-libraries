"""Shared registration helpers used by MCP tools and resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import CallToolResult, TextContent

from .client import VSSApiClient, VSSServiceError
from .config import Settings
from .formatting import build_tool_result, render_resource_payload
from .lifecycle import AppContext


@dataclass(slots=True)
class RegistryContext:
    """Reusable helpers for MCP tool and resource registration."""

    settings: Settings

    def tool_annotations(
        self,
        *,
        read_only: bool,
        destructive: bool,
        idempotent: bool,
    ) -> dict[str, bool]:
        """Create consistent annotation hints for VSS tools."""

        return {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": True,
        }

    def client(self, ctx: Context[ServerSession, AppContext]) -> VSSApiClient:
        """Return the VSS API client from the typed MCP context."""

        return ctx.request_context.lifespan_context.client

    @staticmethod
    def pagination_params(
        limit: int,
        offset: int,
        query_params: dict[str, str] | None,
    ) -> dict[str, str]:
        """Merge explicit pagination arguments with optional passthrough query params."""

        params = dict(query_params or {})
        params["limit"] = str(limit)
        params["offset"] = str(offset)
        return params

    @staticmethod
    def error_result(message: str) -> CallToolResult:
        """Return a structured MCP tool error."""

        payload = {"ok": False, "detail": message}
        return CallToolResult(
            content=[TextContent(type="text", text=message)],
            structuredContent=payload,
            isError=True,
        )

    async def request_tool(
        self,
        ctx: Context[ServerSession, AppContext],
        *,
        method: str,
        path: str,
        response_format: str,
        query_params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        include_binary_content: bool = False,
    ) -> CallToolResult:
        """Execute a backend request and convert it into an MCP tool result."""

        try:
            response = await self.client(ctx).request(
                method=method,
                path=path,
                query_params=query_params,
                json_body=json_body,
                data=data,
                files=files,
                include_binary_content=include_binary_content,
            )
        except VSSServiceError as exc:
            await ctx.error(exc.detail)
            return self.error_result(exc.detail)

        return build_tool_result(response, response_format=response_format)

    async def request_resource(self, path: str, resource_name: str) -> str:
        """Load a read-only backend payload and render it for an MCP resource."""

        client = VSSApiClient(self.settings)
        await client.open()
        try:
            try:
                response = await client.request(method="GET", path=path)
            except VSSServiceError as exc:
                raise RuntimeError(exc.detail) from exc

            if not response.ok:
                raise RuntimeError(
                    f"VSS returned HTTP {response.status_code} while loading {resource_name}."
                )

            return render_resource_payload(response)
        finally:
            await client.close()
