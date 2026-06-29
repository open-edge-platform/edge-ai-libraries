# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
import pytest

from src.common.schema import QueryRequest, TimeRange, ImageUrlInput, ImageBase64Input


def test_time_range_validation():
    """TimeRange should reject windows where start is after end."""
    with pytest.raises(ValueError):
        TimeRange(
            start=datetime(2026, 3, 2, tzinfo=timezone.utc),
            end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )


def test_query_request_normalizes_tags():
    """QueryRequest should trim query text and normalize tag list."""
    request = QueryRequest(query="  person near car  ", tags=[" traffic ", "", "  "])
    assert request.query == "person near car"
    assert request.tags == ["traffic"]


def test_query_request_accepts_generic_filters():
    """QueryRequest should accept valid dynamic filter payloads."""
    request = QueryRequest(
        query="person near car",
        filters={
            "video_id": {"op": "eq", "value": "traffic_001"},
            "timestamp": {"op": "between", "value": [1, 5]},
        },
    )
    assert request.filters is not None
    assert request.filters["video_id"].op == "eq"


def test_query_request_rejects_invalid_filter_field_name():
    """QueryRequest should reject filter keys with invalid characters."""
    with pytest.raises(ValueError):
        QueryRequest(
            query="person near car",
            filters={
                "invalid field": {"op": "eq", "value": "x"},
            },
        )


def test_query_request_rejects_too_many_filters():
    """QueryRequest should enforce configured maximum filter count."""
    filters = {f"f{i}": {"op": "eq", "value": i} for i in range(21)}
    with pytest.raises(ValueError):
        QueryRequest(query="person near car", filters=filters)


def test_query_request_accepts_slash_backslash_dash_and_128_chars():
    """Allowed filter key characters and max length should pass validation."""
    valid_key = "camera-zone/entry\\north_01"
    long_key = "a" * 128
    request = QueryRequest(
        query="person near car",
        filters={
            valid_key: {"op": "eq", "value": "ok"},
            long_key: {"op": "eq", "value": "ok"},
        },
    )
    assert request.filters is not None
    assert valid_key in request.filters
    assert long_key in request.filters


def test_query_request_rejects_filter_field_over_128_chars():
    """Filter field names longer than 128 chars should be rejected."""
    too_long_key = "a" * 129
    with pytest.raises(ValueError):
        QueryRequest(
            query="person near car",
            filters={too_long_key: {"op": "eq", "value": "x"}},
        )


def test_query_request_accepts_primary_where_predicate():
    """QueryRequest should accept primary where predicate syntax."""
    request = QueryRequest(
        query="person near car",
        where={"field": "camera_zone", "op": "eq", "value": "zone_a"},
    )
    assert request.where is not None
    assert request.where.field == "camera_zone"
    assert request.where.op == "eq"


def test_where_rejects_mixed_predicate_and_logical_keys():
    """Where clauses should not mix predicate and logical forms."""
    with pytest.raises(ValueError):
        QueryRequest(
            query="person near car",
            where={
                "field": "camera_zone",
                "op": "eq",
                "value": "zone_a",
                "all": [{"field": "score", "op": "gte", "value": 0.5}],
            },
        )


def test_where_rejects_depth_greater_than_limit():
    """Where validation should reject trees beyond configured depth limit."""
    too_deep = {
        "all": [
            {
                "all": [
                    {
                        "all": [
                            {
                                "all": [
                                    {
                                        "all": [
                                            {"field": "score", "op": "gte", "value": 0.5}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    with pytest.raises(ValueError):
        QueryRequest(query="person near car", where=too_deep)


def test_where_accepts_not_block_with_predicate():
    """Primary where should support logical not blocks."""
    request = QueryRequest(
        query="person near car",
        where={
            "not": {
                "field": "camera_zone",
                "op": "eq",
                "value": "zone_b",
            }
        },
    )
    assert request.where is not None
    assert request.where.not_ is not None
    assert request.where.not_.field == "camera_zone"


def test_where_rejects_timezone_naive_datetime_strings():
    """Time-like range strings should include timezone information."""
    with pytest.raises(ValueError):
        QueryRequest(
            query="person near car",
            where={
                "field": "created_at",
                "op": "between",
                "value": ["2026-03-01T00:00:00", "2026-03-02T00:00:00"],
            },
        )


# ── Image query modality tests ──────────────────────────────────────


def test_query_request_accepts_image_url():
    """QueryRequest should accept an image_url input without text query."""
    request = QueryRequest(
        image={"type": "image_url", "image_url": "https://example.com/photo.jpg"},
    )
    assert request.query is None
    assert request.image is not None
    assert request.image.type == "image_url"
    assert request.image.image_url == "https://example.com/photo.jpg"


def test_query_request_accepts_image_base64():
    """QueryRequest should accept a base64-encoded image input."""
    request = QueryRequest(
        image={"type": "image_base64", "image_base64": "aWFtYW5pbWFnZQ=="},
    )
    assert request.query is None
    assert request.image is not None
    assert request.image.type == "image_base64"


def test_query_request_rejects_both_query_and_image():
    """QueryRequest should reject payloads with both text and image."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        QueryRequest(
            query="person near car",
            image={"type": "image_url", "image_url": "https://example.com/photo.jpg"},
        )


def test_query_request_rejects_neither_query_nor_image():
    """QueryRequest should reject payloads with no query modality."""
    with pytest.raises(ValueError, match="either query.*or image must be provided"):
        QueryRequest(top_k=5)


def test_query_request_image_with_filters():
    """Image queries should still accept filter payloads."""
    request = QueryRequest(
        image={"type": "image_url", "image_url": "https://example.com/photo.jpg"},
        where={"field": "video_id", "op": "eq", "value": "v1"},
        top_k=5,
    )
    assert request.image is not None
    assert request.where is not None
    assert request.top_k == 5


def test_query_request_rejects_empty_image_url():
    """Image URL input must be non-empty."""
    with pytest.raises(ValueError):
        QueryRequest(
            image={"type": "image_url", "image_url": ""},
        )


def test_query_request_rejects_empty_image_base64():
    """Image base64 input must be non-empty."""
    with pytest.raises(ValueError):
        QueryRequest(
            image={"type": "image_base64", "image_base64": ""},
        )
