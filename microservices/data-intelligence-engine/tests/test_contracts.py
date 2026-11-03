# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The projection contracts say what a projection actually provides.

These import only `assetlib.contracts`, which pulls in nothing heavier
than the standard library -- so they run without llama-index or a live Milvus.
"""

from typing import Sequence, Set

from assetlib.contracts import ChunkProjection, Projection, Source


class FakeVectorProjection:
    """Shaped like core.indexer.VectorIndexer."""

    kind = "vector"

    def __init__(self):
        self.projection_id = "p1"
        self.name = "pool"
        self.source = Source(source_id="s1", source_type="vector", location=None)
        self.version = 0
        self.deleted = []

    @property
    def collection(self):
        return None

    def accepts(self, asset) -> bool:
        return True

    def add(self, assets):
        return {"chunks_added": len(assets)}

    def remove(self, asset_ids):
        return self.delete_by_metadata("asset_id", list(asset_ids))

    def materialize(self, request):
        return {"chunks_added": 0}

    def retrieve(self, query):
        return []

    def load(self) -> Sequence:
        return []

    def indexed_asset_ids(self, asset_ids: Sequence[str]) -> Set[str]:
        return set()

    def count(self) -> int:
        return 0

    def delete_by_metadata(self, field: str, values: Sequence[str]) -> int:
        self.deleted.append((field, list(values)))
        self.version += 1
        return len(values)


class FakeGraphProjection:
    """Shaped like core.indexer.GraphIndexer: no chunks to enumerate or drop."""

    kind = "graph"

    def __init__(self):
        self.projection_id = "p2"
        self.name = "pool"
        self.source = Source(source_id="s2", source_type="graph", location=None)

    @property
    def collection(self):
        return None

    def accepts(self, asset) -> bool:
        return True

    def add(self, assets):
        return {"vertices_added": len(assets)}

    def remove(self, asset_ids):
        raise ValueError("cannot remove assets")

    def materialize(self, request):
        return {"vertices_added": 0}

    def retrieve(self, query):
        return []


def test_chunk_projection_distinguishes_the_two_kinds():
    """This is what replaced `hasattr(projection, "delete_by_metadata")`."""
    assert isinstance(FakeVectorProjection(), ChunkProjection)
    assert not isinstance(FakeGraphProjection(), ChunkProjection)


def test_a_partial_implementation_is_not_a_chunk_projection():
    class HalfWay:
        version = 0

        def load(self):
            return []

    assert not isinstance(HalfWay(), ChunkProjection)


def test_projection_protocol_declares_no_postprocess():
    """Postprocessing operates on a result set, not on a projection."""
    members = set(Projection.__annotations__) | set(Projection.__dict__)
    assert "postprocess" not in members
    assert {"accepts", "add", "remove", "materialize", "retrieve"} <= members
