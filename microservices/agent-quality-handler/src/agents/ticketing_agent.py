# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Ticketing Agent — creates maintenance tickets from analysis and policy outputs."""

import json
import logging
import datetime
from typing import Any

from ..utility import llm_client, prompt_loader

log = logging.getLogger(__name__)


def run(
    use_case_id: str,
    config: dict,
    policy_result: dict,
    analysis_result: dict,
    prompts_dir: str | None = None,
) -> dict[str, Any]:
    """Generate a maintenance ticket from policy + analysis outputs."""
    if llm_client.is_fallback_mode():
        return _fallback_ticket(policy_result, analysis_result)

    # Try to get a TICKETING section; fall back to ANALYSIS section prompt
    try:
        section_text = prompt_loader.get_section(use_case_id, "TICKETING", prompts_dir)
    except KeyError:
        section_text = "Generate a maintenance ticket with priority, summary, and recommended action."

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)

    user_message = (
        f"{section_text}\n\n"
        f"Policy result:\n{json.dumps(policy_result, indent=2)}\n\n"
        f"Analysis result:\n{json.dumps(analysis_result, indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=300)
    log.info("Ticketing agent LLM response received (%d chars)", len(raw))
    return {"ticket": raw, "mode": "llm"}


def _fallback_ticket(policy_result: dict, analysis_result: dict) -> dict[str, Any]:
    violations = policy_result.get("violations", [])
    total = analysis_result.get("total_detections", 0)
    priority = "HIGH" if violations else ("MEDIUM" if total > 10 else "LOW")
    return {
        "mode": "fallback",
        "ticket_id": f"TICKET-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "priority": priority,
        "summary": f"{total} detections found; {len(violations)} policy violations.",
        "violations": violations,
        "recommended_action": policy_result.get("recommendation", "Review required"),
    }
