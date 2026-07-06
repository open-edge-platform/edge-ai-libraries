# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Factory for selecting the active vector-store backend at runtime."""

from __future__ import annotations

import threading
from typing import Optional

from src.common import logger, settings
from src.core.vectorstores.base import BaseVectorStore

_SUPPORTED_BACKENDS = ("vdms", "milvus")

_vector_store_instance: Optional[BaseVectorStore] = None
_lock = threading.Lock()


def get_vector_store() -> BaseVectorStore:
    """Return the configured vector-store backend as a cached singleton.

    Selection is driven by ``settings.VECTORDB_BACKEND`` (``vdms`` or ``milvus``).
    """
    global _vector_store_instance
    if _vector_store_instance is not None:
        return _vector_store_instance

    with _lock:
        if _vector_store_instance is not None:
            return _vector_store_instance

        backend = (settings.VECTORDB_BACKEND or "vdms").strip().lower()
        if backend == "vdms":
            from src.core.vectorstores.vdms_store import VDMSVectorStore

            _vector_store_instance = VDMSVectorStore()
        elif backend == "milvus":
            from src.core.vectorstores.milvus_store import MilvusVectorStore

            _vector_store_instance = MilvusVectorStore()
        else:
            raise ValueError(
                f"Unsupported VECTORDB_BACKEND '{backend}'. "
                f"Supported backends: {', '.join(_SUPPORTED_BACKENDS)}."
            )

        logger.info("Vector store backend initialized: %s", backend)
        return _vector_store_instance


def reset_vector_store() -> None:
    """Reset the cached vector-store instance (primarily for tests)."""
    global _vector_store_instance
    with _lock:
        _vector_store_instance = None
