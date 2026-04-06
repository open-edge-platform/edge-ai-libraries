
"""MCP server exposing selected VSS endpoints as tools and resources."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from .config import Settings, get_settings
from .formatting import build_tool_result, render_resource_payload
from .logging_config import configure_logging
from .client import VSSApiClient, VSSServiceError


settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)

UPLOAD_API_GUIDE = f"""# VSS Direct Upload API

Do not upload media through this MCP server.

Upload videos or images directly to the VSS backend:

- Endpoint: `{settings.vss_base_url}/videos`
- Method: `POST`
- Content-Type: `multipart/form-data`

Multipart fields:

- `video` (required): binary file payload
- `name` (optional): display name for the media
- `tags` (optional): comma-separated tag list

Example:

```bash
curl -X POST "{settings.vss_base_url}/videos" \\
  -F "video=@/path/to/file.mp4" \\
  -F "name=Demo clip" \\
  -F "tags=demo,test"
```

Recommended follow-up MCP workflow:

1. Use `vss_list_videos` to confirm the upload is visible.
2. Use `vss_get_video` to inspect the uploaded asset or metadata.
3. Use `vss_create_video_search_embeddings` if the uploaded video needs embeddings.
4. Use `vss_execute_search_query` when you want to search across processed content.
"""


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator["AppContext"]:
    """Create and clean up the shared VSS client used by tools and resources."""

    client = VSSApiClient(settings)
    await client.open()

    logger.info(
        "Starting VSS MCP server on %s:%s%s against %s",
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
        settings.vss_base_url,
    )
    try:
        yield AppContext(settings=settings, client=client)
    finally:
        await client.close()
        logger.info("Stopped VSS MCP server")


@dataclass(slots=True)
class AppContext:
    """Typed lifespan context shared with all MCP handlers."""

    settings: Settings
    client: VSSApiClient


mcp = FastMCP(
    name="vss_mcp",
    instructions=(
        "Use the vss_* tools to interact with the Video Search and "
        "Summarization backend. Prefer resources for read-only context and "
        "use vss_execute_search_query for search instead of saved-query "
        "management. "
        "tools for actions or filtered reads. Do not upload media through this "
        "MCP server. Upload videos or images directly to the VSS backend at "
        f"{settings.vss_base_url}/videos using multipart/form-data with the "
        "'video' field and optional 'name' and 'tags' fields, then use the MCP "
        "tools to inspect the uploaded asset or trigger follow-up operations. "
        "For detailed upload instructions, read the vss://help/upload-api "
        "resource or invoke the vss_upload_api_help prompt."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
    streamable_http_path=settings.mcp_path,
    stateless_http=settings.stateless_http,
    log_level=settings.log_level,
    json_response=True,
    lifespan=lifespan,
)


def _tool_annotations(
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


def _client(ctx: Context[ServerSession, AppContext]) -> VSSApiClient:
    """Return the VSS API client from the typed MCP context."""

    return ctx.request_context.lifespan_context.client


def _pagination_params(
    limit: int,
    offset: int,
    query_params: dict[str, str] | None,
) -> dict[str, str]:
    """Merge explicit pagination arguments with optional passthrough query params."""

    params = dict(query_params or {})
    params["limit"] = str(limit)
    params["offset"] = str(offset)
    return params


def _error_result(message: str) -> CallToolResult:
    """Return a structured MCP tool error."""

    payload = {"ok": False, "detail": message}
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        structuredContent=payload,
        isError=True,
    )


async def _request_tool(
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
        response = await _client(ctx).request(
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
        return _error_result(exc.detail)

    return build_tool_result(response, response_format=response_format)


async def _request_resource(path: str, resource_name: str) -> str:
    """Load a read-only backend payload and render it for an MCP resource."""

    client = VSSApiClient(settings)
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


@mcp.resource(
    "vss://app/config",
    name="vss_app_config_resource",
    title="VSS application configuration",
    description="Read the backend application configuration from VSS /app/config.",
    mime_type="application/json",
)
async def vss_app_config_resource() -> str:
    """Expose the VSS application configuration as an MCP resource."""

    return await _request_resource(path="/app/config", resource_name="app config")


@mcp.resource(
    "vss://app/features",
    name="vss_app_features_resource",
    title="VSS feature flags",
    description="Read the backend feature flags from VSS /app/features.",
    mime_type="application/json",
)
async def vss_app_features_resource() -> str:
    """Expose the VSS feature list as an MCP resource."""

    return await _request_resource(path="/app/features", resource_name="app features")


@mcp.resource(
    "vss://tags",
    name="vss_tags_resource",
    title="VSS tags",
    description="Read the current list of tags from VSS /tags.",
    mime_type="application/json",
)
async def vss_tags_resource() -> str:
    """Expose the VSS tag list as an MCP resource."""

    return await _request_resource(path="/tags", resource_name="tags")


@mcp.resource(
    "vss://videos",
    name="vss_videos_resource",
    title="VSS videos",
    description="Read the current list of videos from VSS /videos.",
    mime_type="application/json",
)
async def vss_videos_resource() -> str:
    """Expose the VSS video list as an MCP resource."""

    return await _request_resource(path="/videos", resource_name="videos")


@mcp.resource(
    "vss://videos/{video_id}",
    name="vss_video_resource",
    title="VSS video details",
    description=(
        "Read a video payload from VSS /videos/{videoId}. Binary payloads are "
        "represented as JSON metadata rather than embedded directly."
    ),
    mime_type="application/json",
)
async def vss_video_resource(
    video_id: str,
) -> str:
    """Expose a specific video payload as an MCP resource."""

    return await _request_resource(
        path=f"/videos/{video_id}",
        resource_name=f"video {video_id}",
    )


@mcp.resource(
    "vss://help/upload-api",
    name="vss_upload_api_help_resource",
    title="VSS upload API help",
    description=(
        "Detailed instructions for uploading media directly to the VSS backend "
        "instead of through MCP."
    ),
    mime_type="text/markdown",
)
def vss_upload_api_help_resource() -> str:
    """Expose direct VSS upload guidance as a discoverable MCP resource."""

    return UPLOAD_API_GUIDE


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

    return UPLOAD_API_GUIDE


@mcp.tool(
    name="vss_get_app_config",
    annotations=_tool_annotations(read_only=True, destructive=False, idempotent=True),
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

    return await _request_tool(
        ctx,
        method="GET",
        path="/app/config",
        response_format=response_format,
    )


@mcp.tool(
    name="vss_get_app_features",
    annotations=_tool_annotations(read_only=True, destructive=False, idempotent=True),
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

    return await _request_tool(
        ctx,
        method="GET",
        path="/app/features",
        response_format=response_format,
    )


@mcp.tool(
    name="vss_list_tags",
    annotations=_tool_annotations(read_only=True, destructive=False, idempotent=True),
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

    return await _request_tool(
        ctx,
        method="GET",
        path="/tags",
        query_params=_pagination_params(limit, offset, query_params),
        response_format=response_format,
    )


@mcp.tool(
    name="vss_delete_tag",
    annotations=_tool_annotations(read_only=False, destructive=True, idempotent=False),
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

    return await _request_tool(
        ctx,
        method="DELETE",
        path=f"/tags/{tag_id}",
        response_format=response_format,
    )


@mcp.tool(
    name="vss_get_video",
    annotations=_tool_annotations(read_only=True, destructive=False, idempotent=True),
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

    return await _request_tool(
        ctx,
        method="GET",
        path=f"/videos/{video_id}",
        include_binary_content=include_binary_content,
        response_format=response_format,
    )


@mcp.tool(
    name="vss_list_videos",
    annotations=_tool_annotations(read_only=True, destructive=False, idempotent=True),
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

    return await _request_tool(
        ctx,
        method="GET",
        path="/videos",
        query_params=_pagination_params(limit, offset, query_params),
        response_format=response_format,
    )


@mcp.tool(
    name="vss_create_video_search_embeddings",
    annotations=_tool_annotations(read_only=False, destructive=False, idempotent=False),
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

    return await _request_tool(
        ctx,
        method="POST",
        path=f"/videos/search-embeddings/{video_id}",
        response_format=response_format,
    )


@mcp.tool(
    name="vss_execute_search_query",
    annotations=_tool_annotations(read_only=False, destructive=False, idempotent=False),
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

    return await _request_tool(
        ctx,
        method="POST",
        path="/search/query",
        json_body=body,
        response_format=response_format,
    )


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
