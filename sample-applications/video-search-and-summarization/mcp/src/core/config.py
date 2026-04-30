# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runtime configuration for the spec-driven MCP REST proxy."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_FILTER_CONFIG_PATH = "all.json"


# Used in long lived singleton.
@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings for the MCP proxy server.

    Attributes:
        spec_url: URL of the upstream OpenAPI / Swagger document
            (from ``API_SPEC_URL``).
        api_base_url: Base URL the proxy forwards REST traffic to
            (from ``API_BASE_URL``).
        filter_config_path: Absolute path to the JSON filter file
            (from ``FILTER_FILE_PATH``).
        request_timeout_seconds: Timeout applied to both the spec download and
            every proxied request (from ``REQUEST_TIMEOUT``).
        log_level: Python logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        mcp_host: Bind address for the MCP HTTP listener (from ``MCP_HOST``).
        mcp_port: TCP port for the MCP HTTP listener (from ``MCP_PORT``).
        mcp_path: URL path prefix exposed by the MCP server (from ``MCP_PATH``).
        stateless_http: Whether the MCP HTTP transport runs without sessions.
    """

    spec_url: str
    """URL of the upstream OpenAPI / Swagger document."""

    api_base_url: str
    """Base URL the proxy forwards REST traffic to (from ``API_BASE_URL``)."""

    filter_config_path: str
    request_timeout_seconds: float
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    stateless_http: bool


def _read_positive_float(name: str, default: float) -> float:
    """Read a strictly-positive float from the environment.

    Args:
        name: Environment variable to read.
        default: Value to return when the variable is unset.

    Returns:
        The parsed float value, or ``default`` when the variable is unset.

    Raises:
        ValueError: If the variable is set but not a positive number.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid number.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


def _read_port(name: str, default: int) -> int:
    """Read and validate a TCP port number from the environment.

    Args:
        name: Environment variable to read.
        default: Value to return when the variable is unset.

    Returns:
        The validated port number in ``[1, 65535]``.

    Raises:
        ValueError: If the variable is set but is not an integer in range.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid integer port.") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535.")

    return port

def _read_bool(name: str, default: bool) -> bool:
    """Read a boolean flag from the environment.

    Accepts the case-insensitive forms ``true/false``, ``yes/no``, ``on/off``,
    and ``1/0``.

    Args:
        name: Environment variable to read.
        default: Value to return when the variable is unset.

    Returns:
        The parsed boolean value, or ``default`` when the variable is unset.

    Raises:
        ValueError: If the variable is set to an unrecognised string.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be one of true/false, yes/no, on/off, or 1/0.")


def _read_path(name: str, default: str) -> str:
    """Read an HTTP URL path from the environment, normalising the leading slash.

    Args:
        name: Environment variable to read.
        default: Path used when the variable is unset or blank.

    Returns:
        A path that is guaranteed to start with ``/``.
    """

    value = os.getenv(name, default).strip() or default
    return value if value.startswith("/") else f"/{value}"


def _read_api_base_url() -> str:
    """Return the configured backend base URL.

    Returns:
        The non-empty value of the ``API_BASE_URL`` environment variable,
        with any trailing slash stripped.

    Raises:
        ValueError: If the environment variable is unset or blank.
    """

    base_url = os.getenv("API_BASE_URL", "").strip()
    if base_url:
        return base_url.rstrip("/")

    raise ValueError(
        "Set API_BASE_URL to the base URL of the running REST service "
        "(e.g. http://<HOST_IP>:12345/apiBase)."
    )


def _read_spec_url() -> str:
    """Return the configured upstream OpenAPI spec URL.

    Returns:
        The non-empty value of the ``API_SPEC_URL`` environment variable.

    Raises:
        ValueError: If the environment variable is unset or blank.
    """

    spec_url = os.getenv("API_SPEC_URL", "").strip()
    if spec_url:
        return spec_url

    raise ValueError(
        "Set API_SPEC_URL so the server knows which OpenAPI/Swagger document to load."
    )


def _read_filter_config_path() -> str:
    """Return the configured filter config file path and validate it exists.

    Returns:
        The non-empty value of the ``FILTER_FILE_PATH`` environment variable.

    Raises:
        ValueError: If the environment variable is unset, blank, or the file
            does not exist at the specified path.
    """

    filter_path = os.getenv("FILTER_FILE_PATH", "").strip()
    if not filter_path:
        raise ValueError(
            "Set FILTER_FILE_PATH to the absolute path of the filter configuration file."
        )

    path_obj = Path(filter_path)
    if not path_obj.exists():
        raise ValueError(
            f"Filter config file does not exist at FILTER_FILE_PATH: {filter_path}"
        )

    return filter_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read and validate all runtime settings from the environment.

    The result is cached for the lifetime of the process so callers can call
    this function freely without re-parsing the environment.

    Returns:
        A populated :class:`Settings` instance.

    Raises:
        ValueError: If any required variable is missing or any optional
            variable is set to an invalid value.
    """

    settings = Settings(
        spec_url=_read_spec_url(),
        api_base_url=_read_api_base_url(),
        filter_config_path=_read_filter_config_path(),
        request_timeout_seconds=_read_positive_float(
            "REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        mcp_host=os.getenv("MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST,
        mcp_port=_read_port("MCP_PORT", DEFAULT_MCP_PORT),
        mcp_path=_read_path("MCP_PATH", DEFAULT_MCP_PATH),
        stateless_http=_read_bool("MCP_STATELESS_HTTP", True),
    )
    logger.debug(
        "Settings resolved: spec_url=%s filter=%s api_base_url=%s host=%s port=%d path=%s",
        settings.spec_url,
        settings.filter_config_path,
        settings.api_base_url,
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
    )
    return settings
