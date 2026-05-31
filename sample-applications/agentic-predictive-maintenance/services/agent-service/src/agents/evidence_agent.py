# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evidence Agent — builds an audit trail of defect evidence for compliance."""

import json
import logging
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader

log = logging.getLogger(__name__)


def run(
    use_case_id: str,
    config: dict,
    prompts_dir: str | None = None,
) -> dict[str, Any]:
    """Return a structured evidence record for audit compliance."""
    detections = storage_client.get_detections()

    if llm_client.is_fallback_mode():
        return _fallback_evidence(detections)

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    evidence_instructions = prompt_loader.get_section(use_case_id, "EVIDENCE", prompts_dir)

    user_message = (
        f"{evidence_instructions}\n\n"
        f"All detection records ({len(detections)}):\n"
        f"{json.dumps(detections[:100], indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message)
    log.info("Evidence agent LLM response received (%d chars)", len(raw))
    return {"evidence": raw, "mode": "llm", "record_count": len(detections)}


def _fallback_evidence(detections: list[dict]) -> dict[str, Any]:
    return {
        "mode": "fallback",
        "record_count": len(detections),
        "frame_ids": sorted({d["frame_id"] for d in detections}),
        "unique_labels": sorted({d["label"] for d in detections}),
        "max_confidence": max((d.get("confidence", 0) for d in detections), default=0),
    }
