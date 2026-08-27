# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Registry-based factory for selecting the active storage backend.

Backends self-register with :func:`register_backend` (a class decorator) in their
own storage module, so adding a new object store requires only a new
``*_storage.py`` file — no edits here. The concrete backend classes are imported
lazily (only when first needed) via :func:`_load_backends`.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional, Type

from src.common import logger, settings
from src.core.storage.base import BaseStorage

# name -> backend class. Populated by @register_backend at storage-module import.
_REGISTRY: Dict[str, Type[BaseStorage]] = {}

_storage_instance: Optional[BaseStorage] = None
_lock = threading.Lock()
_backends_loaded = False


def register_backend(name: str):
    """Class decorator that registers a :class:`BaseStorage` implementation.

    Args:
        name: The ``STORAGE_BACKEND`` value that selects this backend
            (case-insensitive).
    """
    key = name.strip().lower()

    def decorator(cls: Type[BaseStorage]) -> Type[BaseStorage]:
        _REGISTRY[key] = cls
        return cls

    return decorator


def _load_backends() -> None:
    """Import the built-in backend modules once so they self-register."""
    global _backends_loaded
    if _backends_loaded:
        return
    from src.core.storage import local_storage, minio_storage  # noqa: F401 (self-register)

    _backends_loaded = True


def get_storage() -> BaseStorage:
    """Return the configured storage backend as a cached singleton.

    Selection is driven by ``settings.STORAGE_BACKEND`` and resolved against the
    backend registry.
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    with _lock:
        if _storage_instance is not None:
            return _storage_instance

        _load_backends()
        backend = (settings.STORAGE_BACKEND or "minio").strip().lower()
        backend_cls = _REGISTRY.get(backend)
        if backend_cls is None:
            raise ValueError(
                f"Unsupported STORAGE_BACKEND '{backend}'. "
                f"Supported backends: {', '.join(sorted(_REGISTRY))}."
            )

        _storage_instance = backend_cls()
        logger.info("Storage backend initialized: %s", backend)
        return _storage_instance


def reset_storage() -> None:
    """Reset the cached storage instance (primarily for tests)."""
    global _storage_instance
    with _lock:
        _storage_instance = None
