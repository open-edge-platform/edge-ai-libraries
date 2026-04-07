"""Formatting helpers for MCP tool and resource responses."""

from __future__ import annotations

import base64
import json

from mcp.types import CallToolResult, TextContent

from .client import VSSResponse
from .models import ResponseFormat, VSSOperationResult


def _to_operation_result(response: VSSResponse) -> VSSOperationResult:
    """Convert a normalized backend response into the tool result model."""

    return VSSOperationResult(
        endpoint=response.endpoint,
        method=response.method,
        status_code=response.status_code,
        ok=response.ok,
        content_type=response.content_type,
        headers=response.headers,
        content_size_bytes=response.content_size_bytes,
        data=response.data,
        text=response.text,
        content_base64=(
            base64.b64encode(response.binary_body).decode("ascii")
            if response.binary_body is not None
            else None
        ),
        note=response.note,
    )


def _render_markdown(result: VSSOperationResult) -> str:
    """Render a readable Markdown summary for a tool response."""

    lines = [
        f"# VSS {result.method} {result.endpoint}",
        "",
        f"- Status: `{result.status_code}`",
        f"- Success: `{str(result.ok).lower()}`",
    ]

    if result.content_type:
        lines.append(f"- Content-Type: `{result.content_type}`")
    lines.append(f"- Size: `{result.content_size_bytes}` bytes")

    if result.note:
        lines.extend(["", f"Note: {result.note}"])

    if result.data is not None:
        lines.extend(
            [
                "",
                "```json",
                json.dumps(result.data, indent=2, sort_keys=True),
                "```",
            ]
        )
    elif result.text is not None:
        lines.extend(["", "```text", result.text, "```"])
    elif result.content_base64 is not None:
        lines.extend(
            [
                "",
                "Binary content was included in `structuredContent.content_base64`.",
            ]
        )

    return "\n".join(lines)


def build_tool_result(response: VSSResponse, *, response_format: str) -> CallToolResult:
    """Build an MCP CallToolResult with text and structured output."""

    result = _to_operation_result(response)
    structured_content = result.model_dump(mode="json")

    if response_format == ResponseFormat.JSON:
        text = json.dumps(structured_content, indent=2, sort_keys=True)
    else:
        text = _render_markdown(result)

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured_content,
        isError=not result.ok,
    )


def render_resource_payload(response: VSSResponse) -> str:
    """Render a resource payload as JSON text suitable for model context."""

    if response.data is not None:
        return json.dumps(response.data, indent=2, sort_keys=True)

    payload = {
        "endpoint": response.endpoint,
        "method": response.method,
        "status_code": response.status_code,
        "content_type": response.content_type,
        "content_size_bytes": response.content_size_bytes,
        "text": response.text,
        "note": response.note,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
