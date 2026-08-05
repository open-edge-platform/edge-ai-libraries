# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Milvus write-path integration test.

Validates the dataprep write path end-to-end against a REAL Milvus container
(milvus-lite is not supported by langchain_milvus's ORM ``col`` property). The
test is skipped unless ``MILVUS_IT_URI`` points at a running Milvus instance,
e.g.::

    MILVUS_IT_URI=http://localhost:19531 poetry run pytest tests/test_milvus_integration.py

A reusable proxy-disabled compose for this is documented under
``docker/milvus`` / the spike compose. Because the Milvus *retriever* is out of
scope, this round-trip (write -> read back vectors + metadata) is the primary
verification that the Milvus backend works.
"""

import os
import random
import uuid

import pytest

MILVUS_IT_URI = os.environ.get("MILVUS_IT_URI")

pytestmark = pytest.mark.skipif(
    not MILVUS_IT_URI,
    reason="Set MILVUS_IT_URI=http://host:port to run the Milvus integration test.",
)


@pytest.fixture
def collection_name():
    return f"dataprep_it_{uuid.uuid4().hex[:8]}"


def test_milvus_write_and_readback(monkeypatch, collection_name):
    from src.common import settings
    from src.core.vectorstores.milvus_store import MilvusVectorStore

    monkeypatch.setattr(settings, "VDB_METRIC_TYPE", "IP")

    store = MilvusVectorStore(uri=MILVUS_IT_URI, collection_name=collection_name)

    # Health probe should succeed against the live container.
    assert store.health()["status"] == "ok"

    dim = 512
    texts = ["frame a", "frame b"]
    embeddings = [[random.random() for _ in range(dim)] for _ in range(2)]
    metadatas = [
        {"video_id": "v1", "tags": ["car", "road"], "bbox": [1, 2, 3, 4], "timestamp": 1.5, "n": None},
        {"video_id": "v1", "tags": ["person"], "timestamp": 2.5},
    ]

    ids = store.add_embeddings(texts, embeddings, metadatas)
    assert len(ids) == 2
    assert all(isinstance(i, str) for i in ids)  # int64 pks normalized to str

    store.update_index()  # no-op, must not raise

    # Read back via pymilvus and verify list metadata preserved + None dropped.
    from pymilvus import Collection, connections

    connections.connect(alias="it_reader", uri=MILVUS_IT_URI)
    try:
        col = Collection(collection_name, using="it_reader")
        col.flush()
        col.load()
        assert col.num_entities == 2
        rows = col.query(
            expr='video_id == "v1"', output_fields=["*"], limit=5, using="it_reader"
        )
        by_text = {r["text"]: r for r in rows}
        assert by_text["frame a"]["tags"] == ["car", "road"]
        assert by_text["frame a"]["bbox"] == [1, 2, 3, 4]
        assert "n" not in by_text["frame a"]  # None dropped
        assert by_text["frame b"]["tags"] == ["person"]
    finally:
        col.drop()
        connections.disconnect("it_reader")
