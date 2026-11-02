# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.common_filters import clean_tags


def _pgvector_from_condition(condition: FilterCondition) -> dict[str, Any]:
    """Convert a FilterCondition to a PGVector-compatible single-key operator dict.

    PGVector's ``_handle_field_filter`` validates that each field-value dict has
    **exactly one key**.  For range conditions, we use PGVector's native
    ``$between`` operator (value is a ``[lower, upper]`` list) instead of the
    common two-key ``{"$gte": ..., "$lte": ...}`` form which would be rejected.
    """
    op = condition.op
    if op == "eq":
        return {"$eq": condition.value}
    if op == "in":
        return {"$in": condition.value}
    if op == "gte":
        return {"$gte": condition.value}
    if op == "lte":
        return {"$lte": condition.value}
    if op == "between":
        lower, upper = condition.value
        return {"$between": [lower, upper]}
    raise ValueError(f"Unsupported PGVector filter operator: {op}")


def build_filters(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | None:
    """Build PGVector-compatible metadata filters.

    PGVector's filter parser accepts a flat dict with multiple field keys —
    it implicitly ANDs them.  Each field value must be a single-key operator
    dict.  Range conditions use PGVector's native ``$between`` operator.
    """
    result: dict[str, Any] = {}

    cleaned_tags = clean_tags(tags)
    if cleaned_tags:
        if len(cleaned_tags) == 1:
            result["tags"] = {"$eq": cleaned_tags[0]}
        else:
            result["tags"] = {"$in": cleaned_tags}

    if time_filter:
        result[property_name] = {
            "$between": [
                time_filter.start.isoformat(),
                time_filter.end.isoformat(),
            ]
        }

    if filters:
        for field_name, condition in filters.items():
            result[field_name] = _pgvector_from_condition(condition)

    return result or None
