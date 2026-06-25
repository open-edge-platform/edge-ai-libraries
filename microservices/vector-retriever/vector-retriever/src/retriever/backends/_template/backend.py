# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Template backend implementation.

Copy this file into `src/retriever/backends/<name>/backend.py` and fill in the logic.
"""

from src.retriever.backends.base import VectorStoreBackend


def get_vectordb() -> VectorStoreBackend:
    """Create and return backend vector store instance for this template."""
    raise NotImplementedError("Implement get_vectordb() for your backend")


def check_ready() -> bool:
    """Validate backend readiness for this template implementation."""
    _ = get_vectordb()
    return True
