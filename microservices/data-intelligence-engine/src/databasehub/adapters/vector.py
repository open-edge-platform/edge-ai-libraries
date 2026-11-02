# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The vector backend contract: one adapter owns one connection."""

from abc import ABC, abstractmethod
from typing import List, Sequence, Set

from databasehub.models import VectorCollection
from llama_index.core import StorageContext
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import BasePydanticVectorStore


class VectorAdapter(ABC):
    """Connection-owning contract for a vector backend.

    Every method names the collection it acts on, so one adapter serves every
    collection its connection can reach and keeps no per-collection state.

    This is the *whole* boundary between the engine and a vector backend. A
    `VectorOperator` layer used to sit on top of it; seven of its nine methods
    forwarded straight to the identically named method here, so the two names
    described one seam. Behaviour that is genuinely backend-neutral belongs here
    as a concrete method instead -- `storage_context` is the only one so far.

    Note what is deliberately absent: storing and searching by raw embedding.
    Both already exist on the path the engine actually uses, where a projection's
    `VectorStoreIndex` does the embedding (core/indexer.py). Offering them a
    second time here meant two ways to write the same rows, with only one of them
    ever called. `vector_store` is the seam for that path; add an embedding-level
    API back only when something needs it.
    """

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
        """Which of `values` appear in `collection` under `field`.

        Bounded by `len(values)`, not by how many records match -- the caller
        asks about a known set of ids, so this must not degrade into a scan of
        the collection.

        An implementation that cannot answer may return a *subset*: the caller
        treats a missing value as not-yet-indexed, which costs re-indexing, not
        correctness. It must never claim a value is present when it is not.
        """

    @abstractmethod
    def count_records(self, collection: VectorCollection) -> int:
        """How many records `collection` holds.

        For reporting, so an implementation may return 0 rather than raise when
        the backend cannot say.
        """

    @abstractmethod
    def load_nodes(self, collection: VectorCollection) -> List[BaseNode]:
        """Every record in `collection`, as nodes."""

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

    # --- backend-neutral ------------------------------------------------------

    def existing_concept_store(
        self, collection: VectorCollection, concept_ids: Set[str], exact: bool = True,
    ):
        """Return a validated existing concept store, or None if unsupported.
        `exact=False` accepts a collection holding other concepts too."""
        return None

    def storage_context(self, collection: VectorCollection) -> StorageContext:
        """A LlamaIndex storage context bound to `collection`."""
        return StorageContext.from_defaults(vector_store=self.vector_store(collection))

    def flush(self, collection: VectorCollection) -> None:
        """Make writes to `collection` visible to later reads.

        A no-op on a backend that needs none; a projection calls it after
        inserting, since the insert itself goes through LlamaIndex and cannot.
        """
