# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""JSON filter loading for controlling which REST operations are exposed via MCP.

The filter file is the single source of truth for what an MCP client can do
through the proxy. It enumerates every API operation (by HTTP method and path)
and declares whether it is exposed as a tool, a resource, or hidden.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = {"GET", "PUT", "POST", "DELETE", "PATCH", "HEAD", "OPTIONS"}
OPERATION_KEY_PATTERN = re.compile(r"^(GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)\s+(/.+)$")
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ApiExposure = Literal["tool", "resource", "disabled"]


class ApiConfig(BaseModel):
    """Per-operation MCP exposure settings loaded from JSON.

    Attributes:
        expose: How the operation should appear: as an MCP tool, an MCP
            resource, or hidden entirely.
        tool_name: Tool-name suffix (combined with the global ``prefix``
            to form the final MCP tool name). Required when ``expose='tool'``;
            forbidden otherwise.
        resource_name: Resource-name suffix (combined with the global
            ``prefix`` to form the final MCP resource name). Required
            when ``expose='resource'``; forbidden otherwise.
        description: Optional override prepended to the OpenAPI-generated
            description of the resulting tool/resource.
    """

    model_config = ConfigDict(extra="forbid")

    expose: ApiExposure = Field(
        description="Whether this API is exposed as a tool, a resource, or disabled.",
    )
    tool_name: str | None = Field(
        default=None,
        description="Explicit MCP tool name suffix for tool-exposed APIs.",
    )
    resource_name: str | None = Field(
        default=None,
        description="Explicit MCP resource name suffix for resource-exposed APIs.",
    )
    description: str | None = Field(
        default=None,
        description="Optional description override for the tool/resource generated from this API.",
    )

    @field_validator("tool_name", "resource_name")
    @classmethod
    def _normalize_component_name(_cls, value: str | None) -> str | None:
        """Strip whitespace and ensure the name is a valid identifier."""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if TOOL_NAME_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "Name must be a valid identifier using letters, numbers, and underscores."
            )
        return normalized

    @field_validator("description")
    @classmethod
    def _normalize_description(_cls, value: str | None) -> str | None:
        """Trim surrounding whitespace; collapse all-whitespace strings to ``None``."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_name_requirements(self) -> "ApiConfig":
        """Enforce that each name field is present only for its matching expose value."""

        if self.tool_name is not None and self.expose != "tool":
            raise ValueError('tool_name is only allowed when expose is "tool".')
        if self.resource_name is not None and self.expose != "resource":
            raise ValueError('resource_name is only allowed when expose is "resource".')
        if self.expose == "tool" and not self.tool_name:
            raise ValueError('tool_name is required when expose is "tool".')
        if self.expose == "resource" and not self.resource_name:
            raise ValueError('resource_name is required when expose is "resource".')
        return self


class ProxyFilterConfig(BaseModel):
    """Top-level filter configuration loaded from JSON.

    Attributes:
        enabled: Master kill switch. When ``False`` the proxy refuses to expose
            any API regardless of per-entry settings.
        server_name: ``FastMCP`` server name surfaced to clients.
        prefix: Prefix applied to every generated MCP tool and resource
            name. Final names follow the pattern
            ``f"{prefix}_{tool_name}"`` for tools and
            ``f"{prefix}_{resource_name}"`` for resources.
        apis: Per-operation rules keyed as ``"METHOD /path"``. Operations not
            listed here are excluded from MCP entirely.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="When false, no REST operations are proxied.")
    server_name: str = Field(
        default="app_proxy_mcp",
        description="FastMCP server name shown to clients.",
    )
    prefix: str = Field(
        default="api",
        description="Prefix applied to generated MCP tool and resource names.",
    )
    apis: dict[str, ApiConfig] = Field(
        default_factory=dict,
        description='Explicit per-API entries keyed as "METHOD /path".',
    )

    @field_validator("server_name", "prefix")
    @classmethod
    def _normalize_names(_cls, value: str) -> str:
        """Lowercase, strip, and replace ``-`` with ``_`` for identifier-like fields."""

        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            raise ValueError("Server and prefix values must not be empty.")
        return normalized

    @field_validator("apis")
    @classmethod
    def _normalize_api_entries(_cls, value: dict[str, ApiConfig]) -> dict[str, ApiConfig]:
        """Normalise every API key to canonical ``METHOD /path`` form."""

        return {_normalize_operation_key(raw_key): cfg for raw_key, cfg in value.items()}

    @model_validator(mode="after")
    def _validate_name_uniqueness(self) -> "ProxyFilterConfig":
        """Reject duplicate ``tool_name`` or ``resource_name`` values across the filter."""

        seen_tools: dict[str, str] = {}
        seen_resources: dict[str, str] = {}
        for api_key, config in self.apis.items():
            if config.tool_name is not None:
                previous = seen_tools.get(config.tool_name)
                if previous is not None:
                    raise ValueError(
                        f'tool_name "{config.tool_name}" is used by both "{previous}" and "{api_key}".'
                    )
                seen_tools[config.tool_name] = api_key
            if config.resource_name is not None:
                previous = seen_resources.get(config.resource_name)
                if previous is not None:
                    raise ValueError(
                        f'resource_name "{config.resource_name}" is used by both "{previous}" and "{api_key}".'
                    )
                seen_resources[config.resource_name] = api_key
        return self


def load_filter_config(path: str) -> ProxyFilterConfig:
    """Load and validate the JSON filter configuration file.

    Args:
        path: Filesystem path to the JSON filter file.

    Returns:
        A validated :class:`ProxyFilterConfig`.

    Raises:
        ValueError: If the file is missing, not valid JSON, or fails schema
            validation.
    """

    config_path = Path(path).expanduser()
    logger.debug("Reading filter config from %s", config_path)

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Filter config file not found: {config_path}") from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Filter config file is not valid JSON: {config_path}") from exc

    config = ProxyFilterConfig.model_validate(raw_data)
    logger.debug(
        "Filter config validated: %d API entries, master enabled=%s",
        len(config.apis),
        config.enabled,
    )
    return config


def operation_key(method: str, path: str) -> str:
    """Return the canonical filter key for a ``(method, path)`` pair.

    Args:
        method: HTTP method, case-insensitive.
        path: Request path including any ``{param}`` placeholders.

    Returns:
        A string of the form ``"METHOD /path"``.
    """

    return f"{method.upper()} {path}"


def api_config_for(
    config: ProxyFilterConfig, method: str, path: str
) -> ApiConfig | None:
    """Return the explicit per-operation config for a ``(method, path)`` pair, if any."""

    return config.apis.get(operation_key(method, path))


def operation_is_enabled(config: ProxyFilterConfig, method: str, path: str) -> bool:
    """Return whether the given operation should appear anywhere in MCP."""

    if not config.enabled:
        return False
    api_config = api_config_for(config, method, path)
    return api_config is not None and api_config.expose != "disabled"


def tool_is_enabled(config: ProxyFilterConfig, method: str, path: str) -> bool:
    """Return whether the given operation should be exposed as a tool."""

    if not config.enabled:
        return False
    api_config = api_config_for(config, method, path)
    return api_config is not None and api_config.expose == "tool"


def resource_is_enabled(config: ProxyFilterConfig, method: str, path: str) -> bool:
    """Return whether the given operation should be exposed as a resource.

    Resources must be read-only (``GET``) — any non-``GET`` operation that
    declares ``expose: resource`` is rejected here even if the schema accepted it.
    """

    if not config.enabled:
        return False
    api_config = api_config_for(config, method, path)
    if api_config is None or api_config.expose != "resource":
        return False
    return method.upper() == "GET"


def configured_tool_name(
    config: ProxyFilterConfig, method: str, path: str
) -> str | None:
    """Return the final MCP tool name (with prefix) for a tool-exposed operation.

    Args:
        config: Loaded filter configuration.
        method: HTTP method.
        path: Request path.

    Returns:
        The fully prefixed tool name, e.g. ``"vss_run_search_query"``, or
        ``None`` when no explicit ``tool_name`` was configured for the entry.
    """

    api_config = api_config_for(config, method, path)
    if api_config is None or api_config.tool_name is None:
        return None
    return f"{config.prefix}_{api_config.tool_name}"


def configured_resource_name(
    config: ProxyFilterConfig, method: str, path: str
) -> str | None:
    """Return the final MCP resource name (with prefix) for a resource-exposed operation.

    Mirrors :func:`configured_tool_name` but reads the ``resource_name`` field
    and applies the same ``prefix``.

    Args:
        config: Loaded filter configuration.
        method: HTTP method.
        path: Request path.

    Returns:
        The fully prefixed resource name, e.g. ``"vss_app_features"``, or
        ``None`` when no explicit ``resource_name`` was configured for the entry.
    """

    api_config = api_config_for(config, method, path)
    if api_config is None or api_config.resource_name is None:
        return None
    return f"{config.prefix}_{api_config.resource_name}"


def _normalize_operation_key(value: str) -> str:
    """Validate and canonicalise one filter JSON operation key.

    Args:
        value: Raw key as read from JSON (e.g. ``"  get   /widgets "``).

    Returns:
        A canonical ``"METHOD /path"`` key with a single space and uppercased
        method.

    Raises:
        ValueError: If the key is malformed, uses an unsupported method, or
            contains glob wildcards.
    """

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
