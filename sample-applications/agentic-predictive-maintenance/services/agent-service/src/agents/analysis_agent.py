# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Analysis Agent — produces a structured analysis report of detected defects."""

import json
import logging
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader

log = logging.getLogger(__name__)


def run(
    use_case_id: str,
    config: dict,
    prompts_dir: str | None = None,
    min_confidence: float = 0.5,
) -> dict[str, Any]:
    """Analyse detections and return a structured report."""
    detections = storage_client.get_detections(min_confidence=min_confidence)

    if llm_client.is_fallback_mode():
        return _fallback_analysis(detections)

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    analysis_instructions = prompt_loader.get_section(use_case_id, "ANALYSIS", prompts_dir)

    user_message = (
        f"{analysis_instructions}\n\n"
        f"Detections ({len(detections)} total):\n{json.dumps(detections[:50], indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message)
    log.info("Analysis agent LLM response received (%d chars)", len(raw))
    return {"report": raw, "mode": "llm", "total_detections": len(detections)}


def _fallback_analysis(detections: list[dict]) -> dict[str, Any]:
    from collections import Counter
    counts = Counter(d["label"] for d in detections)
    return {
        "mode": "fallback",
        "total_detections": len(detections),
        "by_class": [{"label": k, "count": v} for k, v in counts.most_common()],
        "high_confidence": [d for d in detections if d.get("confidence", 0) >= 0.8],
    }
