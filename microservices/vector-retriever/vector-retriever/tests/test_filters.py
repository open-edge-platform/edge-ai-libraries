# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone

import pytest

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.vdms.filters import (
    build_generic_filters,
    build_tag_filter,
    build_time_filter,
    merge_filters,
)
from src.retriever.filters import build_filters


def test_build_tag_filter_single():
    """VDMS tag filter should map one tag to equality syntax."""
    assert build_tag_filter(["traffic"]) == {"tags": ["==", "traffic"]}


def test_build_tag_filter_multiple():
    """VDMS tag filter should keep multiple tags as a list value."""
    assert build_tag_filter(["traffic", "intersection"]) == {
        "tags": ["==", ["traffic", "intersection"]]
    }


def test_build_time_filter():
    """Time filter should include requested timestamp field."""
    window = TimeRange(
        start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        end=datetime(2026, 3, 2, tzinfo=timezone.utc),
    )
    result = build_time_filter(window, property_name="created_at")
    assert "created_at" in result


def test_merge_filters():
    """Merged filter should preserve keys from all filter fragments."""
    merged = merge_filters(
        {"tags": ["==", "traffic"]},
        {"created_at": [">=", "2026-03-01T00:00:00+00:00", "<=", "2026-03-02T00:00:00+00:00"]},
    )
    assert "tags" in merged
    assert "created_at" in merged


def test_build_generic_filters_eq_and_between():
    """VDMS build_generic_filters only pushes down gte; eq and between use fallback."""
    filters = {
        "video_id": FilterCondition(op="eq", value="traffic_001"),
        "timestamp": FilterCondition(op="between", value=[2, 10]),
    }

    result = build_generic_filters(filters)
    # eq and between are not pushed down to VDMS (langchain-vdms constraint-ordering
    # artefact silently excludes the first-indexed descriptor); service evaluates them
    # in the in-memory fallback path instead.
    assert result is None


def test_build_generic_filters_accepts_dynamic_field():
    """VDMS generic filters with eq fall back to in-memory evaluation (result is None)."""
    filters = {
        "camera_zone": FilterCondition(op="eq", value="zone_a"),
    }

    result = build_generic_filters(filters)
    assert result is None


def test_build_generic_filters_in_gte_lte():
    """VDMS generic filters: only gte is pushed down; in and lte use fallback."""
    filters = {
        "bucket_name": FilterCondition(op="in", value=["cam-a", "cam-b"]),
        "timestamp": FilterCondition(op="gte", value=10),
        "frame_number": FilterCondition(op="lte", value=100),
    }

    result = build_generic_filters(filters)
    # Only gte is safe to push down to VDMS; in and lte are evaluated in-memory.
    assert result == {"timestamp": [">=", 10]}


def test_build_filters_milvus_returns_expr_string():
    """Milvus backend should emit string expression filters."""
    window = TimeRange(
        start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        end=datetime(2026, 3, 2, tzinfo=timezone.utc),
    )

    result = build_filters(
        backend="milvus",
        tags=["traffic"],
        time_filter=window,
        filters={"score": FilterCondition(op="gte", value=0.5)},
        property_name="created_at",
    )

    assert isinstance(result, str)
    assert "tags ==" in result
    assert "created_at >=" in result
    assert "score >= 0.5" in result


def test_build_filters_pgvector_returns_mongo_dict():
    """PGVector backend should emit single-key operator dicts compatible with its filter parser.

    PGVector's _handle_field_filter requires each field-value dict to have exactly
    one key, so range conditions use its native $between operator instead of the
    two-key {"$gte": ..., "$lte": ...} form used by other backends.
    """
    window = TimeRange(
        start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        end=datetime(2026, 3, 2, tzinfo=timezone.utc),
    )

    result = build_filters(
        backend="pgvector",
        tags=["traffic", "intersection"],
        time_filter=window,
        filters={"score": FilterCondition(op="between", value=[0.2, 0.9])},
        property_name="created_at",
    )

    assert isinstance(result, dict)
    assert result["tags"] == {"$in": ["traffic", "intersection"]}
    assert result["created_at"] == {"$between": ["2026-03-01T00:00:00+00:00", "2026-03-02T00:00:00+00:00"]}
    assert result["score"] == {"$between": [0.2, 0.9]}


def test_build_filters_unknown_backend_raises():
    """Unknown backend names should raise filter-construction errors."""
    with pytest.raises(ValueError):
        build_filters(
            backend="unknown",
            tags=None,
            time_filter=None,
            filters=None,
        )
