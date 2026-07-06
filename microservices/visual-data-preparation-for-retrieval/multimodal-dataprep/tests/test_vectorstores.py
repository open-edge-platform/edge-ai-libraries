# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pluggable vector-store abstraction.

Covers the factory selection logic, the backend-neutral metadata adapters, and
the common insert contract using a mocked backend client (no real DB).
"""

import pytest

from src.core.vectorstores import (
    BaseVectorStore,
    adapt_for_milvus,
    adapt_for_vdms,
    get_vector_store,
    reset_vector_store,
)
from src.core.vectorstores.metadata import CANONICAL_FIELDS


# --------------------------- metadata adapters -----------------------------
def test_adapt_for_vdms_flattens_lists_and_dicts():
    md = {
        "video_id": "v1",
        "tags": ["car", "road"],
        "bbox": [1, 2, 3, 4],
        "fps": 30.0,
        "none_field": None,
        "nested": {"a": 1},
    }
    out = adapt_for_vdms(md)
    assert out["tags"] == "car,road"
    assert out["bbox"] == "1,2,3,4"
    assert out["fps"] == 30.0
    assert "none_field" not in out
    assert out["nested"] == '{"a": 1}'


def test_adapt_for_milvus_preserves_lists_drops_none():
    md = {"video_id": "v1", "tags": ["car"], "bbox": [1, 2], "none_field": None}
    out = adapt_for_milvus(md)
    assert out["tags"] == ["car"]
    assert out["bbox"] == [1, 2]
    assert "none_field" not in out


def test_canonical_fields_present():
    for required in ("video_id", "timestamp", "tags", "bbox", "fps"):
        assert required in CANONICAL_FIELDS


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
