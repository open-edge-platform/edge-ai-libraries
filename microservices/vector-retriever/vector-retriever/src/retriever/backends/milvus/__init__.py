# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.retriever.backends.milvus.filters import build_filters


def get_vectordb():
    """Return the configured Milvus vector store instance."""
    from src.retriever.backends.milvus.backend import get_vectordb as _get_vectordb

    return _get_vectordb()


def check_ready() -> bool:
    """Run Milvus backend readiness checks."""
    from src.retriever.backends.milvus.backend import check_ready as _check_ready

    return _check_ready()


__all__ = ["build_filters", "check_ready", "get_vectordb"]
