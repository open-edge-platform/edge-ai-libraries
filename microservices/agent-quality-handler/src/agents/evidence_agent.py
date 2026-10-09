# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evidence Agent — builds an audit trail of defect evidence for compliance."""

import json
import logging
from typing import Any

from ..utility import llm_client, storage_client, prompt_loader
from .context import AgentContext

log = logging.getLogger(__name__)

_BBOX_FIELDS = ("x", "y", "width", "height")
_CORE_FIELDS = {"frame_id", "confidence", "label", *_BBOX_FIELDS}


def _build_detection_entry(d: dict) -> dict:
    """Build one audit-trail entry for a detection record.

    Detections are modality-agnostic: a vision detector supplies bounding-box
    fields (``x``/``y``/``width``/``height``), while a sensor/timeseries or
    fused detector typically does not. When bbox fields are present we use
    them (vision evidence); otherwise any other non-core fields the detector
    attached (e.g. ``sensor_id``, ``value``, ``modality``) are carried through
    as generic metadata so non-visual evidence isn't silently dropped.
    """
    entry: dict[str, Any] = {
        "frame_id": d.get("frame_id"),
        "confidence": round(d.get("confidence", 0.0), 3),
    }
    if all(field in d and d[field] is not None for field in _BBOX_FIELDS):
        entry["bbox"] = [d[field] for field in _BBOX_FIELDS]
    else:
        metadata = {k: v for k, v in d.items() if k not in _CORE_FIELDS and v is not None}
        if metadata:
            entry["metadata"] = metadata
    return entry


def run(context: AgentContext) -> dict[str, Any]:
    """Return a structured evidence record for audit compliance."""
    use_case_id, config, prompts_dir = context.use_case_id, context.config, context.prompts_dir
    summary = storage_client.get_summary(min_id=context.min_id, max_id=context.max_id)

    if llm_client.is_fallback_mode():
        return _fallback_evidence(summary)

    # Fetch top-5 highest-confidence detections per class for the audit trail.
    # This replaces fetching all records — the prompt only needs stats + exemplars.
    retention = config.get("evidence", {}).get("retention_frames", 1000)
    top_detections: dict[str, list] = {}
    for cls in summary.get("by_class", []):
        label = cls["label"]
        records = storage_client.get_detections(
            label=label,
            min_confidence=0.0,
            limit=5,
            min_id=context.min_id,
            max_id=context.max_id,
        )
        top_detections[label] = [_build_detection_entry(d) for d in records]

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
