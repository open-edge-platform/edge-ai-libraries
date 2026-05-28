"""YAML configuration loader for subscription and service settings."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class HashConfig:
    algorithm: str = "sha1"
    truncate: int = 16


@dataclass
class DedupConfig:
    enabled: bool = False
    strategy: str = "field_hash"
    fields: list[str] = field(default_factory=list)
    window_seconds: int = 30
    on_missing: str = "skip"
    hash: HashConfig = field(default_factory=HashConfig)


@dataclass
class DeliveryTarget:
    type: str = "log"
    url: str = ""
    topic: str = ""


@dataclass
class SubscriptionConfig:
    alert_type: str = ""
    dedup: DedupConfig = field(default_factory=DedupConfig)
    delivery: list[DeliveryTarget] = field(default_factory=list)


@dataclass
class ServiceConfig:
    retry_attempts: int = 3
    retry_interval_seconds: int = 5


@dataclass
class AppConfig:
    service: ServiceConfig = field(default_factory=ServiceConfig)
    subscriptions: list[SubscriptionConfig] = field(default_factory=list)

    def get_subscription(self, alert_type: str) -> SubscriptionConfig | None:
        for sub in self.subscriptions:
            if sub.alert_type == alert_type:
                return sub
        return None


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_VAR_PATTERN.sub(_replacer, value)


def _resolve_dict(data: Any) -> Any:
    """Recursively resolve environment variables in a dict/list structure."""
    if isinstance(data, str):
        return _resolve_env_vars(data)
    if isinstance(data, dict):
        return {k: _resolve_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_dict(item) for item in data]
    return data


def _parse_delivery(raw: list[dict]) -> list[DeliveryTarget]:
    targets: list[DeliveryTarget] = []
    for item in raw:
        targets.append(
            DeliveryTarget(
                type=item.get("type", "log"),
                url=item.get("url", ""),
                topic=item.get("topic", ""),
            )
        )
    return targets


def _parse_dedup(raw: dict) -> DedupConfig:
    hash_raw = raw.get("hash", {})
    return DedupConfig(
        enabled=raw.get("enabled", False),
        strategy=raw.get("strategy", "field_hash"),
        fields=raw.get("fields", []),
        window_seconds=raw.get("window_seconds", 30),
        on_missing=raw.get("on_missing", "skip"),
        hash=HashConfig(
            algorithm=hash_raw.get("algorithm", "sha1"),
            truncate=hash_raw.get("truncate", 16),
        ),
    )


def _build_delivery_from_env(handlers_csv: str) -> list[DeliveryTarget]:
    """Build delivery targets from a comma-separated env variable."""
    targets: list[DeliveryTarget] = []
    for handler in handlers_csv.split(","):
        handler = handler.strip().lower()
        if not handler:
            continue
        target = DeliveryTarget(type=handler)
        if handler == "mqtt":
            target.topic = ""  # uses default topic from handler
        if handler == "webhook":
            target.url = os.environ.get("WEBHOOK_URL", "")
        targets.append(target)
    return targets


def load_config(path: str) -> AppConfig:
    """Load and parse the YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    raw = _resolve_dict(raw)

    service_raw = raw.get("service", {})
    service_cfg = ServiceConfig(
        retry_attempts=service_raw.get("retry_attempts", 3),
        retry_interval_seconds=service_raw.get("retry_interval_seconds", 5),
    )

    # If DELIVERY_HANDLERS env var is set, use it for all subscriptions
    env_handlers = os.environ.get("DELIVERY_HANDLERS", "").strip()
    env_delivery = _build_delivery_from_env(env_handlers) if env_handlers else None

    subscriptions: list[SubscriptionConfig] = []
    for sub_raw in raw.get("subscriptions", []):
        dedup_cfg = _parse_dedup(sub_raw.get("dedup", {}))
        delivery_targets = (
            env_delivery if env_delivery is not None
            else _parse_delivery(sub_raw.get("delivery", []))
        )
        subscriptions.append(
            SubscriptionConfig(
                alert_type=sub_raw.get("alert_type", ""),
                dedup=dedup_cfg,
                delivery=delivery_targets,
            )
        )

    return AppConfig(service=service_cfg, subscriptions=subscriptions)
