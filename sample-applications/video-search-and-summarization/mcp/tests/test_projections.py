# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for payload projections."""

from __future__ import annotations

import json

import pytest

from src.projections import (
    MAX_RESULT_BYTES,
    attach_video_names,
    build_timeline,
    cap_payload,
    caption_progress,
    indexed_status,
    is_final_summary_done,
    is_timeline_done,
    slim_search_hit,
    slim_summary,
    slim_video,
    truncate,
    unwrap_search_results,
)
from src.tools.search import clip_links


def make_search_hit(**overrides) -> dict:
    """Return an aggregated hit shaped like search-ms with aggregation enabled."""
    hit = {
        "id": None,
        "type": "Document",
        "page_content": "Video segment from 38.0s to 54.0s, seeking to 42.5s",
        "frame_scores": [[f"{38 + i}.0s", f"0.8{i}"] for i in range(16)],
        "metadata": {
            "video_id": "vid-1",
            "video_url": "http://minio/vid-1/source.mp4",
            "video_rel_url": "/vid-1/source.mp4",
            "timestamp": 42.5,
            "seek_timestamp": 42.5,
            "segment_start": 38.0,
            "segment_end": 54.0,
            "relevance_score": 0.8712345,
            "tags": "outdoor,daytime",
            "bucket_name": "vss",
            "date_time": "2026-08-01T10:00:00.000Z",
            "created_at": "2026-08-01T10:00:00.000Z",
            "aggregated": True,
            "rank": 1,
            "score_breakdown": {f"metric_{i}": i * 0.1 for i in range(12)},
            "best_frame_info": {
                "timestamp": 42.5,
                "frame_number": 340,
                "frame_type": "I",
                "detection_confidence": 0.91,
                "detected_label": "person",
            },
            "video_metadata": {
                "duration": 300,
                "fps": 30,
                "tags": ["outdoor"],
                "created_at": "2026-08-01T10:00:00.000Z",
                "bucket_name": "video-summary",
            },
        },
    }
    hit["metadata"].update(overrides)
    return hit


def make_ui_state(*, captions: int = 2, complete: bool = True) -> dict:
    """Return a UIState with ``captions`` summaries of eight frames each."""
    frames = []
    frame_summaries = []
    for batch in range(captions):
        ids = [str(batch * 8 + n + 1) for n in range(8)]
        frames.extend(
            {
                "chunkId": str(batch),
                "frameId": frame_id,
                "url": f"http://minio/state/chunk_{batch}_frame_{offset}.jpeg",
                "videoTimeStamp": batch * 8.0 + offset,
            }
            for offset, frame_id in enumerate(ids)
        )
        frame_summaries.append(
            {
                "summary": f"Caption for chunk {batch}.",
                "frames": ids,
                "frameKey": "#".join(ids),
                "startFrame": ids[0],
                "endFrame": ids[-1],
                "status": "complete",
                "stateId": "state-1",
            }
        )

    return {
        "stateId": "state-1",
        "videoId": "vid-1",
        "title": "Warehouse Friday",
        "summary": "A long rolled-up summary." if complete else "",
        "chunks": [
            {"chunkId": str(i), "duration": {"from": i * 8, "to": (i + 1) * 8}}
            for i in range(captions)
        ],
        "frames": frames,
        "frameSummaries": frame_summaries,
        "systemConfig": {
            "framePrompt": "x" * 800,
            "summaryMapPrompt": "y" * 800,
            "summaryReducePrompt": "z" * 800,
            "summarySinglePrompt": "w" * 800,
            "multiFrame": 8,
            "frameOverlap": 0,
        },
        "userInputs": {
            "chunkDuration": 8,
            "samplingFrame": 8,
            "frameOverlap": 0,
            "multiFrame": 8,
        },
        "inferenceConfig": {"textInference": {"model": "m", "device": "CPU"}},
        "videoSummaryStatus": "complete" if complete else "na",
        "frameSummaryStatus": {"complete": captions, "inProgress": 0, "na": 0, "ready": 0},
        "chunkingStatus": "complete",
        "videoChunkingStatus": "complete",
    }


# Text, videos and indexing


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [("hello", 100, "hello"), (None, 1000, "")],
)
def test_truncate_leaves_short_text_and_none_untouched(text, limit: int, expected: str) -> None:
    assert truncate(text, limit) == expected


def test_truncate_marks_truncated_text() -> None:
    assert truncate("a" * 50, 10).endswith("[truncated]")


def test_slim_video_prefers_datastore_filename_over_the_hex_name_column() -> None:
    """POST /videos ignores the caller's name, persisting multer's hex."""
    result = slim_video(
        {
            "videoId": "vid-1",
            "name": "a3f9c1e88b2d4a7f9e0c1b2a3d4e5f60",
            "tags": ["outdoor"],
            "createdAt": "2026-08-01T10:00:00.000Z",
            "dataStore": {"bucket": "vss", "objectName": "vid-1", "fileName": "warehouse.mp4"},
        }
    )
    assert result["name"] == "warehouse.mp4"
    assert result["video_id"] == "vid-1"
    assert "dbId" not in result


def test_slim_video_falls_back_to_name_when_datastore_absent() -> None:
    assert slim_video({"videoId": "v", "name": "fallback", "tags": []})["name"] == "fallback"


def test_slim_video_carries_the_rows_indexing_status() -> None:
    assert slim_video({"videoId": "v", "searchEmbeddings": True})["indexed"] is True
    assert slim_video({"videoId": "v"})["indexed"] is None


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"searchEmbeddings": True}, True),
        ({"textEmbeddings": True}, True),
        ({"searchEmbeddings": False, "textEmbeddings": True}, True),
        ({"searchEmbeddings": False}, False),
        ({}, None),
        ({"searchEmbeddings": None}, None),
    ],
)
def test_indexed_status(row: dict, expected: bool | None) -> None:
    assert indexed_status(row) is expected


# Search projections and links


def test_slim_search_hit_keeps_only_actionable_fields() -> None:
    assert set(slim_search_hit(make_search_hit())) == {
        "video_id",
        "start_s",
        "end_s",
        "seek_s",
        "score",
        "url",
    }


def test_slim_search_hit_drops_empty_urls_rather_than_forwarding_them() -> None:
    """Empty strings read to a model as real answers and must not survive."""
    assert "url" not in slim_search_hit(make_search_hit(video_url="", video_rel_url=""))


@pytest.mark.parametrize("filename", ("source.mp4", "clip.webm", "audio.mp3", "frame.jpeg"))
def test_clip_links_preserve_the_original_url(filename: str) -> None:
    url = f"https://host/{filename}?download=1&name=a%20b#t=12.5"
    result = slim_search_hit(make_search_hit(video_url=url))
    (link,) = clip_links([result])
    assert result["url"] == url
    assert link.type == "resource_link"
    assert str(link.uri) == url


def test_clip_links_are_deduplicated_and_named() -> None:
    links = clip_links(
        [
            {"video_id": "v1", "video_name": "a.mp4", "url": "http://h/a.mp4"},
            {"video_id": "v1", "video_name": "a.mp4", "url": "http://h/a.mp4"},
            {"video_id": "v2", "url": "http://h/b.mp4"},
        ]
    )
    assert [link.name for link in links] == ["a.mp4", "v2"]


@pytest.mark.parametrize(
    "url",
    (
        "/vss/vid-1/source.mp4",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://",
        "https://[invalid/source.mp4",
        "https://host/clip.mp4\nMEDIA:file:///etc/passwd",
        "https://host/a b.mp4",
    ),
)
def test_non_remote_or_malformed_urls_get_no_resource_link(url: str) -> None:
    result = slim_search_hit(make_search_hit(video_url=url))
    assert result["url"] == url
    assert clip_links([result]) == []


def test_slim_search_hit_omits_video_name_when_the_hit_carries_none() -> None:
    """Live payloads have no join and no filename in video_metadata."""
    assert "video_name" not in slim_search_hit(make_search_hit())


def test_slim_search_hit_drops_the_scoring_telemetry() -> None:
    result = slim_search_hit(make_search_hit())
    for noisy in ("score_breakdown", "frame_scores", "best_frame_info", "rank"):
        assert noisy not in result


def test_slim_search_hit_shrinks_the_payload_by_an_order_of_magnitude() -> None:
    raw = make_search_hit()
    raw_size = len(json.dumps(raw).encode())
    slim_size = len(json.dumps(slim_search_hit(raw)).encode())
    assert raw_size > 1_000
    assert slim_size < 250


def test_slim_search_hit_rounds_scores_and_timestamps() -> None:
    result = slim_search_hit(make_search_hit())
    assert result["score"] == 0.871
    assert result["start_s"] == 38.0


def test_slim_search_hit_handles_legacy_flat_shape_without_segment_bounds() -> None:
    """Aggregation-disabled paths emit raw VDMS metadata with no segments."""
    result = slim_search_hit(
        {
            "metadata": {
                "video_id": "vid-2",
                "timestamp": 12.0,
                "relevance_score": 0.5,
                "video_url": "http://minio/vid-2/source.mp4",
            }
        }
    )
    assert result["seek_s"] == 12.0
    assert result["start_s"] == 12.0


def test_slim_search_hit_uses_a_joined_video_filename_when_present() -> None:
    """pipeline-manager enriches some paths with the video row."""
    raw = make_search_hit()
    raw["video"] = {"dataStore": {"fileName": "joined.mp4"}}
    assert slim_search_hit(raw)["video_name"] == "joined.mp4"


@pytest.mark.parametrize("datastore_url", ("http://host:12345/datastore", "http://host:12345/datastore/"))
def test_slim_search_hit_builds_absolute_playable_url_from_the_backend_join(
    datastore_url: str,
) -> None:
    """The joined videoPlaybackUrl beats broken internal metadata URLs."""
    raw = make_search_hit()
    raw["videoPlaybackUrl"] = "/vss/vid-1/source.mp4"
    result = slim_search_hit(raw, datastore_url)
    assert result["url"] == "http://host:12345/datastore/vss/vid-1/source.mp4"


def test_slim_search_hit_keeps_joined_playback_url_and_legacy_timestamp() -> None:
    raw = {
        "videoPlaybackUrl": "/video-summary/video-id/source.mp4",
        "metadata": {"video_id": "video-id", "timestamp": 12.5},
    }
    result = slim_search_hit(raw, "http://192.0.2.20:23456/datastore")
    assert result["url"] == (
        "http://192.0.2.20:23456/datastore/video-summary/video-id/source.mp4"
    )
    assert result["seek_s"] == 12.5


def test_slim_search_hit_returns_relative_playback_path_without_a_datastore_base() -> None:
    """Still meaningful to a caller that knows its own gateway host."""
    raw = make_search_hit()
    raw["videoPlaybackUrl"] = "/vss/vid-1/source.mp4"
    assert slim_search_hit(raw)["url"] == "/vss/vid-1/source.mp4"


def test_slim_search_hit_falls_back_to_broken_metadata_urls_without_a_join() -> None:
    """An older backend without the join must not leave every hit urlless."""
    raw = make_search_hit()
    assert slim_search_hit(raw, "http://host:12345/datastore")["url"] == raw["metadata"]["video_url"]


def test_attach_video_names_fills_in_names_by_id() -> None:
    hits = [slim_search_hit(make_search_hit())]
    attach_video_names(hits, {"vid-1": "warehouse.mp4"})
    assert hits[0]["video_name"] == "warehouse.mp4"


def test_attach_video_names_leaves_unknown_ids_alone() -> None:
    hits = [slim_search_hit(make_search_hit())]
    attach_video_names(hits, {"other": "x.mp4"})
    assert "video_name" not in hits[0]


def test_attach_video_names_does_not_overwrite_a_name_already_present() -> None:
    raw = make_search_hit()
    raw["video"] = {"dataStore": {"fileName": "joined.mp4"}}
    hits = [slim_search_hit(raw)]
    attach_video_names(hits, {"vid-1": "listing.mp4"})
    assert hits[0]["video_name"] == "joined.mp4"


# Timeline and completion


def test_build_timeline_derives_time_bounds_from_frame_timestamps() -> None:
    timeline = build_timeline(make_ui_state(captions=2))
    assert len(timeline) == 2
    assert timeline[0]["start_s"] == 0.0
    assert timeline[0]["end_s"] == 7.0
    assert timeline[1]["start_s"] == 8.0


def test_build_timeline_orders_entries_by_start_time() -> None:
    state = make_ui_state(captions=3)
    state["frameSummaries"].reverse()
    starts = [entry["start_s"] for entry in build_timeline(state)]
    assert starts == sorted(starts)


def test_build_timeline_skips_uncaptioned_batches() -> None:
    state = make_ui_state(captions=2)
    state["frameSummaries"][1]["summary"] = ""
    assert len(build_timeline(state)) == 1


def test_build_timeline_tolerates_missing_frames() -> None:
    state = make_ui_state(captions=1)
    state["frames"] = []
    timeline = build_timeline(state)
    assert len(timeline) == 1
    assert timeline[0]["start_s"] is None


def test_timeline_done_when_captions_drained_and_chunking_complete() -> None:
    assert is_timeline_done(make_ui_state()) is True


def test_timeline_done_even_though_summary_status_is_na() -> None:
    """produceFinalSummary=false leaves videoSummaryStatus at 'na' forever."""
    state = make_ui_state(complete=False)
    assert state["videoSummaryStatus"] == "na"
    assert is_timeline_done(state) is True
    assert is_final_summary_done(state) is False


@pytest.mark.parametrize(
    "frame_summary_status",
    [
        {"complete": 1, "inProgress": 1, "na": 0, "ready": 0},
        {"complete": 1, "inProgress": 0, "na": 0, "ready": 2},
        {"complete": 0, "inProgress": 0, "na": 4, "ready": 0},
    ],
)
def test_timeline_not_done_while_batches_are_pending(frame_summary_status: dict) -> None:
    state = make_ui_state()
    state["frameSummaryStatus"] = frame_summary_status
    assert is_timeline_done(state) is False


def test_timeline_not_done_before_chunking_finishes() -> None:
    state = make_ui_state()
    state["videoChunkingStatus"] = "inProgress"
    assert is_timeline_done(state) is False


def test_caption_progress_totals_every_bucket() -> None:
    state = make_ui_state()
    state["frameSummaryStatus"] = {"complete": 3, "inProgress": 1, "na": 2, "ready": 4}
    assert caption_progress(state)["total"] == 10


# Summary projections and payload caps


def test_slim_summary_omits_final_summary_by_default() -> None:
    result = slim_summary(make_ui_state())
    assert "summary" not in result
    assert "timeline" in result


def test_slim_summary_includes_final_summary_on_request() -> None:
    assert slim_summary(make_ui_state(), final_summary=True)["summary"] == "A long rolled-up summary."


def test_slim_summary_drops_ui_plumbing() -> None:
    result = slim_summary(make_ui_state())
    for noisy in ("frames", "chunks", "systemConfig", "inferenceConfig"):
        assert noisy not in result


def test_slim_summary_reports_caption_progress() -> None:
    result = slim_summary(make_ui_state(captions=3))
    assert (result["captioned"], result["total_chunks"]) == (3, 3)


def test_slim_summary_stays_within_the_byte_budget_for_a_long_video() -> None:
    """A 40-chunk state must still fit; excess timeline entries are dropped."""
    state = make_ui_state(captions=40)
    for entry in state["frameSummaries"]:
        entry["summary"] = "A detailed caption. " * 30
    result = slim_summary(state)
    assert len(json.dumps(result).encode()) <= MAX_RESULT_BYTES
    assert result["truncated"] is True
    assert result["omitted"] == 40 - len(result["timeline"])


def test_raw_state_is_far_larger_than_the_summary_projection() -> None:
    state = make_ui_state(captions=40)
    raw_size = len(json.dumps(state).encode())
    slim_size = len(json.dumps(slim_summary(state)).encode())
    assert raw_size / slim_size > 3


def test_summary_completion_follows_the_requested_product() -> None:
    state = make_ui_state(complete=False)
    assert slim_summary(state)["completed"] is True
    rollup = slim_summary(state, final_summary=True)
    assert rollup["completed"] is False
    assert "summary" not in rollup


def test_cap_payload_leaves_small_payloads_untouched() -> None:
    payload = {"items": [1, 2, 3]}
    assert cap_payload(payload, "items") == {**payload, "truncated": False, "omitted": 0}


def test_cap_payload_reports_when_it_trims() -> None:
    capped = cap_payload({"items": ["x" * 100 for _ in range(200)]}, "items", max_bytes=1_000)
    assert len(json.dumps(capped).encode()) <= 1_000
    assert capped["truncated"] is True
    assert capped["omitted"] == 200 - len(capped["items"])


def test_cap_payload_does_not_mutate_the_input() -> None:
    payload = {"items": ["x" * 100 for _ in range(50)]}
    cap_payload(payload, "items", max_bytes=500)
    assert len(payload["items"]) == 50


# Search envelope


def test_unwrap_search_results_unwraps_the_double_nested_envelope() -> None:
    payload = {"results": [{"query_id": "q1", "results": [{"metadata": {}}] * 3}]}
    assert len(unwrap_search_results(payload)) == 3


def test_unwrap_search_results_flattens_multiple_query_blocks() -> None:
    payload = {
        "results": [
            {"query_id": "q1", "results": [{"metadata": {}}]},
            {"query_id": "q2", "results": [{"metadata": {}}, {"metadata": {}}]},
        ]
    }
    assert len(unwrap_search_results(payload)) == 3


@pytest.mark.parametrize("payload", (None, {"results": []}, "nonsense"))
def test_unwrap_search_results_returns_empty_for_unrecognised_shapes(payload) -> None:
    assert unwrap_search_results(payload) == []
