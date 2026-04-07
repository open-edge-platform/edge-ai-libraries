"""Feature flag resolution and server guidance helpers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from .client import fetch_backend_features
from .config import Settings


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """Resolved feature flags from the VSS backend."""

    raw: dict[str, Any]
    summary_enabled: bool
    search_enabled: bool


def resolve_feature_flags(settings: Settings, logger: logging.Logger) -> FeatureFlags:
    """Resolve VSS feature flags once during MCP startup."""

    payload = fetch_backend_features(settings)
    flags = FeatureFlags(
        raw=payload,
        summary_enabled=str(payload.get("summary", "")).upper() == "FEATURE_ON",
        search_enabled=str(payload.get("search", "")).upper() == "FEATURE_ON",
    )
    logger.info(
        "Resolved VSS feature flags: summary=%s search=%s (summary_enabled=%s search_enabled=%s)",
        payload.get("summary"),
        payload.get("search"),
        flags.summary_enabled,
        flags.search_enabled,
    )
    return flags


def build_upload_api_guide(settings: Settings, flags: FeatureFlags) -> str:
    """Build the direct-upload guide shown to MCP clients."""

    follow_up_steps = [
        "1. Use `vss_list_videos` to confirm the upload is visible.",
        "2. Use `vss_get_video` to inspect the uploaded asset or metadata.",
    ]
    next_step_number = 3

    if flags.summary_enabled:
        follow_up_steps.extend(
            [
                f"{next_step_number}. Use `vss_list_summaries` to inspect summary runs that already exist.",
                f"{next_step_number + 1}. Use `vss_start_summary_pipeline` to create a new summary for an uploaded video.",
            ]
        )
        next_step_number += 2
    else:
        follow_up_steps.append(
            f"{next_step_number}. Summary features are currently disabled by the backend "
            "`/app/features` response, so summary tools and resources are not registered."
        )
        next_step_number += 1

    if flags.search_enabled:
        follow_up_steps.extend(
            [
                f"{next_step_number}. Use `vss_create_video_search_embeddings` if the uploaded video needs embeddings.",
                f"{next_step_number + 1}. Use `vss_execute_search_query` when you want to search across processed content.",
            ]
        )
    else:
        follow_up_steps.append(
            f"{next_step_number}. Search features are currently disabled by the backend `/app/features` response, "
            "so embedding generation and MCP search tools are not registered."
        )

    return f"""# VSS Direct Upload API

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

{chr(10).join(follow_up_steps)}
"""


def build_server_instructions(settings: Settings, flags: FeatureFlags) -> str:
    """Build MCP server instructions that reflect the current backend features."""

    summary_instruction = (
        "Summary is enabled by the backend feature flags, so summary tools and resources are available. "
        if flags.summary_enabled
        else "Summary is disabled by the backend feature flags, so summary tools and resources are not registered. "
    )
    search_instruction = (
        "Search is enabled by the backend feature flags, so "
        "`vss_create_video_search_embeddings` and `vss_execute_search_query` are available. "
        if flags.search_enabled
        else "Search is disabled by the backend feature flags, so search tools are not registered. "
    )
    return (
        "Use the vss_* tools to interact with the Video Search and "
        "Summarization backend. Prefer resources for read-only context and "
        "tools for actions or filtered reads. "
        f"{summary_instruction}"
        f"{search_instruction}"
        "Do not upload media through this MCP server. Upload videos or images "
        f"directly to the VSS backend at {settings.vss_base_url}/videos using "
        "multipart/form-data with the 'video' field and optional 'name' and "
        "'tags' fields, then use the MCP tools to inspect the uploaded asset or "
        "trigger follow-up operations. For detailed upload instructions, read "
        "the vss://help/upload-api resource or invoke the vss_upload_api_help prompt."
    )
