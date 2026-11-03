# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset-library records survive persistence round trips.

`AssetLibrary` owns the generic record and `FileAssetLibrary` adds document
and file state around it.
"""

from types import SimpleNamespace
from typing import Any, Mapping

from assetlib import AssetLibrary, Source
from core.file_asset_library import FileAsset, FileAssetLibrary
from llama_index.core.schema import Document


class FakeProjection:
    kind = "vector"
    version = 0

    def __init__(self, source):
        self.projection_id = f"p-{source.source_id}"
        self.name = "pool"
        self.source = source

    @property
    def collection(self):
        return None

    def accepts(self, asset):
        return True

    def add(self, assets):
        return {}

    def remove(self, asset_ids):
        return 0

    def materialize(self, request):
        return {}

    def retrieve(self, query):
        return []


class SimpleLibrary(AssetLibrary):
    """The smallest possible specialization: assets are plain dicts."""

    def build_projection(self, projection_id, name, source):
        return FakeProjection(source)

    def asset_to_record(self, asset) -> dict:
        return {"asset_id": asset.asset_id, "payload": asset.payload}

    def asset_from_record(self, record: Mapping[str, Any]):
        return SimpleNamespace(
            asset_id=str(record["asset_id"]), payload=record["payload"]
        )


def _source_record(source_id="s1", collection="docs"):
    return {
        "source_id": source_id,
        "name": "primary",
        "source_type": "vector",
        "database_id": "default-vector",
        "collection": {"name": collection, "dimension": 8},
        "operator_options": {},
    }


def _library_record(**overrides):
    record = {
        "idx": "lib-1",
        "name": "library",
        "description": "a library",
        "sources": [_source_record()],
        "assets": [{"asset_id": "a1", "payload": "hello"}],
        "asset_pools": [
            {
                "asset_pool_id": "pool",
                "name": "pool",
                "metadata": {"origin": "test"},
                "asset_ids": ["a1"],
                "revision": 3,
                "source_statuses": {
                    "s1": {
                        "source_id": "s1",
                        "status": "failed",
                        "indexed_revision": 2,
                        "indexed_asset_ids": ["a1"],
                        "error": "backend down",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                },
                "sources": [_source_record()],
            }
        ],
    }
    record.update(overrides)
    return record


def test_a_library_round_trips():
    library = SimpleLibrary.from_record(
        _library_record(), databasehub=SimpleNamespace()
    )

    assert library.idx == "lib-1"
    assert library.name == "library"
    assert library.description == "a library"
    assert set(library.sources) == {"s1"}
    assert library.asset_count == 1
    assert library.assets["a1"].payload == "hello"

    pool = library.asset_pools["pool"]
    assert pool.asset_ids == ["a1"]
    assert pool.revision == 3
    assert pool.metadata == {"origin": "test"}
    status = pool.source_statuses["s1"]
    assert (status.status, status.indexed_revision) == ("failed", 2)
    assert status.error == "backend down"
    assert status.updated_at == "2026-01-01T00:00:00+00:00"

    again = library.to_record()
    assert again["idx"] == "lib-1"
    assert again["asset_pools"][0]["revision"] == 3
    assert again["asset_pools"][0]["source_statuses"]["s1"]["error"] == "backend down"
    assert again["assets"] == [{"asset_id": "a1", "payload": "hello"}]

    # And a second trip is a fixed point.
    third = SimpleLibrary.from_record(again, databasehub=SimpleNamespace()).to_record()
    assert third == again


def test_the_former_asset_set_keys_still_load():
    record = _library_record()
    pool = record.pop("asset_pools")[0]
    pool["asset_set_id"] = pool.pop("asset_pool_id")
    record["asset_sets"] = [pool]

    library = SimpleLibrary.from_record(record, databasehub=SimpleNamespace())

    assert set(library.asset_pools) == {"pool"}
    assert library.asset_pools["pool"].revision == 3


def test_a_pool_that_recorded_a_single_source_still_loads():
    record = _library_record()
    pool = record["asset_pools"][0]
    pool["source"] = pool.pop("sources")[0]

    library = SimpleLibrary.from_record(record, databasehub=SimpleNamespace())

    assert len(library.asset_pools["pool"].projections) == 1


def test_a_pool_that_recorded_projection_ids_still_loads():
    record = _library_record()
    pool = record["asset_pools"][0]
    pool.pop("sources")
    pool["projection_ids"] = ["proj-1"]
    record["projections"] = [{"projection_id": "proj-1", "source": _source_record()}]

    library = SimpleLibrary.from_record(record, databasehub=SimpleNamespace())

    assert len(library.asset_pools["pool"].projections) == 1


def test_an_unreachable_source_is_reported_not_fatal():
    record = _library_record()
    record["sources"] = [_source_record(), _source_record("s1")]  # duplicate id

    library = SimpleLibrary.from_record(record, databasehub=SimpleNamespace())

    assert set(library.sources) == {"s1"}


# --- document asset-library state --------------------------------------------


class StubFileAssetLibrary(FileAssetLibrary):
    """Real persistence, fake projections -- no databasehub, no Milvus."""

    def build_projection(self, projection_id, name, source):
        return FakeProjection(source)


def _document_library_record():
    record = _library_record()
    record["assets"] = [
        {
            "asset_id": "a1",
            "document": {"text": "hello", "id_": "a1", "metadata": {}},
            "origin": {
                "source_id": "file:/tmp/a.txt",
                "name": "",
                "source_type": "file",
                "database_id": "",
                "collection": "/tmp/a.txt",
                "operator_options": {},
            },
        }
    ]
    record["file_map"] = {"a.txt": "/tmp/a.txt"}
    return record


def test_a_file_asset_library_round_trips_with_its_files():
    library = StubFileAssetLibrary.from_record(
        _document_library_record(), databasehub=SimpleNamespace()
    )

    assert library.file_map == {"a.txt": "/tmp/a.txt"}
    assert library.document_count == 1
    asset = library.assets["a1"]
    assert isinstance(asset, FileAsset)
    assert asset.origin == "file:///tmp/a.txt"
    assert asset.content.text() == "hello"

    again = library.to_record()
    assert again["file_map"] == {"a.txt": "/tmp/a.txt"}
    assert again["assets"][0]["origin"] == "file:///tmp/a.txt"


def test_an_asset_persisted_before_origins_had_a_name_still_loads():
    """The key used to be `source`, back when origins shared the registry."""
    record = _document_library_record()
    record["assets"][0]["source"] = record["assets"][0].pop("origin")

    library = StubFileAssetLibrary.from_record(
        record, databasehub=SimpleNamespace()
    )

    assert library.assets["a1"].origin == "file:///tmp/a.txt"


def test_stale_persisted_counts_are_ignored():
    """They were written by an older engine and were always wrong; now derived."""
    record = _document_library_record()
    record["document_count"] = 999
    record["chunk_count"] = 12345

    library = StubFileAssetLibrary.from_record(
        record, databasehub=SimpleNamespace()
    )

    assert library.document_count == 1
    assert "document_count" not in library.to_record()


def test_origins_do_not_leak_into_the_source_registry():
    """An asset's origin is not somewhere the library materializes to."""
    library = StubFileAssetLibrary.from_record(
        _document_library_record(), databasehub=SimpleNamespace()
    )

    assert set(library.sources) == {"s1"}
    assert all(source.database_id for source in library.sources.values())
    assert [source.to_record()["source_id"] for source in library.sources.values()] == ["s1"]


def test_forgetting_assets_updates_the_pools_and_the_count():
    library = StubFileAssetLibrary.from_record(
        _document_library_record(), databasehub=SimpleNamespace()
    )

    assert library.forget_assets(["a1"]) == ["a1"]

    assert library.document_count == 0
    assert library.asset_pools["pool"].asset_ids == []
    assert library.asset_pools["pool"].source_statuses["s1"].indexed_asset_ids == []
    assert library.asset_pools["pool"].revision == 3, "removing work creates none"
