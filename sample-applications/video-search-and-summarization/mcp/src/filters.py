"""JSON filter loading and operation selection for the MCP REST proxy."""

from __future__ import annotations

import json
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import OperationSpec


class PathRule(BaseModel):
    """A path-pattern rule with optional HTTP method constraints."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        description="Path pattern such as /videos/{videoId}, /videos/*, or /search/**."
    )
    methods: list[str] | None = Field(
        default=None,
        description="Optional list of HTTP methods to constrain this rule.",
    )

    @field_validator("path")
    @classmethod
    def _validate_path(_cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Rule path must not be empty.")
        return normalized if normalized.startswith("/") else f"/{normalized}"

    @field_validator("methods")
    @classmethod
    def _normalize_methods(_cls, methods: list[str] | None) -> list[str] | None:
        if methods is None:
            return None

        normalized = []
        for method in methods:
            candidate = method.strip().upper()
            if not candidate:
                raise ValueError("HTTP methods must not be empty.")
            normalized.append(candidate)
        return normalized

    def matches(self, operation: OperationSpec) -> bool:
        """Return whether this rule matches the given operation."""

        if not _path_matches(operation.path, self.path):
            return False
        return self.methods is None or operation.method in self.methods


class ProxyFilterConfig(BaseModel):
    """Filter configuration loaded from JSON."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="When false, no REST operations are proxied.")
    server_name: str = Field(
        default="app_proxy_mcp",
        description="FastMCP server name shown to clients.",
    )
    tool_prefix: str = Field(
        default="api",
        description="Prefix applied to generated MCP tool names.",
    )
    resource_scheme: str = Field(
        default="api",
        description="URI scheme used for generated MCP resources.",
    )
    guidance_markdown: str | None = Field(
        default=None,
        description="Optional guidance shown to MCP clients for special handling patterns.",
    )
    include: list[PathRule] = Field(
        default_factory=list,
        description="Operations must match at least one include rule to be proxied.",
    )
    exclude: list[PathRule] = Field(
        default_factory=list,
        description="Exclude rules applied after include matching.",
    )
    resource_methods: list[str] = Field(
        default_factory=lambda: ["GET"],
        description="HTTP methods that may be exposed as read-only resources.",
    )

    @field_validator("server_name", "tool_prefix", "resource_scheme")
    @classmethod
    def _normalize_names(_cls, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            raise ValueError("Server and prefix values must not be empty.")
        return normalized

    @field_validator("guidance_markdown")
    @classmethod
    def _normalize_guidance(_cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("resource_methods")
    @classmethod
    def _normalize_resource_methods(_cls, methods: list[str]) -> list[str]:
        normalized = []
        for method in methods:
            candidate = method.strip().upper()
            if not candidate:
                raise ValueError("resource_methods entries must not be empty.")
            normalized.append(candidate)
        return normalized


def load_filter_config(path: str) -> ProxyFilterConfig:
    """Load and validate the JSON filter configuration file."""

    config_path = Path(path).expanduser()
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Filter config file not found: {config_path}") from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Filter config file is not valid JSON: {config_path}") from exc

    return ProxyFilterConfig.model_validate(raw_data)


def operation_is_enabled(config: ProxyFilterConfig, operation: OperationSpec) -> bool:
    """Return whether the given operation should be exposed through MCP."""

    if not config.enabled:
        return False

    if not config.include:
        return False

    if not any(rule.matches(operation) for rule in config.include):
        return False

    return not any(rule.matches(operation) for rule in config.exclude)


def resource_is_enabled(config: ProxyFilterConfig, operation: OperationSpec) -> bool:
    """Return whether a filtered operation should also become a resource."""

    return (
        operation_is_enabled(config, operation)
        and operation.method in config.resource_methods
        and operation.read_only
        and operation.request_body is None
    )


def _path_matches(path: str, pattern: str) -> bool:
    """Match exact paths plus segment-aware wildcard patterns."""

    if path == pattern:
        return True

    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*\*", "__DOUBLE_WILDCARD__")
    escaped = escaped.replace(r"\*", "[^/]*")
    escaped = escaped.replace(r"\?", "[^/]")
    escaped = escaped.replace("__DOUBLE_WILDCARD__", ".*")
    return re.fullmatch(escaped, path) is not None
