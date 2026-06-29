# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.common_filters import clean_tags


def build_tag_filter(tags: list[str] | None) -> dict[str, Any] | None:
    """Build VDMS tag filter expression from request tags."""
    cleaned = clean_tags(tags)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return {"tags": ["==", cleaned[0]]}
    return {"tags": ["==", cleaned]}


def build_time_filter(
    time_filter: TimeRange | None,
    property_name: str = "created_at",
) -> dict[str, Any] | None:
    """Build VDMS inclusive time-range filter for the given metadata field."""
    if not time_filter:
        return None
    return {
        property_name: [
            ">=",
            time_filter.start.isoformat(),
            "<=",
            time_filter.end.isoformat(),
        ]
    }


def merge_filters(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge VDMS filter fragments into a single dictionary."""
    merged: dict[str, Any] = {}
    for item in filters:
        if not item:
            continue
        merged.update(item)
    return merged or None


def build_generic_filters(
    filters: dict[str, FilterCondition] | None,
) -> dict[str, Any] | None:
    """Translate dynamic field filters into VDMS operator syntax.

    Only ``gte`` (``>=``) is pushed down as a VDMS constraint.  VDMS's
    constraint-based ANN search can silently exclude the first-indexed
    descriptor for ``eq``, ``in``, ``lte``, and ``between`` predicates (a
    langchain-vdms batch-insert ordering artefact).  Those operators are
    omitted here so the service over-fetches from VDMS without constraints
    and evaluates them through the post-retrieval in-memory filter path.

    ``gte`` is safe to push down because, in practice, the first-indexed
    descriptor always has the smallest field values, so it is never a false
    positive when excluded by a ``>=`` constraint.  Pushing down ``gte``
    also ensures ``compiled_backend_filter`` is populated for
    ``explain_filters`` responses.
    """
    if not filters:
        return None

    vdms_filter: dict[str, Any] = {}
    for field_name, condition in filters.items():
        if condition.op == "gte":
            vdms_filter[field_name] = [">=", condition.value]
        # eq, in, lte, between are handled in-memory to avoid the VDMS
        # constraint-based ANN search dropping the first-indexed descriptor.

    return vdms_filter or None


def build_filters(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | None:
    """Build full VDMS filter payload from tags, time, and dynamic fields."""
    return merge_filters(
        build_tag_filter(tags),
        build_time_filter(time_filter, property_name=property_name),
        build_generic_filters(filters),
    )
