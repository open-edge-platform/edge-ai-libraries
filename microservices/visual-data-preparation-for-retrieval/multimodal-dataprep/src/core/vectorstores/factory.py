# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Registry-based factory for selecting the active vector-store backend.

Backends self-register with :func:`register_backend` (a class decorator) in
their own store module, so adding a new vector DB requires only a new
``*_store.py`` file — no edits here. The concrete backend classes are imported
lazily (only when first needed) so a heavy backend dependency is not loaded at
import time.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional, Type

from src.common import logger, settings
from src.core.vectorstores.base import BaseVectorStore

# name -> backend class. Populated by @register_backend at store-module import.
_REGISTRY: Dict[str, Type[BaseVectorStore]] = {}

_vector_store_instance: Optional[BaseVectorStore] = None
_lock = threading.Lock()
_backends_loaded = False


def register_backend(name: str):
    """Class decorator that registers a :class:`BaseVectorStore` implementation.

    Args:
        name: The ``VECTORDB_BACKEND`` value that selects this backend
            (case-insensitive).
    """
    key = name.strip().lower()

    def decorator(cls: Type[BaseVectorStore]) -> Type[BaseVectorStore]:
        _REGISTRY[key] = cls
        return cls

    return decorator


def _load_backends() -> None:
    """Import the built-in backend modules once so they self-register.

    Importing the store modules is cheap because each backend defers its heavy
    third-party imports (e.g. ``langchain_vdms``, ``langchain_milvus``) until an
    actual connection is established.
    """
    global _backends_loaded
    if _backends_loaded:
        return
    from src.core.vectorstores import milvus_store, vdms_store  # noqa: F401 (self-register)

    _backends_loaded = True


def get_vector_store() -> BaseVectorStore:
    """Return the configured vector-store backend as a cached singleton.

    Selection is driven by ``settings.VECTORDB_BACKEND`` and resolved against the
    backend registry.
    """
    global _vector_store_instance
    if _vector_store_instance is not None:
        return _vector_store_instance

    with _lock:
        if _vector_store_instance is not None:
            return _vector_store_instance

        _load_backends()
        backend = (settings.VECTORDB_BACKEND or "vdms").strip().lower()
        backend_cls = _REGISTRY.get(backend)
        if backend_cls is None:
            raise ValueError(
                f"Unsupported VECTORDB_BACKEND '{backend}'. "
                f"Supported backends: {', '.join(sorted(_REGISTRY))}."
            )

        _vector_store_instance = backend_cls()
        logger.info("Vector store backend initialized: %s", backend)
        return _vector_store_instance


def reset_vector_store() -> None:
    """Reset the cached vector-store instance (primarily for tests)."""
    global _vector_store_instance
    with _lock:
        _vector_store_instance = None
