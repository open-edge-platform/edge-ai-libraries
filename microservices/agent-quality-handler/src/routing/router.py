# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Severity router — classifies detection batches and determines agent routes.

In LLM mode the router calls the LLM with detection summary data and a
classification prompt.  In fallback mode it applies deterministic threshold
rules from the agents config.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader
from .agent_registry import load_registry
from .route_utils import normalize_route

log = logging.getLogger(__name__)


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Maps severity to the ordered list of agents that should execute.
SEVERITY_ROUTES: dict[Severity, list[str]] = {
    Severity.LOW: ["policy", "ticketing"],
    Severity.MEDIUM: ["policy", "analysis", "ticketing"],
    Severity.HIGH: ["policy", "analysis", "evidence", "ticketing"],
    Severity.CRITICAL: ["policy", "analysis", "evidence", "ticketing"],
}


class RoutingDecision:
    """Encapsulates the outcome of severity classification."""

    __slots__ = ("severity", "reason", "route", "summary")

    def __init__(
        self,
        severity: Severity,
        reason: str,
        route: list[str],
        summary: dict[str, Any],
    ):
        self.severity = severity
        self.reason = reason
        self.route = route
        self.summary = summary

    def should_run(self, agent: str) -> bool:
        return agent in self.route

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "reason": self.reason,
            "route": self.route,
        }


def classify(
    use_case_id: str,
    config: dict[str, Any],
    prompts_dir: str | None = None,
    min_id: int | None = None,
    max_id: int | None = None,
) -> RoutingDecision:
    """Classify the severity of a detection batch and return a routing decision."""
    summary = storage_client.get_summary(min_id=min_id, max_id=max_id)

    if llm_client.is_fallback_mode():
        return _fallback_classify(summary, config)

    return _llm_classify(use_case_id, summary, prompts_dir, config)


def _llm_classify(
    use_case_id: str,
    summary: dict[str, Any],
    prompts_dir: str | None,
    config: dict[str, Any] | None = None,
) -> RoutingDecision:
    """Use the LLM to classify severity."""
    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    router_instructions = prompt_loader.get_section(
        use_case_id, "ROUTER", prompts_dir
    )

    user_message = (
        f"{router_instructions}\n\n"
        f"Detection summary:\n{json.dumps(summary, indent=2)}"
    )

    raw = llm_client.call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=256,
        temperature=0.1,
    )
    log.info("Router LLM response received (%d chars)", len(raw))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code fences
        import re

        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            log.warning("Router LLM returned unparseable response, defaulting to HIGH")
            return RoutingDecision(
                severity=Severity.HIGH,
                reason="LLM response could not be parsed; defaulting to HIGH for safety",
                route=SEVERITY_ROUTES[Severity.HIGH],
                summary=summary,
            )

    severity_str = parsed.get("severity", "HIGH").upper()
    try:
        severity = Severity(severity_str)
    except ValueError:
        log.warning("Unknown severity %r from LLM, defaulting to HIGH", severity_str)
        severity = Severity.HIGH

    reason = parsed.get("reason", "Classified by LLM")
    raw_route = parsed.get("route", SEVERITY_ROUTES[severity])
    if not isinstance(raw_route, list):
        raw_route = SEVERITY_ROUTES[severity]

    # Normalize: drop unknown agent names, dedupe, and guarantee ticketing
    # runs after policy/analysis regardless of the order the LLM returned.
    route = normalize_route(raw_route, load_registry(config) if config is not None else None)
    if not route:
        route = SEVERITY_ROUTES[severity]
    elif route != raw_route:
        log.info(
            "Router route normalized for dependency-safety/dedup: "
            "llm_route=%s effective_route=%s",
            raw_route,
            route,
        )

    return RoutingDecision(
        severity=severity, reason=reason, route=route, summary=summary
    )


def _fallback_classify(
    summary: dict[str, Any], config: dict[str, Any]
) -> RoutingDecision:
    """Rule-based severity classification using config thresholds."""
    by_class = summary.get("by_class", [])
    total_count = sum(c.get("count", 0) for c in by_class)
    critical_classes = set(
        config.get("policy", {}).get("critical_classes", ["Rupture", "Disconnect"])
    )

    has_critical_high_conf = False
    has_critical_any = False
    max_confidence = 0.0

    for cls_stat in by_class:
        label = cls_stat.get("label", "")
        avg_conf = cls_stat.get("avg_confidence", 0.0)
        cls_max = cls_stat.get("max_confidence", 0.0)
        max_confidence = max(max_confidence, cls_max)

        if label in critical_classes:
            has_critical_any = True
            if cls_max >= 0.8:
                has_critical_high_conf = True

    # Apply classification rules
    if has_critical_high_conf or total_count > 50:
        severity = Severity.CRITICAL
        reason = _build_reason(
            severity, total_count, has_critical_high_conf, max_confidence
        )
    elif has_critical_any or total_count > 20:
        severity = Severity.HIGH
        reason = _build_reason(
            severity, total_count, has_critical_any, max_confidence
        )
    elif total_count > 5 or max_confidence >= 0.6:
        severity = Severity.MEDIUM
        reason = _build_reason(severity, total_count, False, max_confidence)
    else:
        severity = Severity.LOW
        reason = _build_reason(severity, total_count, False, max_confidence)

    return RoutingDecision(
        severity=severity,
        reason=reason,
        route=SEVERITY_ROUTES[severity],
        summary=summary,
    )


def _build_reason(
    severity: Severity,
    total: int,
    has_critical: bool,
    max_conf: float,
) -> str:
    parts = [f"{total} total detection(s)"]
    if has_critical:
        parts.append("critical-class detections present")
    parts.append(f"max confidence {max_conf:.3f}")
    return f"{severity.value}: {'; '.join(parts)}"
