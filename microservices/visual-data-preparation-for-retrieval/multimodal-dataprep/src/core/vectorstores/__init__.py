# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable vector-store abstraction for the DataPrep microservice.

Backends implement :class:`~src.core.vectorstores.base.BaseVectorStore` and are
selected at runtime via the ``VECTORDB_BACKEND`` setting through
:func:`~src.core.vectorstores.factory.get_vector_store`. LangChain integrations
(``langchain_vdms``, ``langchain_milvus``) are the common integration point.
"""

from src.core.vectorstores.base import BaseVectorStore
from src.core.vectorstores.factory import get_vector_store, reset_vector_store
from src.core.vectorstores.metadata import (
    CANONICAL_FIELDS,
    adapt_for_milvus,
    adapt_for_vdms,
)

__all__ = [
    "BaseVectorStore",
    "get_vector_store",
    "reset_vector_store",
    "CANONICAL_FIELDS",
    "adapt_for_vdms",
    "adapt_for_milvus",
]
