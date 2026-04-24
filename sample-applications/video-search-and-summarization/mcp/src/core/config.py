"""Configuration helpers for the spec-driven MCP REST proxy."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_FILTER_CONFIG_PATH = "all.json"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the MCP proxy server."""

    spec_url: str
    filter_config_path: str
    target_base_url: str | None
    request_timeout_seconds: float
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    stateless_http: bool


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


def project_root() -> Path:
    """Return the mcp project root regardless of current working directory."""

    return Path(__file__).resolve().parents[2]


def bundled_filter_config_path() -> Path:
    """Return the bundled example filter config path."""

    return project_root() / DEFAULT_FILTER_CONFIG_PATH


def _resolve_path_input(value: str, *, default_path: Path | None = None) -> str | None:
    """Resolve a configured path relative to cwd first, then project root."""

    normalized = value.strip()
    if not normalized:
        return str(default_path) if default_path is not None else None

    candidate = Path(normalized).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())

    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.exists():
        return str(cwd_candidate)

    project_candidate = (project_root() / candidate).resolve()
    return str(project_candidate)


def _read_spec_url() -> str:
    """Read the configured OpenAPI specification URL."""

    spec_url = os.getenv("API_SPEC_URL", "").strip()
    if spec_url:
        return spec_url

    raise ValueError(
        "Set API_SPEC_URL so the server knows which OpenAPI/Swagger document to load."
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return validated MCP proxy settings."""

    target_base_url = os.getenv("API_BASE_URL", "").strip() or None

    return Settings(
        spec_url=_read_spec_url(),
        filter_config_path=_resolve_path_input(
            os.getenv("FILTER_FILE_PATH", ""),
            default_path=bundled_filter_config_path(),
        )
        or str(bundled_filter_config_path()),
        target_base_url=target_base_url.rstrip("/") if target_base_url else None,
        request_timeout_seconds=_read_positive_float(
            "APP_PROXY_REQUEST_TIMEOUT",
            DEFAULT_REQUEST_TIMEOUT_SECONDS,
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        mcp_host=os.getenv("MCP_HOST", DEFAULT_MCP_HOST).strip() or DEFAULT_MCP_HOST,
        mcp_port=_read_port("MCP_PORT", DEFAULT_MCP_PORT),
        mcp_path=_read_path("MCP_PATH", DEFAULT_MCP_PATH),
        stateless_http=_read_bool("MCP_STATELESS_HTTP", True),
    )
