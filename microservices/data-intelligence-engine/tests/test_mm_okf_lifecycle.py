# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Real sync, binding transitions and OKF hooks over in-memory projections.

Only backend/model operations are faked. OKF parsing, provenance resolution,
the serving-text selector and the vector-before-graph ordering stay real.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from assetlib.contracts import Source
from assetlib.sources.binding import DEGRADE, PREPARING, SERVING
from core.file_asset_library import FileAsset, FileAssetLibrary, file_origin
from core.indexer import GraphIndexer, MultimodalIndexer, VectorIndexer
from core.knowledge import Knowledge
from databasehub.models import GraphCollection, VectorCollection


class _Vector(VectorIndexer):
    def __init__(self, library, source):
        # Skip model/adapter construction, retaining real accepts/type identity.
        self.library = library
        self.source = source
        self.configuration = dict(source.configuration)
        self.projection_id = f"p-{source.source_id}"
        self.name = "pool"
        self.version = 0
        self.store = library.stores.setdefault(
            source.source_id, {"chunks": {}, "concepts": {}},
        )
        self.add_calls = 0
        self.fail_on_add = None
        self.after_add = lambda: None

    def add(self, assets):
        self.add_calls += 1
        self.library.events.append(("add", self.source.source_id))
        # Even a failed batch may have left a partial asset in the backend.
        for asset in assets:
            self.store["chunks"][asset.asset_id] = SimpleNamespace(
                node_id=f"{self.source.source_id}:{asset.asset_id}",
                metadata={"asset_id": asset.asset_id,
                          "file_path": asset.origin.removeprefix("file://")},
            )
        self.version += 1
        if self.add_calls == self.fail_on_add:
            raise RuntimeError("vector batch failed")
        self.after_add()
        return {"chunks_added": len(assets)}

    def indexed_asset_ids(self, asset_ids):
        return set(self.store["chunks"]) & set(asset_ids)

    def delete_by_metadata(self, field, values):
        assert field == "asset_id"
        self.library.events.append(("delete", self.source.source_id))
        for asset_id in values:
            self.store["chunks"].pop(asset_id, None)
        return len(values)

    def load(self):
        self.library.events.append(("load", self.source.source_id))
        return list(self.store["chunks"].values())

    def count(self):
        return len(self.store["chunks"])

    def build_concept_index(self, concepts):
        self.library.events.append(("concept-build", self.source.source_id))
        if self.library.fail_concepts:
            raise RuntimeError("concept vectors failed")
        self.store["concepts"].update((node.cid, deepcopy(node)) for node in concepts)

    def load_concept_index(self, concept_ids):
        self.library.events.append(("concept-load", self.source.source_id))
        assert concept_ids == set(self.store["concepts"])


class _MediaVector(_Vector, MultimodalIndexer):
    pass


class _Graph(GraphIndexer):
    def __init__(self, library, source):
        self.library = library
        self.source = source
        self.configuration = dict(source.configuration)
        self.projection_id = f"p-{source.source_id}"
        self.name = "pool"
        self._knowledge = Knowledge(self.configuration)
        self._okf_context = None
        self.store = library.stores.setdefault(source.source_id, {})

    def add(self, assets):
        self.library.events.append(("add", self.source.source_id))
        assert any(asset.asset_kind == "okf" for asset in assets)
        assert self.okf_context
        self.store.update(deepcopy(self.okf_context))
        return {"concepts_added": sum(map(len, self.okf_context.values()))}


class _Library(FileAssetLibrary):
    BACKFILL_BATCH_SIZE = 1

    def __init__(self):
        super().__init__("okf-lifecycle", databasehub=SimpleNamespace())
        self.stores = {}
        self.events = []
        self.graph_phases = []
        self.fail_finish = None
        self.fail_concepts = False

    def build_projection(self, projection_id, name, source):
        cls = _Graph if source.source_type == "graph" else (
            _MediaVector if source.profile.get("encoder_kind") == "multimodal" else _Vector
        )
        return cls(self, source)

    def _observe_graph(self, phase, pool, projection):
        if projection.kind == "graph":
            vector = self._vector_projection(pool)
            self.graph_phases.append((
                phase, vector.source.source_id if vector else None,
                {sid: (status.status, status.serving_state, status.replaces)
                 for sid, status in pool.source_statuses.items()},
                set(pool.frozen_sources),
            ))

    def _prepare_projection_add(self, pool, projection, assets):
        self.events.append(("prepare", projection.source.source_id))
        self._observe_graph("prepare", pool, projection)
        super()._prepare_projection_add(pool, projection, assets)

    def _finish_projection_add(self, pool, projection, assets):
        self.events.append(("finish", projection.source.source_id))
        self._observe_graph("finish", pool, projection)
        super()._finish_projection_add(pool, projection, assets)
        if projection.source.source_id == self.fail_finish:
            raise RuntimeError("vector finish failed")


def _source(library, source_id, *, kind="vector", media=False, enabled=True):
    return library.add_source(Source(
        source_id, kind,
        GraphCollection(source_id) if kind == "graph" else VectorCollection(source_id, 4),
        name=source_id, enabled=enabled,
        profile={"encoder_kind": "multimodal" if media else "text"},
    ))


def _corpus(tmp_path):
    documents = []
    for name in ("one", "two"):
        path = tmp_path / f"{name}.txt"
        path.write_text(f"Report {name}", encoding="utf-8")
        documents.append(FileAsset(name, origin=file_origin(str(path))))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "concept.md").write_text(
        "---\ntype: Decision\ntitle: Edge AI\n"
        "source_files:\n  - one.txt\n  - two.txt\n---\nAn indexed decision.\n",
        encoding="utf-8",
    )
    return [*documents, FileAsset("okf", origin=file_origin(str(bundle)), asset_kind="okf")]


@pytest.fixture
def library(tmp_path):
    library = _Library()
    pool = library.create_asset_pool("pool", "pool")
    assets = _corpus(tmp_path)
    library.register_assets(assets)
    library.add_assets_to_pool(pool.asset_pool_id, [asset.asset_id for asset in assets])
    for source_id in ("text", "later"):
        _source(library, source_id)
    _source(library, "media", media=True)
    _source(library, "graph", kind="graph")
    return library


def _attach(library, *source_ids):
    library.set_asset_pool_sources("pool", [{"source_id": sid} for sid in source_ids])
    pool = library.asset_pools["pool"]
    return {p.source.source_id: p for p in pool.projections}


def _assert_ready(pool, *source_ids):
    for source_id in source_ids:
        status = pool.source_statuses[source_id]
        assert (status.status, status.serving_state) == ("ready", SERVING)
        assert status.indexed_revision == pool.revision
        assert status.error is None


def test_first_backfill_serves_text_before_both_okf_hooks(library):
    projections = _attach(library, "graph", "media", "text", "later")
    pool = library.asset_pools["pool"]
    assert all(s.serving_state == PREPARING for s in pool.source_statuses.values())
    assert library._vector_projection(pool) is None

    library.sync_asset_pool("pool")

    _assert_ready(pool, "media", "text", "later", "graph")
    assert [phase[:2] for phase in library.graph_phases] == [
        ("prepare", "text"), ("finish", "text"),
    ]
    for _, _, statuses, _ in library.graph_phases:
        assert statuses["text"] == ("ready", SERVING, None)
        assert statuses["graph"] == ("indexing", PREPARING, None)
    concepts = projections["graph"].store["okf"]
    assert len(concepts) == 1
    assert concepts[0].source_chunk_ids == ["text:one", "text:two"]
    assert projections["text"].store["concepts"] == {concepts[0].cid: concepts[0]}
    assert not projections["media"].store["concepts"]
    assert not projections["later"].store["concepts"]
    assert projections["graph"].okf_context is None
    assert [event for event in library.events if event[1] == "text"] == [
        ("prepare", "text"), ("delete", "text"), ("add", "text"),
        ("delete", "text"), ("add", "text"), ("finish", "text"),
        ("load", "text"), ("concept-build", "text"), ("concept-load", "text"),
    ]
    events = list(library.events)
    library.sync_asset_pool("pool")
    assert library.events == events, "a ready pool needs no second graph pass"


@pytest.mark.parametrize("failure", ["first-batch", "second-batch", "finish"])
def test_failed_vector_never_serves_partial_chunks_and_retry_recovers(library, failure):
    projections = _attach(library, "graph", "media", "text")
    text = projections["text"]
    if failure == "finish":
        library.fail_finish = "text"
    else:
        text.fail_on_add = 1 if failure == "first-batch" else 2

    library.sync_asset_pool("pool")

    pool = library.asset_pools["pool"]
    status = pool.source_statuses["text"]
    assert (status.status, status.serving_state) == ("failed", PREPARING)
    assert not any(h["serving_state"] == SERVING for h in status.serving_history)
    assert library._vector_projection(pool) is None
    assert pool.source_statuses["graph"].status == "failed"
    assert "requires a vector source" in pool.source_statuses["graph"].error
    assert not projections["graph"].store
    assert not text.store["concepts"]
    if failure == "second-batch":
        assert status.indexed_asset_ids == ["one"]
        assert status.stale_asset_ids == ["two"]
        assert set(text.store["chunks"]) == {"one", "two"}
    text.fail_on_add = None
    library.fail_finish = None

    library.sync_asset_pool("pool")

    _assert_ready(pool, "text", "graph")
    assert status.stale_asset_ids == []
    assert set(text.store["chunks"]) == {"one", "two"}
    assert projections["graph"].store["okf"][0].source_chunk_ids == ["text:one", "text:two"]


def test_replacement_keeps_old_okf_dependency_until_final_settlement(library):
    _attach(library, "text")
    library.sync_asset_pool("pool")
    library.set_asset_pool_sources("pool", [
        {"source_id": "graph"}, {"source_id": "later", "replaces": "text"},
        {"source_id": "text"}, {"source_id": "media"},
    ])
    library.sync_asset_pool("pool")

    pool = library.asset_pools["pool"]
    for _, selected, statuses, frozen in library.graph_phases:
        assert selected == "text"
        assert statuses["later"] == ("ready", PREPARING, "text")
        assert statuses["text"] == ("ready", SERVING, None)
        assert "text" not in frozen
    assert len(library.graph_phases) == 2
    _assert_ready(pool, "later", "graph")
    assert pool.source_statuses["later"].replaces is None
    assert pool.source_statuses["text"].serving_state == DEGRADE
    assert "text" in pool.frozen_sources
    assert all(p.source.source_id != "text" for p in pool.projections)
    assert library.stores["graph"]["okf"][0].source_chunk_ids == ["text:one", "text:two"]
    assert not library.stores["later"]["concepts"], "replacement provenance migration is deferred"


@pytest.mark.parametrize("state", [PREPARING, DEGRADE, "disabled"])
def test_selector_still_excludes_nonserving_text_and_serving_multimodal(library, state):
    projections = _attach(library, "media", "text")
    pool = library.asset_pools["pool"]
    pool.source_statuses["media"].serving_state = SERVING
    pool.source_statuses["text"].serving_state = PREPARING if state == "disabled" else state
    if state == "disabled":
        library.update_source("text", enabled=False)
    pool.refresh_serving()

    assert isinstance(projections["media"], MultimodalIndexer)
    assert projections["media"] in pool.serving
    assert library._vector_projection(pool) is None


@pytest.mark.parametrize("state", [DEGRADE, "disabled"])
def test_frozen_text_keeps_no_writes_or_hooks(library, state):
    _attach(library, "graph", "text")
    pool = library.asset_pools["pool"]
    if state == "disabled":
        library.update_source("text", enabled=False)
    else:
        pool.source_statuses["text"].serving_state = DEGRADE
        pool.freeze("text", library.sources["text"])
    library.events.clear()

    library.sync_asset_pool("pool")

    assert all(sid != "text" for _, sid in library.events)
    assert library._vector_projection(pool) is None
    assert pool.source_statuses["graph"].status == "failed"
    assert not library.stores["text"]["chunks"]


def test_older_revision_does_not_publish_a_preparing_text_source(library):
    projections = _attach(library, "graph", "text")
    changed = False

    def concurrent_change():
        nonlocal changed
        if not changed:
            changed = True
            library.note_assets_changed(["one"])

    projections["text"].after_add = concurrent_change
    library.sync_asset_pool("pool")

    pool = library.asset_pools["pool"]
    status = pool.source_statuses["text"]
    assert status.status == "pending"
    assert status.indexed_revision < pool.revision
    assert status.pending_revision == pool.revision
    assert status.serving_state == PREPARING
    assert status.stale_asset_ids == ["one"]
    assert library._vector_projection(pool) is None
    assert pool.source_statuses["graph"].status == "failed"

    library.sync_asset_pool("pool")

    _assert_ready(pool, "text", "graph")


def test_concept_vector_failure_marks_graph_failed_without_demoting_ready_text(library):
    projections = _attach(library, "graph", "text")
    library.fail_concepts = True

    library.sync_asset_pool("pool")

    pool = library.asset_pools["pool"]
    _assert_ready(pool, "text")
    graph = pool.source_statuses["graph"]
    assert (graph.status, graph.serving_state) == ("failed", PREPARING)
    assert graph.error == "concept vectors failed"
    assert projections["graph"].store["okf"]
    assert not projections["text"].store["concepts"]

    library.fail_concepts = False
    library.sync_asset_pool("pool")

    _assert_ready(pool, "text", "graph")
    assert projections["graph"].okf_context is None