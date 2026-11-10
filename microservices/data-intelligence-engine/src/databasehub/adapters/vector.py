# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import List, Sequence, Set

from databasehub.models import VectorCollection
from llama_index.core import StorageContext
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import BasePydanticVectorStore


class VectorAdapter(ABC):
    """Connection-owning contract for a vector backend; holds no per-collection state."""

    @abstractmethod
    def reconcile(self, collection: VectorCollection) -> None:
        """Raise unless `collection` exists and is usable."""

    @abstractmethod
    def vector_store(self, collection: VectorCollection) -> BasePydanticVectorStore:
        """The LlamaIndex vector store bound to `collection`."""

    @abstractmethod
    def delete_by_metadata(
        self, collection: VectorCollection, field: str, values: Sequence[str]
    ) -> int:
        """Drop every record whose `field` is one of `values`; return how many."""

    @abstractmethod
    def present_metadata_values(
        self, collection: VectorCollection, field: str, values: Sequence[str]
    ) -> Set[str]:
        """Which of `values` appear under `field`; may under-report, must never over-report."""

    @abstractmethod
    def count_records(self, collection: VectorCollection) -> int:
        """How many records `collection` holds, or 0 if the backend cannot say."""

    @abstractmethod
    def load_nodes(self, collection: VectorCollection) -> List[BaseNode]:
        """Every record in `collection`, as nodes."""

    @abstractmethod
    def close(self) -> None:
        """Release the backend clients this adapter holds."""

    # --- liveness -------------------------------------------------------------

    def ping(self) -> None:
        """Raise if the backend is not reachable; the default assumes the constructor connected."""

    # --- backend-neutral ------------------------------------------------------

    def existing_concept_store(
        self, collection: VectorCollection, concept_ids: Set[str], exact: bool = True,
    ):
        """A validated existing concept store, or None; `exact=False` allows extra concepts."""
        return None

    def storage_context(self, collection: VectorCollection) -> StorageContext:
        """A LlamaIndex storage context bound to `collection`."""
        return StorageContext.from_defaults(vector_store=self.vector_store(collection))

    def flush(self, collection: VectorCollection) -> None:
        """Make writes to `collection` visible to later reads."""
