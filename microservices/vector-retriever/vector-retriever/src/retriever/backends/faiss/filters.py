# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from src.common.schema import FilterCondition, TimeRange
from src.retriever.backends.common_filters import build_filters_mongo


def build_filters(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | None:
    """Build FAISS-compatible metadata filters using mongo-style helpers."""
    return build_filters_mongo(
        tags=tags,
        time_filter=time_filter,
        filters=filters,
        property_name=property_name,
    )
