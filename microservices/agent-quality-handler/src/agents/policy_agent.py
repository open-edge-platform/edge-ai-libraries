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

    config = config or {}
    policy_config = config.get("policy", {}) or {}
    non_actionable = _get_non_actionable_classes(policy_config)
    filtered_summary = {k: v for k, v in summary.items() if k not in non_actionable}
    qualifying_defects = _compute_qualifying_defects(filtered_summary, policy_config)
    selected_defect = _select_primary_defect(filtered_summary, policy_config)

    if selected_defect is not None:
        policy_text = _build_policy_output(filtered_summary, policy_config, selected_defect)
        return {"policy": policy_text, "mode": "llm", "summary": summary, "qualifying_defects": qualifying_defects}

    selection_prompt = _build_selection_prompt(policy_config, selected_defect)
    user_message = (
        f"{policy_instructions}\n\n"
        f"{selection_prompt}"
        f"Detection summary:\n{json.dumps(filtered_summary, indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=512)
    log.info("Policy agent LLM response received (%d chars)", len(raw))
    return {"policy": raw, "mode": "llm", "summary": summary, "qualifying_defects": qualifying_defects}


def _compute_qualifying_defects(summary: dict, policy_config: dict) -> list[dict]:
    """Return qualifying defect dicts sorted by tier → count desc → confidence desc."""
    if not isinstance(summary, dict):
        return []

    policy_config = policy_config or {}
    non_actionable = set(policy_config.get("non_actionable_classes", []) or [])
    priority_thresholds = policy_config.get("priority_thresholds", {}) or {}
    tier_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}\

    class_to_tier: dict[str, tuple[str, float]] = {}
    for tier, cfg in priority_thresholds.items():
        if not isinstance(cfg, dict):
            continue
        min_conf = float(cfg.get("min_avg_confidence", 0.0) or 0.0)
        for cls in cfg.get("classes", []) or []:
            class_to_tier[str(cls)] = (str(tier).upper(), min_conf)

    qualifying = []
    for label, stats in summary.items():
        if not isinstance(stats, dict):
            continue
        if label in non_actionable or label not in class_to_tier:
            continue
        avg_conf = float(stats.get("avg_confidence", 0.0) or 0.0)
        tier, min_conf = class_to_tier.get(label, (None, 0.0))
        if tier is None or avg_conf < min_conf:
            continue
        qualifying.append({
            "label": label,
            "tier": tier,
            "avg_confidence": avg_conf,
            "count": int(stats.get("count", 0) or 0),
        })

    if not qualifying:
        return []

    top_tier = min(qualifying, key=lambda item: tier_order.get(item["tier"].lower(), 99))["tier"]
    qualifying = [item for item in qualifying if item["tier"] == top_tier]
    qualifying.sort(key=lambda item: (-item["avg_confidence"], -item["count"], item["label"]))
    return qualifying


def _get_non_actionable_classes(policy_config: dict) -> set[str]:
    """Return configured non-actionable labels when present."""
    if not isinstance(policy_config, dict):
        return set()
    return set(policy_config.get("non_actionable_classes", []) or [])


def _get_priority_thresholds(policy_config: dict) -> dict[str, dict[str, Any]]:
    """Normalize threshold config for both detailed and generic agent YAMLs."""
    if not isinstance(policy_config, dict):
        return {}

    configured = policy_config.get("priority_thresholds", {}) or {}
    if configured:
        return configured

    alert_threshold = float(policy_config.get("alert_threshold", 0.0) or 0.0)
    defect_classes = list(policy_config.get("defect_classes", []) or [])
    critical_classes = list(policy_config.get("critical_classes", []) or [])
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

    if not thresholds and defect_classes:
        thresholds["high"] = {
            "min_avg_confidence": alert_threshold,
            "classes": defect_classes,
        }

    return thresholds


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


def _select_primary_defect(summary: dict, policy_config: dict) -> str | None:
    """Select the primary defect from the highest active tier by highest avg_confidence."""
    qualifying = _compute_qualifying_defects(summary, policy_config)
    if not qualifying:
        return None

    qualifying.sort(key=lambda item: (-item["avg_confidence"], -item["count"], item["label"]))
    return qualifying[0]["label"]


def _build_policy_output(summary: dict, policy_config: dict, selected_defect: str) -> str:
    """Build deterministic policy output using the selected defect only."""
    if not isinstance(summary, dict):
        summary = {}
    policy_config = policy_config or {}
    priority_thresholds = _get_priority_thresholds(policy_config)
    tier_name = None
    confidence = 0.0
    selected_stats = summary.get(selected_defect, {}) if isinstance(summary, dict) else {}

    for tier, cfg in priority_thresholds.items():
        if not isinstance(cfg, dict):
            continue
        classes = cfg.get("classes", []) or []
        if selected_defect in classes:
            tier_name = str(tier).upper()
            confidence = float(selected_stats.get("avg_confidence", 0.0) or 0.0)
            break

    if tier_name is None:
        tier_name = "HIGH"
        confidence = float(selected_stats.get("avg_confidence", 0.0) or 0.0)

    return (
        "Policy Status: Policy Violation Detected\n"
        f"Priority: {tier_name}\n"
        f"Primary Defect: {selected_defect}\n"
        f"Reported Confidence: {confidence}\n"
        "Policy Decision: Action Required"
    )


def _build_selection_prompt(policy_config: dict, selected_defect: str | None) -> str:
    """Compact fallback prompt directing the model to mirror the selected defect only."""
    non_actionable = _get_non_actionable_classes(policy_config)
    priority_thresholds = _get_priority_thresholds(policy_config)
    lines = [
        "Selection rule: do not print a Qualifying Defects list.",
        "Evaluate only actionable classes and exclude configured non-actionable classes before scoring.",
        "Respect the threshold rules exactly. A class below its tier minimum is not eligible to be selected.",
        "Output must contain only: Policy Status, Priority, Primary Defect, Reported Confidence, Policy Decision.",
        "Do not include any Qualifying Defects section, any list of defect names, or any extra summary text.",
    ]
    if non_actionable:
        lines.append(f"Configured non-actionable classes: {', '.join(non_actionable)}")
    if selected_defect:
        lines.append(f"The selected primary defect is fixed to: {selected_defect}. Use this exact class name in the output.")
    else:
        lines.append("No actionable defect qualifies; return Policy Status: No Policy Violation and Policy Decision: No Action Required.")
    if priority_thresholds:
        lines.append("\nPriority thresholds — apply exactly as written:")
        for tier, cfg in priority_thresholds.items():
            if not isinstance(cfg, dict):
                continue
            min_conf = float(cfg.get("min_avg_confidence", 0.0) or 0.0)
            classes = ", ".join(str(cls) for cls in (cfg.get("classes", []) or []))
            lines.append(f"- {str(tier).upper()} (min avg_confidence {min_conf:.2f}): {classes}")
    return "\n".join(lines) + "\n\n"


def _fallback_policy(summary: dict, config: dict) -> dict[str, Any]:
    fallback = llm_client.load_fallback_policy() or {}
    thresholds = fallback.get("thresholds", {}) or {}
    actions = fallback.get("actions", {}) or {}
    action_priority = {
        "MONITOR": 1,
        "SCHEDULE_MAINTENANCE": 2,
        "HALT_PIPELINE": 3,
    }
    summary = summary or {}
    violations: list[dict] = []
    for cls_stat in summary.get("by_class", []) or []:
        if not isinstance(cls_stat, dict):
            continue
        label = cls_stat.get("label")
        if not label:
            continue
        avg_conf = float(cls_stat.get("avg_confidence", 0.0) or 0.0)
        threshold = float((thresholds.get(label, {}) or {}).get("alert_above", 0.7) or 0.7)
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
