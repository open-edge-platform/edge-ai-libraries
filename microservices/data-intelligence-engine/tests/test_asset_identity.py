# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""An asset is one file, and re-ingesting that file updates it.

The pieces a loader splits a file into are blocks of one asset, not assets. And
because an asset's id comes from where it came from rather than from a loader's
per-run document id, ingesting the same file twice is an update -- which only
works if the pools it belongs to are told its content changed.
"""

import pytest

from assetlib import AssetPool, Source
from core.content import TEXT, ContentStream
from core.file_asset_library import (
    FileAssetLibrary,
    asset_id_for,
    file_origin,
)
from databasehub.models import VectorCollection
from . import dbhub
from llama_index.core.schema import Document


class FakeProjection:
    """A chunk projection that reports what it holds, as Milvus would."""

    kind = "vector"
    version = 0

    def __init__(self, source_id="s1"):
        self.projection_id = f"p-{source_id}"
        self.name = "pool"
        self.source = Source(
            source_id=source_id,
            name="primary",
            source_type="vector",
            database_id=dbhub.VECTOR_DATABASE,
            location=VectorCollection("docs", 8),
        )
        self.added = []
        self.deleted = []
        self.removed = []
        self.held = set()

    @property
    def collection(self):
        return None

    def accepts(self, asset):
        return True

    def materialize(self, request):
        return {}

    def retrieve(self, query):
        return []

    def remove(self, asset_ids):
        removed = self.held & set(asset_ids)
        self.removed.append(list(asset_ids))
        self.held -= removed
        return len(removed)

    def load(self):
        return []

    def count(self):
        return len(self.held)

    def indexed_asset_ids(self, asset_ids):
        return self.held & set(asset_ids)

    def delete_by_metadata(self, field, values):
        self.deleted.append((field, list(values)))
        self.held -= set(values)
        return 0

    def add(self, assets):
        self.added.extend(asset.asset_id for asset in assets)
        self.held.update(asset.asset_id for asset in assets)
        return {"chunks_added": len(assets)}


class StubLibrary(FileAssetLibrary):
    def build_projection(self, projection_id, name, source):
        return FakeProjection(source.source_id)


def _library_with_pool():
    library = StubLibrary(
        name="library", databasehub=dbhub.with_vector(dbhub.object_hub())
    )
    projection = FakeProjection()
    # The pool's source belongs to the library, as it would if the pool had been
    # created through the API rather than assembled here.
    library.add_source(projection.source)
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.set_projections([projection])
    library._asset_pools["pool"] = pool
    return library, pool, projection


def _pages(*texts):
    return [
        Document(text=text, id_=f"page-{i}", metadata={"page_label": str(i + 1)})
        for i, text in enumerate(texts)
    ]


def _ingest(library, path, *pages):
    """What the library-assets endpoint does, without the HTTP layer."""
    origin = file_origin(path)
    asset = library.create_asset(
        origin=origin,
        stream=ContentStream.from_documents(_pages(*pages), asset_id_for(origin)),
    )
    replaced = asset.asset_id in library.assets
    library.register_assets([asset])
    library.add_assets_to_pool("pool", [asset.asset_id])
    if replaced:
        library.note_assets_changed([asset.asset_id])
    return asset


# --- identity -----------------------------------------------------------------


def test_an_id_is_stable_for_the_same_file():
    assert asset_id_for(file_origin("/w/a.pdf")) == asset_id_for(file_origin("/w/a.pdf"))
    assert asset_id_for(file_origin("/w/a.pdf")) != asset_id_for(file_origin("/w/b.pdf"))


def test_a_relative_and_absolute_path_are_the_same_file():
    import os

    here = os.path.basename(__file__)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    assert file_origin(here) == file_origin(os.path.abspath(here))


def test_one_file_is_one_asset_however_many_pages_it_has():
    library, _, _ = _library_with_pool()

    asset = _ingest(library, "/w/a.pdf", "page one", "page two", "page three")

    assert library.asset_count == 1
    assert library.document_count == 1, "documents are files, not pages"
    assert len(asset.content.blocks) == 3
    assert asset.content.text() == "page one\n\npage two\n\npage three"


def test_asset_listing_reports_identity_origin_and_pool_membership():
    library, _, _ = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "page one")

    page = library.list_assets()

    assert page.total == 1
    dump = page.assets[0].model_dump()
    # The content source is a generated UUID; assert it is present, then compare
    # the stable identity fields.
    assert dump.pop("content_source_id")
    assert dump == {
        "id": asset.asset_id,
        "name": "a.pdf",
        "origin": "file:///w/a.pdf",
        "kind": "file",
        "media_type": "application/pdf",
        "asset_pool_ids": ["pool"],
        "materialization": None,
    }


def test_deleting_an_asset_removes_every_materialization_and_content_record():
    library, first_pool, first_projection = _library_with_pool()
    second_projection = FakeProjection("s2")
    library.add_source(second_projection.source)
    second_pool = AssetPool(asset_pool_id="second", name="second")
    second_pool.set_projections([second_projection])
    library._asset_pools["second"] = second_pool

    asset = _ingest(library, "/w/a.pdf", "page one")
    library.file_map["a.pdf"] = "/w/a.pdf"
    library.add_assets_to_pool("second", [asset.asset_id])
    library.sync_asset_pool("pool")
    library.sync_asset_pool("second")
    content_source = library.sources[asset.content_source_id]
    assert library.content_store.exists(content_source, asset.content_key)

    result = library.delete_assets([asset.asset_id])

    assert result == {
        "removed": [asset.asset_id],
        "materializations_removed": 2,
        "files_removed": [],
        "files_kept": [],
    }
    assert first_projection.removed == [[asset.asset_id]]
    assert second_projection.removed == [[asset.asset_id]]
    assert first_pool.asset_ids == []
    assert second_pool.asset_ids == []
    assert asset.asset_id not in library.assets
    assert "a.pdf" not in library.file_map
    assert not library.content_store.exists(content_source, asset.content_key)


def test_asset_deletion_fails_before_mutation_when_a_source_is_unavailable():
    library, pool, projection = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "page one")
    pool.unavailable_sources["offline"] = projection.source

    with pytest.raises(ValueError, match="unavailable"):
        library.delete_assets([asset.asset_id])

    assert asset.asset_id in library.assets
    assert projection.removed == []


def test_pages_become_blocks_in_reading_order_with_their_page_numbers():
    library, _, _ = _library_with_pool()

    asset = _ingest(library, "/w/a.pdf", "first", "second")
    blocks = asset.content.ordered()

    assert [block.reading_order for block in blocks] == [0, 1]
    assert [block.page for block in blocks] == [1, 2]
    assert all(block.kind == TEXT for block in blocks)


def test_page_metadata_does_not_become_document_metadata():
    library, _, _ = _library_with_pool()

    asset = _ingest(library, "/w/a.pdf", "first", "second")

    assert "page_label" not in asset.content.metadata
    assert asset.content.metadata["asset_id"] == asset.asset_id


# --- re-ingesting the same file -----------------------------------------------


def test_re_ingesting_a_file_updates_the_asset_instead_of_adding_one():
    library, pool, projection = _library_with_pool()
    first = _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")

    second = _ingest(library, "/w/a.pdf", "revised")

    assert second.asset_id == first.asset_id
    assert library.asset_count == 1
    assert pool.asset_ids == [first.asset_id]
    assert library.assets[first.asset_id].content.text() == "revised"


def test_the_replaced_content_is_re_indexed():
    """The source still holds records for the asset -- they are the wrong ones."""
    library, pool, projection = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")
    assert projection.added == [asset.asset_id]

    _ingest(library, "/w/a.pdf", "revised")
    library.sync_asset_pool("pool")

    assert projection.added == [asset.asset_id, asset.asset_id], "written again"
    assert (
        "asset_id",
        [asset.asset_id],
    ) in projection.deleted, "the stale records were dropped first"
    assert pool.source_statuses["s1"].stale_asset_ids == []


def test_an_unchanged_file_is_not_re_indexed():
    library, pool, projection = _library_with_pool()
    _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")

    library.sync_asset_pool("pool")

    assert len(projection.added) == 1


def test_marking_changed_bumps_the_revision_so_the_sync_looks():
    library, pool, projection = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")
    settled = pool.revision

    library.note_assets_changed([asset.asset_id])

    assert pool.revision == settled + 1
    status = pool.source_statuses["s1"]
    assert status.status == "pending"
    assert status.stale_asset_ids == [asset.asset_id]


def test_marking_an_asset_the_pool_does_not_hold_changes_nothing():
    library, pool, _ = _library_with_pool()
    _ingest(library, "/w/a.pdf", "original")
    settled = pool.revision

    library.note_assets_changed(["not-in-this-pool"])

    assert pool.revision == settled


def test_forgetting_an_asset_clears_its_stale_mark():
    library, pool, _ = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")
    library.note_assets_changed([asset.asset_id])

    library.forget_assets([asset.asset_id])

    assert pool.source_statuses["s1"].stale_asset_ids == []
    assert pool.asset_ids == []


def test_stale_marks_survive_a_record_round_trip():
    library, pool, _ = _library_with_pool()
    asset = _ingest(library, "/w/a.pdf", "original")
    library.sync_asset_pool("pool")
    library.note_assets_changed([asset.asset_id])

    restored = StubLibrary.from_record(
        library.to_record(), databasehub=library._databasehub
    )

    status = restored.asset_pools["pool"].source_statuses["s1"]
    assert status.stale_asset_ids == [asset.asset_id]
