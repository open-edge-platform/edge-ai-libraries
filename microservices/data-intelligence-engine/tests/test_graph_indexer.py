# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""GraphIndexer takes OKF bundles only and writes their concepts."""

from types import SimpleNamespace

import pytest

from assetlib.contracts import Source
from assetlib.models import GraphIngestRequest
from core.content import ContentStream
from core.indexer import GraphIndexer
from core.knowledge.okf import OKFNode


class RecordingGraphAdapter:
    def __init__(self):
        self.vertices = []
        self.edges = []
        self.calls = []

    def upsert_vertices(self, collection, vertices):
        self.vertices.extend(vertices)
        self.calls.append("vertices")

    def upsert_edges(self, collection, edges):
        self.edges.extend(edges)
        self.calls.append("edges")


def _indexer(configuration=None):
    adapter = RecordingGraphAdapter()
    source = Source(source_id="g1", source_type="graph", location=None)
    return GraphIndexer("p1", "pool", source, adapter, configuration or {}), adapter


def _okf_asset():
    return SimpleNamespace(
        asset_id="okf-1",
        asset_kind="okf",
        origin="file:///uploads/bundle",
        content=ContentStream(asset_id="okf-1", blocks=[]),
    )


def test_an_okf_bundle_writes_its_concepts():
    indexer, adapter = _indexer()
    concept = OKFNode(ctype="concept", title="Edge AI", okf_file_path="concepts/edge-ai.md")
    indexer.set_okf_context({"okf-1": [concept]})

    result = indexer.add([_okf_asset()])

    assert result["vertices_added"] == 1
    assert [vertex["id"] for vertex in adapter.vertices] == [concept.cid]


def test_documents_are_not_graph_assets():
    indexer, adapter = _indexer()
    document = SimpleNamespace(
        asset_id="doc-1",
        asset_kind="document",
        origin="file:///uploads/a.txt",
        content=ContentStream(asset_id="doc-1", blocks=[]),
    )

    assert indexer.accepts(_okf_asset())
    assert not indexer.accepts(document)
    with pytest.raises(ValueError, match="cannot accept"):
        indexer.add([document])
    assert adapter.vertices == []


def test_the_indexer_materializes_vertices_before_edges_and_bumps_its_version():
    indexer, adapter = _indexer()
    act = OKFNode(ctype="Act", title="ACT-01", links=[("defendant/x", "committed_by")])
    person = OKFNode(ctype="Defendant", title="x")
    indexer.set_okf_context({"okf-1": [act, person]})

    result = indexer.add([_okf_asset()])

    assert adapter.calls == ["vertices", "edges"]
    assert result == {"vertices_added": 2, "edges_added": 1}
    assert indexer.version == 1


def test_materializing_nothing_writes_nothing():
    indexer, adapter = _indexer()

    assert indexer.materialize(GraphIngestRequest()) == {"vertices_added": 0, "edges_added": 0}
    assert adapter.calls == [] and indexer.version == 0


def test_documents_add_nothing_directly_their_extracted_bundle_asset_is_built():
    indexer, adapter = _indexer({
        "asset_types": ["okf", "document"],
        "external_extractor": {"url": "http://okf-extractor:8080"},
    })
    document = SimpleNamespace(
        asset_id="doc-1", asset_kind="document", origin="file:///uploads/a.txt",
        content=ContentStream(asset_id="doc-1", blocks=[]),
    )
    extracted = _okf_asset()

    assert indexer.accepts(document)
    assert indexer.add([document]) == {"vertices_added": 0, "edges_added": 0}

    # The library extracted the document into `extracted` and resolved its
    # provenance by asset id; the bundle builds like any OKF asset.
    indexer.set_okf_context({"okf-1": [
        OKFNode(ctype="Topic", title="Extracted", source_files=["a.txt"], source_chunk_ids=["c1"]),
    ]})
    assert indexer.add([extracted]) == {"vertices_added": 1, "edges_added": 0}
    assert adapter.vertices[0]["id"] == "topic/extracted"
