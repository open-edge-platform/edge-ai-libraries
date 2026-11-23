# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Serving multimodal retrieval and blob access, without models or databases."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.graph_stores.types import EntityNode
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

import config
from api import retrieval
from assetlib.contracts import Source
from assetlib.pool import AssetPool, SourceSyncStatus
from core import file_asset_library as files
from core import retrievers
from core.content import (
    IMAGE,
    ROLE_L2_CAPTION,
    ROLE_SHORT_VIDEO,
    VIDEO,
    ContentBlock,
    ContentStream,
    file_uri,
)
from core.file_asset_library import FileAsset, FileAssetLibrary, describe_vector_source, nodes_to_chunks
from core.indexer import GraphIndexer, MultimodalIndexer, VectorIndexer
from core.knowledge import Knowledge
from databasehub.models import GraphCollection, VectorCollection
from schemas import RetrieveRequest
from tests.video_package import video_package


@pytest.fixture(autouse=True)
def _unscoped_pools(monkeypatch):
    monkeypatch.setattr(retrievers, "pool_asset_scope", lambda asset_pool: None)
    monkeypatch.setattr(retrieval, "pool_asset_scope", lambda asset_pool: None)


def _hit(node_id, score, **metadata):
    return NodeWithScore(node=TextNode(id_=node_id, text=node_id, metadata=metadata), score=score)


class FakeVector(VectorIndexer):
    """Only projection identity and deterministic retrieval; no model loading."""

    def __init__(self, source_id, score=0.1, enabled=True, hits=None):
        self.source = Source(
            source_id=source_id,
            source_type="vector",
            location=VectorCollection(source_id, 4),
            enabled=enabled,
        )
        self.projection_id = f"p-{source_id}"
        self.version = 0
        self.configuration = dict(self.source.configuration)
        self.hits = [_hit(source_id, score)] if hits is None else hits
        self.queries = []

    def retrieve(self, request):
        self.queries.append(request)
        return self.hits


class FakeMultimodal(FakeVector, MultimodalIndexer):
    pass


class FixedRetriever(BaseRetriever):
    def __init__(self, hits):
        super().__init__()
        self._hits = hits

    def _retrieve(self, query_bundle):
        return self._hits


def _pool(*projections, states=None):
    states = states or {}
    return AssetPool(
        asset_pool_id="pool",
        name="pool",
        projections=tuple(projections),
        source_statuses={
            p.source.source_id: SourceSyncStatus(
                source_id=p.source.source_id,
                status="ready",
                serving_state=states.get(p.source.source_id, "SERVING"),
            )
            for p in projections
        },
    )


def _library(pool=None, assets=()):
    # No manager, content-store creation, model load, or on-disk workspace.
    library = FileAssetLibrary.__new__(FileAssetLibrary)
    library.name = "library"
    library._assets = {a.asset_id: a for a in assets}
    library._asset_pools = {} if pool is None else {pool.asset_pool_id: pool}
    library._sources = {} if pool is None else {p.source.source_id: p.source for p in pool.projections}
    library._content_store = None
    return library


def _client(monkeypatch, library):
    monkeypatch.setattr(retrieval, "registry", SimpleNamespace(require=lambda _: library))
    app = FastAPI()
    app.include_router(retrieval.router)
    return TestClient(app)


def test_g4_okf_chooses_first_serving_text_projection_in_pool_order():
    media = FakeMultimodal("xclip")
    preparing = FakeVector("preparing")
    deprecated = FakeVector("deprecated")
    disabled = FakeVector("disabled", enabled=False)
    first, second = FakeVector("z-first"), FakeVector("a-second")
    pool = _pool(
        media, preparing, deprecated, disabled, first, second,
        states={"preparing": "PREPARING", "deprecated": "DEGRADE"},
    )
    library = _library(pool)

    assert library._vector_projection(pool) is first
    pool.projections = (media, preparing, deprecated, disabled)
    pool.refresh_serving()
    assert library._vector_projection(pool) is None


def test_okf_sync_hooks_keep_text_context_and_vector_before_graph(monkeypatch):
    media, text = FakeMultimodal("xclip"), FakeVector("text")
    graph = GraphIndexer.__new__(GraphIndexer)
    graph.source = Source("graph", "graph", None)
    graph._okf_context = None
    graph._knowledge = Knowledge({})
    pool = _pool(graph, media, text)
    library = _library(pool)
    concept = SimpleNamespace(cid="act/a")
    selected = []
    monkeypatch.setattr(
        library, "_resolve_okf_concepts",
        lambda p, g, vector: selected.append(vector) or {"okf": [concept]},
    )
    built, loaded = [], []
    text.build_concept_index = lambda nodes: built.extend(nodes)
    text.load_concept_index = lambda ids: loaded.append(ids)
    asset = FileAsset("okf", asset_kind="okf")

    assert library._sync_projection_order(pool) == [media, text, graph]
    library._prepare_projection_add(pool, graph, [asset])
    library._finish_projection_add(pool, graph, [asset])

    assert selected == [text]
    assert built == [concept]
    assert loaded == [{"act/a"}]
    assert graph.okf_context is None


def test_delete_keeps_graph_plans_frozen_cleanup_and_owned_media_cleanup(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    path = uploads / "clip.mp4"
    path.write_bytes(b"clip")
    monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads))
    asset = FileAsset("asset", origin=file_uri(str(path)), cached=ContentStream("asset", blocks=[
        ContentBlock("clip", kind=VIDEO, media_key=file_uri(str(path))),
    ]))
    media, text = FakeMultimodal("media"), FakeVector("text")
    graph = GraphIndexer.__new__(GraphIndexer)
    graph.source = Source("graph", "graph", None)
    graph._knowledge = Knowledge({})
    removed = []

    class RemovalAdapter:
        def delete_vertices(self, collection, ids):
            return len(ids)

    graph._adapter = RemovalAdapter()
    graph.delete_vertices = lambda ids: removed.append(("graph", list(ids))) or len(ids)
    graph.drop_chunk_provenance = lambda ids: removed.append(("provenance", list(ids)))
    pool = _pool(media, graph, text)
    pool.asset_ids = [asset.asset_id]
    frozen = Source("frozen", "vector", None)
    pool.frozen_sources[frozen.source_id] = frozen
    library = _library(pool, [asset])
    library.file_map = {}
    library._databasehub = SimpleNamespace(get_adapter=lambda _: object())
    plans = []

    def plan(g, vector, assets, requested):
        plans.append((g, vector))
        return {"graph": g, "vector": vector, "vertices": ["asset"], "concepts": ["act/a"], "chunk_ids": ["chunk"]}

    monkeypatch.setattr(library, "_graph_removal_plan", plan)
    for projection in (media, text):
        projection.remove = lambda ids, p=projection: removed.append((p.source.source_id, list(ids))) or len(ids)
    text.remove_concepts = lambda ids: removed.append(("concepts", list(ids)))

    def delete_frozen(hub, sources, ids):
        removed.append(("frozen", list(ids)))
        return {"frozen": len(ids)}

    monkeypatch.setattr(files.frozen_bindings, "delete_assets", delete_frozen)

    result = library.delete_assets([asset.asset_id])

    assert plans == [(graph, text)], "media vectors must not supply OKF chunk provenance"
    assert removed == [
        ("media", ["asset"]), ("text", ["asset"]), ("graph", ["asset"]),
        ("concepts", ["act/a"]), ("provenance", ["chunk"]), ("frozen", ["asset"]),
    ]
    assert result["materializations_removed"] == 4
    assert result["files_removed"] == [str(path)]
    assert not path.exists()
    assert not library._assets


@pytest.mark.parametrize("algorithm", ["rrf", "vectorsimilarity", "bm25"])
def test_g8_three_sources_use_text_algorithm_and_plain_media_vectors(monkeypatch, algorithm):
    text = FakeVector("text", 0.4)
    xclip = FakeMultimodal("xclip", 0.2)
    gme = FakeMultimodal("gme", 0.6)
    preparing = FakeMultimodal("preparing", 99)
    deprecated = FakeVector("deprecated", 99)
    disabled = FakeMultimodal("disabled", 99, enabled=False)
    pool = _pool(
        xclip, text, gme, preparing, deprecated, disabled,
        states={"preparing": "PREPARING", "deprecated": "DEGRADE"},
    )
    # A failed excluded binding must not poison RRF construction either.
    pool.source_statuses["preparing"].mark_failed("not a serving source")
    bm25_sources = []

    def bm25(projection, top_k):
        bm25_sources.append(projection.source.source_id)
        return FixedRetriever(projection.hits)

    monkeypatch.setattr(retrievers, "_bm25_retriever", bm25)
    result = retrievers.build_pool_retriever(_library(pool), pool, algorithm, 3).retrieve("query")

    assert [r.node.metadata["source_id"] for r in result] == ["xclip", "text", "gme"]
    assert [r.score for r in result] == [0.2, 0.4, 0.6]
    assert len(xclip.queries) == len(gme.queries) == 1
    assert xclip.queries[0].query == "query"
    assert not preparing.queries and not deprecated.queries and not disabled.queries
    assert bm25_sources == (["text"] if algorithm == "bm25" else [])


def test_g8_all_sources_keep_their_own_top_k_without_cross_source_score_cutoff():
    first = FakeVector("first", hits=[_hit("shared", 0.8), _hit("tail", 0.1)])
    second = FakeVector("second", hits=[_hit("shared", 0.9)])
    media = FakeMultimodal("xclip", 0.7)
    pool = _pool(first, media, second)

    result = retrievers.build_pool_retriever(_library(pool), pool, "rrf", 2).retrieve("query")

    assert [(r.node.node_id, r.node.metadata["source_id"], r.score) for r in result] == [
        ("shared", "first", 0.8), ("xclip", "xclip", 0.7),
        ("shared", "second", 0.9), ("tail", "first", 0.1),
    ]
    assert all(len(p.queries) == 1 for p in (first, second, media))
    assert all(p.queries[0].top_k == 2 for p in (first, second, media))
    assert "source_id" not in first.hits[0].node.metadata, "cached nodes stay untouched"


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("query", ["query", QueryBundle("query")])
def test_pool_public_retrieval_preserves_shared_ids_callbacks_and_async_arms(asynchronous, query):
    cached = _hit("shared-block", 0.8, block_id="shared-block", source_id="stale")
    cached.node.embedding = [0.1, 0.2]
    calls = []

    class Arm(FixedRetriever):
        def _retrieve(self, query_bundle):
            assert not asynchronous, "async pool must call the arm's async API"
            calls.append(query_bundle.query_str)
            return super()._retrieve(query_bundle)

        async def _aretrieve(self, query_bundle):
            assert asynchronous
            calls.append(query_bundle.query_str)
            return self._hits

    arms = [Arm([cached, cached]), Arm([cached])]
    built = retrievers.PoolVectorRetriever(list(zip(("first", "second"), arms)), 2)
    debug = LlamaDebugHandler(print_trace_on_end=False)
    built.callback_manager = CallbackManager([debug])
    child_debug = LlamaDebugHandler(print_trace_on_end=False)
    for arm in arms:
        arm.callback_manager = CallbackManager([child_debug])

    result = asyncio.run(built.aretrieve(query)) if asynchronous else built.retrieve(query)

    assert [(r.node.node_id, r.node.metadata["source_id"], r.score) for r in result] == [
        ("shared-block", "first", 0.8), ("shared-block", "second", 0.8),
    ], "equal scores retain source order, without rewriting stable node IDs"
    assert [r.node.metadata["block_id"] for r in result] == ["shared-block"] * 2
    assert calls == ["query", "query"]
    start, end = debug.get_event_pairs(CBEventType.RETRIEVE)[0]
    assert start.payload[EventPayload.QUERY_STR] == "query"
    assert end.payload[EventPayload.NODES] == result
    assert len(debug.get_event_pairs(CBEventType.RETRIEVE)) == 1
    assert len(child_debug.get_event_pairs(CBEventType.RETRIEVE)) == 2
    result[0].node.metadata["changed"] = True
    result[0].node.embedding[0] = 9
    assert "changed" not in result[1].node.metadata
    assert cached.node.metadata == {"block_id": "shared-block", "source_id": "stale"}
    assert cached.node.embedding == result[1].node.embedding == [0.1, 0.2]


@pytest.mark.parametrize("algorithm", ["rrf", "graph"])
def test_g8_main_graph_flow_stays_text_only_and_trace_survives_wrapper(monkeypatch, algorithm):
    text, xclip, gme = FakeVector("text", 0.4), FakeMultimodal("xclip", 0.2), FakeMultimodal("gme", 0.6)
    graph = SimpleNamespace(kind="graph", source=Source("graph", "graph", None))
    ignored_graph = SimpleNamespace(kind="graph", source=Source("old-graph", "graph", None))
    pool = _pool(xclip, text, gme, ignored_graph, graph, states={"old-graph": "DEGRADE"})
    pool.source_statuses["old-graph"].mark_failed("old graph must be ignored")
    library = _library(pool)
    graph_calls, bm25_calls = [], []
    trace = {"seeds": ["act/a"], "concepts": [], "edges": []}
    search = SimpleNamespace(last_trace=trace, retrieve=lambda _: text.hits)

    def graph_arm(lib, p, g, vector, top_k):
        graph_calls.append((g, vector))
        return retrievers.GraphSearchArmRetriever(search)

    def bm25(vector, top_k):
        bm25_calls.append(vector)
        return FixedRetriever(vector.hits)

    monkeypatch.setattr(retrievers, "_build_graph_arm", graph_arm)
    monkeypatch.setattr(retrievers, "_bm25_retriever", bm25)
    built = retrievers.build_pool_retriever(library, pool, algorithm, 3)
    chunks = retrieval._retrieve_chunks(
        library,
        RetrieveRequest(query="query", libraries=["library"], retriever_type=algorithm, top_k=3, include_graph_trace=True),
        traces := [],
    )

    assert all(g is graph and vector is text for g, vector in graph_calls)
    assert bm25_calls == ([text, text] if algorithm == "rrf" else [])
    assert retrievers.graph_search_of(built) is search
    assert {c.metadata["source_id"] for c in chunks} == {"text", "xclip", "gme"}
    text_chunk = next(c for c in chunks if c.metadata["source_id"] == "text")
    assert text_chunk.score == pytest.approx(3 / (config.RRF_K + 1) if algorithm == "rrf" else 0.4)
    assert next(c.score for c in chunks if c.metadata["source_id"] == "gme") == 0.6
    assert traces == [{**trace, "library": "library", "asset_pool_id": "pool"}]


def _persisted_graph_pool(monkeypatch):
    """Different real chunkings, persisted graph provenance only for the first."""
    from core.node_parser import build_node_parser

    block = ContentBlock("paragraph", text="A person enters the room. " * 100)
    vectors = []
    for source_id, size in (("first", 128), ("second", 64)):
        vector = FakeVector(source_id)
        vector.configuration = {"chunk_size": size, "chunk_overlap": 0}
        vector._node_parser = build_node_parser(size, 0)
        nodes = vector._text_nodes(block, {"asset_id": "document"})
        vector.hits = [NodeWithScore(node=n, score=0.4) for n in nodes]
        vector.load = lambda nodes=nodes: nodes
        vectors.append(vector)
    first, second = vectors
    assert len(first.load()) < len(second.load())
    assert not {n.node_id for n in first.load()} & {n.node_id for n in second.load()}
    chunk_id = first.hits[0].node.node_id
    concept = EntityNode(name="act/a", properties={
        "_node_type": "OKFConcept",
        "_node_content": json.dumps({"source_chunk_ids": [chunk_id]}),
    })

    class Store:
        def get(self, ids=None, properties=None):
            return [concept] if ids is None or concept.id in ids else []

        def get_triplets(self, ids=None):
            return []

    opens, concept_loads = [], []
    store = Store()
    graph = SimpleNamespace(
        kind="graph", source=Source("graph", "graph", None),
        projection_id="p-graph", version=0, collection=SimpleNamespace(space="space"),
        _adapter=SimpleNamespace(existing_store=lambda space: opens.append(space) or store),
    )
    seed_index = SimpleNamespace(as_retriever=lambda: FixedRetriever([_hit("act/a", 0.9)]))

    def load_concepts(ids):
        concept_loads.append(set(ids))
        return seed_index

    def forbidden(*args, **kwargs):
        raise AssertionError("secondary text source must not load graph concepts")

    first.load_concept_index = load_concepts
    second.load_concept_index = forbidden
    monkeypatch.setattr(retrievers, "_graph_cache", {})
    return _pool(first, graph, second), first, second, concept, opens, concept_loads


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("algorithm", ["rrf", "graph"])
def test_two_text_chunkings_share_only_first_graph_binding_with_real_graph_arm(monkeypatch, algorithm, asynchronous):
    pool, first, second, concept, opens, concept_loads = _persisted_graph_pool(monkeypatch)
    bm25_calls = []
    monkeypatch.setattr(
        retrievers, "_bm25_retriever",
        lambda vector, top_k: bm25_calls.append(vector) or FixedRetriever(vector.hits),
    )
    built = retrievers.build_pool_retriever(_library(pool), pool, algorithm, 100)
    result = asyncio.run(built.aretrieve("person")) if asynchronous else built.retrieve("person")

    assert opens == ["space"]
    assert concept_loads == [{"act/a"}]
    assert bm25_calls == ([first] if algorithm == "rrf" else [])
    assert len(first.queries) == (1 if algorithm == "rrf" else 0)
    assert len(second.queries) == 1
    secondary = [r for r in result if r.node.metadata["source_id"] == "second"]
    assert {r.node.node_id for r in secondary} == {n.node_id for n in second.load()}
    assert all(r.score == 0.4 for r in secondary), "secondary scores must not be RRF-normalized"
    assert any(r.node.metadata["source_id"] == "first" for r in result)
    search = retrievers.graph_search_of(built)
    assert set(search._nodes_by_id) == {n.node_id for n in first.load()}
    assert search.last_trace["seeds"] == ["act/a"]
    assert search.last_trace["concepts"][0]["chunk_ids"] == [first.hits[0].node.node_id]


@pytest.mark.parametrize("algorithm", ["rrf", "graph"])
@pytest.mark.parametrize("problem", ["missing-chunk", "empty", "bad-provenance", "pending", "failed"])
def test_real_graph_arm_still_rejects_invalid_primary_provenance_and_sync(monkeypatch, algorithm, problem):
    pool, first, second, concept, opens, concept_loads = _persisted_graph_pool(monkeypatch)
    if problem == "missing-chunk":
        # Even a real chunk in the second text source cannot satisfy the binding.
        concept.properties["_node_content"] = json.dumps({
            "source_chunk_ids": [second.hits[0].node.node_id],
        })
        message = "missing document chunks"
    elif problem == "empty":
        concept.properties["_node_type"] = "Document"
        message = "no OKF concepts"
    elif problem == "bad-provenance":
        concept.properties["_node_content"] = "{}"
        message = "invalid source_chunk_ids"
    else:
        status = pool.source_statuses[first.source.source_id]
        status.status = problem
        status.error = "sync unfinished"
        message = "sync unfinished"

    with pytest.raises((ValueError, RuntimeError), match=message):
        retrievers.build_pool_retriever(_library(pool), pool, algorithm, 10)
    assert not concept_loads and not second.queries


@pytest.mark.parametrize("algorithm", ["rrf", "graph"])
def test_graph_construction_reads_one_serving_snapshot_even_if_pool_changes(monkeypatch, algorithm):
    pool, first, second, concept, opens, concept_loads = _persisted_graph_pool(monkeypatch)

    class ChangingPool:
        reads = 0
        source_statuses = pool.source_statuses

        @property
        def serving(self):
            self.reads += 1
            assert self.reads == 1, "one retriever must not mix serving snapshots"
            return pool.serving

    changing = ChangingPool()

    def bm25(vector, top_k):
        pool.serving = (second,)
        return FixedRetriever(vector.hits)

    monkeypatch.setattr(retrievers, "_bm25_retriever", bm25)
    built = retrievers.build_pool_retriever(_library(pool), changing, algorithm, 100)

    assert changing.reads == 1
    assert retrievers.graph_search_of(built) is not None
    assert {r.node.metadata["source_id"] for r in built.retrieve("person")} == {"first", "second"}


def test_g9_nodes_to_chunks_retains_actual_source_and_adds_pool():
    hit = _hit("chunk", 0.5, source_id="actual-source", pool_id="stale-pool")

    chunk = nodes_to_chunks([hit], library="library", pool_id="pool")[0]

    assert chunk.metadata == {"source_id": "actual-source", "pool_id": "pool", "library": "library"}
    assert hit.node.metadata["pool_id"] == "stale-pool"


def test_g9_g10_retrieve_endpoint_applies_caption_and_preserves_source_pool(monkeypatch):
    hit = _hit("clip", 0.3, asset_id="asset", block_id="clip", kind=VIDEO, source_id="wrong")
    hit.node.embedding = [0.1, 0.2]
    media = FakeMultimodal("xclip", hits=[hit])
    pool = _pool(media)
    asset = FileAsset("asset", cached=ContentStream("asset", blocks=[
        ContentBlock("clip", kind=VIDEO),
        ContentBlock("other:caption", text="Wrong clip", metadata={"role": ROLE_L2_CAPTION, "source_block_id": "other"}),
        ContentBlock("asset:caption", text="A person enters the room", metadata={"role": ROLE_L2_CAPTION, "source_block_id": "clip"}),
    ]))
    library = _library(pool, [asset])
    with _client(monkeypatch, library) as client:
        response = client.post("/v1/retrieve", json={"libraries": ["library"], "query": "person", "top_k": 3})

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["text"] == "A person enters the room"
    assert chunk["metadata"]["source_id"] == "xclip"
    assert chunk["metadata"]["pool_id"] == "pool"
    assert hit.node.text == "clip", "caption replacement must not mutate cached/indexed nodes"
    assert hit.node.embedding == [0.1, 0.2]


def test_g9_g10_endpoint_deduplicates_same_block_from_two_sources(monkeypatch):
    hit = _hit("clip", 0.3, asset_id="asset", block_id="clip", kind=VIDEO)
    first, second = FakeMultimodal("first", hits=[hit]), FakeMultimodal("second", hits=[hit])
    asset = FileAsset("asset", cached=ContentStream("asset", blocks=[
        ContentBlock("clip", kind=VIDEO),
        ContentBlock("caption", text="Shared clip caption", metadata={
            "role": ROLE_L2_CAPTION, "source_block_id": "clip",
        }),
    ]))
    with _client(monkeypatch, _library(_pool(first, second), [asset])) as client:
        response = client.post("/v1/retrieve", json={"libraries": ["library"], "query": "clip", "top_k": 2})

    assert response.status_code == 200
    chunks = response.json()["chunks"]
    assert len(chunks) == 1
    assert [c["metadata"]["source_id"] for c in chunks] == ["first"]
    assert all(c["text"] == "Shared clip caption" and c["metadata"]["pool_id"] == "pool" for c in chunks)
    assert all(c["metadata"]["block_id"] == "clip" for c in chunks)
    assert hit.node.text == "clip" and "source_id" not in hit.node.metadata


def test_empty_target_searches_document_and_media_in_one_response(monkeypatch):
    document = FakeVector("document", hits=[_hit(
        "paragraph", 0.4, asset_id="report", kind="text",
    )])
    video = FakeMultimodal("video", hits=[_hit(
        "clip", 0.9, asset_id="recording", kind=VIDEO, role=ROLE_SHORT_VIDEO,
    )])
    video.source = replace(video.source, configuration={"target_media": "video"}, profile={
        "encoder_kind": "multimodal", "supported_roles": [ROLE_SHORT_VIDEO],
    })
    library = _library(_pool(document, video))
    with _client(monkeypatch, library) as client:
        all_hits = client.post("/v1/retrieve", json={"libraries": ["library"], "query": "query"})
        scoped = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query",
            "target_media": ["document", "video"], "top_k": 3,
        })
        document_only = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "target_media": ["document"],
        })
    assert all_hits.status_code == scoped.status_code == document_only.status_code == 200
    assert [hit["id"] for hit in all_hits.json()["chunks"]] == ["paragraph", "clip"]
    assert [hit["id"] for hit in scoped.json()["chunks"]] == ["paragraph", "clip"]
    assert [hit["id"] for hit in document_only.json()["chunks"]] == ["paragraph"]
    assert document.queries[-1].filters is not None
    assert document.queries[-2].top_k == video.queries[-1].top_k == 3


@pytest.mark.parametrize("algorithm", ["vectorsimilarity", "bm25", "graph", "rrf"])
def test_media_api_uses_public_pool_factory_with_vector_only_strategy(monkeypatch, algorithm):
    video = FakeMultimodal("video", hits=[_hit("clip", 0.4, kind=VIDEO, role=ROLE_SHORT_VIDEO)])
    video.source = replace(video.source, configuration={"target_media": "video"}, profile={
        "encoder_kind": "multimodal", "supported_roles": [ROLE_SHORT_VIDEO],
    })
    image = FakeMultimodal("image", hits=[_hit("photo", 0.9, kind=IMAGE, role="image")])
    image.source = replace(image.source, configuration={"target_media": "image"}, profile={
        "encoder_kind": "multimodal", "supported_roles": ["image"],
    })
    text = FakeVector("text")
    preparing = FakeMultimodal("preparing")
    disabled = FakeMultimodal("disabled", enabled=False)
    graph = SimpleNamespace(kind="graph", source=Source(
        source_id="graph", source_type="graph", location=GraphCollection("graph"),
    ))
    pool = _pool(text, video, image, preparing, disabled, graph, states={"preparing": "PREPARING"})
    library = _library(pool)
    factory_calls = []
    debug = LlamaDebugHandler(print_trace_on_end=False)
    factory = retrieval.build_pool_retriever

    def build(owner, selected_pool, strategy, depth, **kwargs):
        factory_calls.append((owner, selected_pool, strategy, depth, kwargs))
        built = factory(owner, selected_pool, strategy, depth, **kwargs)
        built.callback_manager = CallbackManager([debug])
        return built

    def unexpected(*args, **kwargs):
        pytest.fail("media must not build graph, BM25 or RRF arms")

    monkeypatch.setattr(retrieval, "build_pool_retriever", build)
    for name in ("_build_graph_arm", "_bm25_retriever", "_fused_pool_retriever"):
        monkeypatch.setattr(retrievers, name, unexpected)
    with _client(monkeypatch, library) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "clip", "top_k": 2,
            "target_media": ["video"], "retriever_type": algorithm,
            "include_graph_trace": True,
        })

    assert response.status_code == 200
    assert len(factory_calls) == 1
    owner, selected_pool, strategy, depth, options = factory_calls[0]
    assert owner is library and selected_pool is pool
    assert strategy == "vectorsimilarity" and depth == 2
    assert options["selected_vectors"] == [video]
    assert options["vector_filters"] is None
    assert options.get("node_filter") is None
    assert len(debug.get_event_pairs(CBEventType.RETRIEVE)) == 1
    assert len(video.queries) == 1
    assert not any(p.queries for p in (text, image, preparing, disabled))
    assert [hit["id"] for hit in response.json()["chunks"]] == ["clip"]
    assert response.json()["graph_traces"] == []


@pytest.mark.parametrize("targets,expected_ids,expected_roles", [
    (["image"], ["figure", "photo"], ["doc_image", "image"]),
    (["audio"], ["speech"], ["l2_transcript"]),
    (["document", "image"], ["paragraph", "figure", "photo"], ["doc_image", "image"]),
    (["document", "audio"], ["paragraph", "speech"], ["l2_transcript"]),
])
def test_media_factory_keeps_projection_filters_separate_from_document_filters(
    monkeypatch, targets, expected_ids, expected_roles,
):
    document = FakeVector("text", hits=[_hit("paragraph", 0.8, kind="text")])
    media = FakeMultimodal("mixed", hits=[
        _hit("speech", 0.9, kind="text", role="l2_transcript"),
        _hit("figure", 0.6, kind=IMAGE, role="doc_image"),
        _hit("photo", 0.4, kind=IMAGE, role="image"),
    ])
    media.source = replace(media.source, profile={
        "encoder_kind": "multimodal", "supported_roles": ["doc_image", "image", "l2_transcript"],
    })
    factory = retrieval.build_pool_retriever
    calls = {}

    def build(owner, pool, strategy, depth, **kwargs):
        selected = kwargs["selected_vectors"]
        assert len(selected) == 1
        calls[selected[0].source.source_id] = (strategy, kwargs)
        return factory(owner, pool, strategy, depth, **kwargs)

    monkeypatch.setattr(retrieval, "build_pool_retriever", build)
    with _client(monkeypatch, _library(_pool(document, media))) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "top_k": 3,
            "target_media": targets, "retriever_type": "rrf",
        })

    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["chunks"]] == expected_ids
    strategy, options = calls["mixed"]
    assert strategy == "vectorsimilarity"
    assert options.get("node_filter") is None
    assert options["vector_filters"] is media.queries[0].filters
    role_filter, = media.queries[0].filters.filters
    assert role_filter.key == "role" and role_filter.value == expected_roles
    if "text" in calls:
        assert calls["text"][0] == "rrf"
        assert calls["text"][1]["vector_filters"] is document.queries[0].filters
        assert document.queries[0].filters.filters[0].key == "kind"
    assert len(media.queries) == 1


@pytest.mark.parametrize("top_k,excluded,expected_depth", [
    (2, ["drop"], 3),
    (100, ["drop", "absent"], 100),
])
def test_media_factory_preserves_exclusion_depth_scores_and_source_ranks(
    monkeypatch, top_k, excluded, expected_depth,
):
    hits = [
        _hit("zero", 0.0, kind="text", role="l2_transcript"),
        _hit("drop", 0.9, kind="text", role="l2_transcript"),
        _hit("negative", -0.1, kind="text", role="l2_transcript"),
    ]
    audio = FakeMultimodal("audio", hits=hits)
    audio.source = replace(audio.source, configuration={"target_media": "audio"}, profile={
        "encoder_kind": "multimodal", "supported_roles": ["l2_transcript"],
    })
    before = [hit.model_dump() for hit in hits]
    with _client(monkeypatch, _library(_pool(audio))) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "top_k": top_k,
            "target_media": ["audio"], "exclude_chunk_ids": excluded,
        })

    assert response.status_code == 200
    assert audio.queries[0].top_k == expected_depth
    chunks = response.json()["chunks"]
    assert [hit["id"] for hit in chunks] == ["zero", "negative"]
    assert [hit["score"] for hit in chunks] == [0.0, -0.1]
    assert [hit["metadata"]["source_rank"] for hit in chunks] == [2, 3]
    assert [hit["metadata"]["rank"] for hit in chunks] == [1, 2]
    assert all(hit["metadata"]["source_id"] == "audio" for hit in chunks)
    assert all(hit["metadata"]["representation"] == "transcript_dense" for hit in chunks)
    assert [hit.model_dump() for hit in hits] == before


def test_media_factory_without_a_serving_retriever_fails_explicitly(monkeypatch):
    audio = FakeMultimodal("audio")
    audio.source = replace(audio.source, configuration={"target_media": "audio"}, profile={
        "encoder_kind": "multimodal", "supported_roles": ["l2_transcript"],
    })
    monkeypatch.setattr(retrieval, "build_pool_retriever", lambda *args, **kwargs: None)
    with _client(monkeypatch, _library(_pool(audio))) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "target_media": ["audio"],
        })
    assert response.status_code == 503
    assert "audio" in response.json()["detail"]
    assert not audio.queries


def test_document_target_is_text_only_until_image_is_selected(monkeypatch):
    document = FakeVector("document", hits=[
        _hit("paragraph", 0.8, asset_id="report", kind="text"),
        _hit("figure", 0.7, asset_id="report", kind=IMAGE, role="doc_image"),
        _hit("standalone", 0.6, asset_id="photo", kind=IMAGE, role="image"),
    ])
    with _client(monkeypatch, _library(_pool(document))) as client:
        doc_only = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "target_media": ["document"],
        })
        image_only = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "target_media": ["image"],
        })
        combined = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query",
            "target_media": ["document", "image"],
        })
    assert all(response.status_code == 200 for response in (
        doc_only, image_only, combined,
    ))
    assert [hit["id"] for hit in doc_only.json()["chunks"]] == ["paragraph"]
    assert [hit["id"] for hit in image_only.json()["chunks"]] == ["figure", "standalone"]
    assert [hit["id"] for hit in combined.json()["chunks"]] == ["paragraph", "figure", "standalone"]
    assert all(request.filters is not None for request in document.queries)


def test_document_figure_hit_in_text_and_image_sources_returns_once(monkeypatch):
    figure = _hit("figure", 0.8, asset_id="report", kind=IMAGE, role="doc_image")
    document = FakeVector("document", hits=[figure])
    image = FakeMultimodal("image", hits=[figure])
    image.source = replace(image.source, configuration={"target_media": "image"}, profile={
        "encoder_kind": "multimodal", "supported_roles": ["doc_image"],
    })
    with _client(monkeypatch, _library(_pool(document, image))) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "figure",
            "target_media": ["document", "image"], "top_k": 2,
        })
        without_images = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "figure",
            "target_media": ["document"],
        })
    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["chunks"]] == ["figure"]
    assert without_images.status_code == 200
    assert without_images.json()["chunks"] == []
    assert len(document.queries) == 2 and len(image.queries) == 1
    assert document.queries[0].top_k == image.queries[0].top_k == 2


def test_mixed_document_video_reranks_through_one_postprocess(monkeypatch):
    from core.multimodal import reranking as media_reranker

    document = FakeVector("document", hits=[_hit("paragraph", 0.8, kind="text")])
    video = FakeMultimodal("video", hits=[_hit("clip", 0.5, kind=VIDEO, role=ROLE_SHORT_VIDEO)])
    video.source = replace(video.source, configuration={"target_media": "video"}, profile={
        "encoder_kind": "multimodal", "supported_roles": [ROLE_SHORT_VIDEO],
    })
    seen = {}
    def rerank(query, groups, options, top_n, *, strict):
        seen.update(query=query, targets=[group[0] for group in groups],
                    libraries=[group[2].name for group in groups], strict=strict)
        hit = groups[1][1][0].model_copy(deep=True)
        hit.score = 0.99
        return [hit], "ok"
    monkeypatch.setattr(media_reranker, "rerank_media", rerank)
    with _client(monkeypatch, _library(_pool(document, video))) as client:
        response = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "query", "top_k": 2,
            "target_media": ["document", "video"], "postprocess": {"top_n": 1},
        })
    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["retrieved_chunks"]] == ["paragraph", "clip"]
    assert [hit["id"] for hit in response.json()["chunks"]] == ["clip"]
    assert seen == {"query": "query", "targets": ["document", "video"],
                    "libraries": ["library", "library"], "strict": True}


@pytest.mark.parametrize("backend", [None, config.LOCAL_OPENVINO])
def test_g12_native_gme_bypasses_registry_even_for_a_gme_model_directory(monkeypatch, tmp_path, backend):
    from core.multimodal import registry

    (tmp_path / "gme_openvino_config.json").write_text("{}")

    def forbidden(*args, **kwargs):
        raise AssertionError("native GME must not consult the multimodal registry")

    monkeypatch.setattr(registry, "resolve", forbidden)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path.parent))
    options = {"embedding_model": tmp_path.name, "block_kinds": ["image", "text"]}
    if backend:
        options["embedding_backend"] = backend
    profile = describe_vector_source(options)

    assert profile["encoder_kind"] == "text"
    assert profile["backend"] == config.LOCAL_OPENVINO
    assert profile["runtime"] == "ov_gme" and profile["fused"] is True
    assert profile["model"] == tmp_path.name
    assert profile["params"]["block_kinds"] == ["image", "text"]
    assert "multimodal_model" not in profile


@pytest.mark.parametrize("kind", ["video", "image", "audio"])
def test_g12_media_defaults_remain_registry_owned_with_native_text_default(monkeypatch, kind):
    from core.multimodal import registry

    monkeypatch.setattr(config, "EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    calls = []
    resolved = SimpleNamespace(
        backend=config.LOCAL_OPENVINO, model_id="microsoft/xclip-fake", params={},
        model=SimpleNamespace(
            supported_roles={ROLE_SHORT_VIDEO}, supported_asset_types={kind}, runtime="ov_core",
        ),
        record=lambda: {"name": "xclip", "path": "fake"},
    )
    monkeypatch.setattr(registry, "resolve", lambda options: calls.append(options) or resolved)

    profile = describe_vector_source({"asset_types": [kind]})

    assert calls == [{"asset_types": [kind]}]
    assert profile["encoder_kind"] == "multimodal"
    assert profile["backend"] == config.LOCAL_OPENVINO
    assert files._is_multimodal({"asset_types": [kind]})


@pytest.mark.parametrize("selection", ["model", "local-model"])
@pytest.mark.parametrize("backend", [config.LOCAL_OPENVINO])
@pytest.mark.parametrize("block_kinds", [None, ["text", "image"]])
def test_g12_explicit_gme_text_model_inherits_native_default_without_registry(monkeypatch, tmp_path, selection, backend, block_kinds):
    from core.multimodal import registry

    monkeypatch.setattr(config, "EMBEDDING_BACKEND", backend)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path.parent))
    (tmp_path / "gme_openvino_config.json").write_text("{}")
    options = {} if block_kinds is None else {"block_kinds": block_kinds}
    options["embedding_model"] = (
        "gme-Qwen2-VL-2B-Instruct-OV" if selection == "model" else tmp_path.name
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("inherited native text backend must not consult registry")

    monkeypatch.setattr(registry, "resolve", forbidden)
    profile = describe_vector_source(options)

    assert profile["encoder_kind"] == "text"
    assert profile["backend"] == config.LOCAL_OPENVINO
    if selection == "local-model":
        assert profile["runtime"] == "ov_gme"
    assert not files._is_multimodal(options)
    assert "multimodal_model" not in profile
    source = Source("text", "vector", VectorCollection("text", 4), configuration=options, profile=profile)
    library, calls = _text_projection_builder(monkeypatch)
    assert type(library.build_projection("p", "pool", source)) is VectorIndexer
    assert calls[0]["backend"] == config.LOCAL_OPENVINO


def test_native_text_default_does_not_capture_explicit_media_only_model(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    package = video_package(tmp_path)
    options = {
        "asset_types": ["video"], "embedding_model": package.name,
    }

    profile = describe_vector_source(options)

    assert profile["encoder_kind"] == "multimodal"
    assert profile["backend"] == config.LOCAL_OPENVINO
    assert files._is_multimodal(options)
    with pytest.raises(ValueError, match="block_kinds"):
        describe_vector_source({**options, "block_kinds": ["image"]})


def test_native_text_default_does_not_make_model_only_video_a_valid_source(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", config.LOCAL_OPENVINO)

    with pytest.raises(ValueError, match="asset_types"):
        describe_vector_source({"embedding_model": "viclip-b-fp16"})


@pytest.mark.parametrize("kind", ["image", "audio"])
@pytest.mark.parametrize("backend", [None, config.LOCAL_OPENVINO])
def test_native_gme_media_asset_scope_is_not_the_document_pipeline(monkeypatch, kind, backend):
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    options = {"asset_types": [kind], "embedding_model": "gme-Qwen2-VL-2B-Instruct-OV"}
    if backend:
        options["embedding_backend"] = backend

    profile = describe_vector_source(options)

    assert profile["encoder_kind"] == "multimodal"
    assert profile["multimodal_model"]["name"] == "gme_qwen2vl"
    assert profile["params"]["asset_types"] == [kind]
    assert profile["params"]["block_roles"] == (["image"] if kind == "image" else ["l2_transcript"])
    if backend:
        assert profile["backend"] == config.LOCAL_OPENVINO


def _text_projection_builder(monkeypatch):
    """Exercise the real VectorIndexer constructor/parser, without a DB/model."""
    from core import embedding, indexer

    class Adapter:
        def reconcile(self, collection):
            pass

        def storage_context(self, collection):
            return None

    library = _library()
    library._databasehub = SimpleNamespace(
        get_registration=lambda _: SimpleNamespace(database_type="vector"),
        get_adapter=lambda _: Adapter(),
    )
    monkeypatch.setattr(library, "PROJECTION_TYPES", {"vector": (VectorIndexer, VectorCollection, Adapter)})
    monkeypatch.setattr(indexer, "VectorStoreIndex", lambda **kwargs: SimpleNamespace(**kwargs))
    calls = []

    def build_embedding(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(get_text_embedding=lambda _: [0.1] * 4)

    monkeypatch.setattr(embedding, "build_embedding", build_embedding)
    return library, calls


@pytest.mark.parametrize("selection", ["default", "model", "tuned-model"])
@pytest.mark.parametrize("changed_id", ["model-B", "model-A"])
def test_text_projection_uses_frozen_profile_after_engine_defaults_change(monkeypatch, selection, changed_id):
    for key, value in {
        "EMBEDDING_BACKEND": config.LOCAL_OPENVINO, "EMBEDDING_MODEL_ID": "model-A",
        "EMBEDDING_DEVICE": "CPU",
        "CHUNK_SIZE": 96, "CHUNK_OVERLAP": 12, "FIGURE_CONTEXT_CHARS": 180,
    }.items():
        monkeypatch.setattr(config, key, value)
    options = {}
    if selection != "default":
        options["embedding_model"] = "explicit-A"
    if selection == "tuned-model":
        options.update(chunk_size=64, chunk_overlap=0, figure_context_chars=80, embedding_device="NPU")
    profile = describe_vector_source(options)
    source = Source("text", "vector", VectorCollection("text", 4), configuration=options, profile=profile)
    source = Source.from_record(source.to_record())
    for key, value in {
        "EMBEDDING_BACKEND": config.REMOTE_OPENAI_COMPATIBLE, "EMBEDDING_MODEL_ID": changed_id,
        "EMBEDDING_DEVICE": "GPU",
        "CHUNK_SIZE": 256, "CHUNK_OVERLAP": 20, "FIGURE_CONTEXT_CHARS": 300,
    }.items():
        monkeypatch.setattr(config, key, value)
    library, calls = _text_projection_builder(monkeypatch)

    projection = library.build_projection("p", "pool", source)

    expected_id = options.get("embedding_model", "model-A")
    assert profile["model_id"] == expected_id
    assert "model_path" not in profile
    assert calls == [{
        "backend": config.LOCAL_OPENVINO, "model_id": expected_id,
        "device": options.get("embedding_device", "CPU"), "api_base": None,
    }]
    assert type(projection) is VectorIndexer
    assert projection._node_parser.chunk_size == options.get("chunk_size", 96)
    assert projection._node_parser.chunk_overlap == options.get("chunk_overlap", 12)
    assert projection._context_chars == options.get("figure_context_chars", 180)
    assert source.configuration == options and source.profile == profile
    assert "blob_reader" not in projection.configuration


@pytest.mark.parametrize("legacy_path", [False, True])
def test_text_projection_compatibility_with_legacy_model_only_profile(monkeypatch, legacy_path):
    monkeypatch.setattr(config, "EMBEDDING_MODEL_ID", "B")
    profile = {
        "encoder_kind": "text", "backend": "openvino", "device": "CPU",
        "model": "/models/A" if legacy_path else "A",
        "params": {"chunk_size": 96, "chunk_overlap": 0, "figure_context_chars": 180},
    }
    options = {"embedding_model": "A"} if legacy_path else {}
    source = Source("text", "vector", VectorCollection("text", 4), configuration=options, profile=profile)
    # A stored record's old backend name is upgraded when it is read back.
    source = Source.from_record(source.to_record())
    assert source.profile["backend"] == config.LOCAL_OPENVINO
    assert source.profile["runtime"] == "ov_llamaindex" and source.profile["fused"] is False
    library, calls = _text_projection_builder(monkeypatch)

    projection = library.build_projection("p", "pool", source)

    assert calls[0]["model_id"] == "A"
    assert "model_path" not in calls[0]
    assert calls[0]["backend"] == config.LOCAL_OPENVINO and calls[0]["device"] == "CPU"
    assert projection._node_parser.chunk_overlap == 0
    assert source.configuration == options


@pytest.mark.parametrize("multimodal", [False, True])
def test_projection_build_keeps_model_selection_and_two_argument_blob_reader(monkeypatch, multimodal):
    built = []

    class ConstructedProjection:
        def __init__(self, **kwargs):
            built.append(("text", kwargs))

    class ConstructedMedia:
        def __init__(self, **kwargs):
            built.append(("multimodal", kwargs))

    class Adapter:
        pass

    library = _library()
    adapter = Adapter()
    library._databasehub = SimpleNamespace(
        get_registration=lambda _: SimpleNamespace(database_type="vector"),
        get_adapter=lambda _: adapter,
    )
    monkeypatch.setattr(library, "PROJECTION_TYPES", {"vector": (ConstructedProjection, VectorCollection, Adapter)})
    monkeypatch.setattr(files, "MultimodalIndexer", ConstructedMedia)
    reads = []
    library.blob_reader = lambda: lambda key, source_id: reads.append((key, source_id)) or b"pixels"
    source = Source(
        "vector", "vector", VectorCollection("v", 4),
        configuration={"asset_types": ["video"]} if multimodal else {},
        profile={
            "encoder_kind": "multimodal" if multimodal else "text",
            **({"backend": config.LOCAL_OPENVINO, "multimodal_model": {
                "name": "viclip-b", "id": "viclip-b-fp16", "path": "viclip-b-fp16",
            }} if multimodal else {}),
        },
    )

    library.build_projection("projection", "pool", source)

    kind, kwargs = built[0]
    assert kind == ("multimodal" if multimodal else "text")
    assert kwargs["configuration"]["blob_reader"]("blobs/image", "content") == b"pixels"
    assert reads == [("blobs/image", "content")]
    assert "blob_reader" not in source.configuration


def _media_library(tmp_path):
    path = tmp_path / "registered.png"
    data = b"\x89PNG\r\n\x1a\nregistered pixels"
    path.write_bytes(data)
    key = file_uri(str(path))
    projection = FakeMultimodal("media")
    pool = _pool(projection)
    pool.asset_ids = ["asset"]
    asset = FileAsset("asset", content_source_id="content", cached=ContentStream("asset", blocks=[
        ContentBlock("image", kind=IMAGE, media_key=key),
    ]))
    library = _library(pool, [asset])
    library._sources.update({
        "content": Source("content", "object", None),
        "other-content": Source("other-content", "object", None),
        "unattached": Source("unattached", "vector", None),
    })
    return library, asset, key, data


@pytest.mark.parametrize("source_id", [None, "content", "media"])
def test_g21_blob_serves_registered_file_with_content_or_projection_source(monkeypatch, tmp_path, source_id):
    library, asset, key, data = _media_library(tmp_path)
    params = {"library": "library", "media_key": key}
    if source_id is not None:
        params["source_id"] = source_id

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params=params)

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"


@pytest.mark.parametrize("source_id", ["other-content", "unattached", "missing", "filtered"])
def test_g21_blob_denies_registered_file_outside_requested_source(monkeypatch, tmp_path, source_id):
    library, asset, key, _ = _media_library(tmp_path)
    filtered = replace(library._sources["media"], source_id="filtered", configuration={"block_kinds": ["video"]})
    library._sources["filtered"] = filtered
    library._asset_pools["pool"].source_statuses["filtered"] = SourceSyncStatus("filtered")

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key, "source_id": source_id})

    assert response.status_code == 404


@pytest.mark.parametrize("path_kind", ["sibling", "outside", "traversal", "origin-only", "text-block", "symlink-alias"])
def test_g21_blob_denies_unregistered_files_even_next_to_registered_media(monkeypatch, tmp_path, path_kind):
    library, asset, _, _ = _media_library(tmp_path)
    private = tmp_path / "private.txt"
    private.write_bytes(b"must not be exposed")
    if path_kind == "outside":
        outside = tmp_path / "outside"
        outside.mkdir()
        private = outside / "private.txt"
        private.write_bytes(b"must not be exposed")
    key = file_uri(str(private))
    if path_kind == "traversal":
        folder = tmp_path / "subdirectory"
        folder.mkdir()
        key = f"file://{folder}/../private.txt"
    elif path_kind == "origin-only":
        asset.origin = key
    elif path_kind == "text-block":
        asset.content.blocks.append(ContentBlock("text", text="not media", media_key=key))
    elif path_kind == "symlink-alias":
        alias = tmp_path / "alias.png"
        alias.symlink_to(tmp_path / "registered.png")
        key = file_uri(str(alias))

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 404


def test_g21_blob_revokes_access_when_asset_is_unregistered(monkeypatch, tmp_path):
    library, asset, key, _ = _media_library(tmp_path)
    del library._assets[asset.asset_id]

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 404


def test_g21_registered_file_missing_on_disk_returns_not_found(monkeypatch, tmp_path):
    library, asset, key, _ = _media_library(tmp_path)
    (tmp_path / "registered.png").unlink()

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 404


def test_binary_blobs_keep_content_source_and_projection_source_reads(monkeypatch, tmp_path):
    library, asset, _, _ = _media_library(tmp_path)
    key, data = "blobs/image", b"GIF89afigure bytes"
    asset.content.blocks[0].media_key = key
    reads = []
    asset.bind_blobs(lambda media_key: reads.append((media_key, "asset")) or data)
    library.content_source = lambda source_id=None: library._sources[source_id or "content"]
    library._content_store = SimpleNamespace(
        get_blob=lambda source, media_key: reads.append((media_key, source.source_id)) or data,
    )

    with _client(monkeypatch, library) as client:
        for source_id in ("content", "media"):
            response = client.get("/v1/blob", params={"library": "library", "media_key": key, "source_id": source_id})
            assert response.status_code == 200
            assert response.content == data
            assert response.headers["content-type"] == "image/gif"

    assert reads == [(key, "content"), (key, "asset")]


@pytest.mark.parametrize("key", ["assets/private.json", "/etc/passwd", "https://example.test/image.png"])
def test_blob_still_rejects_non_blob_non_file_keyspaces(monkeypatch, key):
    with _client(monkeypatch, _library()) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 400


def test_url_image_metadata_and_target_scoping(monkeypatch):
    url = "https://example.test/figure.png"
    vector = FakeVector("text", hits=[_hit("figure", 0.5, kind=IMAGE, media_key=url)])
    library = _library(_pool(vector))

    with _client(monkeypatch, library) as client:
        kept = client.post("/v1/retrieve", json={"libraries": ["library"], "query": "figure"})
        dropped = client.post("/v1/retrieve", json={
            "libraries": ["library"], "query": "figure", "target_media": ["document"],
        })

    assert kept.status_code == dropped.status_code == 200
    assert kept.json()["chunks"][0]["metadata"]["media_key"] == url
    assert dropped.json()["chunks"] == []
