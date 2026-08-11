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

    user_message = (
        f"{policy_instructions}\n\n"
        f"Detection summary:\n{json.dumps(summary, indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=512)
    log.info("Policy agent LLM response received (%d chars)", len(raw))
    return {"policy": raw, "mode": "llm", "summary": summary}


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
