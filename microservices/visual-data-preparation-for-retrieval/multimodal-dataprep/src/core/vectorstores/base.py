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
* ``delete_embeddings`` - remove all vectors belonging to a single stored video
  (``bucket_name`` + ``video_id``), keeping the vector DB in sync when a video is
  deleted from storage.
* ``health``         - report backend connectivity / status.

Vector *querying* is deliberately omitted: no current endpoint queries vectors
from the store (search is the retriever service's responsibility). Add query
methods here only when an endpoint requires them.
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
    def delete_embeddings(self, bucket_name: str, video_id: str) -> int:
        """Delete every vector belonging to one stored video.

        A video is uniquely identified by its ``bucket_name`` + ``video_id``, both
        of which are persisted on every embedding (full frame, detected crop, and
        text/summary). Implementations MUST remove all matching vectors so the
        vector DB stays consistent with storage when a video is deleted.

        The operation is idempotent: deleting a video that has no vectors (already
        removed, or never embedded) is not an error and returns ``0``.

        Args:
            bucket_name: The storage bucket the video was ingested under.
            video_id: The video directory / identifier whose vectors to remove.

        Returns:
            int: The number of vectors deleted, or ``-1`` when the backend cannot
            report an exact count but the delete succeeded.

        Raises:
            Exception: If the backend delete operation fails.
        """

    @abstractmethod
    def delete_bucket_embeddings(self, bucket_name: str) -> int:
        """Delete every vector belonging to one storage bucket.

        The bucket-wide counterpart of :meth:`delete_embeddings`, used to clear a
        whole ingested collection in one call without enumerating its videos.

        The operation is idempotent: clearing a bucket with no vectors is not an
        error and returns ``0``.

        Args:
            bucket_name: The storage bucket whose vectors to remove.

        Returns:
            int: The number of vectors deleted, or ``-1`` when the backend cannot
            report an exact count but the delete succeeded.

        Raises:
            Exception: If the backend delete operation fails.
        """

    @abstractmethod
    def health(self) -> dict:
        """Return a backend-agnostic health/status dict for the active backend."""
