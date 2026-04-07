"""Resource registration for the VSS MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .registry import RegistryContext


def register_core_resources(
    mcp: FastMCP,
    registry: RegistryContext,
    upload_api_guide: str,
) -> None:
    """Register always-on MCP resources."""

    @mcp.resource(
        "vss://app/config",
        name="vss_app_config_resource",
        title="VSS application configuration",
        description="Read the backend application configuration from VSS /app/config.",
        mime_type="application/json",
    )
    async def vss_app_config_resource() -> str:
        """Expose the VSS application configuration as an MCP resource."""

        return await registry.request_resource(path="/app/config", resource_name="app config")

    @mcp.resource(
        "vss://app/features",
        name="vss_app_features_resource",
        title="VSS feature flags",
        description="Read the backend feature flags from VSS /app/features.",
        mime_type="application/json",
    )
    async def vss_app_features_resource() -> str:
        """Expose the VSS feature list as an MCP resource."""

        return await registry.request_resource(path="/app/features", resource_name="app features")

    @mcp.resource(
        "vss://tags",
        name="vss_tags_resource",
        title="VSS tags",
        description="Read the current list of tags from VSS /tags.",
        mime_type="application/json",
    )
    async def vss_tags_resource() -> str:
        """Expose the VSS tag list as an MCP resource."""

        return await registry.request_resource(path="/tags", resource_name="tags")

    @mcp.resource(
        "vss://videos",
        name="vss_videos_resource",
        title="VSS videos",
        description="Read the current list of videos from VSS /videos.",
        mime_type="application/json",
    )
    async def vss_videos_resource() -> str:
        """Expose the VSS video list as an MCP resource."""

        return await registry.request_resource(path="/videos", resource_name="videos")

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
    async def vss_video_resource(video_id: str) -> str:
        """Expose a specific video payload as an MCP resource."""

        return await registry.request_resource(
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

        return upload_api_guide


def register_summary_resources(mcp: FastMCP, registry: RegistryContext) -> None:
    """Register summary-specific resources."""

    @mcp.resource(
        "vss://summary",
        name="vss_summaries_resource",
        title="VSS summary states",
        description="Read summary states from VSS /summary.",
        mime_type="application/json",
    )
    async def vss_summaries_resource() -> str:
        """Expose the VSS summary list as an MCP resource."""

        return await registry.request_resource(path="/summary", resource_name="summary states")

    @mcp.resource(
        "vss://summary/{state_id}",
        name="vss_summary_resource",
        title="VSS summary details",
        description="Read a summary state from VSS /summary/{stateId}.",
        mime_type="application/json",
    )
    async def vss_summary_resource(state_id: str) -> str:
        """Expose a specific VSS summary state as an MCP resource."""

        return await registry.request_resource(
            path=f"/summary/{state_id}",
            resource_name=f"summary state {state_id}",
        )

    @mcp.resource(
        "vss://summary/{state_id}/raw",
        name="vss_summary_raw_resource",
        title="VSS raw summary details",
        description="Read raw summary state data from VSS /summary/{stateId}/raw.",
        mime_type="application/json",
    )
    async def vss_summary_raw_resource(state_id: str) -> str:
        """Expose raw summary state data as an MCP resource."""

        return await registry.request_resource(
            path=f"/summary/{state_id}/raw",
            resource_name=f"raw summary state {state_id}",
        )
