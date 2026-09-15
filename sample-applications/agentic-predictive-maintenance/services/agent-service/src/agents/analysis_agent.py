# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Analysis Agent — produces a structured analysis report of detected defects."""

import json
import logging
from collections import Counter, defaultdict
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
        f"Detection statistics:\n{json.dumps(_compact_stats(detections), indent=2)}"
    )

    raw = llm_client.call_llm(system_prompt=system_prompt, user_message=user_message, max_tokens=800)
    log.info("Analysis agent LLM response received (%d chars)", len(raw))
    return {"report": raw, "mode": "llm", "total_detections": len(detections)}


def _compact_stats(detections: list[dict]) -> dict:
    """Summarise detections into a compact structure instead of sending raw records."""
    # Deduplicate by (frame_id, label) — looping video creates exact duplicates
    seen: set = set()
    unique: list[dict] = []
    for d in detections:
        key = (d.get("frame_id"), d.get("label"))
        if key not in seen:
            seen.add(key)
            unique.append(d)

    by_class: dict[str, list[float]] = defaultdict(list)
    by_frame: dict[int, list[str]] = defaultdict(list)
    for d in unique:
        label = d.get("label", "unknown")
        by_class[label].append(d.get("confidence", 0.0))
        by_frame[int(d.get("frame_id", 0))].append(label)

    class_stats = []
    for label, confs in sorted(by_class.items()):
        class_stats.append({
            "label": label,
            "count": len(confs),
            "avg_confidence": round(sum(confs) / len(confs), 3),
            "max_confidence": round(max(confs), 3),
            "top_frames": sorted(
                {fid for fid, labels in by_frame.items() if label in labels}
            )[:5],
        })

    frame_ids = sorted(by_frame.keys())
    return {
        "total_unique_detections": len(unique),
        "total_frames_with_detections": len(frame_ids),
        "frame_range": {"first": frame_ids[0], "last": frame_ids[-1]} if frame_ids else {},
        "by_class": class_stats,
    }


def _fallback_analysis(detections: list[dict]) -> dict[str, Any]:
    from collections import Counter
    counts = Counter(d["label"] for d in detections)
    return {
        "mode": "fallback",
        "total_detections": len(detections),
        "by_class": [{"label": k, "count": v} for k, v in counts.most_common()],
        "high_confidence": [d for d in detections if d.get("confidence", 0) >= 0.8],
    }
