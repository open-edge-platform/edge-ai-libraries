# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset-pool state transitions, and the sync they exist to serve."""

import threading
import time
from types import SimpleNamespace

import pytest

from assetlib import AssetPool, Source, SourceSyncStatus
from core.content import ContentStream
from core.file_asset_library import FileAsset, FileAssetLibrary
from llama_index.core.schema import Document


class FakeProjection:
    """A chunk projection whose `add` can be held open, as a real one is."""

    kind = "vector"
    version = 0

    def __init__(self, source_id="s1", gate=None, fail_times=0, holds=()):
        self.projection_id = f"p-{source_id}"
        self.name = "pool"
        self.source = Source(
            source_id=source_id,
            source_type="vector",
            database_id="a",
            location=None,
        )
        self.added = []
        self.deleted = []
        # What the backing collection already contains, as a real attached
        # collection may well be non-empty.
        self.held = set(holds)
        self.queried = []
        self._gate = gate
        self._fail_times = fail_times

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
        return 0

    def load(self):
        return []

    def count(self):
        return len(self.held)

    def indexed_asset_ids(self, asset_ids):
        self.queried.append(list(asset_ids))
        return self.held & set(asset_ids)

    def delete_by_metadata(self, field, values):
        self.deleted.append((field, list(values)))
        self.held -= set(values)
        return 0

    def add(self, assets):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("backend unavailable")
        self.added.extend(asset.asset_id for asset in assets)
        self.held.update(asset.asset_id for asset in assets)
        if self._gate is not None:
            self._gate.wait(5)
        return {"chunks_added": len(assets)}


def _asset(name):
    """An asset whose content is already in hand, so no store is needed."""
    stream = ContentStream.from_document(Document(text=name, id_=name))
    return FileAsset(
        asset_id=stream.asset_id, origin=f"file:///{name}", cached=stream
    )


def _asset_library(projection):
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.set_projections([projection])
    library._asset_pools["pool"] = pool
    return library, pool


def _ingest(library, *names):
    assets = [_asset(name) for name in names]
    library.register_assets(assets)
    library.add_assets_to_pool("pool", [asset.asset_id for asset in assets])


# --- status transitions -------------------------------------------------------


def test_mark_pending_keeps_the_last_error():
    """Rebuilding a frozen status used to drop it on the next unrelated ingest."""
    status = SourceSyncStatus(source_id="s1")
    status.mark_failed("Milvus collection 'docs' does not exist")

    status.mark_pending()

    assert status.status == "pending"
    assert status.error == "Milvus collection 'docs' does not exist"


def test_mark_ready_clears_the_error_and_records_progress():
    status = SourceSyncStatus(source_id="s1")
    status.mark_failed("transient")

    status.mark_ready(3, ["a", "b"])

    assert (status.status, status.indexed_revision) == ("ready", 3)
    assert status.indexed_asset_ids == ["a", "b"]
    assert status.error is None


def test_mark_failed_keeps_whatever_did_land():
    status = SourceSyncStatus(source_id="s1")
    status.mark_ready(2, ["a"])

    status.mark_failed("boom")

    assert status.indexed_revision == 2
    assert status.indexed_asset_ids == ["a"]


def test_mark_ready_can_preserve_stale_for_an_older_revision():
    status = SourceSyncStatus(source_id="s1")
    status.mark_stale(["a"])

    status.mark_ready(2, ["a"], clear_stale=False)

    assert status.indexed_revision == 2
    assert status.stale_asset_ids == ["a"]
    status.mark_ready(3, ["a"])
    assert status.stale_asset_ids == []


# --- pool transitions ---------------------------------------------------------


def test_add_asset_ids_bumps_the_revision_and_reopens_every_source():
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.set_projections([FakeProjection()])
    pool.source_statuses["s1"].mark_ready(0, [])

    assert pool.add_asset_ids(["a", "b"]) is True
    assert pool.asset_ids == ["a", "b"]
    assert pool.revision == 1
    assert pool.source_statuses["s1"].status == "pending"


def test_add_asset_ids_ignores_what_it_already_has():
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.add_asset_ids(["a"])

    assert pool.add_asset_ids(["a"]) is False
    assert pool.revision == 1  # unchanged


def test_set_projections_starts_pending_when_there_is_already_work():
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.add_asset_ids(["a"])

    pool.set_projections([FakeProjection(source_id="s2")])

    status = pool.source_statuses["s2"]
    assert (status.status, status.indexed_revision) == ("pending", -1)


def test_set_projections_starts_ready_when_the_pool_is_empty():
    pool = AssetPool(asset_pool_id="pool", name="pool")

    pool.set_projections([FakeProjection()])

    status = pool.source_statuses["s1"]
    assert (status.status, status.indexed_revision) == ("ready", 0)


# --- attaching a source to a pool that already has assets ---------------------


def test_a_pool_needs_no_sources_to_exist():
    """Sources are optional at creation; they can be attached later."""
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())

    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")

    assert pool.projections == ()
    assert pool.source_statuses == {}
    assert pool.asset_ids == []


def test_a_source_attached_later_picks_up_what_the_pool_already_holds():
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")
    library._asset_pools["pool"] = pool
    _ingest(library, "doc-A")

    projection = FakeProjection()
    pool.set_projections(
        [projection], library._already_indexed(pool, [projection])
    )

    assert pool.source_statuses["s1"].status == "pending"
    library.sync_asset_pool("pool")
    assert projection.added == ["doc-A"]


def test_attaching_a_source_that_already_holds_everything_needs_no_sync():
    """An attached collection may already contain the pool's assets."""
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")
    library._asset_pools["pool"] = pool
    _ingest(library, "doc-A", "doc-B")

    projection = FakeProjection(holds={"doc-A", "doc-B"})
    pool.set_projections(
        [projection], library._already_indexed(pool, [projection])
    )

    status = pool.source_statuses["s1"]
    assert (status.status, status.indexed_revision) == ("ready", pool.revision)
    assert status.indexed_asset_ids == ["doc-A", "doc-B"]

    library.sync_asset_pool("pool")
    assert projection.added == [], "nothing to re-index"


def test_attaching_a_partially_filled_source_only_syncs_the_difference():
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")
    library._asset_pools["pool"] = pool
    _ingest(library, "doc-A", "doc-B")

    projection = FakeProjection(holds={"doc-A"})
    pool.set_projections(
        [projection], library._already_indexed(pool, [projection])
    )

    status = pool.source_statuses["s1"]
    assert status.status == "pending"
    assert status.indexed_asset_ids == ["doc-A"]

    library.sync_asset_pool("pool")
    assert projection.added == ["doc-B"], "doc-A was already there"


def test_the_check_is_bounded_by_the_pools_assets():
    """It asks about known ids rather than enumerating the collection."""
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")
    library._asset_pools["pool"] = pool
    _ingest(library, "doc-A", "doc-B")

    projection = FakeProjection(holds={"doc-A"})
    library._already_indexed(pool, [projection])

    assert projection.queried == [["doc-A", "doc-B"]]


def test_an_empty_pool_asks_its_new_source_nothing():
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = AssetPool(asset_pool_id="pool", name="pool")
    projection = FakeProjection(holds={"doc-A"})

    assert library._already_indexed(pool, [projection]) == {}
    assert projection.queried == []


def test_re_attaching_a_source_keeps_its_progress():
    """Replacing the source list must not make a synced source start over."""
    staying = FakeProjection(source_id="s1")
    library, pool = _asset_library(staying)
    _ingest(library, "doc-A")
    pool.source_statuses["s1"].mark_ready(pool.revision, ["doc-A"])

    added = FakeProjection(source_id="s2")
    pool.set_projections(
        [staying, added], library._already_indexed(pool, [staying, added])
    )

    kept = pool.source_statuses["s1"]
    assert (kept.status, kept.indexed_revision) == ("ready", 1)
    assert kept.indexed_asset_ids == ["doc-A"]
    assert staying.queried == [], "a source that stays is not re-interrogated"
    assert pool.source_statuses["s2"].status == "pending"


def test_detaching_a_source_drops_its_status():
    pool = AssetPool(asset_pool_id="pool", name="pool")
    first, second = FakeProjection(source_id="s1"), FakeProjection(source_id="s2")
    pool.set_projections([first, second])

    pool.set_projections([second])

    assert set(pool.source_statuses) == {"s2"}


# --- sync ---------------------------------------------------------------------


def test_an_ingest_during_a_sync_is_not_lost():
    """The regression this restructuring is for.

    `sync_asset_pool` used to snapshot the pool, spend minutes in
    `projection.add`, then write the snapshot back -- reverting anything ingested
    meanwhile *and* recording `ready`, so the reverted assets were never indexed.
    """
    gate = threading.Event()
    projection = FakeProjection(gate=gate)
    library, pool = _asset_library(projection)

    _ingest(library, "doc-A")
    syncing = threading.Thread(target=library.sync_asset_pool, args=("pool",))
    syncing.start()
    try:
        time.sleep(0.2)  # the sync is inside projection.add
        _ingest(library, "doc-B")
    finally:
        gate.set()
        syncing.join()

    status = pool.source_statuses["s1"]
    assert pool.asset_ids == ["doc-A", "doc-B"], "the mid-sync ingest survived"
    assert pool.revision == 2
    assert projection.added == ["doc-A"]
    # Recorded against the revision the sync actually covered, so it is behind
    # the pool and the next sync collects doc-B.
    assert status.indexed_revision == 1 < pool.revision

    library.sync_asset_pool("pool")

    assert projection.added == ["doc-A", "doc-B"]
    assert pool.source_statuses["s1"].indexed_revision == 2
    assert projection.added.count("doc-A") == 1, "no duplicate re-add"


def test_a_failed_sync_retries_without_duplicating_chunks():
    """A retry re-parses documents into fresh node ids, so it must delete first."""
    projection = FakeProjection(fail_times=1)
    library, pool = _asset_library(projection)
    _ingest(library, "doc-A")

    library.sync_asset_pool("pool")
    failed = pool.source_statuses["s1"]
    assert failed.status == "failed"
    assert failed.error == "backend unavailable"
    assert projection.added == []

    library.sync_asset_pool("pool")

    assert pool.source_statuses["s1"].status == "ready"
    assert projection.added == ["doc-A"]
    # Both attempts scoped their delete to the assets they were about to write.
    assert projection.deleted == [("asset_id", ["doc-A"]), ("asset_id", ["doc-A"])]


@pytest.mark.parametrize("initially_stale", [False, True])
def test_same_asset_changed_during_sync_stays_stale_until_next_revision(initially_stale):
    projection = FakeProjection()
    library, pool = _asset_library(projection)
    _ingest(library, "doc-A")
    if initially_stale:
        library.sync_asset_pool("pool")
        library.note_assets_changed(["doc-A"])
    revision = pool.revision
    add = projection.add

    def change_during_add(assets):
        result = add(assets)
        library.note_assets_changed(["doc-A"])
        return result

    projection.add = change_during_add
    library.sync_asset_pool("pool")

    status = pool.source_statuses["s1"]
    assert status.indexed_revision == revision < pool.revision
    assert status.stale_asset_ids == ["doc-A"]
    assert projection.held == {"doc-A"}, "backend presence must not hide the update"
    writes = len(projection.added)
    projection.add = add
    library.sync_asset_pool("pool")

    assert projection.added[writes:] == ["doc-A"]
    assert projection.deleted[-1] == ("asset_id", ["doc-A"])
    assert status.indexed_revision == pool.revision
    assert status.stale_asset_ids == []


def test_any_revision_change_conservatively_preserves_existing_stale():
    projection = FakeProjection()
    library, pool = _asset_library(projection)
    _ingest(library, "doc-A")
    library.sync_asset_pool("pool")
    library.note_assets_changed(["doc-A"])
    revision = pool.revision
    add = projection.add

    def ingest_during_add(assets):
        result = add(assets)
        _ingest(library, "doc-B")
        return result

    projection.add = ingest_during_add
    library.sync_asset_pool("pool")

    status = pool.source_statuses["s1"]
    assert status.indexed_revision == revision < pool.revision
    assert status.stale_asset_ids == ["doc-A"]
    projection.add = add
    library.sync_asset_pool("pool")
    assert projection.added == ["doc-A", "doc-A", "doc-A", "doc-B"]
    assert status.stale_asset_ids == []


def test_sync_is_a_no_op_once_the_revision_is_covered():
    projection = FakeProjection()
    library, pool = _asset_library(projection)
    _ingest(library, "doc-A")

    library.sync_asset_pool("pool")
    library.sync_asset_pool("pool")

    assert projection.added == ["doc-A"]
    assert projection.deleted == [("asset_id", ["doc-A"])]


# --- persistence --------------------------------------------------------------


def test_a_pool_survives_a_record_round_trip():
    projection = FakeProjection()
    library, pool = _asset_library(projection)
    _ingest(library, "doc-A")
    pool.source_statuses["s1"].mark_ready(1, ["doc-A"])
    pool.source_statuses["s1"].mark_failed("later failure")

    record = library.to_record()
    pool_record = record["asset_pools"][0]

    assert pool_record["asset_ids"] == ["doc-A"]
    assert pool_record["revision"] == 1
    status_record = pool_record["source_statuses"]["s1"]
    assert status_record["status"] == "failed"
    assert status_record["error"] == "later failure"
    assert status_record["indexed_asset_ids"] == ["doc-A"]
