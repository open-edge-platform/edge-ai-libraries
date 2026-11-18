# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the agent-facing ``best_frame_info`` enrichment.

A search result must carry everything a downstream agent needs to fetch the
exact peak frame from dataprep's ``GET /media/frame`` endpoint, in one object:
the frame's address (``video_id``, ``bucket_name``, ``media_path`` for live),
its ``timestamp``, and crop coordinates for the detected-crop variant.
"""

from src.vdms_retriever.retriever import (
    _derive_media_path,
    aggregate_frame_results_to_videos,
)


def _frame(**metadata):
    return {"metadata": metadata, **metadata}


# --- _derive_media_path ----------------------------------------------------


def test_derive_media_path_live_segment():
    url = "/live-streams/stream-abc/segments/1790655530.mp4"
    assert _derive_media_path(url, "stream-abc") == "segments/1790655530.mp4"


def test_derive_media_path_upload_returns_none():
    # Uploaded video: single object directly under video_id -> no media_path.
    url = "/video-summary/vid-123/myclip.mp4"
    assert _derive_media_path(url, "vid-123") is None


def test_derive_media_path_missing_inputs():
    assert _derive_media_path("", "vid") is None
    assert _derive_media_path(None, "vid") is None
    assert _derive_media_path("/a/b/c.mp4", "not-present") is None


# --- best_frame_info enrichment -------------------------------------------


def test_best_frame_info_has_agent_addressing_fields_for_live():
    frames = [
        _frame(
            video_id="stream-abc",
            bucket_name="live-streams",
            timestamp=3.0,
            relevance_score=0.9,
            is_live=True,
            frame_type="detected_crop",
            is_detected_crop=True,
            crop_index=1,
            crop_bbox=[10, 20, 110, 220],
            detected_label="person",
            detection_confidence=0.88,
            video_url="/live-streams/stream-abc/segments/1790655530.mp4",
            video_rel_url="/live-streams/stream-abc/segments/1790655530.mp4",
        ),
    ]

    videos, _ = aggregate_frame_results_to_videos(frames)
    assert videos, "expected at least one aggregated video"
    info = videos[0]["best_frame_info"]

    # Address + time for GET /media/frame
    assert info["video_id"] == "stream-abc"
    assert info["bucket_name"] == "live-streams"
    assert info["timestamp"] == 3.0
    assert info["is_live"] is True
    assert info["media_path"] == "segments/1790655530.mp4"
    # Crop variant addressing
    assert info["is_detected_crop"] is True
    assert info["crop_index"] == 1
    assert info["crop_bbox"] == [10, 20, 110, 220]
    assert info["detected_label"] == "person"


def test_best_frame_info_for_upload_has_no_media_path():
    frames = [
        _frame(
            video_id="vid-123",
            bucket_name="video-summary",
            timestamp=12.5,
            relevance_score=0.7,
            frame_type="full_frame",
            video_url="/video-summary/vid-123/myclip.mp4",
            video_rel_url="/video-summary/vid-123/myclip.mp4",
        ),
    ]

    videos, _ = aggregate_frame_results_to_videos(frames)
    info = videos[0]["best_frame_info"]
    assert info["video_id"] == "vid-123"
    assert info["bucket_name"] == "video-summary"
    assert info["is_live"] is False
    assert info["media_path"] is None
    assert info["is_detected_crop"] is False
