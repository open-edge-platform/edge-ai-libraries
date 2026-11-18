# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Temporal-segment grouping for live-stream search results.

Live embeddings all share one ``video_id`` (the stream id) and carry a
``timestamp`` that is the offset *within* their ~10s recorded segment. Grouping
those by ``timestamp // segment_duration`` would collapse an entire stream into
the two [0,8) and [8,16) buckets -- the "only two results per stream that never
grow" bug. These tests pin the live-aware grouping.
"""

from src.vdms_retriever.retriever import create_temporal_segments


def _frame(**metadata):
    return {"metadata": metadata, **metadata}


def test_live_results_group_by_segment_not_by_timestamp_bucket():
    # One stream, three distinct recorded segments, each with a frame whose
    # in-segment offset lands in the same [0,8) bucket. Bucketing by timestamp
    # would yield ONE group; segment-aware grouping must yield THREE.
    frames = [
        _frame(video_id="stream-1", is_live=True, segment_id="stream-1_seg_100",
               timestamp=2.0, relevance_score=0.9),
        _frame(video_id="stream-1", is_live=True, segment_id="stream-1_seg_110",
               timestamp=3.0, relevance_score=0.8),
        _frame(video_id="stream-1", is_live=True, segment_id="stream-1_seg_120",
               timestamp=1.5, relevance_score=0.7),
    ]
    segments = create_temporal_segments(frames, segment_duration=8)
    assert len(segments) == 3


def test_live_results_grow_with_more_segments():
    frames = [
        _frame(video_id="s", is_live=True, segment_id=f"s_seg_{i}", timestamp=1.0,
               relevance_score=0.5)
        for i in range(12)
    ]
    assert len(create_temporal_segments(frames, segment_duration=8)) == 12


def test_two_streams_do_not_merge():
    frames = [
        _frame(video_id="a", is_live=True, segment_id="a_seg_1", timestamp=1.0),
        _frame(video_id="b", is_live=True, segment_id="b_seg_1", timestamp=1.0),
    ]
    segments = create_temporal_segments(frames, segment_duration=8)
    assert len(segments) == 2
    assert {s["video_id"] for s in segments} == {"a", "b"}


def test_non_live_grouping_is_unchanged():
    # Uploaded video: timestamps span the whole file, grouped into 8s buckets.
    frames = [
        _frame(video_id="vid", timestamp=1.0),   # bucket 0
        _frame(video_id="vid", timestamp=5.0),   # bucket 0
        _frame(video_id="vid", timestamp=9.0),   # bucket 1
        _frame(video_id="vid", timestamp=20.0),  # bucket 2
    ]
    segments = create_temporal_segments(frames, segment_duration=8)
    assert len(segments) == 3


def test_is_live_string_false_is_treated_as_non_live():
    # VDMS may return the stored boolean as a string; "false" must not be truthy.
    frames = [
        _frame(video_id="vid", is_live="false", timestamp=1.0),
        _frame(video_id="vid", is_live="false", timestamp=5.0),
    ]
    # Both land in bucket 0 of the same video -> one group (non-live behaviour).
    segments = create_temporal_segments(frames, segment_duration=8)
    assert len(segments) == 1


def test_live_tile_range_widens_to_matched_frames():
    frames = [
        _frame(video_id="s", is_live=True, segment_id="s_seg_1", timestamp=2.0),
        _frame(video_id="s", is_live=True, segment_id="s_seg_1", timestamp=7.0),
    ]
    segments = create_temporal_segments(frames, segment_duration=8)
    assert len(segments) == 1
    seg = segments[0]
    assert seg["segment_start"] == 2.0
    assert seg["segment_end"] == 7.0


def test_overlap_filter_keeps_distinct_live_segments():
    # Different live segment FILES sharing one stream video_id, each matched at a
    # similar in-segment offset. Overlap filtering must NOT treat them as the
    # same timeline and discard all but the top-scored one.
    from src.vdms_retriever.retriever import apply_temporal_overlap_filtering

    segments = [
        {
            "video_id": "stream-1",
            "dedup_id": "stream-1_live_stream-1_seg_100",
            "segment_start": 2.0,
            "segment_end": 7.0,
            "final_score": 0.9,
        },
        {
            "video_id": "stream-1",
            "dedup_id": "stream-1_live_stream-1_seg_110",
            "segment_start": 2.0,
            "segment_end": 7.0,
            "final_score": 0.8,
        },
        {
            "video_id": "stream-1",
            "dedup_id": "stream-1_live_stream-1_seg_120",
            "segment_start": 3.0,
            "segment_end": 6.0,
            "final_score": 0.7,
        },
    ]
    kept = apply_temporal_overlap_filtering(segments, min_gap_seconds=0)
    assert len(kept) == 3


def test_overlap_filter_still_dedupes_non_live_overlaps():
    # Non-live segments from one video with overlapping ranges collapse as before.
    from src.vdms_retriever.retriever import apply_temporal_overlap_filtering

    segments = [
        {"video_id": "vid", "segment_start": 0.0, "segment_end": 8.0, "final_score": 0.9},
        {"video_id": "vid", "segment_start": 1.0, "segment_end": 7.0, "final_score": 0.8},
    ]
    kept = apply_temporal_overlap_filtering(segments, min_gap_seconds=0)
    assert len(kept) == 1
