# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Abstract base class for pluggable vector-store backends.

The contract is intentionally trimmed to the operations the DataPrep service
actually performs today:

* ``connect``        - establish / lazily initialize the backend connection.
* ``add_embeddings`` - persist precomputed vectors + metadata + ids.
* ``clean_metadata`` - adapt the backend-neutral canonical metadata to the
  representation the backend accepts.
* ``update_index``   - flush/refresh the index (no-op for backends that index
  eagerly, e.g. Milvus).
* ``health``         - report backend connectivity / status.

Vector *deletion* and *querying* are deliberately omitted: no current endpoint
deletes or queries vectors from the store (``delete_video`` only removes objects
from storage). Add those methods here only when an endpoint requires them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class BaseVectorStore(ABC):
    """Common interface every vector-store backend must implement."""

    @abstractmethod
    def connect(self) -> None:
        """Establish or lazily initialize the backend connection / collection."""

    @abstractmethod
    def add_embeddings(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Persist precomputed embeddings with their texts and metadata.

        Args:
            texts: Per-vector text/content payloads.
            embeddings: Precomputed embedding vectors.
            metadatas: Per-vector canonical metadata dicts (already cleaned, or
                cleaned internally via :meth:`clean_metadata`).
            ids: Optional explicit ids; backends generate ids when omitted.

        Returns:
            The list of stored record ids, normalized to ``str``.
        """

    @abstractmethod
    def clean_metadata(self, metadata: dict) -> dict:
        """Adapt canonical metadata to the backend's accepted representation."""

    @abstractmethod
    def update_index(self) -> None:
        """Flush/refresh the index. No-op for backends that index eagerly."""

    @abstractmethod
    def health(self) -> dict:
        """Return a backend-agnostic health/status dict for the active backend."""
