# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Deleting an asset takes what it wrote out of the pool's graph source too."""

import json

import pytest
from llama_index.core.graph_stores.types import EntityNode
from llama_index.core.schema import TextNode

from assetlib import Source
from core.file_asset_library import asset_id_for, file_origin
from core.indexer import GraphIndexer, VectorIndexer
from databasehub.adapters.graph import GraphAdapter
from databasehub.models import GraphCollection

from .test_asset_identity import FakeProjection, _ingest, _library_with_pool


def _concept(cid, chunk_ids):
    content = {"title": cid, "source_chunk_ids": json.dumps(chunk_ids)}
    return EntityNode(name=cid, label="Act", properties={"_node_type": "OKFConcept", "_node_content": json.dumps(content)})


class FakeStore:
    """Enough of NebulaPropertyGraphStore for the concept backend to read."""

    def __init__(self, nodes):
        self.nodes = {node.id: node for node in nodes}

    def get(self, properties=None, ids=None):
        if ids is not None:
            return [self.nodes[i] for i in ids if i in self.nodes]
        return [n for n in self.nodes.values() if all(n.properties.get(k) == v for k, v in (properties or {}).items())]

    def get_triplets(self, ids=None):
        return []


class RecordingGraphAdapter(GraphAdapter):
    def __init__(self, store):
        self.store = store
        self.deleted = []
        self.upserted = []

    def existing_store(self, space):
        return self.store

    def delete_vertices(self, collection, vertex_ids):
        self.deleted.extend(vertex_ids)
        for vid in vertex_ids:
            self.store.nodes.pop(vid, None)
        return len(vertex_ids)

    def upsert_vertices(self, collection, vertices):
        self.upserted.extend(vertices)
        for v in vertices:
            self.store.nodes[v["id"]] = EntityNode(name=v["id"], label=v["label"], properties=v["properties"])

    def upsert_edges(self, collection, edges):
        pass

    def query(self, collection, statement, parameters):
        return []

    def clear(self, collection):
        pass

    def close(self):
        pass


class ChunkedProjection(FakeProjection, VectorIndexer):
    """A vector source whose chunks carry their asset id, as Milvus rows do."""

    def __init__(self):
        super().__init__()
        self.concepts_removed = []

    def load(self):
        return [TextNode(id_=f"{asset_id}-c{i}", text="x", metadata={"asset_id": asset_id}) for asset_id in sorted(self.held) for i in range(2)]

    def remove_concepts(self, concept_ids):
        self.concepts_removed.extend(concept_ids)
        return len(concept_ids)


def _graph_pool(store_nodes=(), configuration=None):
    library, pool, _ = _library_with_pool()
    vector = ChunkedProjection()
    adapter = RecordingGraphAdapter(FakeStore(list(store_nodes)))
    graph = GraphIndexer("p-g", "pool", Source(source_id="g1", source_type="graph", location=GraphCollection("space")), adapter, configuration)
    library.add_source(graph.source)
    pool.set_projections([vector, graph])
    return library, pool, vector, graph, adapter


def test_a_document_in_a_graph_pool_can_be_deleted():
    library, pool, vector, graph, adapter = _graph_pool()
    asset = _ingest(library, "/w/a.pdf", "page one")
    vector.held.add(asset.asset_id)

    result = library.delete_assets([asset.asset_id])

    assert result["removed"] == [asset.asset_id]
    assert adapter.deleted == []                    # documents write nothing to a graph
    assert vector.removed == [[asset.asset_id]]     # its chunks went
    assert asset.asset_id not in library.assets


def test_concepts_stop_citing_a_deleted_documents_chunks():
    library, pool, vector, graph, adapter = _graph_pool()
    asset = _ingest(library, "/w/a.pdf", "page one")
    other = _ingest(library, "/w/b.pdf", "page two")
    vector.held.update({asset.asset_id, other.asset_id})
    adapter.store.nodes["act/x"] = _concept("act/x", [f"{asset.asset_id}-c0", f"{other.asset_id}-c1"])
    adapter.store.nodes["act/y"] = _concept("act/y", [f"{other.asset_id}-c0"])

    library.delete_assets([asset.asset_id])

    rewritten = {v["id"]: json.loads(v["properties"]["_node_content"]) for v in adapter.upserted}
    assert list(rewritten) == ["act/x"]             # only the concept that cited it
    assert json.loads(rewritten["act/x"]["source_chunk_ids"]) == [f"{other.asset_id}-c1"]
    assert rewritten["act/x"]["n_sources"] == 1


def _bundle(root, *titles):
    (root / "act").mkdir(parents=True)
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    for title in titles:
        (root / "act" / f"{title}.md").write_text(f"---\ntype: Act\ntitle: {title}\n---\nbody\n", encoding="utf-8")


def test_an_okf_bundle_takes_its_concepts_but_not_ones_another_bundle_shares(tmp_path):
    pytest.importorskip("yaml")
    library, pool, vector, graph, adapter = _graph_pool()
    _bundle(tmp_path / "one", "a", "shared")
    _bundle(tmp_path / "two", "shared", "b")
    first = library.create_okf_asset(file_origin(str(tmp_path / "one")))
    second = library.create_okf_asset(file_origin(str(tmp_path / "two")))
    library.register_assets([first, second])
    library.add_assets_to_pool("pool", [first.asset_id, second.asset_id])

    library.delete_assets([first.asset_id])

    assert adapter.deleted == ["act/a"]
    assert vector.concepts_removed == ["act/a"]
    assert second.asset_id in library.assets


def test_an_okf_bundle_whose_files_are_gone_is_refused_before_anything_changes(tmp_path):
    library, pool, vector, graph, adapter = _graph_pool()
    missing = library.create_okf_asset(file_origin(str(tmp_path / "gone")))
    library.register_assets([missing])
    library.add_assets_to_pool("pool", [missing.asset_id])

    with pytest.raises(ValueError, match="bundle cannot be read"):
        library.delete_assets([missing.asset_id])

    assert missing.asset_id in library.assets
    assert adapter.deleted == []


def test_a_document_in_a_document_format_graph_source_is_not_parsed_as_a_bundle():
    library, pool, vector, graph, adapter = _graph_pool(configuration={
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://okf-extractor:8080"},
    })
    asset = _ingest(library, "/w/a.pdf", "page one")
    vector.held.add(asset.asset_id)

    library.delete_assets([asset.asset_id])

    assert adapter.deleted == [] and asset.asset_id not in library.assets
