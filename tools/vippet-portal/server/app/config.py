"""Configuration for the ViPPET Portal aggregation service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: No instances are seeded by default; register them through `PORTAL_INSTANCES`
#: or the Instances page.
DEFAULT_SEED_INSTANCES: tuple[str, ...] = ()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _parse_seed_instances(raw: str | None) -> list[tuple[str | None, str]]:
    """Parse `Name=url,Name2=url2` (name optional) into (name, url) pairs."""
    source = raw.split(",") if raw else list(DEFAULT_SEED_INSTANCES)
    parsed: list[tuple[str | None, str]] = []
    for entry in source:
        entry = entry.strip()
        if not entry:
            continue
        name, separator, url = entry.partition("=")
        if separator:
            parsed.append((name.strip() or None, url.strip()))
        else:
            parsed.append((None, name))
    return parsed


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("PORTAL_DB_PATH", _PROJECT_ROOT / "shared" / "db" / "app.db")
        )
    )
    #: Per-request timeout when talking to a single ViPPET instance.
    request_timeout: float = field(
        default_factory=lambda: float(os.environ.get("PORTAL_REQUEST_TIMEOUT", "15"))
    )
    #: How long aggregated fan-out responses stay cached, in seconds.
    cache_ttl: int = field(default_factory=lambda: _env_int("PORTAL_CACHE_TTL", 15))
    seed_instances: tuple[tuple[str | None, str], ...] = field(
        default_factory=lambda: tuple(
            _parse_seed_instances(os.environ.get("PORTAL_INSTANCES"))
        )
    )

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
