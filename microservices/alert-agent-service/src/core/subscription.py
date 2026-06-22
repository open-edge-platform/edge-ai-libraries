# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Optional YAML subscription config for default per-alert routing.

Supported formats:

Agent-native format:
  subscriptions:
    - alert_name: "Fire Detection"
      tools: ["log_alert", "trigger_webhook", "capture_snapshot"]
      tool_arguments:
        trigger_webhook:
          url: "${WEBHOOK_URL}"
      dedup:
        enabled: true
        strategy: field_hash
        fields: ["source_id"]
        window_seconds: 30
        on_missing: skip
      escalation:
        threshold_consecutive: 3
        additional_tools: ["publish_mqtt"]

Alert-service format:
  service:
    retry_attempts: 3
    retry_interval_seconds: 5
  subscriptions:
    - alert_type: CONCEALMENT
      dedup:
        enabled: true
        strategy: field_hash
        fields: ["metadata.poi_id", "metadata.camera_id"]
        window_seconds: 30
        on_missing: skip
        hash:
          algorithm: sha1
          truncate: 16
      delivery:
        - type: webhook
          url: "${WEBHOOK_URL}"
        - type: mqtt
          topic: alerts/concealment
        - type: log

The loader accepts both formats, ignores the alert-service top-level `service`
section, and normalizes alert-service `dedup.hash` / `delivery` entries into the
agent-native schema.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    return _ENV_VAR_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)


def _resolve(data: Any) -> Any:
    if isinstance(data, str):
        return _resolve_env_vars(data)
    if isinstance(data, dict):
        return {k: _resolve(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve(item) for item in data]
    return data


@dataclass
class SubscriptionEntry:
    alert_name: str
    tools: List[str] = field(default_factory=lambda: ["log_alert"])
    tool_arguments: Dict[str, dict] = field(default_factory=dict)
    dedup: Optional[dict] = None
    escalation: Optional[dict] = None


@dataclass
class SubscriptionConfig:
    subscriptions: List[SubscriptionEntry] = field(default_factory=list)

    def get(self, alert_name: Optional[str]) -> Optional[SubscriptionEntry]:
        if not alert_name:
            return None
        for sub in self.subscriptions:
            if sub.alert_name == alert_name:
                return sub
        return None


_EMPTY_CONFIG = SubscriptionConfig()


def _normalize_dedup(dedup: Any) -> Optional[dict]:
    if not isinstance(dedup, dict):
        return dedup

    normalized = dict(dedup)
    if "hash_algorithm" not in normalized and isinstance(normalized.get("hash"), dict):
        hash_cfg = normalized.pop("hash")
        if "algorithm" in hash_cfg:
            normalized["hash_algorithm"] = hash_cfg["algorithm"]
        if "truncate" in hash_cfg:
            normalized["hash_truncate"] = hash_cfg["truncate"]
    else:
        normalized.pop("hash", None)

    return normalized


def _normalize_delivery(sub: dict) -> tuple[List[str], Dict[str, dict]]:
    if "tools" in sub:
        tools = sub.get("tools")
        if not isinstance(tools, list):
            tools = ["log_alert"]
        tool_arguments = sub.get("tool_arguments")
        if not isinstance(tool_arguments, dict):
            tool_arguments = {}
        return tools, tool_arguments

    tools: List[str] = []
    tool_arguments: Dict[str, dict] = {}

    delivery = sub.get("delivery") or []
    if not isinstance(delivery, list):
        delivery = []

    for item in delivery:
        if not isinstance(item, dict):
            continue

        delivery_type = item.get("type")
        if delivery_type == "log":
            tools.append("log_alert")
        elif delivery_type == "webhook":
            tools.append("trigger_webhook")
            if item.get("url"):
                tool_arguments["trigger_webhook"] = {"url": item["url"]}
        elif delivery_type == "mqtt":
            tools.append("publish_mqtt")
            if item.get("topic"):
                tool_arguments["publish_mqtt"] = {"topic_override": item["topic"]}

    return tools or ["log_alert"], tool_arguments


def load_subscription_config(path: str) -> SubscriptionConfig:
    config_path = Path(path)
    if not config_path.exists():
        logger.debug("Subscription config not found at %s — running without defaults", path)
        return _EMPTY_CONFIG

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        raw = _resolve(raw)
    except Exception as exc:
        logger.error("Failed to load subscription config %s: %s", path, exc)
        return _EMPTY_CONFIG

    entries: List[SubscriptionEntry] = []
    for sub in raw.get("subscriptions", []):
        if not isinstance(sub, dict):
            continue

        alert_name = sub.get("alert_name") or sub.get("alert_type") or ""
        if not alert_name:
            continue
        tools, tool_arguments = _normalize_delivery(sub)
        entries.append(SubscriptionEntry(
            alert_name=alert_name,
            tools=tools,
            tool_arguments=tool_arguments,
            dedup=_normalize_dedup(sub.get("dedup")),
            escalation=sub.get("escalation"),
        ))

    logger.info("Loaded %d subscription entries from %s", len(entries), path)
    return SubscriptionConfig(subscriptions=entries)
