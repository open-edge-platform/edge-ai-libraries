# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Graph retrieval reports what it walked, for the console to highlight."""

from types import SimpleNamespace

from llama_index.core.schema import TextNode

from api.retrieval import _graph_trace
from core.graph_search import GraphSearchRetriever, InMemoryConceptGraphBackend
from core.retrievers import GraphSearchArmRetriever, RRFRetriever, _RRFArm, graph_search_of


def _search():
    # a -- b -- c, and d unconnected. Each concept backs one chunk.
    backend = InMemoryConceptGraphBackend(
        {"a": [("b", "rel")], "b": [("a", "rel"), ("c", "next")], "c": [("b", "next")], "d": []},
        {"a": ["ch-a"], "b": ["ch-b"], "c": ["ch-c"], "d": ["ch-d"]},
    )
    chunks = [TextNode(id_=f"ch-{x}", text=x) for x in "abcd"]
    indexer = SimpleNamespace(as_retriever=lambda: SimpleNamespace())
    search = GraphSearchRetriever(chunks, indexer, backend, hops=2, inverse_freq=False, hub_gate=False)
    search.seeder = SimpleNamespace(seed=lambda *args, **kwargs: ["a"])
    return search


def test_the_walk_records_seeds_hops_and_crossed_edges():
    search = _search()
    results = search.custom_retrieve("anything")

    trace = search.last_trace
    assert trace["seeds"] == ["a"]
    assert [(c["id"], c["hop"]) for c in trace["concepts"]] == [("a", 0), ("b", 1), ("c", 2)]
    assert trace["edges"] == [
        {"source": "a", "target": "b", "relation": "rel"},
        {"source": "b", "target": "c", "relation": "next"},
    ]
    assert {r.node.node_id for r in results} == {"ch-a", "ch-b", "ch-c"}


def test_a_reported_concept_keeps_only_chunks_that_reached_the_result():
    search = _search()
    search.custom_retrieve("anything")
    trace = {**search.last_trace, "library": "lib", "asset_pool_id": "pool"}

    reported = _graph_trace(trace, {"ch-a", "ch-c"})

    assert {c.id: c.hit_chunk_ids for c in reported.concepts} == {"a": ["ch-a"], "b": [], "c": ["ch-c"]}


def test_the_graph_search_is_found_inside_a_graph_arm_and_an_rrf_fusion():
    search = _search()
    arm = GraphSearchArmRetriever(search)
    fused = RRFRetriever.__new__(RRFRetriever)
    fused._retrievers = [_RRFArm("vectorsimilarity", object()), _RRFArm("graph", arm)]

    assert graph_search_of(arm) is search
    assert graph_search_of(fused) is search
    assert graph_search_of(object()) is None


def test_seeds_from_another_pools_concepts_are_ignored():
    """One vector source in two pools holds both pools' concept vectors; a
    seed outside this pool's graph must not start (or break) the walk."""
    search = _search()
    search.seeder = SimpleNamespace(seed=lambda *args, **kwargs: ["other-pool/x", "c"])

    results = search.custom_retrieve("anything")

    assert search.last_trace["seeds"] == ["c"]
    assert {r.node.node_id for r in results} == {"ch-a", "ch-b", "ch-c"}

    search.seeder = SimpleNamespace(seed=lambda *args, **kwargs: ["other-pool/x"])
    assert search.custom_retrieve("anything") == [] and search.last_trace["seeds"] == []


def test_a_pools_share_of_a_graph_keeps_only_its_concepts_and_their_edges():
    from core.graph_search import InMemoryConceptGraphBackend

    backend = InMemoryConceptGraphBackend(
        {"a": [("b", "rel"), ("x", "rel")], "b": [("a", "rel")], "x": [("a", "rel")]},
        {"a": ["ch-a"], "b": ["ch-b"], "x": ["ch-x"]},
    )
    mine = backend.restricted_to({"a", "b"})

    assert mine.concept_ids() == {"a", "b"}
    assert mine.neighbors(["a"]) == {"a": [("b", "rel")]}
    assert mine.source_chunk_ids(["x"]) == {"x": []}
