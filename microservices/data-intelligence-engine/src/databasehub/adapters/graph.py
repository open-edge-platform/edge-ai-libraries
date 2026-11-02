# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The graph backend contract: one adapter owns one connection."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping

from databasehub.models import GraphCollection


class GraphAdapter(ABC):
    """Connection-owning contract for a graph backend.

    Every method names the graph space it acts on. See
    `adapters/vector.py:VectorAdapter` for why this is an ABC here rather than a
    Protocol paired with an operator class.
    """

    @abstractmethod
    def upsert_vertices(
        self, collection: GraphCollection, vertices: List[Dict[str, Any]]
    ) -> None: ...

    @abstractmethod
    def upsert_edges(
        self, collection: GraphCollection, edges: List[Dict[str, Any]]
    ) -> None: ...

    @abstractmethod
    def query(
        self,
        collection: GraphCollection,
        statement: str,
        parameters: Mapping[str, Any],
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def clear(self, collection: GraphCollection) -> None: ...

    def delete_vertices(self, collection: GraphCollection, vertex_ids: List[str]) -> int:
        """Delete these vertices and every edge touching them; return how many.

        Concrete so an adapter without removal support still constructs; asset
        deletion then reports the backend cannot remove what it wrote.
        """
        raise NotImplementedError(f"{type(self).__name__} cannot delete vertices")

    @abstractmethod
    def close(self) -> None:
        """Release the backend clients this adapter holds."""

    # --- liveness -------------------------------------------------------------

    def ping(self) -> None:
        """Raise if the backend is not reachable; return if it is.

        Concrete, and doing nothing is a truthful default for a backend whose
        constructor already dialled -- `check` builds the adapter first, so
        getting this far means the connection was established. A backend that
        connects lazily, or that can be reached but not used, overrides this
        with the cheapest real round trip it has.
        """
