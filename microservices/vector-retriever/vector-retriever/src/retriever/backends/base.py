# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Any, Protocol


class VectorStoreBackend(Protocol):
    """Minimal protocol required for vector store backend adapters."""

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[tuple[Any, float]]:
        """Run similarity search and return `(document, score)` tuples."""
        ...

    def similarity_search_with_score_by_vector(
        self,
        embedding: list[float],
        k: int = 4,
        **kwargs: Any,
    ) -> list[tuple[Any, float]]:
        """Run similarity search from a pre-computed vector."""
        ...


@dataclass(frozen=True)
class BackendSpec:
    """Registry metadata describing how to load a backend implementation."""

    backend_module_path: str
    filters_module_path: str
    get_vectordb_attr: str = "get_vectordb"
    check_ready_attr: str = "check_ready"
    build_filters_attr: str = "build_filters"
