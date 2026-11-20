# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping

from databasehub.models import GraphCollection


class GraphAdapter(ABC):
    """Connection-owning contract for a graph backend; every method names its graph space."""

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
        """Delete these vertices and every edge touching them; return how many."""
        raise NotImplementedError(f"{type(self).__name__} cannot delete vertices")

    @abstractmethod
    def close(self) -> None:
        """Release the backend clients this adapter holds."""

    # --- liveness -------------------------------------------------------------

    def ping(self) -> None:
        """Raise if the backend is not reachable; the default assumes the constructor connected."""
