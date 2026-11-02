# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Real service -> engine client -> graph ingestion without a live model/database."""
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from llama_index.core.schema import TextNode

import config
from core.indexer import VectorIndexer
from core.knowledge import extractor as client_module
from core.knowledge.extraction_jobs import ExtractionJobs
from core.knowledge.okf import OKFNode, resolve_task_source_chunk_ids
from okf_extractor import service
from okf_extractor.config import Config

from .test_asset_identity import FakeProjection, _ingest, _library_with_pool
from .test_asset_graph_deletion import _graph_pool
from .test_graph_indexer import _indexer
from .test_okf_extractor_service import TaskModel


class TaskVector(FakeProjection, VectorIndexer):
    """The fake's behavior, typed as the text vector source OKF hooks look for."""
    def __init__(self):
        super().__init__()
        self.concept_batches = []

    def accepts(self, asset):
        return getattr(asset, "asset_kind", "document") != "okf"

    def load(self):
        return [TextNode(id_=f"chunk-{asset_id}", text="chunk", metadata={"asset_id": asset_id})
                for asset_id in sorted(self.held)]

    def build_concept_index(self, concepts):
        self.concept_batches.append(concepts)

    def load_concept_index(self, ids):
        assert ids == {node.cid for node in self.concept_batches[-1]}


@pytest.fixture(autouse=True)
def inline_extraction_jobs(monkeypatch):
    """Run extraction jobs on the syncing thread, so a sync's `auto` extraction
    has finished when the call returns."""
    monkeypatch.setattr(ExtractionJobs, "inline", True)


@pytest.fixture
def exchange(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    shared_dir = tmp_path / "workspace/uploads"
    monkeypatch.setattr(config, "UPLOAD_DIR", str(shared_dir))
    TaskModel.instances = []
    monkeypatch.setattr(service, "LLMClient", TaskModel)
    raw = deepcopy(Config.load().raw)
    raw["merge"]["llm_canonicalize"] = False
    original = httpx.Client
    with TestClient(service.create_app(Config(raw), api_key="", upload_dir=shared_dir)) as api:
        def handle(request):
            response = api.post(request.url.path, json=json.loads(request.content))
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)

        monkeypatch.setattr(client_module.httpx, "Client", lambda **kwargs: original(
            transport=httpx.MockTransport(handle), **kwargs,
        ))
        yield TaskModel


def _generated(library, pool):
    """The extracted bundle asset in the pool, and its folder."""
    assets = [library.assets[i] for i in pool.asset_ids if library.assets[i].asset_kind == "okf"
              and (Path(library.assets[i].origin.removeprefix("file://")) / "task.json").is_file()]
    assert len(assets) == 1, [a.origin for a in assets]
    return assets[0], Path(assets[0].origin.removeprefix("file://"))


def _pool():
    library, pool, _ = _library_with_pool()
    vector = TaskVector()
    graph, adapter = _indexer({
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://extractor"},
    })
    library.add_source(graph.source)
    pool.set_projections([vector, graph])
    return library, pool, vector, graph, adapter


def test_document_sync_builds_generated_concepts_and_replans_the_whole_corpus(exchange, tmp_path):
    library, pool, vector, graph, adapter = _pool()
    first = _ingest(library, "/different-host/reports/a.pdf", "First document.")
    second = _ingest(library, "/different-host/profiles/a.pdf", "Second document.")

    library.sync_asset_pool("pool")

    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready", status.error
    assert len(exchange.instances) == 1
    assert adapter.vertices[0]["id"] == "topic/corpus"
    content = json.loads(adapter.vertices[0]["properties"]["_node_content"])
    assert set(json.loads(content["source_chunk_ids"])) == {f"chunk-{first.asset_id}", f"chunk-{second.asset_id}"}
    assert [node.title for node in vector.concept_batches[0]] == ["Corpus"]
    assert graph.okf_context is None  # ingest-only objects aren't retrieval state
    # The extracted bundle is an OKF asset of the pool, in the library's upload area.
    generated, folder = _generated(library, pool)
    assert folder.parent.name == "okf-extracted" and (folder / "index.md").is_file()
    assert generated.asset_id in status.indexed_asset_ids
    assert len(list((tmp_path / "workspace").rglob("instructions.yaml"))) == 1

    third = _ingest(library, "/third-host/b.txt", "New source.")
    library.sync_asset_pool("pool")

    assert status.status == "ready", status.error
    reviews = [body for kind, body in exchange.instances[-1].events if kind == "review"]
    assert len(reviews) == 3  # not just the newly added document
    assert set(vector.concept_batches[-1][0].source_chunk_ids) == {
        f"chunk-{asset.asset_id}" for asset in (first, second, third)
    }
    # Re-extraction updates the same asset in place rather than adding another.
    assert _generated(library, pool)[0].asset_id == generated.asset_id
    assert len(list((tmp_path / "workspace").rglob("instructions.yaml"))) == 1


def test_restored_graph_reuses_its_durable_bundle_on_an_okf_only_sync(exchange, tmp_path):
    library, pool, vector, graph, _ = _pool()
    _ingest(library, "/host/a.pdf", "Document source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].status == "ready"

    root = tmp_path / "manual"
    root.mkdir()
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "manual.md").write_text("---\ntype: Topic\ntitle: Manual\n---\nManual concept.\n", encoding="utf-8")
    manual = library.create_okf_asset(root.as_uri())
    library.register_assets([manual])
    library.add_assets_to_pool("pool", [manual.asset_id])
    restored, adapter = _indexer(graph.configuration)
    pool.set_projections([vector, restored])

    library.sync_asset_pool("pool")

    status = pool.source_statuses[restored.source.source_id]
    assert status.status == "ready", status.error
    assert len(exchange.instances) == 1, "the extracted bundle asset survives a fresh GraphIndexer"
    assert {node.title for node in vector.concept_batches[-1]} == {"Manual", "Corpus"}
    # Only the new manual bundle is written: the extracted one is an asset the
    # source already indexed.
    assert {vertex["id"] for vertex in adapter.vertices} == {"topic/manual"}


def test_failed_reextraction_preserves_the_previous_bundle(exchange, monkeypatch, tmp_path):
    library, pool, _, graph, _ = _pool()
    _ingest(library, "/host/a.pdf", "Original source.")
    library.sync_asset_pool("pool")
    generated, folder = _generated(library, pool)
    original = (folder / "task.json").read_text()
    _ingest(library, "/host/a.pdf", "Changed source.")

    def fail(*args, **kwargs):
        raise httpx.ConnectError("model unavailable")

    monkeypatch.setattr(exchange, "chat", fail)
    library.sync_asset_pool("pool")

    # The extraction job failed; the graph keeps serving the previous bundle.
    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready" and status.extraction_outdated
    job = library.extraction_jobs.list("pool")[0]
    assert job.state == "failed" and "502" in job.error
    assert (folder / "task.json").read_text() == original
    assert (folder / "index.md").is_file()
    assert _generated(library, pool)[0].asset_id == generated.asset_id


def test_inline_document_provenance_resolves_by_asset_id_not_local_paths():
    concept = OKFNode(ctype="Topic", title="Inline", source_files=["logical/a.txt", "logical/b.txt"])
    chunks = [
        TextNode(id_="a0", text="a", metadata={"asset_id": "a"}),
        TextNode(id_="b0", text="b", metadata={"asset_id": "b"}),
        TextNode(id_="a1", text="a more", metadata={"asset_id": "a"}),
    ]
    resolve_task_source_chunk_ids([concept], chunks, {"logical/a.txt": "a", "logical/b.txt": "b"})
    assert concept.source_chunk_ids == ["a0", "a1", "b0"]


@pytest.mark.parametrize("sources", [{}, {"a.txt": "missing"}])
def test_unknown_or_unindexed_task_provenance_is_an_error(sources):
    with pytest.raises(ValueError, match="unknown task sources|no matching chunks"):
        resolve_task_source_chunk_ids([OKFNode(source_files=["a.txt"])], [], sources)


def test_deleted_documents_trigger_fresh_planning_not_stale_cache_reuse(exchange):
    library, pool, vector, graph, _ = _graph_pool(configuration={
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://extractor"},
    })
    vector.build_concept_index = lambda concepts: None
    vector.load_concept_index = lambda ids: None
    first = _ingest(library, "/host/first.pdf", "First source.")
    second = _ingest(library, "/host/second.pdf", "Second source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].status == "ready"
    library.delete_assets([first.asset_id])

    # The corpus changed: the generated bundle is outdated and rebuilt without
    # the deleted document; the next sync re-extracts what is left.
    assert pool.source_statuses[graph.source.source_id].extraction_outdated
    assert pool.source_statuses[graph.source.source_id].status == "pending"
    library.sync_asset_pool("pool")

    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready", status.error
    assert len(exchange.instances) == 2
    reviews = [body for kind, body in exchange.instances[-1].events if kind == "review"]
    assert len(reviews) == 1 and reviews[0]["content"] == "Second source."


def test_refresh_retires_concepts_and_vectors_that_disappear(exchange, monkeypatch):
    library, pool, vector, graph, adapter = _graph_pool(configuration={
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://extractor"},
    })
    vector.build_concept_index = lambda concepts: None
    vector.load_concept_index = lambda ids: None
    _ingest(library, "/host/a.pdf", "Original source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].status == "ready"

    original_chat = exchange.chat

    def renamed(self, *args, **kwargs):
        choice = original_chat(self, *args, **kwargs)
        for call in choice["message"].get("tool_calls", []):
            if call["function"]["name"] == "write_concept":
                values = json.loads(call["function"]["arguments"])
                values["title"] = "Updated"
                call["function"]["arguments"] = json.dumps(values)
        return choice

    monkeypatch.setattr(exchange, "chat", renamed)
    _ingest(library, "/host/a.pdf", "Updated source.")
    library.sync_asset_pool("pool")

    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready", status.error
    assert adapter.deleted == ["topic/corpus"]
    assert vector.concepts_removed == ["topic/corpus"]
    assert set(adapter.store.nodes) == {"topic/updated"}


def test_deleting_the_only_source_removes_its_generated_concepts(exchange):
    library, pool, vector, graph, adapter = _graph_pool(configuration={
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://extractor"},
    })
    vector.build_concept_index = lambda concepts: None
    vector.load_concept_index = lambda ids: None
    asset = _ingest(library, "/host/a.pdf", "Only source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].status == "ready"

    _, folder = _generated(library, pool)
    library.delete_assets([asset.asset_id])

    assert adapter.deleted == ["topic/corpus"]
    assert vector.concepts_removed == ["topic/corpus"]
    assert not adapter.store.nodes
    # With no documents left, the extracted bundle asset goes too.
    assert not [a for a in library.assets.values() if a.asset_kind == "okf"]
    assert not folder.exists()


def test_invalid_candidate_bundle_is_removed_and_cannot_replace_the_good_cache(exchange, monkeypatch, tmp_path):
    library, pool, vector, graph, _ = _pool()
    _ingest(library, "/host/a.pdf", "Original source.")
    library.sync_asset_pool("pool")
    _, folder = _generated(library, pool)
    before = (folder / "task.json").read_text()
    original_extract = graph.extract_documents

    def invalid(assets, output_dir):
        target = output_dir / "invalid.okf"
        target.mkdir()
        (target / "index.md").write_text("# index\n", encoding="utf-8")
        (target / "concept.md").write_text("---\ntype: Topic\ntitle: Invalid\n---\nNo provenance.\n", encoding="utf-8")
        (target / "task.json").write_text('{"sources": []}', encoding="utf-8")
        return [target]

    monkeypatch.setattr(graph, "extract_documents", invalid)
    _ingest(library, "/host/a.pdf", "Changed source.")
    library.sync_asset_pool("pool")

    assert library.extraction_jobs.list("pool")[0].state == "failed"
    assert pool.source_statuses[graph.source.source_id].extraction_outdated
    assert (folder / "task.json").read_text() == before
    assert not list(folder.parent.rglob("invalid.okf"))

    monkeypatch.setattr(graph, "extract_documents", original_extract)
    library.sync_asset_pool("pool")
    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready", status.error
    assert library.extraction_jobs.list("pool")[0].state == "succeeded"
    assert not status.extraction_outdated


def test_sequential_deletes_do_not_require_a_resync_to_remove_the_last_generated_concept(exchange):
    library, pool, vector, graph, adapter = _graph_pool(configuration={
        "asset_types": ["okf", "document"], "external_extractor": {"url": "http://extractor"},
    })
    vector.build_concept_index = lambda concepts: None
    vector.load_concept_index = lambda ids: None
    first = _ingest(library, "/host/a.pdf", "First source.")
    last = _ingest(library, "/host/b.pdf", "Last source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].status == "ready"

    library.delete_assets([first.asset_id])
    assert adapter.deleted == []
    library.delete_assets([last.asset_id])

    assert adapter.deleted == ["topic/corpus"]
    assert not adapter.store.nodes