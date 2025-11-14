#!/usr/bin/env python3
"""Utility to recompute qualitative scores for stored aggregated results.
It's a validation and tuning utility that lets you:

1. Replay scoring on existing aggregated results without re-running the full search pipeline
2. Test parameter changes offline before deploying new configuration
3. Debug ranking behavior by comparing original_rank vs. recomputed rank after tuning knobs
4. Verify consistency after code changes to the scoring logic

Scenario 1 - Tuning weights:
# Edit config.yaml or export new AGGREGATION_QUAL_* values
export AGGREGATION_QUAL_MAX_WEIGHT=0.7
export AGGREGATION_QUAL_TOP_WEIGHT=0.3

# See how rankings would shift WITHOUT re-querying VDMS
python scripts/recompute_affregate_scores.py score.json --top 20


Scenario 2 - Validating code changes:
# After modifying calculate_segment_score, quickly verify the new rankings match expectations
python scripts/recompute_affregate_scores.py score.json


Scenario 3 - Understanding contextual boost:
# Try different sigma/boost settings and observe the impact on segments near the global peak
export AGGREGATION_CONTEXT_SIGMA_SECONDS=20.0
python scripts/recompute_affregate_scores.py score.json

Expected format of score:
{
    "id": null,
    "metadata": {
    "video_id": "a6d1eb93-0d7e-448e-8cd7-f06d32878728",
    "video_url": "http://vdms-dataprep:8000/v1/dataprep/videos/download?video_id=a6d1eb93-0d7e-448e-8cd7-f06d32878728&bucket_name=video-summary",
    "video_rel_url": "/v1/dataprep/videos/download?video_id=a6d1eb93-0d7e-448e-8cd7-f06d32878728&bucket_name=video-summary",
    "timestamp": 595.0,
    "relevance_score": 0.2907029848371755,
    "tags": "",
    "bucket_name": "video-summary",
    "date_time": "",
    "segment_start": 592,
    "segment_end": 600,
    "seek_timestamp": 595.0,
    "score_breakdown": {
        "score": 0.2907029848371755,
        "max_frame_score": 0.2974147797,
        "top_n_avg_score": 0.2782374074,
        "top_n_frame_count": 6,
        "avg_frame_score": 0.24928637408125,
        "quality_score": 0.29070269939500004,
        "frame_count": 16,
        "contextual_weight": 1.9638082208988035e-06,
        "contextual_boost_factor": 0.5,
        "contextual_sigma_seconds": 40.0,
        "segment_best_timestamp": 595.0,
        "global_peak_timestamp": 450.0
    },
    "best_frame_info": {
        "timestamp": 595.0,
        "frame_number": 17850,
        "frame_type": "detected_crop",
        "detection_confidence": 0.9155675172805786,
        "detected_label": "car"
    },
    "aggregated": true,
    "video_metadata": {
        "duration": 599.4666666666667,
        "fps": 30.0,
        "tags": [],
        "upload_timestamp": "",
        "bucket_name": "video-summary"
    },
    "rank": 20
    },
    "page_content": "Video segment from 592s to 600s, seeking to 595.0s",
    "type": "Document",
    "frame_scores": [
    [
        "592.0s",
        "0.2062"
    ],
    [
        "592.0s",
        "0.2273"
    ],
    [
        "592.5s",
        "0.2239"
    ],
    [
        "593.0s",
        "0.2079"
    ],
    [
        "593.5s",
        "0.2604"
    ],
    [
        "594.0s",
        "0.2009"
    ],
    [
        "594.0s",
        "0.2853"
    ],
    [
        "594.5s",
        "0.2264"
    ],
    [
        "594.5s",
        "0.2780"
    ],
    [
        "595.0s",
        "0.2974"
    ],
    [
        "595.5s",
        "0.2882"
    ],
    [
        "596.0s",
        "0.2555"
    ],
    [
        "596.0s",
        "0.2584"
    ],
    [
        "597.5s",
        "0.2600"
    ],
    [
        "598.0s",
        "0.2566"
    ],
    [
        "598.5s",
        "0.2560"
    ]
    ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

with patch("langchain_community.vectorstores.vdms.VDMS_Client") as mock_vdms_client:
    mock_vdms_client.return_value = Mock()
    from src.vdms_retriever.retriever import (
        calculate_segment_score,
        get_aggregation_config,
    )


def load_segments(path: Path) -> List[Dict[str, Any]]:
    """Load aggregated segments from an score.json-style file."""
    data = json.loads(path.read_text())
    segments: List[Dict[str, Any]] = []

    for query in data.get("results", []):
        for doc in query.get("results", []):
            metadata = doc.get("metadata", {})
            frames: List[Dict[str, float]] = []

            for ts_str, score_str in doc.get("frame_scores", []):
                try:
                    timestamp = float(str(ts_str).rstrip("s"))
                    score = float(score_str)
                except (TypeError, ValueError):
                    continue
                frames.append({"timestamp": timestamp, "relevance_score": score})

            if not frames:
                best_info = metadata.get("best_frame_info") or {}
                timestamp = float(
                    best_info.get(
                        "timestamp",
                        metadata.get(
                            "seek_timestamp", metadata.get("segment_start", 0.0)
                        ),
                    )
                    or 0.0
                )
                score = float(metadata.get("relevance_score", 0.0) or 0.0)
                frames.append({"timestamp": timestamp, "relevance_score": score})

            video_duration = metadata.get("video_duration")
            if video_duration is None:
                video_duration = (metadata.get("video_metadata") or {}).get("duration")
            if video_duration is None:
                video_duration = 30.0

            segments.append(
                {
                    "video_id": metadata.get("video_id"),
                    "segment_start": metadata.get("segment_start"),
                    "segment_end": metadata.get("segment_end"),
                    "frames": frames,
                    "video_duration": video_duration,
                    "original_rank": metadata.get("rank"),
                    "label": f"{metadata.get('video_id', '')[:8]}_[{metadata.get('segment_start')}-{metadata.get('segment_end')}s]",
                }
            )

    return segments


def recompute_scores(segments: List[Dict[str, Any]], config: Dict[str, Any]):
    """Re-run the qualitative scoring on pre-aggregated segments."""
    global_best_frame: Dict[str, Any] | None = None
    global_max_score = 0.0

    for segment in segments:
        for frame in segment.get("frames", []):
            score = float(frame.get("relevance_score", 0.0) or 0.0)
            if score > global_max_score:
                global_max_score = score
                global_best_frame = {
                    "video_id": segment.get("video_id"),
                    "timestamp": frame.get("timestamp"),
                    "relevance_score": score,
                }

    scored_segments: List[Dict[str, Any]] = []
    for segment in segments:
        score_data = calculate_segment_score(
            segment,
            global_max_score,
            global_best_frame,
            config,
        )
        scored_segments.append({"segment": segment, "score_data": score_data})

    scored_segments.sort(key=lambda entry: entry["score_data"]["score"], reverse=True)
    return scored_segments


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-score aggregated segments with qualitative scoring"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="score.json",
        help="Path to score-style aggregated results (default: score.json)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top-ranked segments to display (default: 15)",
    )
    args = parser.parse_args()

    dataset_path = Path(args.path)
    if not dataset_path.exists():
        raise SystemExit(f"Dataset file not found: {dataset_path}")

    config = get_aggregation_config()
    segments = load_segments(dataset_path)
    scored = recompute_scores(segments, config)

    print(f"Loaded {len(segments)} segments from {dataset_path}")
    print(f"Global max frame score: {scored[0]['score_data']['max_frame_score']:.5f}")
    print(f"Top {min(args.top, len(scored))} segments after qualitative re-score:\n")

    for idx, entry in enumerate(scored[: args.top], start=1):
        segment = entry["segment"]
        score_data = entry["score_data"]
        print(
            f"#{idx:02d} score={score_data['score']:.6f} "
            f"orig_rank={segment.get('original_rank')} "
            f"label={segment['label']} "
            f"max={score_data['max_frame_score']:.4f} "
            f"top_avg={score_data['top_n_avg_score']:.4f} "
            f"top_count={score_data['top_n_frame_count']} "
            f"context={score_data['contextual_weight']:.3f}"
        )


if __name__ == "__main__":
    main()
