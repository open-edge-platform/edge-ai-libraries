# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The vector adapter is the whole backend boundary."""

from types import SimpleNamespace

import pytest

from databasehub.adapters.milvus import MilvusAdapter
from databasehub.adapters.vector import VectorAdapter
from databasehub.models import VectorCollection


class StubAdapter(VectorAdapter):
    """A complete implementation: nothing here is optional."""

    def __init__(self):
        self.calls = []
        self.store = SimpleNamespace(name="store")

    def reconcile(self, collection):
        self.calls.append(("reconcile", collection))

    def vector_store(self, collection):
        self.calls.append(("vector_store", collection))
        return self.store

    def delete_by_metadata(self, collection, field, values):
        self.calls.append(("delete_by_metadata", collection, field, list(values)))
        return len(values)

    def present_metadata_values(self, collection, field, values):
        self.calls.append(("present_metadata_values", collection, field, list(values)))
        return set(values)

    def count_records(self, collection):
        self.calls.append(("count_records", collection))
        return 0

    def load_nodes(self, collection):
        self.calls.append(("load_nodes", collection))
        return []

    def close(self):
        self.calls.append(("close",))


COLLECTION = VectorCollection("documents", 4)


def test_storage_context_binds_the_collections_store():
    """The one concrete helper: the seam towards LlamaIndex."""
    adapter = StubAdapter()

    context = adapter.storage_context(COLLECTION)

    assert context.vector_store is adapter.store
    assert adapter.calls == [("vector_store", COLLECTION)]


def test_flush_defaults_to_a_no_op():
    """A backend that needs no flush inherits one that does nothing."""
    adapter = StubAdapter()

    assert adapter.flush(COLLECTION) is None
    assert adapter.calls == []


def test_every_method_names_its_collection():
    adapter = StubAdapter()

    adapter.reconcile(COLLECTION)
    assert adapter.delete_by_metadata(COLLECTION, "asset_id", ["a", "b"]) == 2
    assert adapter.present_metadata_values(COLLECTION, "asset_id", ["a"]) == {"a"}
    assert adapter.count_records(COLLECTION) == 0
    adapter.load_nodes(COLLECTION)
    adapter.close()

    assert [call[1] for call in adapter.calls if len(call) > 1] == [COLLECTION] * 5


def test_the_contract_has_no_embedding_level_write_or_search():
    """Storing and searching by raw embedding duplicated the index path.

    Both existed on the adapter and on the `VectorStoreIndex` a projection owns;
    only the index path was ever called. If either comes back, it needs a caller.
    """
    assert not hasattr(VectorAdapter, "store")
    assert not hasattr(VectorAdapter, "store_nodes")
    assert not hasattr(VectorAdapter, "search")
    assert not hasattr(VectorAdapter, "clear")


def test_an_incomplete_adapter_cannot_be_instantiated():
    """The ABC is enforced, unlike the Protocol the operator layer took."""

    class HalfWay(VectorAdapter):
        def reconcile(self, collection):
            pass

    with pytest.raises(TypeError):
        HalfWay()


def test_milvus_implements_the_contract():
    assert issubclass(MilvusAdapter, VectorAdapter)
    # It overrides flush, because Milvus does need sealing.
    assert MilvusAdapter.flush is not VectorAdapter.flush
