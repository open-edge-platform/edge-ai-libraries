"""Shared models for MCP tool output formatting."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseFormat(str, Enum):
    """Supported MCP tool response formats."""

    MARKDOWN = "markdown"
    JSON = "json"


class VSSOperationResult(BaseModel):
    """Structured content returned for every VSS MCP tool call."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(description="VSS backend path that was called.")
    method: str = Field(description="HTTP method used for the backend request.")
    status_code: int = Field(description="HTTP status returned by the VSS backend.")
    ok: bool = Field(description="True when the backend returned a 2xx status code.")
    content_type: str | None = Field(
        default=None,
        description="Response content type returned by the VSS backend.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Response headers returned by the VSS backend.",
    )
    content_size_bytes: int = Field(description="Response body size in bytes.")
    data: Any = Field(
        default=None,
        description="Parsed JSON payload when the backend responded with JSON.",
    )
    text: str | None = Field(
        default=None,
        description="Decoded text payload for text-like backend responses.",
    )
    content_base64: str | None = Field(
        default=None,
        description="Base64-encoded binary response content when requested.",
    )
    note: str | None = Field(
        default=None,
        description="Additional context such as omitted binary payload warnings.",
    )
