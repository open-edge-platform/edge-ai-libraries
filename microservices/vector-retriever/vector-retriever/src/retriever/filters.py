# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.registry import build_filters as build_backend_filters


def build_filters(
    backend: str,
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | str | None:
    """Build backend-specific filter payload from normalized query filters."""
    return build_backend_filters(
        backend=backend,
        tags=tags,
        time_filter=time_filter,
        filters=filters,
        property_name=property_name,
    )


__all__ = ["build_filters"]
