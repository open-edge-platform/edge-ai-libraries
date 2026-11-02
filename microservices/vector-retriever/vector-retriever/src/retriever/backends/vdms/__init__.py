# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.retriever.backends.vdms.filters import (
    build_filters,
    build_generic_filters,
    build_tag_filter,
    build_time_filter,
    merge_filters,
)


def get_vectordb():
    """Return the configured VDMS vector store instance."""
    from src.retriever.backends.vdms.backend import get_vectordb as _get_vectordb

    return _get_vectordb()


def check_ready() -> bool:
    """Run VDMS backend readiness checks."""
    from src.retriever.backends.vdms.backend import check_ready as _check_ready

    return _check_ready()


__all__ = [
    "build_filters",
    "build_generic_filters",
    "build_tag_filter",
    "build_time_filter",
    "check_ready",
    "get_vectordb",
    "merge_filters",
]
