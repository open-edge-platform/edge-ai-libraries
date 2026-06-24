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
    summary = storage_client.get_summary()

    if llm_client.is_fallback_mode():
        return _fallback_evidence(summary)

    # Fetch top-5 highest-confidence detections per class for the audit trail.
    # This replaces fetching all records — the prompt only needs stats + exemplars.
    retention = config.get("evidence", {}).get("retention_frames", 1000)
    top_detections: dict[str, list] = {}
    for cls in summary.get("by_class", []):
        label = cls["label"]
        records = storage_client.get_detections(label=label, min_confidence=0.0, limit=5)
        top_detections[label] = [
            {"frame_id": d["frame_id"], "confidence": round(d["confidence"], 3),
             "bbox": [d["x"], d["y"], d["width"], d["height"]]}
            for d in records
        ]

    evidence_data = {
        "summary": summary,
        "top_detections_per_class": top_detections,
        "retention_frames": retention,
    }

    system_prompt = prompt_loader.get_section(use_case_id, "SYSTEM", prompts_dir)
    evidence_instructions = prompt_loader.get_section(use_case_id, "EVIDENCE", prompts_dir)

    total_detections = sum(c.get("count", 0) for c in summary.get("by_class", []))
    user_message = (
        f"{evidence_instructions}\n\n"
        f"Total detections: {total_detections}\n"
        f"Evidence data:\n{json.dumps(evidence_data, indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=600)
    log.info("Evidence agent LLM response received (%d chars)", len(raw))
    return {"evidence": raw, "mode": "llm", "record_count": total_detections}


def _fallback_evidence(summary: dict) -> dict[str, Any]:
    by_class = summary.get("by_class", [])
    return {
        "mode": "fallback",
        "record_count": sum(c.get("count", 0) for c in by_class),
        "unique_labels": [c["label"] for c in by_class],
        "max_confidence": max((c.get("max_confidence", 0) for c in by_class), default=0),
    }
