# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from datetime import datetime
from typing import Any

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.common_filters import clean_tags


def _milvus_literal(value: Any) -> str:
    """Convert Python values to Milvus expression literals."""
    if isinstance(value, datetime):
        value = value.isoformat()
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(_milvus_literal(v) for v in value) + "]"
    return str(value)


def _build_tag_filter(tags: list[str] | None) -> str | None:
    """Build Milvus tag expression from normalized tags."""
    cleaned = clean_tags(tags)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return f"tags == {_milvus_literal(cleaned[0])}"
    return f"tags in {_milvus_literal(cleaned)}"


def _build_time_filter(
    time_filter: TimeRange | None,
    property_name: str,
) -> str | None:
    """Build inclusive time-range expression for Milvus."""
    if not time_filter:
        return None
    start = _milvus_literal(time_filter.start.isoformat())
    end = _milvus_literal(time_filter.end.isoformat())
    return f"({property_name} >= {start} AND {property_name} <= {end})"


def _build_generic_filters(
    filters: dict[str, FilterCondition] | None,
) -> list[str]:
    """Translate dynamic field filters into Milvus expression parts."""
    if not filters:
        return []

    expressions: list[str] = []
    for field_name, condition in filters.items():
        if condition.op == "eq":
            expressions.append(f"{field_name} == {_milvus_literal(condition.value)}")
        elif condition.op == "in":
            expressions.append(f"{field_name} in {_milvus_literal(condition.value)}")
        elif condition.op == "gte":
            expressions.append(f"{field_name} >= {_milvus_literal(condition.value)}")
        elif condition.op == "lte":
            expressions.append(f"{field_name} <= {_milvus_literal(condition.value)}")
        elif condition.op == "between":
            lower, upper = condition.value
            expressions.append(
                f"({field_name} >= {_milvus_literal(lower)} AND {field_name} <= {_milvus_literal(upper)})"
            )
        else:
            raise ValueError(f"Unsupported filter operator: {condition.op}")

    return expressions


def build_filters(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> str | None:
    """Build full Milvus `expr` string from request filters."""
    expressions = [
        part
        for part in [
            _build_tag_filter(tags),
            _build_time_filter(time_filter, property_name=property_name),
            *_build_generic_filters(filters),
        ]
        if part
    ]
    if not expressions:
        return None
    return " AND ".join(expressions)
