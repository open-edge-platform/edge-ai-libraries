"""Configuration helpers for the VSS MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PATH = "/mcp"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the MCP server."""

    app_name: str
    app_version: str
    vss_base_url: str
    request_timeout_seconds: float
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    stateless_http: bool
    vss_api_token: str | None
    vss_auth_scheme: str


def _read_positive_float(name: str, default: float) -> float:
    """Read a positive float from the environment."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:  # pragma: no cover - exercised via startup validation
        raise ValueError(f"{name} must be a valid number.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


def _read_port(name: str, default: int) -> int:
    """Read and validate a TCP port number from the environment."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        port = int(raw_value)
    except ValueError as exc:  # pragma: no cover - exercised via startup validation
        raise ValueError(f"{name} must be a valid integer port.") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535.")

    return port


def _read_bool(name: str, default: bool) -> bool:
    """Read a boolean flag from the environment."""

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
    """Read and normalize an HTTP path."""

    value = os.getenv(name, default).strip() or default
    return value if value.startswith("/") else f"/{value}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return validated MCP server settings."""

    vss_base_url = os.getenv("VSS_BASE_URL", "").strip()
    if not vss_base_url:
        raise ValueError(
            "VSS_BASE_URL must be set to the base URL of the VSS backend, "
            "for example http://localhost:8000."
        )

    return Settings(
        app_name="VSS MCP Proxy",
        app_version="0.1.0",
        vss_base_url=vss_base_url.rstrip("/"),
        request_timeout_seconds=_read_positive_float(
            "VSS_REQUEST_TIMEOUT",
            DEFAULT_REQUEST_TIMEOUT_SECONDS,
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        mcp_host=os.getenv("MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST,
        mcp_port=_read_port("MCP_PORT", DEFAULT_MCP_PORT),
        mcp_path=_read_path("MCP_PATH", DEFAULT_MCP_PATH),
        stateless_http=_read_bool("MCP_STATELESS_HTTP", True),
        vss_api_token=os.getenv("VSS_API_TOKEN", "").strip() or None,
        vss_auth_scheme=os.getenv("VSS_AUTH_SCHEME", "Bearer").strip() or "Bearer",
    )
