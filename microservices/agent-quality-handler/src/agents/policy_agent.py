# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Policy Agent — generates inspection policies from detection data.

In LLM mode:  calls the configured inference backend via the llm_client wrapper.
In fallback mode: applies threshold-based rules from policy_fallback.json.
"""

import json
import logging
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader

log = logging.getLogger(__name__)


def run(
    use_case_id: str,
    config: dict,
    prompts_dir: str | None = None,
    min_id: int | None = None,
    max_id: int | None = None,
) -> dict[str, Any]:
    """Return a policy dict based on current detections."""
    summary = storage_client.get_summary(min_id=min_id, max_id=max_id) or {}
    if not isinstance(summary, dict):
        summary = {}

    if llm_client.is_fallback_mode():
        return _fallback_policy(summary, config)

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    policy_instructions = prompt_loader.get_section(use_case_id, "POLICY", prompts_dir)

    policy_config = config.get("policy", {})
    non_actionable = _get_non_actionable_classes(policy_config)
    filtered_summary = {k: v for k, v in summary.items() if k not in non_actionable}

    selection_prompt = _build_selection_prompt(policy_config, filtered_summary)
    user_message = (
        f"{policy_instructions}\n\n"
        f"{selection_prompt}"
    )
    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=512)
    log.info("Policy agent LLM response received (%d chars)", len(raw))
    return {"policy": raw, "mode": "llm", "summary": summary}


def _get_non_actionable_classes(policy_config: dict) -> set[str]:
    """Return configured non-actionable labels when present."""
    if not isinstance(policy_config, dict):
        return set()
    return set(policy_config.get("non_actionable_classes", []))


def _get_priority_thresholds(policy_config: dict) -> dict[str, dict[str, Any]]:
    """Normalize threshold config for both detailed and generic agent YAMLs."""
    if not isinstance(policy_config, dict):
        return {}

    configured = policy_config.get("priority_thresholds", {})
    if configured:
        return configured

    alert_threshold = float(policy_config.get("alert_threshold", 0.0))
    defect_classes = list(policy_config.get("defect_classes", []))
    critical_classes = list(policy_config.get("critical_classes", []))
    if not defect_classes and not critical_classes:
        return {}

    thresholds: dict[str, dict[str, Any]] = {}
    if critical_classes:
        thresholds["critical"] = {
            "min_avg_confidence": alert_threshold,
            "classes": critical_classes,
        }

    remaining = [cls for cls in defect_classes if cls not in critical_classes]
    if remaining:
        thresholds["high"] = {
            "min_avg_confidence": alert_threshold,
            "classes": remaining,
        }

    return thresholds


def _build_selection_prompt(policy_config: dict, summary: dict | None = None) -> str:
    """Inject thresholds and raw summary JSON; LLM applies the evaluation procedure."""
    priority_thresholds = _get_priority_thresholds(policy_config)

    threshold_lines: list[str] = []
    for tier, cfg in priority_thresholds.items():
        if not isinstance(cfg, dict):
            continue
        min_conf = float(cfg.get("min_avg_confidence", 0.0))
        classes = ", ".join(str(cls) for cls in cfg.get("classes", []))
        threshold_lines.append(f"  {str(tier).upper()} (min_required={min_conf:.4f}): {classes}")

    lines = ["Threshold rules:"]
    lines.extend(threshold_lines)
    lines.append("")
    lines.append("Detection summary (JSON):")
    lines.append(json.dumps(summary or {}, indent=2))
    return "\n".join(lines) + "\n\n"


def _fallback_policy(summary: dict, config: dict) -> dict[str, Any]:
    fallback = llm_client.load_fallback_policy() or {}
    thresholds = fallback.get("thresholds", {})
    actions = fallback.get("actions", {})
    action_priority = {
        "MONITOR": 1,
        "SCHEDULE_MAINTENANCE": 2,
        "HALT_PIPELINE": 3,
    }
    violations: list[dict] = []
    for cls_stat in summary.get("by_class", []):
        if not isinstance(cls_stat, dict):
            continue
        label = cls_stat.get("label")
        if not label:
            continue
        avg_conf = float(cls_stat.get("avg_confidence", 0.0))
        threshold = float(thresholds.get(label, {}).get("alert_above", 0.7))
        if avg_conf >= threshold:
            violations.append({
                "label": label,
                "avg_confidence": avg_conf,
                "threshold": threshold,
                "action": actions.get(label, fallback.get("default_action", "MONITOR")),
            })
    recommendation = fallback.get("default_action", "MONITOR")
    if violations:
        recommendation = max(
            (violation["action"] for violation in violations),
            key=lambda action: action_priority.get(action, 0),
        )
    return {
        "mode": "fallback",
        "violations": violations,
        "recommendation": recommendation,
    }
