# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import types

import src.retriever.service as service_module
from src.common.schema import QueryRequest


class _FakeVectorDb:
    """Tiny vector DB stub for deterministic service unit tests."""

    def __init__(self, docs_with_score):
        self.docs_with_score = docs_with_score
        self.last_call = None
        self.last_vector_call = None

    def similarity_search_with_score(self, query, k, fetch_k, filter):
        self.last_call = {
            "query": query,
            "k": k,
            "fetch_k": fetch_k,
            "filter": filter,
        }
        return self.docs_with_score

    def similarity_search_with_score_by_vector(self, embedding, k, filter=None):
        self.last_vector_call = {
            "embedding": embedding,
            "k": k,
            "filter": filter,
        }
        return self.docs_with_score


class _FailThenSucceedVectorDb:
    """DB stub that raises on first call, then succeeds on second."""

    def __init__(self, docs_with_score):
        self.docs_with_score = docs_with_score
        self.call_count = 0

    def similarity_search_with_score(self, query, k, fetch_k, filter):
        self.call_count += 1
        if self.call_count == 1:
            raise ConnectionError("simulated dropped connection")
        return self.docs_with_score


def test_execute_single_query_includes_explain_fields_when_requested(monkeypatch):
    """Explain mode should include compiled backend and rewrite details."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v1", "tags": ["traffic"]},
                page_content="frame-a",
            ),
            0.91,
        )
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        query="person near car",
        explain_filters=True,
        where={"field": "video_id", "op": "eq", "value": "v1"},
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.applied_filters.normalized_where is not None
    # For VDMS, eq is not pushed down (langchain-vdms constraint-ordering artefact).
    # The predicate is evaluated in-memory; no native backend filter is compiled.
    assert result.applied_filters.compiled_backend_filter is None
    assert result.applied_filters.warnings is not None
    assert any("video_id:eq" in warning for warning in result.applied_filters.warnings)
    assert result.applied_filters.dropped_or_rewritten_clauses == ["video_id:eq"]
    assert fake_db.last_call is not None
    assert fake_db.last_call["filter"] is None


def test_execute_single_query_omits_explain_fields_by_default(monkeypatch):
    """Non-explain mode should keep explain-only fields unset."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v2", "tags": ["person"]},
                page_content="frame-b",
            ),
            0.8,
        )
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        query="person near car",
        where={"field": "video_id", "op": "eq", "value": "v2"},
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.applied_filters.compiled_backend_filter is None
    assert result.applied_filters.dropped_or_rewritten_clauses is None


def test_execute_single_query_applies_fallback_for_any_clause(monkeypatch):
    """`any` clauses should still be enforced even when not pushed down."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-match", "tags": ["traffic"]},
                page_content="frame-keep",
            ),
            0.95,
        ),
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-drop", "tags": ["night"]},
                page_content="frame-drop",
            ),
            0.9,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        query="person near car",
        explain_filters=True,
        where={
            "any": [
                {"field": "video_id", "op": "eq", "value": "v-match"},
                {"field": "tags", "op": "contains_any", "value": ["pedestrian"]},
            ]
        },
        top_k=2,
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.items[0].metadata["video_id"] == "v-match"
    assert result.applied_filters.normalized_where is not None
    assert result.applied_filters.compiled_backend_filter is None
    assert result.applied_filters.warnings is not None
    assert any("any'/'not" in warning for warning in result.applied_filters.warnings)


def test_execute_single_query_reports_vdms_lte_as_fallback_only(monkeypatch):
    """VDMS explain output should surface fallback-only operators like lte."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v1", "frame_number": 10},
                page_content="frame-a",
            ),
            0.91,
        ),
        (
            types.SimpleNamespace(
                metadata={"video_id": "v2", "frame_number": 50},
                page_content="frame-b",
            ),
            0.8,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    result = service_module.execute_single_query(
        QueryRequest(
            query="frame query",
            explain_filters=True,
            where={"field": "frame_number", "op": "lte", "value": 30},
            top_k=2,
        )
    )

    assert result.count == 1
    assert result.items[0].metadata["video_id"] == "v1"
    assert result.applied_filters.compiled_backend_filter is None
    assert result.applied_filters.warnings is not None
    assert any("frame_number:lte" in warning for warning in result.applied_filters.warnings)
    assert result.applied_filters.dropped_or_rewritten_clauses == ["frame_number:lte"]
    assert fake_db.last_call is not None
    assert fake_db.last_call["filter"] is None
    assert fake_db.last_call["fetch_k"] > fake_db.last_call["k"]


def test_execute_single_query_logs_final_debug_inputs(monkeypatch, caplog):
    """Debug logging should include final query/filter execution state."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-match", "tags": ["traffic"]},
                page_content="frame-keep",
            ),
            0.95,
        ),
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-match", "tags": ["night"]},
                page_content="frame-drop",
            ),
            0.9,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "milvus")

    request = QueryRequest(
        query="person near car",
        where={
            "all": [
                {"field": "video_id", "op": "eq", "value": "v-match"},
                {"field": "tags", "op": "contains_any", "value": ["traffic"]},
            ]
        },
        top_k=2,
    )

    with caplog.at_level(logging.DEBUG, logger=service_module.logger.name):
        result = service_module.execute_single_query(request)

    assert result.count == 1
    assert fake_db.last_call is not None

    debug_message = next(
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "Final query execution inputs" in record.getMessage()
    )

    assert "query='person near car'" in debug_message
    assert "normalized_where={'all':" in debug_message
    assert 'compiled_backend_filter=\'video_id == "v-match"\'' in debug_message
    assert "top_k=2" in debug_message
    assert f"fetch_k={fake_db.last_call['fetch_k']}" in debug_message
    assert "fallback_filter_active=True" in debug_message
    assert "overfetch_active=True" in debug_message


def test_reconnect_retry_on_connection_error(monkeypatch):
    """A dropped backend connection should be retried once with a fresh client."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v1"},
                page_content="frame-a",
            ),
            0.9,
        )
    ]
    failing_db = _FailThenSucceedVectorDb(docs)
    fresh_db = _FakeVectorDb(docs)

    cache_cleared = []

    call_count = [0]

    def fake_get_vectordb():
        call_count[0] += 1
        if call_count[0] == 1:
            return failing_db
        return fresh_db

    def fake_clear_cache():
        cache_cleared.append(True)

    monkeypatch.setattr(service_module, "get_vectordb", fake_get_vectordb)
    monkeypatch.setattr(service_module, "clear_vectordb_cache", fake_clear_cache)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(query="test query")
    result = service_module.execute_single_query(request)

    # Should succeed via the retry path
    assert result.count == 1
    assert result.items[0].metadata["video_id"] == "v1"
    # Cache must have been cleared on the first failure
    assert len(cache_cleared) == 1
    # The failing DB was called once; fresh DB handled the retry
    assert failing_db.call_count == 1


def test_execute_single_query_clamps_non_positive_top_k(monkeypatch):
    """Invalid top_k values should clamp to the minimum supported page size."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v1"},
                page_content="frame-a",
            ),
            0.91,
        ),
        (
            types.SimpleNamespace(
                metadata={"video_id": "v2"},
                page_content="frame-b",
            ),
            0.9,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    result = service_module.execute_single_query(QueryRequest(query="test query", top_k=0))

    assert result.count == 1
    assert fake_db.last_call is not None
    assert fake_db.last_call["k"] == 1


def test_execute_single_query_matches_timezone_aware_eq_filters(monkeypatch):
    """Datetime equality fallback should compare normalized timestamp values."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"created_at": "2026-03-01T00:00:00Z", "video_id": "v-match"},
                page_content="frame-a",
            ),
            0.91,
        ),
        (
            types.SimpleNamespace(
                metadata={"created_at": "2026-03-02T00:00:00Z", "video_id": "v-drop"},
                page_content="frame-b",
            ),
            0.9,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    result = service_module.execute_single_query(
        QueryRequest(
            query="test query",
            where={"field": "created_at", "op": "eq", "value": "2026-03-01T00:00:00+00:00"},
            top_k=2,
        )
    )

    assert result.count == 1
    assert result.items[0].metadata["video_id"] == "v-match"


# ── Image query tests ────────────────────────────────────────────────


class _FakeEmbeddingAPI:
    """Stub embedding client that returns deterministic image embeddings."""

    def __init__(self, api_url="", model_name=""):
        self.last_image = None

    def embed_image(self, image):
        self.last_image = image
        return [0.1, 0.2, 0.3]


def test_execute_single_query_image_url(monkeypatch):
    """Image URL queries should compute embedding and use vector search."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v1"},
                page_content="frame-a",
            ),
            0.95,
        )
    ]
    fake_db = _FakeVectorDb(docs)
    fake_embed = _FakeEmbeddingAPI()

    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module, "EmbeddingAPI", lambda **kw: fake_embed)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        image={"type": "image_url", "image_url": "https://example.com/photo.jpg"},
        top_k=5,
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.query == "[image_url]"
    assert fake_db.last_vector_call is not None
    assert fake_db.last_vector_call["embedding"] == [0.1, 0.2, 0.3]
    assert fake_db.last_call is None  # text search not called


def test_execute_single_query_image_base64(monkeypatch):
    """Image base64 queries should compute embedding and use vector search."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v2"},
                page_content="frame-b",
            ),
            0.88,
        )
    ]
    fake_db = _FakeVectorDb(docs)
    fake_embed = _FakeEmbeddingAPI()

    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module, "EmbeddingAPI", lambda **kw: fake_embed)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        image={"type": "image_base64", "image_base64": "aWFtYW5pbWFnZQ=="},
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.query == "[image_base64]"
    assert fake_db.last_vector_call is not None


def test_execute_single_query_image_with_where_filter(monkeypatch):
    """Image queries should apply where filters in fallback path."""
    docs = [
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-match", "tags": ["traffic"]},
                page_content="frame-keep",
            ),
            0.95,
        ),
        (
            types.SimpleNamespace(
                metadata={"video_id": "v-drop", "tags": ["night"]},
                page_content="frame-drop",
            ),
            0.9,
        ),
    ]
    fake_db = _FakeVectorDb(docs)
    fake_embed = _FakeEmbeddingAPI()

    monkeypatch.setattr(service_module, "get_vectordb", lambda: fake_db)
    monkeypatch.setattr(service_module, "EmbeddingAPI", lambda **kw: fake_embed)
    monkeypatch.setattr(service_module.settings, "RETRIEVER_BACKEND", "vdms")

    request = QueryRequest(
        image={"type": "image_url", "image_url": "https://example.com/photo.jpg"},
        where={"field": "video_id", "op": "eq", "value": "v-match"},
        top_k=2,
    )
    result = service_module.execute_single_query(request)

    assert result.count == 1
    assert result.items[0].metadata["video_id"] == "v-match"
