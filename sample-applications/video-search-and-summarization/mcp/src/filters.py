"""JSON filter loading and exact operation selection for the MCP REST proxy."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import OperationSpec


SUPPORTED_METHODS = {"GET", "PUT", "POST", "DELETE", "PATCH", "HEAD", "OPTIONS"}
OPERATION_KEY_PATTERN = re.compile(r"^(GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)\s+(/.+)$")
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ApiExposure = Literal["tool", "resource", "disabled"]

class ApiConfig(BaseModel):
    """Per-operation MCP exposure settings loaded from JSON."""

    model_config = ConfigDict(extra="forbid")

    expose: ApiExposure = Field(
        description="Whether this API is exposed as a tool, a resource, or disabled.",
    )
    tool_name: str | None = Field(
        default=None,
        description="Explicit MCP tool name suffix for tool-exposed APIs.",
    )
    description: str | None = Field(
        default=None,
        description="Optional shared description override for the tool/resource generated from this API.",
    )

    @field_validator("tool_name")
    @classmethod
    def _normalize_tool_name(_cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if TOOL_NAME_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "tool_name must be a valid identifier using letters, numbers, and underscores."
            )
        return normalized

    @field_validator("description")
    @classmethod
    def _normalize_description(_cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_tool_name_requirements(self) -> "ApiConfig":
        if self.expose == "tool" and not self.tool_name:
            raise ValueError('tool_name is required when expose is "tool".')
        if self.expose != "tool" and self.tool_name is not None:
            raise ValueError('tool_name is only allowed when expose is "tool".')
        return self


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
    apis: dict[str, ApiConfig] = Field(
        default_factory=dict,
        description='Explicit per-API entries keyed as "METHOD /path".',
    )

    @field_validator("server_name", "tool_prefix", "resource_scheme")
    @classmethod
    def _normalize_names(_cls, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            raise ValueError("Server and prefix values must not be empty.")
        return normalized

    @field_validator("apis")
    @classmethod
    def _normalize_api_entries(_cls, value: dict[str, ApiConfig]) -> dict[str, ApiConfig]:
        normalized: dict[str, ApiConfig] = {}
        for raw_key, config in value.items():
            normalized[_normalize_operation_key(raw_key)] = config
        return normalized

    @model_validator(mode="after")
    def _validate_tool_name_uniqueness(self) -> "ProxyFilterConfig":
        seen: dict[str, str] = {}
        for api_key, config in self.apis.items():
            if config.tool_name is None:
                continue
            previous_api = seen.get(config.tool_name)
            if previous_api is not None:
                raise ValueError(
                    f'tool_name "{config.tool_name}" is used by both "{previous_api}" and "{api_key}".'
                )
            seen[config.tool_name] = api_key
        return self


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
    """Return whether the given operation should appear anywhere in MCP."""

    if not config.enabled:
        return False

    api_config = operation_config(config, operation)
    return api_config is not None and api_config.expose != "disabled"


def tool_is_enabled(config: ProxyFilterConfig, operation: OperationSpec) -> bool:
    """Return whether the given operation should be exposed as a tool."""

    if not config.enabled:
        return False

    api_config = operation_config(config, operation)
    return api_config is not None and api_config.expose == "tool"


def resource_is_enabled(config: ProxyFilterConfig, operation: OperationSpec) -> bool:
    """Return whether an explicitly configured operation should become a resource."""

    if not config.enabled:
        return False

    api_config = operation_config(config, operation)
    return (
        api_config is not None
        and api_config.expose == "resource"
        and operation.read_only
        and operation.request_body is None
    )


def operation_config(config: ProxyFilterConfig, operation: OperationSpec) -> ApiConfig | None:
    """Return the explicit per-operation config for the given REST operation."""

    return config.apis.get(operation_key(operation))


def operation_key(operation: OperationSpec) -> str:
    """Return the normalized JSON key for an operation."""

    return f"{operation.method} {operation.path}"


def configured_tool_name(config: ProxyFilterConfig, operation: OperationSpec) -> str | None:
    """Return the final MCP tool name for a tool-exposed operation."""

    api_config = operation_config(config, operation)
    if api_config is None or api_config.tool_name is None:
        return None
    return f"{config.tool_prefix}_{api_config.tool_name}"


def _normalize_operation_key(value: str) -> str:
    """Normalize and validate one proxy JSON operation key."""

    normalized = " ".join(value.strip().split())
    match = OPERATION_KEY_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError('API keys must use the format "METHOD /path".')

    method, path = match.groups()
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported HTTP method in API key: {method}")
    if any(token in path for token in ("*", "?")):
        raise ValueError("Wildcard API keys are not supported; list each API explicitly.")
    return f"{method} {path}"
