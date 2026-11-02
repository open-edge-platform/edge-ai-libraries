# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from src.common.schema import FilterCondition, TimeRange


def clean_tags(tags: list[str] | None) -> list[str]:
    """Trim tag values and drop empty entries."""
    if not tags:
        return []
    return [tag.strip() for tag in tags if tag and tag.strip()]


def _mongo_from_condition(condition: FilterCondition) -> dict[str, Any]:
    """Convert a normalized filter condition to a single-key mongo-style operator dict."""
    if condition.op == "eq":
        return {"$eq": condition.value}
    if condition.op == "in":
        return {"$in": condition.value}
    if condition.op == "gte":
        return {"$gte": condition.value}
    if condition.op == "lte":
        return {"$lte": condition.value}
    if condition.op == "between":
        lower, upper = condition.value
        return {"$gte": lower, "$lte": upper}
    raise ValueError(f"Unsupported filter operator: {condition.op}")


def _build_generic_filters_mongo(
    filters: dict[str, FilterCondition] | None,
) -> dict[str, Any] | None:
    """Build mongo-style filters for dynamic metadata fields."""
    if not filters:
        return None

    mongo_filter: dict[str, Any] = {}
    for field_name, condition in filters.items():
        mongo_filter[field_name] = _mongo_from_condition(condition)
    return mongo_filter or None


def _merge_mongo_filters(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge multiple mongo-style filter documents into one."""
    merged: dict[str, Any] = {}
    for item in filters:
        if not item:
            continue
        for key, value in item.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged or None


def build_filters_mongo(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | None:
    """Build a combined mongo-style filter from tags, time, and fields."""
    cleaned_tags = clean_tags(tags)
    tag_filter = None
    if cleaned_tags:
        if len(cleaned_tags) == 1:
            tag_filter = {"tags": {"$eq": cleaned_tags[0]}}
        else:
            tag_filter = {"tags": {"$in": cleaned_tags}}

    time_range_filter = None
    if time_filter:
        time_range_filter = {
            property_name: {
                "$gte": time_filter.start.isoformat(),
                "$lte": time_filter.end.isoformat(),
            }
        }

    return _merge_mongo_filters(
        tag_filter,
        time_range_filter,
        _build_generic_filters_mongo(filters),
    )
