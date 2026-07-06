# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Factory for selecting the active storage backend at runtime."""

from __future__ import annotations

import threading
from typing import Optional

from src.common import logger, settings
from src.core.storage.base import BaseStorage

_SUPPORTED_BACKENDS = ("minio", "local")

_storage_instance: Optional[BaseStorage] = None
_lock = threading.Lock()


def get_storage() -> BaseStorage:
    """Return the configured storage backend as a cached singleton.

    Selection is driven by ``settings.STORAGE_BACKEND`` (``minio`` or ``local``).
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    with _lock:
        if _storage_instance is not None:
            return _storage_instance

        backend = (settings.STORAGE_BACKEND or "minio").strip().lower()
        if backend == "minio":
            from src.core.storage.minio_storage import MinioStorage

            _storage_instance = MinioStorage()
        elif backend == "local":
            from src.core.storage.local_storage import LocalStorage

            _storage_instance = LocalStorage()
        else:
            raise ValueError(
                f"Unsupported STORAGE_BACKEND '{backend}'. "
                f"Supported backends: {', '.join(_SUPPORTED_BACKENDS)}."
            )

        logger.info("Storage backend initialized: %s", backend)
        return _storage_instance


def reset_storage() -> None:
    """Reset the cached storage instance (primarily for tests)."""
    global _storage_instance
    with _lock:
        _storage_instance = None
