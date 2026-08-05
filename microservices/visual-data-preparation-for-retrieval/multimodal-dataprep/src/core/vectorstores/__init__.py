# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable vector-store abstraction for the DataPrep microservice.

Backends implement :class:`~src.core.vectorstores.base.BaseVectorStore`, register
themselves with :func:`~src.core.vectorstores.factory.register_backend`, and are
selected at runtime via the ``VECTORDB_BACKEND`` setting through
:func:`~src.core.vectorstores.factory.get_vector_store`. LangChain integrations
(``langchain_vdms``, ``langchain_milvus``) are the common integration point.

Backend-specific metadata adaptation lives in each backend's store module; this
package exposes only the backend-neutral contract primitives
(:data:`CANONICAL_FIELDS`, :func:`project_to_canonical`).
"""

from src.core.vectorstores.base import BaseVectorStore
from src.core.vectorstores.factory import (
    get_vector_store,
    register_backend,
    reset_vector_store,
)
from src.core.vectorstores.metadata import CANONICAL_FIELDS, project_to_canonical

__all__ = [
    "BaseVectorStore",
    "get_vector_store",
    "register_backend",
    "reset_vector_store",
    "CANONICAL_FIELDS",
    "project_to_canonical",
]
