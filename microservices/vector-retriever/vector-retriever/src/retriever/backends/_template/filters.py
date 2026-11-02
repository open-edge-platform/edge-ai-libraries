# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Template filter translator.

Copy this file into `src/retriever/backends/<name>/filters.py` and map
`tags`, `time_filter`, and generic `filters` to your backend's query syntax.
"""

from typing import Any

from src.common.schema import FilterCondition, TimeRange


def build_filters(
    tags: list[str] | None,
    time_filter: TimeRange | None,
    filters: dict[str, FilterCondition] | None,
    property_name: str = "created_at",
) -> dict[str, Any] | str | None:
    """Translate normalized filters into backend-native format."""
    raise NotImplementedError("Implement build_filters() for your backend")
