# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable storage abstraction for the DataPrep microservice.

This package decouples the service from any single object-store implementation
(MinIO today, local filesystem, or future object stores). Backends implement
:class:`~src.core.storage.base.BaseStorage`, register themselves with
:func:`~src.core.storage.factory.register_backend`, and are selected at runtime
via the ``STORAGE_BACKEND`` setting through
:func:`~src.core.storage.factory.get_storage`.
"""

from src.core.storage.base import BaseStorage, StorageObject
from src.core.storage.factory import get_storage, register_backend, reset_storage

__all__ = ["BaseStorage", "StorageObject", "get_storage", "register_backend", "reset_storage"]
