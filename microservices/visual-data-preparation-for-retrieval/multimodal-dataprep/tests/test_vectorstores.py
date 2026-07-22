# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pluggable vector-store abstraction.

Covers the factory selection logic, the backend-neutral metadata adapters, and
the common insert contract using a mocked backend client (no real DB).
"""

import pytest

from src.core.vectorstores import (
    BaseVectorStore,
    get_vector_store,
    project_to_canonical,
    reset_vector_store,
)
from src.core.vectorstores.metadata import (
    CANONICAL_FIELDS,
    flatten_to_scalars,
)


# --------------------------- metadata primitives ---------------------------
def test_project_to_canonical_drops_non_canonical_keys():
    md = {"video_id": "v1", "shm": "seg1", "frame_id": "f1", "not_a_field": 1}
    out = project_to_canonical(md)
    assert out == {"video_id": "v1"}


def test_flatten_to_scalars_flattens_lists_and_dicts_drops_none():
    md = {
        "video_id": "v1",
        "tags": ["car", "road"],
        "crop_bbox": [1, 2, 3, 4],
        "fps": 30.0,
        "created_at": None,
        "date_time": {"a": 1},
    }
    out = flatten_to_scalars(md)
    assert out["tags"] == "car,road"
    assert out["crop_bbox"] == "1,2,3,4"
    assert out["fps"] == 30.0
    assert "created_at" not in out
    assert out["date_time"] == '{"a": 1}'


# --------------------------- backend clean_metadata ------------------------
def test_vdms_clean_metadata_projects_and_flattens():
    from src.core.vectorstores.vdms_store import VDMSVectorStore

    store = VDMSVectorStore(host="h", port="1", collection_name="c")
    md = {
        "video_id": "v1",
        "tags": ["car", "road"],
        "crop_bbox": [1, 2, 3, 4],
        "created_at": None,
    }
    out = store.clean_metadata(md)
    assert out["tags"] == "car,road"
    assert out["crop_bbox"] == "1,2,3,4"
    assert "created_at" not in out


def test_milvus_clean_metadata_preserves_lists_drops_none():
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530", collection_name="c")
    md = {"video_id": "v1", "tags": ["car"], "crop_bbox": [1, 2], "created_at": None}
    out = store.clean_metadata(md)
    assert out["tags"] == ["car"]
    assert out["crop_bbox"] == [1, 2]
    assert "created_at" not in out


def test_canonical_fields_present():
    for required in (
        "video_id",
        "timestamp",
        "tags",
        "crop_bbox",
        "detected_label",
        "frame_number",
        "fps",
        "video_url",
        "bucket_name",
    ):
        assert required in CANONICAL_FIELDS


def _make_store(backend):
    if backend == "vdms":
        from src.core.vectorstores.vdms_store import VDMSVectorStore

        return VDMSVectorStore(host="h", port="1", collection_name="c")
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    return MilvusVectorStore(uri="http://localhost:19530", collection_name="c")


@pytest.mark.parametrize("backend", ["vdms", "milvus"])
def test_clean_metadata_drops_transient_keys(backend):
    store = _make_store(backend)
    md = {
        # canonical, retriever-critical fields that MUST survive
        "video_id": "v1",
        "frame_number": 7,
        "detected_label": "car",
        "tags": ["a"],
        "video_url": "http://vdms-dataprep:8000/x",
        # transient pipeline plumbing that must be stripped before storage
        "shm": "seg1",
        "shape": [3, 224, 224],
        "dtype": "float32",
        "frame_id": "f1",
        "stream_id": "s1",
        "batch_id": 2,
        "enqueue_ts": 123.0,
    }
    out = store.clean_metadata(md)
    for keep in ("video_id", "frame_number", "detected_label", "tags", "video_url"):
        assert keep in out
    for drop in ("shm", "shape", "dtype", "frame_id", "stream_id", "batch_id", "enqueue_ts"):
        assert drop not in out


# --------------------------- factory selection -----------------------------
def test_factory_selects_vdms(monkeypatch):
    from src.common import settings
    from src.core.vectorstores.vdms_store import VDMSVectorStore

    monkeypatch.setattr(settings, "VECTORDB_BACKEND", "vdms")
    reset_vector_store()
    try:
        store = get_vector_store()
        assert isinstance(store, VDMSVectorStore)
        assert isinstance(store, BaseVectorStore)
        assert get_vector_store() is store  # cached singleton
    finally:
        reset_vector_store()


def test_factory_selects_milvus(monkeypatch):
    from src.common import settings
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    monkeypatch.setattr(settings, "VECTORDB_BACKEND", "milvus")
    reset_vector_store()
    try:
        store = get_vector_store()
        assert isinstance(store, MilvusVectorStore)
    finally:
        reset_vector_store()


def test_factory_rejects_unknown_backend(monkeypatch):
    from src.common import settings

    monkeypatch.setattr(settings, "VECTORDB_BACKEND", "bogus")
    reset_vector_store()
    try:
        with pytest.raises(ValueError):
            get_vector_store()
    finally:
        reset_vector_store()


# --------------------------- insert contract (mocked) ----------------------
def test_vdms_add_embeddings_delegates_and_cleans(monkeypatch):
    from src.core.vectorstores.vdms_store import VDMSVectorStore

    store = VDMSVectorStore(host="h", port="1", collection_name="c")

    captured = {}

    class FakeVideoDB:
        def add_from(self, texts, embeddings, metadatas, ids, batch_size):
            captured["metadatas"] = metadatas
            captured["ids"] = ids
            return ids

        def check_and_update_properties(self):
            captured["updated"] = True

    # Bypass real connect()
    store.video_db = FakeVideoDB()
    monkeypatch.setattr(store, "connect", lambda: None)

    ids = store.add_embeddings(
        texts=["t1"],
        embeddings=[[0.1, 0.2]],
        metadatas=[{"video_id": "v1", "tags": ["a", "b"], "none_f": None}],
    )
    assert len(ids) == 1
    assert all(isinstance(i, str) for i in ids)
    # VDMS adapter flattened the list and dropped None
    assert captured["metadatas"][0]["tags"] == "a,b"
    assert "none_f" not in captured["metadatas"][0]
    assert captured["updated"] is True


def test_milvus_update_index_is_noop():
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530", collection_name="c")
    # Should not raise even though no connection exists.
    store.update_index()


def test_milvus_uri_resolution(monkeypatch):
    from src.common import settings
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    monkeypatch.setattr(settings, "MILVUS_URI", "", raising=False)
    s = MilvusVectorStore(host="myhost", port="1234")
    assert s.uri == "http://myhost:1234"

    s2 = MilvusVectorStore(uri="http://explicit:9999")
    assert s2.uri == "http://explicit:9999"


# --------------------------- delete contract (mocked) ----------------------
def test_vdms_delete_embeddings_uses_constraints(monkeypatch):
    from src.core.vectorstores.vdms_store import VDMSVectorStore

    store = VDMSVectorStore(host="h", port="1", collection_name="c")
    captured = {}

    class FakeVideoDB:
        def delete(self, constraints=None, **kwargs):
            captured["constraints"] = constraints
            return True

    store.video_db = FakeVideoDB()
    monkeypatch.setattr(store, "connect", lambda: None)

    result = store.delete_embeddings("bucket-a", "video-1")
    # VDMS cannot report an exact count -> -1 on success.
    assert result == -1
    assert captured["constraints"] == {
        "video_id": ["==", "video-1"],
        "bucket_name": ["==", "bucket-a"],
    }


def test_milvus_delete_embeddings_builds_safe_expr(monkeypatch):
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530", collection_name="c")
    captured = {}

    class FakeStore:
        def delete(self, expr=None, **kwargs):
            captured["expr"] = expr
            return True

    store.store = FakeStore()
    monkeypatch.setattr(store, "connect", lambda: None)

    result = store.delete_embeddings("bucket-a", "video-1")
    assert result == -1
    assert captured["expr"] == 'video_id == "video-1" and bucket_name == "bucket-a"'


def test_milvus_delete_embeddings_reports_zero_on_failure(monkeypatch):
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530", collection_name="c")

    class FakeStore:
        def delete(self, expr=None, **kwargs):
            return False  # langchain_milvus signals failure/no-op via False

    store.store = FakeStore()
    monkeypatch.setattr(store, "connect", lambda: None)

    assert store.delete_embeddings("bucket-a", "video-1") == 0


@pytest.mark.parametrize(
    "bucket, vid",
    [
        ('b"; drop', "v1"),
        ("b", 'v" or "1"=="1'),
        ("b", "v id"),  # space is not allowed
        ("", "v1"),
    ],
)
def test_milvus_delete_embeddings_rejects_unsafe_identifiers(monkeypatch, bucket, vid):
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530", collection_name="c")

    class FakeStore:
        def delete(self, expr=None, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("delete must not be called for unsafe identifiers")

    store.store = FakeStore()
    monkeypatch.setattr(store, "connect", lambda: None)

    with pytest.raises(ValueError):
        store.delete_embeddings(bucket, vid)
