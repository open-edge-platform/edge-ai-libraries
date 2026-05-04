# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""JSON filter loading for controlling which REST operations are exposed via MCP.

The filter file is the single source of truth for what an MCP client can do
through the proxy. Each entry under ``apis`` declares two things: the kind of
MCP component to register (``tool`` or ``resource``) and the human-readable
``name`` to register it under. Operations not listed in ``apis`` are excluded.
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
OPERATION_KEY_PATTERN = re.compile(r"^(GET|CONNECT|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)\s+(/.+)$")
NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ApiType = Literal["tool", "resource"]


class ApiConfig(BaseModel):
    """Per-operation MCP exposure settings loaded from JSON.

    Attributes:
        type: Either ``"tool"`` or ``"resource"`` — selects which MCP
            component kind FastMCP will register for this operation.
        name: Suffix combined with the global ``prefix`` to form the final
            MCP component name (e.g. ``prefix="vss"`` + ``name="get_tags"``
            → ``"vss_get_tags"``). Must be a valid identifier.
        description: Optional override prepended to the OpenAPI-generated
            description of the resulting tool/resource.
    """

    model_config = ConfigDict(extra="forbid")

    type: ApiType = Field(description="MCP component kind to register for this operation.")
    name: str = Field(description="Identifier suffix used (with the prefix) as the MCP name.")
    description: str | None = Field(
        default=None,
        description="Optional description override prepended to the OpenAPI description.",
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Ensure ``name`` is a non-empty valid identifier."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty.")
        if NAME_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "name must be a valid identifier (letters, numbers, underscores only)."
            )
        return normalized

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        """Trim whitespace; collapse all-whitespace strings to ``None``."""

        if value is None:
            return None
        return value.strip() or None


class ProxyFilterConfig(BaseModel):
    """Top-level filter configuration loaded from JSON.

    Attributes:
        server_name: ``FastMCP`` server name surfaced to clients.
        prefix: Prefix applied to every generated MCP component name. Final
            names follow the pattern ``f"{prefix}_{name}"``.
        apis: Per-operation rules keyed as ``"METHOD /path"``. Operations not
            listed here are excluded from MCP entirely.
    """

    model_config = ConfigDict(extra="forbid")

    server_name: str = Field(
        default="app_proxy_mcp",
        description="FastMCP server name shown to clients.",
    )
    prefix: str = Field(
        default="api",
        description="Prefix applied to generated MCP component names.",
    )
    apis: dict[str, ApiConfig] = Field(
        default_factory=dict,
        description='Explicit per-API entries keyed as "METHOD /path".',
    )

    @field_validator("server_name", "prefix")
    @classmethod
    def _normalize_names(cls, value: str) -> str:
        """Lowercase, strip, and replace ``-`` with ``_`` for identifier-like fields."""

        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            raise ValueError("server_name and prefix must not be empty.")
        if NAME_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "server_name and prefix must be valid identifiers "
                "(letters, numbers, underscores; must start with a letter or underscore)."
            )
        return normalized

    @field_validator("apis")
    @classmethod
    def _normalize_api_keys(cls, value: dict[str, ApiConfig]) -> dict[str, ApiConfig]:
        """Normalise every API key to canonical ``"METHOD /path"`` form.

        Raises ``ValueError`` if two raw keys normalise to the same canonical key
        (e.g. ``"get /foo"`` and ``"GET /foo"`` in the same file).
        """

        normalized: dict[str, ApiConfig] = {}
        for raw_key, cfg in value.items():
            canonical = _normalize_operation_key(raw_key)
            if canonical in normalized:
                raise ValueError(
                    f'Duplicate API key: "{raw_key}" normalises to "{canonical}", '
                    f"which is already defined."
                )
            normalized[canonical] = cfg
        return normalized

    @model_validator(mode="after")
    def _validate_apis(self) -> "ProxyFilterConfig":
        """Cross-entry checks: name uniqueness, and resources must be GET-only."""

        seen_names: dict[str, str] = {}
        for api_key, cfg in self.apis.items():
            previous = seen_names.get(cfg.name)
            if previous is not None:
                raise ValueError(
                    f'name "{cfg.name}" is used by both "{previous}" and "{api_key}".'
                )
            seen_names[cfg.name] = api_key

            if cfg.type == "resource" and not api_key.startswith("GET "):
                raise ValueError(
                    f'"{api_key}" is configured as a resource, but only GET operations '
                    f"can be exposed as MCP resources."
                )
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
    logger.debug("Filter config validated: %d API entries", len(config.apis))
    return config


def operation_key(method: str, path: str) -> str:
    """Return the canonical filter key for a ``(method, path)`` pair."""

    return f"{method.upper()} {path}"


def api_config_for(
    config: ProxyFilterConfig, method: str, path: str
) -> ApiConfig | None:
    """Return the per-operation config for ``(method, path)``, or ``None``.

    Returns ``None`` when the operation is not listed in the filter.
    """

    return config.apis.get(operation_key(method, path))


def configured_name(
    config: ProxyFilterConfig, method: str, path: str
) -> str | None:
    """Return the final MCP component name (with prefix) for an operation.

    Args:
        config: Loaded filter configuration.
        method: HTTP method.
        path: Request path.

    Returns:
        The fully prefixed MCP name, e.g. ``"vss_run_search_query"``, or
        ``None`` when the operation is not in the filter.
    """

    api_config = api_config_for(config, method, path)
    if api_config is None:
        return None
    return f"{config.prefix}_{api_config.name}"


def _normalize_operation_key(value: str) -> str:
    """Validate and canonicalise a JSON operation key.

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
    parts = normalized.split(" ", 1)
    if len(parts) != 2:
        raise ValueError('API keys must use the format "METHOD /path".')

    normalized = f"{parts[0].upper()} {parts[1]}"
    match = OPERATION_KEY_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError('API keys must use the format "METHOD /path".')

    method, path = match.groups()
    method = method.upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported HTTP method in API key: {method}")
    if any(token in path for token in ("*", "?")):
        raise ValueError("Wildcard API keys are not supported; list each API explicitly.")
    return f"{method} {path}"
