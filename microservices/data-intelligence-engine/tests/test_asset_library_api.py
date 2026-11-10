# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The engine exposes a single asset-library contract."""

import asyncio
from threading import RLock
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from api import asset_library as asset_library_api
from api import databases as databases_api
from api import retrieval as retrieval_api
from main import app
from schemas import (
    AssetCreateRequest,
    AssetCreateResult,
    AssetDeleteRequest,
    AssetDeleteResult,
    AssetLibraryOut,
    AssetOut,
    AssetPage,
    AssetPoolIn,
    AssetPoolOut,
    AssetPoolSourcesIn,
    BackendOption,
    DatabaseIn,
    DatabaseOut,
    PostprocessOptions,
    RetrieveRequest,
    RetrieveResult,
    RetrievedChunk,
    SourceOut,
)


def _paths():
    return {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_asset_library_surface_is_reachable():
    assert asset_library_api.LIBRARY_API_PREFIX == "/v1/libraries"
    paths = _paths()
    for suffix, method in (
        ("", "GET"),
        ("", "POST"),
        ("/{library}", "GET"),
        ("/{library}", "PATCH"),
        ("/{library}", "DELETE"),
        ("/{library}/sources", "GET"),
        ("/{library}/sources/{source_id}", "PATCH"),
        ("/{library}/assets", "GET"),
        ("/{library}/assets", "POST"),
        ("/{library}/assets", "DELETE"),
        ("/{library}/assets/{asset_id}", "DELETE"),
        ("/{library}/assets/{asset_id}/enrichment", "GET"),
        ("/{library}/uploads/{file_path}", "PUT"),
        ("/{library}/asset_pools/{asset_pool_id}/graph", "GET"),
        ("/{library}/asset_pools/{asset_pool_id}/routing", "GET"),
        ("/{library}/asset_pools", "POST"),
        ("/{library}/asset_pools/{asset_pool_id}/sources", "GET"),
        ("/{library}/asset_pools/{asset_pool_id}/assets", "GET"),
    ):
        assert (asset_library_api.LIBRARY_API_PREFIX + suffix, method) in paths, suffix


def test_no_deprecated_library_routes_are_mounted():
    paths = app.openapi()["paths"]
    assert all("knowledge" not in path for path in paths)
    assert all(path.split("/")[1:3] != ["v1", "engine"] for path in paths)
    assert "/v1/" + "ingestion" not in paths
    assert all("/files" not in path for path in paths if path.startswith("/v1/libraries"))


def test_retrieve_is_the_only_retrieval_endpoint():
    paths = app.openapi()["paths"]
    assert ("/v1/retrieve", "POST") in _paths()
    assert all(path.split("/")[1:3] != ["v1", "retrieval"] for path in paths)


def test_database_surface_uses_only_the_plural_routes():
    assert databases_api.DATABASE_API_PREFIX == "/v1/databases"
    paths = _paths()
    for path, method in (
        ("/v1/databases", "GET"),
        ("/v1/databases", "POST"),
        ("/v1/databases/backends", "GET"),
        ("/v1/databases/{database_id}", "GET"),
        ("/v1/databases/{database_id}", "PATCH"),
        ("/v1/databases/{database_id}", "DELETE"),
        ("/v1/databases/{database_id}/check", "POST"),
    ):
        assert (path, method) in paths
    assert ("/v1/database/status", "GET") not in paths


def test_database_api_uses_id_and_type_fields():
    assert set(DatabaseIn.model_fields) == {
        "id", "type", "backend", "options", "description"
    }
    assert set(DatabaseOut.model_fields) == {
        "id", "type", "backend", "options", "description", "in_use_by"
    }
    assert set(BackendOption.model_fields) == {"database_type", "backends"}

    request = DatabaseIn(id="main", type="vector", backend="milvus")
    response = DatabaseOut(id=request.id, type=request.type, backend=request.backend)
    assert request.model_dump()["id"] == response.model_dump()["id"] == "main"
    assert request.model_dump()["type"] == response.model_dump()["type"] == "vector"
    with pytest.raises(ValidationError):
        DatabaseIn.model_validate(
            {"database_id": "main", "database_type": "vector", "backend": "milvus"}
        )


def test_source_output_uses_id_and_type_fields():
    source = SourceOut(
        id="source-1",
        name="primary",
        type="vector",
        database_id="database-1",
        collection_name="documents",
    )

    assert source.model_dump()["id"] == "source-1"
    assert source.model_dump()["type"] == "vector"
    assert "source_id" not in SourceOut.model_fields
    assert "source_type" not in SourceOut.model_fields
    with pytest.raises(ValidationError):
        SourceOut.model_validate(
            {
                "source_id": "source-1",
                "name": "primary",
                "source_type": "vector",
                "database_id": "database-1",
                "collection_name": "documents",
            }
        )


def test_asset_pool_create_uses_optional_source_ids():
    pool = AssetPoolIn.model_validate(
        {
            "id": "pool-1",
            "name": "Documents",
            "sources": ["source-1"],
        }
    )

    assert pool.sources == ["source-1"]
    assert AssetPoolIn(id="empty", name="Empty").sources is None
    source_schema = app.openapi()["components"]["schemas"]["AssetPoolIn"][
        "properties"
    ]["sources"]
    assert source_schema["anyOf"][0]["items"]["type"] == "string"
    with pytest.raises(ValidationError):
        AssetPoolIn.model_validate(
            {
                "id": "pool-1",
                "name": "Documents",
                "sources": [{"source_id": "source-1"}],
            }
        )

    update = AssetPoolSourcesIn(sources=["source-1"])
    assert update.sources == ["source-1"]


def test_pool_handlers_translate_source_ids(monkeypatch):
    calls = []
    pool = AssetPoolOut(id="pool-1", name="Documents")

    class FakeLibrary:
        def create_asset_pool(self, **kwargs):
            calls.append(("create", kwargs))

        def set_asset_pool_sources(self, **kwargs):
            calls.append(("update", kwargs))

        def _require_asset_pool(self, asset_pool_id):
            assert asset_pool_id == "pool-1"

        def to_out(self):
            return SimpleNamespace(asset_pools=[pool])

    class FakeRegistry:
        def __init__(self):
            self.library = FakeLibrary()

        def get(self, library):
            assert library == "library-1"
            return self.library

        def save(self):
            pass

    monkeypatch.setattr(asset_library_api, "registry", FakeRegistry())

    created = asyncio.run(
        asset_library_api.create_asset_pool(
            "library-1",
            AssetPoolIn(id="pool-1", name="Documents", sources=["source-1"]),
        )
    )
    updated = asyncio.run(
        asset_library_api.set_asset_pool_sources(
            "library-1",
            "pool-1",
            AssetPoolSourcesIn(sources=["source-2"]),
            BackgroundTasks(),
        )
    )

    assert created is pool
    assert updated is pool
    assert calls[0][1]["source_configurations"] == [{"source_id": "source-1"}]
    assert calls[1][1]["source_configurations"] == [{"source_id": "source-2"}]


@pytest.mark.parametrize("asset_pool_ids", ([], ["pool-1"]))
def test_create_assets_returns_202_and_defers_to_a_background_task(
    monkeypatch, asset_pool_ids
):
    """The slow path -- extract, store, index -- runs in the background, so the
    request returns at once and names the assets without having extracted them."""
    pool = SimpleNamespace(asset_ids=[])

    class FakeLibrary:
        name = "library-1"

        def __init__(self):
            self.asset_pools = {"pool-1": pool}

        def content_source(self, source_id=None):
            assert source_id is None, "no override was asked for"
            return SimpleNamespace(source_id="content-1", source_type="object")

    class FakeRegistry:
        def __init__(self):
            self.library = FakeLibrary()
            self.lock = RLock()

        def get(self, library):
            assert library == "library-1"
            return self.library

        def save(self):
            raise AssertionError("create_assets must not save; the task does")

    fake_registry = FakeRegistry()
    monkeypatch.setattr(asset_library_api, "registry", fake_registry)
    monkeypatch.setattr(asset_library_api, "_resolve_uploads", lambda paths: paths)
    monkeypatch.setattr(asset_library_api, "file_origin", lambda path: f"file://{path}")
    monkeypatch.setattr(asset_library_api, "asset_id_for", lambda _origin: "asset-1")
    scheduled = []
    monkeypatch.setattr(
        asset_library_api,
        "materialize",
        SimpleNamespace(
            ingest=lambda *args: scheduled.append(args),
            begin_materialization=lambda *args: None,
        ),
    )

    background_tasks = BackgroundTasks()
    result = asyncio.run(
        asset_library_api.create_assets(
            "library-1",
            AssetCreateRequest(
                file_paths=["manual.pdf"], asset_pool_ids=asset_pool_ids
            ),
            background_tasks,
        )
    )

    # Accepted immediately: nothing was extracted, stored or indexed inline.
    assert result.status == "materializing"
    assert result.asset_ids == ["asset-1"]
    assert result.asset_pool_ids == asset_pool_ids
    assert result.file_paths == ["manual.pdf"]
    assert result.content_source_id == "content-1"
    assert "warnings" not in result.model_dump()
    assert pool.asset_ids == [], "the pool is filled by the task, not the request"
    # Exactly one background task, carrying what the task needs to do the work.
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is asset_library_api.materialize.ingest
    assert task.args[0] is fake_registry.library
    assert task.args[1:] == (["manual.pdf"], "", "", asset_pool_ids, "content-1")


def test_missing_asset_file_reports_its_resolved_upload_path(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))

    with pytest.raises(ValueError) as caught:
        asset_library_api._resolve_uploads(["missing.pdf"])

    assert "Asset file not found: 'missing.pdf'" in str(caught.value)
    assert str(tmp_path / "missing.pdf") in str(caught.value)


@pytest.mark.parametrize("name", ["legacy.doc", "slides.ppt", "book.epub", "archive.zip"])
def test_unsupported_asset_file_type_is_rejected_before_ingest(monkeypatch, tmp_path, name):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / name).write_bytes(b"\xd0\xcf\x11\xe0")

    with pytest.raises(ValueError, match=f"Unsupported asset file type: '{name}'"):
        asset_library_api._resolve_uploads([name])


@pytest.mark.parametrize("name", ["report.pdf", "sheet.xlsx", "page.htm", "photo.png", "clip.mp4"])
def test_documents_and_media_files_are_accepted(monkeypatch, tmp_path, name):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / name).write_bytes(b"data")

    assert asset_library_api._resolve_uploads([name]) == [str(tmp_path / name)]


def test_a_plain_folder_stands_for_its_supported_files(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))
    folder = tmp_path / "batch"
    (folder / "sub").mkdir(parents=True)
    (folder / ".hidden").mkdir()
    (folder / "b.pdf").write_bytes(b"data")
    (folder / "sub" / "a.txt").write_text("text")
    (folder / "archive.zip").write_bytes(b"PK")
    (folder / ".DS_Store").write_bytes(b"")
    (folder / ".hidden" / "c.txt").write_text("text")

    assert asset_library_api._resolve_uploads(["batch"]) == [
        str(folder / "b.pdf"),
        str(folder / "sub" / "a.txt"),
    ]


def test_a_folder_with_nothing_supported_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "archive.zip").write_bytes(b"PK")

    with pytest.raises(ValueError, match="holds no supported files"):
        asset_library_api._resolve_uploads(["empty"])


@pytest.mark.parametrize("path", ["", "/etc/passwd", "../x.pdf", "a/../../x.pdf", "a//b.pdf", "./a.pdf"])
def test_upload_paths_cannot_leave_the_library_folder(monkeypatch, tmp_path, path):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Invalid upload path"):
        asset_library_api._upload_target("lib-1", path)


def test_upload_paths_keep_their_folders(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_library_api.config, "UPLOAD_DIR", str(tmp_path))

    assert asset_library_api._upload_target("lib-1", "docs/sub/a.pdf") == str(
        tmp_path / "lib-1" / "docs" / "sub" / "a.pdf"
    )


def test_pool_member_routes_return_attached_sources_and_asset_ids(monkeypatch):
    attached = SourceOut(
        id="source-1",
        name="primary",
        type="vector",
        database_id="database-1",
        collection_name="documents",
    )
    unattached = SourceOut(
        id="source-2",
        name="secondary",
        type="vector",
        database_id="database-1",
        collection_name="other-documents",
    )
    pool = SimpleNamespace(
        source_statuses={"source-1": object()},
        asset_ids=["asset-2", "asset-1"],
    )

    class FakeLibrary:
        def _require_asset_pool(self, asset_pool_id):
            assert asset_pool_id == "pool-1"
            return pool

        def to_out(self):
            return SimpleNamespace(sources=[attached, unattached])

    class FakeRegistry:
        def get(self, library):
            assert library == "library-1"
            return FakeLibrary()

    monkeypatch.setattr(asset_library_api, "registry", FakeRegistry())

    sources = asyncio.run(
        asset_library_api.list_asset_pool_sources("library-1", "pool-1")
    )
    assets = asyncio.run(
        asset_library_api.list_asset_pool_assets("library-1", "pool-1")
    )

    assert sources == [attached]
    assert assets == ["asset-2", "asset-1"]


def test_pool_source_dependency_failure_is_service_unavailable(monkeypatch):
    class FakeLibrary:
        def set_asset_pool_sources(self, **kwargs):
            raise RuntimeError("embedding model unavailable")

    class FakeRegistry:
        def get(self, library):
            return FakeLibrary()

    monkeypatch.setattr(asset_library_api, "registry", FakeRegistry())

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            asset_library_api.set_asset_pool_sources(
                "library-1",
                "pool-1",
                AssetPoolSourcesIn(sources=["source-1"]),
                BackgroundTasks(),
            )
        )

    assert caught.value.status_code == 503
    assert "embedding model unavailable" in caught.value.detail


def test_asset_library_and_pool_api_use_id_fields():
    pool = AssetPoolOut(id="pool-1", name="Documents")
    library = AssetLibraryOut(id="library-1", name="Library", asset_pools=[pool])

    assert library.model_dump()["id"] == "library-1"
    assert library.model_dump()["asset_pools"][0]["id"] == "pool-1"
    assert "idx" not in AssetLibraryOut.model_fields
    assert "asset_pool_id" not in AssetPoolIn.model_fields
    assert "asset_pool_id" not in AssetPoolOut.model_fields

    with pytest.raises(ValidationError):
        AssetPoolIn.model_validate({"asset_pool_id": "pool-1", "name": "Pool"})
    with pytest.raises(ValidationError):
        AssetPoolOut.model_validate({"asset_pool_id": "pool-1", "name": "Pool"})
    with pytest.raises(ValidationError):
        AssetLibraryOut.model_validate({"idx": "library-1", "name": "Library"})


def test_openapi_operation_ids_are_unique():
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for methods in schema["paths"].values()
        for operation in methods.values()
        if "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_retrieve_request_uses_libraries_and_optional_postprocess():
    request = RetrieveRequest.model_validate(
        {
            "query": "q",
            "libraries": ["library-1", "library-2"],
            "postprocess": {"query": "rerank q", "top_n": 2},
        }
    )

    assert request.libraries == ["library-1", "library-2"]
    assert request.postprocess == PostprocessOptions(query="rerank q", top_n=2)
    assert "library" not in RetrieveRequest.model_fields
    assert "rerank_top_n" not in RetrieveRequest.model_fields


def test_asset_creation_request_uses_path_library_and_explicit_pool_list():
    request = AssetCreateRequest(
        file_paths=["manual.pdf"], asset_pool_ids=["searchable"]
    )

    assert request.asset_pool_ids == ["searchable"]
    assert "library" not in AssetCreateRequest.model_fields
    assert "asset_pool_id" not in AssetCreateRequest.model_fields


def test_asset_creation_and_retrieval_results_use_library():
    created = AssetCreateResult(library="library-1")
    retrieve = RetrieveResult(query="q", libraries=["library-1"])

    assert created.model_dump()["library"] == "library-1"
    assert retrieve.model_dump()["libraries"] == ["library-1"]
    assert "kb_name" not in created.model_dump()
    assert "kb_name" not in retrieve.model_dump()


def test_asset_creation_status_is_materializing_or_stored_and_has_no_warnings():
    assert AssetCreateResult(library="library-1", status="materializing").status == "materializing"
    assert AssetCreateResult(library="library-1", status="stored").status == "stored"
    with pytest.raises(ValidationError):
        AssetCreateResult(library="library-1", status="indexing")
    assert "warnings" not in AssetCreateResult.model_fields
    schema = app.openapi()["components"]["schemas"]["AssetCreateResult"]["properties"]
    assert "warnings" not in schema
    assert set(schema["status"]["enum"]) == {"stored", "materializing"}


def test_retrieve_merges_libraries_before_optional_postprocess(monkeypatch):
    libraries = {
        "first": SimpleNamespace(name="First"),
        "second": SimpleNamespace(name="Second"),
    }
    captured = {}

    class FakeRegistry:
        def require(self, reference):
            return libraries[reference]

    chunks = {
        "First": [
            RetrievedChunk(id="keep", text="first", score=0.8),
            RetrievedChunk(id="drop", text="old", score=0.9),
        ],
        "Second": [RetrievedChunk(id="best", text="second", score=1.0)],
    }

    def fake_postprocess(query, retrieved, processor_type, top_n, model):
        captured.update(
            query=query,
            ids=[chunk.id for chunk in retrieved],
            processor_type=processor_type,
            top_n=top_n,
            model=model,
        )
        return retrieved[:top_n]

    monkeypatch.setattr(retrieval_api, "registry", FakeRegistry())
    monkeypatch.setattr(
        retrieval_api,
        "_retrieve_chunks",
        lambda library, _body, _traces: chunks[library.name],
    )
    monkeypatch.setattr(retrieval_api, "postprocess_chunks", fake_postprocess)
    monkeypatch.setattr(retrieval_api.config, "RERANK_MODEL_ID", "BAAI/bge-reranker-large")

    result = asyncio.run(
        retrieval_api.retrieve(
            RetrieveRequest(
                query="search query",
                libraries=["first", "second"],
                top_k=5,
                exclude_chunk_ids=["drop"],
                postprocess=PostprocessOptions(query="rerank query", top_n=1),
            )
        )
    )

    assert result.libraries == ["First", "Second"]
    assert [chunk.id for chunk in result.retrieved_chunks] == ["keep", "best"]
    assert [chunk.id for chunk in result.chunks] == ["keep"]
    assert captured == {
        "query": "rerank query",
        "ids": ["keep", "best"],
        "processor_type": "reranker",
        "top_n": 1,
        "model": None,
    }


def test_asset_list_and_delete_models_use_asset_ids():
    asset = AssetOut(
        id="asset-1",
        name="manual.pdf",
        origin="file:///workspace/uploads/manual.pdf",
        kind="file",
        media_type="application/pdf",
        asset_pool_ids=["searchable"],
    )
    page = AssetPage(assets=[asset], total=1)
    request = AssetDeleteRequest(asset_ids=[asset.id])
    result = AssetDeleteResult(
        library="library-1",
        removed=[asset.id],
        materializations_removed=2,
    )

    assert page.assets[0].id == request.asset_ids[0]
    assert result.materializations_removed == 2


def test_asset_library_output_includes_document_projection_fields():
    fields = AssetLibraryOut.model_fields
    for name in (
        "id",
        "name",
        "description",
        "asset_count",
        "sources",
        "asset_pools",
        "document_count",
        "chunk_count",
    ):
        assert name in fields
    assert "file_map" not in fields
