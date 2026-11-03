# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A pool may hold more than any one of its sources wants.

Reports and the recordings that go with them belong in the same pool -- they are
about the same thing, and a graph is what relates them. But a graph source
extracting knowledge has no use for the recordings and a text collection has no
use for a video, so each projection takes the assets it accepts and no others.

The trap this has to avoid is progress: a source measured against assets it will
never hold can never be up to date, so it re-syncs on every pass forever.
`sync_asset_pool` therefore computes everything -- what is indexed, what is
missing, what revision has been reached -- against that source's own subset.
"""

from types import SimpleNamespace

from assetlib import AssetPool
from core.content import ContentBlock, ContentStream
from core.file_asset_library import FileAsset, FileAssetLibrary
from core.indexer import accepts_asset


class FakeProjection:
    kind = "vector"
    version = 0

    def __init__(self, source_id="s1", asset_types=None):
        self.projection_id = f"p-{source_id}"
        self.name = "pool"
        self.configuration = {"asset_types": asset_types} if asset_types else {}
        self.source = SimpleNamespace(source_id=source_id)
        self.added = []
        self.queried = []
        self.held = set()

    def accepts(self, asset):
        return accepts_asset(asset, self.configuration)

    def indexed_asset_ids(self, asset_ids):
        self.queried.append(list(asset_ids))
        return self.held & set(asset_ids)

    def delete_by_metadata(self, field, values):
        self.held -= set(values)
        return 0

    def count(self):
        return len(self.held)

    def load(self):
        return []

    def materialize(self, request):
        return {}

    def retrieve(self, query):
        return []

    def remove(self, asset_ids):
        return 0

    def add(self, assets):
        self.added.append([asset.asset_id for asset in assets])
        self.held.update(asset.asset_id for asset in assets)
        return {"chunks_added": len(assets)}


def _asset(asset_id, name):
    return FileAsset(
        asset_id=asset_id,
        origin=f"file:///w/{name}",
        cached=ContentStream(
            asset_id=asset_id,
            blocks=[ContentBlock(block_id=f"{asset_id}:0", text="words")],
        ),
    )


def _library(*projections):
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = AssetPool(asset_pool_id="pool", name="pool")
    pool.set_projections(list(projections))
    library._asset_pools["pool"] = pool
    return library, pool


def _ingest(library, *named):
    assets = [_asset(asset_id, name) for asset_id, name in named]
    library.register_assets(assets)
    library.add_assets_to_pool("pool", [asset.asset_id for asset in assets])


# --- what the filter matches --------------------------------------------------


def test_an_unconfigured_projection_takes_everything():
    assert accepts_asset(_asset("a1", "clip.mp4"), {})


def test_an_extension_matches():
    asset = _asset("a1", "report.pdf")

    assert accepts_asset(asset, {"asset_types": ["pdf"]})
    assert not accepts_asset(asset, {"asset_types": ["docx"]})


def test_a_mime_family_matches_so_all_video_can_be_named_at_once():
    assert accepts_asset(_asset("a1", "clip.mp4"), {"asset_types": ["video"]})
    assert accepts_asset(_asset("a1", "clip.mp4"), {"asset_types": ["video/mp4"]})
    assert not accepts_asset(_asset("a1", "clip.mp4"), {"asset_types": ["image"]})


def test_the_filter_never_reads_the_content():
    """It is asked of every asset on every sync; loading each stream would cost
    as much as indexing them."""
    asset = FileAsset(asset_id="a1", origin="file:///w/report.pdf")

    assert accepts_asset(asset, {"asset_types": ["pdf"]})  # no loader bound


def test_something_that_is_not_an_asset_is_not_accepted():
    assert not accepts_asset(SimpleNamespace(asset_id="a1"), {})


# --- sync ---------------------------------------------------------------------


def test_a_source_only_receives_what_it_accepts():
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    vector = FakeProjection(source_id="s2")
    library, _ = _library(graph, vector)
    _ingest(library, ("a1", "report.pdf"), ("a2", "clip.mp4"))

    library.sync_asset_pool("pool")

    assert graph.added == [["a1"]], "the recording is not knowledge to extract"
    assert vector.added == [["a1", "a2"]]


def test_a_filtered_source_reaches_ready_and_stops_re_syncing():
    """The trap: measured against the whole pool it would never be up to date."""
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    library, pool = _library(graph)
    _ingest(library, ("a1", "report.pdf"), ("a2", "clip.mp4"))

    library.sync_asset_pool("pool")
    status = pool.source_statuses["s1"]
    assert (status.status, status.indexed_revision) == ("ready", pool.revision)

    library.sync_asset_pool("pool")
    assert graph.added == [["a1"]], "not indexed a second time"


def test_a_source_that_accepts_nothing_in_the_pool_is_ready_not_pending():
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    library, pool = _library(graph)
    _ingest(library, ("a2", "clip.mp4"))

    library.sync_asset_pool("pool")

    status = pool.source_statuses["s1"]
    assert (status.status, status.indexed_revision) == ("ready", pool.revision)
    assert graph.added == [], "add is not called with an empty batch"


def test_the_backend_is_only_asked_about_the_assets_it_could_hold():
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    library, _ = _library(graph)
    _ingest(library, ("a1", "report.pdf"), ("a2", "clip.mp4"))

    library.sync_asset_pool("pool")

    assert graph.queried == [["a1"]]


def test_attaching_a_source_asks_only_about_its_own_subset():
    library = FileAssetLibrary(name="library", databasehub=SimpleNamespace())
    pool = library.create_asset_pool(asset_pool_id="pool", name="pool")
    library._asset_pools["pool"] = pool
    _ingest(library, ("a1", "report.pdf"), ("a2", "clip.mp4"))

    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    pool.set_projections([graph], library._already_indexed(pool, [graph]))

    assert graph.queried == [["a1"]]


# --- direct dispatch ----------------------------------------------------------


def test_a_mixed_batch_is_split_between_the_projections_that_want_it():
    """It used to be rejected outright, so a mixed pool could not be written to."""
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    vector = FakeProjection(source_id="s2")
    library, _ = _library(graph, vector)
    assets = [_asset("a1", "report.pdf"), _asset("a2", "clip.mp4")]

    library.add_assets(assets, ["pool"])

    assert graph.added == [["a1"]]
    assert vector.added == [["a1", "a2"]]


def test_a_batch_no_projection_wants_is_still_an_error():
    graph = FakeProjection(source_id="s1", asset_types=["pdf"])
    library, _ = _library(graph)

    try:
        library.add_assets([_asset("a2", "clip.mp4")], ["pool"])
    except ValueError as error:
        assert "accepts" in str(error)
    else:
        raise AssertionError("expected a ValueError")
