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
    summary = storage_client.get_summary(min_id=min_id, max_id=max_id)

    if llm_client.is_fallback_mode():
        return _fallback_policy(summary, config)

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    policy_instructions = prompt_loader.get_section(use_case_id, "POLICY", prompts_dir)

    policy_config = config.get("policy", {})
    priority_thresholds = policy_config.get("priority_thresholds", {})
    qualifying_defects: list[dict] = []
    qualifying_section = ""
    if priority_thresholds:
        qualifying_defects = _compute_qualifying_defects(summary, policy_config)
        qualifying_section = _format_qualifying_prompt(qualifying_defects)

    user_message = (
        f"{policy_instructions}\n\n"
        f"{qualifying_section}"
        f"Detection summary:\n{json.dumps(summary, indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=512)
    log.info("Policy agent LLM response received (%d chars)", len(raw))
    return {"policy": raw, "mode": "llm", "summary": summary, "qualifying_defects": qualifying_defects}


def _compute_qualifying_defects(summary: dict, policy_config: dict) -> list[dict]:
    """Return qualifying defect dicts sorted by tier → count desc → confidence desc."""
    non_actionable = set(policy_config.get("non_actionable_classes", []))
    priority_thresholds = policy_config.get("priority_thresholds", {})
    tier_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}\

    class_to_tier: dict[str, tuple[str, float]] = {}
    for tier, cfg in priority_thresholds.items():
        min_conf = float(cfg.get("min_avg_confidence", 0.0))
        for cls in cfg.get("classes", []):
            class_to_tier[cls] = (tier.upper(), min_conf)

    qualifying = []
    for label, stats in summary.items():
        if label in non_actionable or label not in class_to_tier:
            continue
        avg_conf = float(stats.get("avg_confidence", 0.0))
        tier, min_conf = class_to_tier[label]
        if avg_conf >= min_conf:
            qualifying.append({
                "label": label,
                "tier": tier,
                "avg_confidence": avg_conf,
                "count": stats.get("count", 0),
                "_order": (tier_order.get(tier.lower(), 99), -stats.get("count", 0), -avg_conf),
            })

    qualifying.sort(key=lambda x: x["_order"])
    for q in qualifying:
        del q["_order"]
    return qualifying


def _format_qualifying_prompt(qualifying: list[dict]) -> str:
    """Format the pre-computed list into a compact prompt block for the policy LLM."""
    if not qualifying:
        return "Qualifying defects: none — report No Policy Violation, No Action Required.\n\n"

    lines = ["Qualifying defects (pre-computed — use these values exactly in your output):"]
    for q in qualifying:
        lines.append(f"  - {q['label']} | Priority: {q['tier']} | Confidence: {q['avg_confidence']} | Count: {q['count']}")
    primary = qualifying[0]
    lines.append(f"Primary Defect: {primary['label']} | Priority: {primary['tier']} | Confidence: {primary['avg_confidence']}")
    return "\n".join(lines) + "\n\n"


def _build_qualifying_section(summary: dict, policy_config: dict) -> str:
    """Kept for compatibility — prefer _compute_qualifying_defects + _format_qualifying_prompt."""
    return _format_qualifying_prompt(_compute_qualifying_defects(summary, policy_config))


def _fallback_policy(summary: dict, config: dict) -> dict[str, Any]:
    fallback = llm_client.load_fallback_policy()
    thresholds = fallback.get("thresholds", {})
    actions = fallback.get("actions", {})
    action_priority = {
        "MONITOR": 1,
        "SCHEDULE_MAINTENANCE": 2,
        "HALT_PIPELINE": 3,
    }
    violations: list[dict] = []
    for cls_stat in summary.get("by_class", []):
        label = cls_stat["label"]
        avg_conf = cls_stat.get("avg_confidence", 0.0)
        threshold = thresholds.get(label, {}).get("alert_above", 0.7)
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
