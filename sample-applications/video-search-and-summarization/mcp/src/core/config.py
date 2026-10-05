# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runtime configuration for the VSS MCP server."""

from __future__ import annotations

import ipaddress
import logging
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_WAIT_SECONDS = 600.0
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_APP_HOST_PORT = 12345

#: How ``vss_index_video`` makes a video searchable; ``auto`` follows the
#: deployment's features.
INDEX_STRATEGIES = ("auto", "summary", "embeddings")

#: A bare hostname or IPv4 literal -- no scheme, port, path or spaces.
_HOSTNAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.\-]*[A-Za-z0-9])?")

_BOOLS = {
    "1": True, "true": True, "yes": True, "on": True,
    "0": False, "false": False, "no": False, "off": False,
}


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings for the VSS MCP server.

    Attributes:
        vss_base_url: Pipeline Manager URL,
            ``http://<VSS_IP>:<APP_HOST_PORT>/manager``, reached through the
            client-reachable gateway. Also the base agents upload videos to.
        vss_datastore_url: Object store as the gateway serves it; search hits'
            playable URLs are built against this.
        request_timeout_seconds: Timeout for one HTTP call (``REQUEST_TIMEOUT``).
        poll_interval_seconds: Delay between pipeline polls (``POLL_INTERVAL``).
        default_wait_seconds: Default wall-clock budget for tools that wait on
            a pipeline (``DEFAULT_WAIT_SECONDS``).
        index_strategy: ``auto``, ``summary`` or ``embeddings``
            (``VSS_INDEX_STRATEGY``), validated at startup.
        log_level: Python logging level name.
        mcp_host: Bind address for the MCP HTTP listener.
        mcp_port: TCP port for the MCP HTTP listener.
        mcp_path: URL path prefix exposed by the MCP server.
        stateless_http: Whether the MCP HTTP transport runs without sessions.
    """

    vss_base_url: str
    vss_datastore_url: str
    request_timeout_seconds: float
    poll_interval_seconds: float
    default_wait_seconds: float
    index_strategy: str
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    stateless_http: bool


def _read_env(name: str, default: T, parse: Callable[[str], T]) -> T:
    """Read ``name`` with ``parse``, or return ``default`` when unset.

    Raises:
        ValueError: Naming the variable, if ``parse`` rejects its value.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return parse(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} {exc}") from exc


def _positive_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("must be a valid number.") from None
    if not (math.isfinite(value) and value > 0):
        raise ValueError("must be a finite number greater than zero.")
    return value


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ValueError("must be a valid integer port.") from None
    if not 1 <= port <= 65535:
        raise ValueError("must be between 1 and 65535.")
    return port


def _bool(raw: str) -> bool:
    try:
        return _BOOLS[raw.lower()]
    except KeyError:
        raise ValueError(
            "must be one of true/false, yes/no, on/off, or 1/0."
        ) from None


def _read_path(name: str, default: str) -> str:
    """Read a URL path, guaranteeing a leading ``/``."""

    value = os.getenv(name, default).strip() or default
    return value if value.startswith("/") else f"/{value}"


def _read_vss_host() -> str:
    """Return the host every VSS URL is built from.

    ``VSS_IP`` wins; otherwise ``HOST_IP``, since the MCP server normally runs
    beside the gateway. IPv6 literals are bracketed for use in a URL.

    Raises:
        ValueError: If neither is set, or the value is not a bare host.
    """

    for name in ("VSS_IP", "HOST_IP"):
        host = os.getenv(name, "").strip()
        if host:
            break
    else:
        raise ValueError(
            "Set HOST_IP (or VSS_IP when VSS runs on another machine) to the "
            "client-reachable address of the VSS gateway."
        )

    bare = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    if ":" in bare:
        try:
            ipaddress.IPv6Address(bare)
        except ValueError:
            bare = ""
        else:
            return f"[{bare}]"
    if not _HOSTNAME_PATTERN.fullmatch(bare):
        raise ValueError(
            f"{name} must be a bare IP address or hostname (no scheme, port "
            f"or path), got {host!r}."
        )
    return bare


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read and validate all runtime settings once per process.

    Raises:
        ValueError: If a required variable is missing or any is invalid.
    """

    gateway = (
        f"http://{_read_vss_host()}:"
        f"{_read_env('APP_HOST_PORT', DEFAULT_APP_HOST_PORT, _port)}"
    )
    index_strategy = os.getenv("VSS_INDEX_STRATEGY", "auto").strip().lower() or "auto"
    if index_strategy not in INDEX_STRATEGIES:
        raise ValueError(
            f"VSS_INDEX_STRATEGY must be one of {', '.join(INDEX_STRATEGIES)}; "
            f"got {index_strategy!r}."
        )

    settings = Settings(
        vss_base_url=f"{gateway}/manager",
        vss_datastore_url=f"{gateway}/datastore",
        request_timeout_seconds=_read_env(
            "REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS, _positive_float
        ),
        poll_interval_seconds=_read_env(
            "POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS, _positive_float
        ),
        default_wait_seconds=_read_env(
            "DEFAULT_WAIT_SECONDS", DEFAULT_WAIT_SECONDS, _positive_float
        ),
        index_strategy=index_strategy,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        mcp_host=os.getenv("MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST,
        mcp_port=_read_env("MCP_PORT", DEFAULT_MCP_PORT, _port),
        mcp_path=_read_path("MCP_PATH", DEFAULT_MCP_PATH),
        stateless_http=_read_env("MCP_STATELESS_HTTP", True, _bool),
    )
    logger.debug(
        "Settings resolved: vss_base_url=%s host=%s port=%d path=%s",
        settings.vss_base_url,
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
    )
    return settings
