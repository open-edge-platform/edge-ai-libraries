# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

from fastapi.testclient import TestClient

import src.common.middleware as middleware_module
import src.main as main_module
from src.common.schema import (
    AppliedFilters,
    FilterCapabilitiesResponse,
    QueryResultBlock,
    QueryResultItem,
)
from src.main import app


def test_filter_capabilities_endpoint_returns_payload(monkeypatch):
    """Capabilities endpoint should return advertised backend metadata."""
    expected = FilterCapabilitiesResponse(
        active_backend="vdms",
        backends=[
            {
                "backend": "milvus",
                "top_level_fields": ["where"],
                "logical_blocks": ["all", "any", "not"],
                "supported_operators": ["eq", "between"],
                "pushdown_operators": ["eq"],
                "known_fields": {"created_at": "datetime"},
                "max_where_depth": 5,
                "max_where_clauses": 50,
                "max_where_list_size": 100,
            }
        ],
    )

    monkeypatch.setattr(
        main_module,
        "get_filter_capabilities",
        lambda backend_name=None: expected,
    )

    client = TestClient(app)
    response = client.get("/capabilities/filters?backend=milvus")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_backend"] == "vdms"
    assert payload["backends"][0]["backend"] == "milvus"
    assert payload["backends"][0]["top_level_fields"] == ["where"]


def test_filter_capabilities_endpoint_returns_400_for_unknown_backend(monkeypatch):
    """Capabilities endpoint should map unsupported backend errors to 400."""

    def _raise_not_implemented(backend_name=None):
        raise NotImplementedError(f"Unsupported retriever backend: {backend_name}")

    monkeypatch.setattr(main_module, "get_filter_capabilities", _raise_not_implemented)

    client = TestClient(app)
    response = client.get("/capabilities/filters?backend=unknown")

    assert response.status_code == 400
    assert "Unsupported retriever backend" in response.json()["detail"]


def test_query_endpoint_rejects_empty_batch():
    """Query endpoint should reject empty request payloads."""
    client = TestClient(app)
    response = client.post("/query", json=[])

    assert response.status_code == 400
    assert response.json()["detail"] == "Request body must contain at least one query"


def test_query_endpoint_returns_batch_payload(monkeypatch):
    """Query endpoint should serialize batch executor outputs."""

    async def _fake_execute_batch(_requests):
        return (
            [
                QueryResultBlock(
                    query_id="q-1",
                    query="person near car",
                    count=1,
                    items=[
                        QueryResultItem(
                            score=0.88,
                            metadata={"video_id": "v1"},
                            page_content="frame-1",
                        )
                    ],
                    applied_filters=AppliedFilters(
                        normalized_where={"field": "video_id", "op": "eq", "value": "v1"},
                        compiled_backend_filter={"video_id": ["==", "v1"]},
                        dropped_or_rewritten_clauses=["tags -> where(field='tags', op='contains_any', value=<tags>)"],
                    ),
                )
            ],
            [],
        )

    monkeypatch.setattr(main_module, "execute_batch", _fake_execute_batch)

    client = TestClient(app)
    response = client.post(
        "/query",
        json=[{"query_id": "q-1", "query": "person near car", "explain_filters": True}],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["query_id"] == "q-1"
    assert payload["results"][0]["applied_filters"]["compiled_backend_filter"] == {
        "video_id": ["==", "v1"]
    }
    assert payload["errors"] == []


def test_query_endpoint_uses_single_request_start_log(caplog, monkeypatch):
    """Query requests should log one shared request-entry line plus completion details."""

    async def _fake_execute_batch(_requests):
        return ([], [])

    monkeypatch.setattr(main_module, "execute_batch", _fake_execute_batch)

    client = TestClient(app)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/query",
            json=[{"query_id": "q-1", "query": "person near car"}],
            headers={"x-request-id": "req-456"},
        )

    assert response.status_code == 200
    assert "Received request request_id=req-456 method=POST path=/query" in caplog.text
    assert "Received batch query request_id=req-456" not in caplog.text
    assert (
        "Completed batch query request_id=req-456 query_count=1 result_count=0 error_count=0"
        in caplog.text
    )


def test_request_id_middleware_logs_request_entry(caplog):
    """Middleware should log request method/path when a request arrives."""
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger=middleware_module.logger.name):
        response = client.get("/health", headers={"x-request-id": "req-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert "Received request request_id=req-123 method=GET path=/health" in caplog.text
