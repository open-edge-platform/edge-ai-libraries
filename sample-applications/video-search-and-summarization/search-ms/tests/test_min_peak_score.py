# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the minimum peak score filter applied at retrieval time."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import server
from src.utils.retriever_delegate import RetrievedDocument, _build_retriever_payload


def _payload_request(**overrides):
    return server.QueryRequest(query_id="q1", query="person walking", **overrides)


def test_payload_includes_min_score_when_positive():
    item = _build_retriever_payload(_payload_request(), 100, None, 0.25)[0]
    assert item["min_score"] == 0.25


@pytest.mark.parametrize("min_score", [None, 0, 0.0])
def test_payload_omits_min_score_when_disabled(min_score):
    item = _build_retriever_payload(_payload_request(), 100, None, min_score)[0]
    assert "min_score" not in item


def test_request_accepts_camel_case_alias():
    assert server.QueryRequest(
        query_id="q1", query="x", minPeakScore=0.123
    ).min_peak_score == pytest.approx(0.123)


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_request_rejects_out_of_range(value):
    with pytest.raises(ValidationError):
        server.QueryRequest(query_id="q1", query="x", min_peak_score=value)


def test_resolve_falls_back_to_setting(monkeypatch):
    monkeypatch.setattr(server.settings, "SEARCH_MIN_PEAK_SCORE", 0.3)
    assert server.resolve_min_peak_score(_payload_request()) == pytest.approx(0.3)
    assert server.resolve_min_peak_score(
        _payload_request(min_peak_score=0)
    ) == 0.0


def _frame(video_id, timestamp, score):
    doc = RetrievedDocument(
        "frame",
        {"video_id": video_id, "timestamp": timestamp, "video_url": f"/b/{video_id}/v.mp4"},
    )
    return doc, score


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server.settings, "RETRIEVER_ENDPOINT", "http://retriever/query")
    monkeypatch.setattr(server.settings, "SEARCH_MIN_PEAK_SCORE", 0.0)
    calls = []

    async def fake_retrieve(query_request, initial_k, time_range=None, min_score=None):
        calls.append(min_score)
        # Simulates an older retriever that ignores min_score.
        return [_frame("v1", 1, 0.9), _frame("v2", 50, 0.15), _frame("v3", 90, -0.05)]

    monkeypatch.setattr(server, "retrieve_frames_via_service", fake_retrieve)
    return TestClient(server.app), calls


def _video_ids(response):
    return {hit["metadata"]["video_id"] for hit in response.json()["results"][0]["results"]}


def test_query_forwards_and_enforces_min_peak_score(client):
    test_client, calls = client
    response = test_client.post(
        "/query", json=[{"query_id": "q1", "query": "x", "minPeakScore": 0.2}]
    )
    assert response.status_code == 200
    assert calls == [0.2]
    assert _video_ids(response) == {"v1"}
    stats = response.json()["results"][0]["aggregation_stats"]
    assert stats["min_peak_score"] == 0.2


def test_query_default_zero_keeps_every_frame(client):
    test_client, calls = client
    response = test_client.post("/query", json=[{"query_id": "q1", "query": "x"}])
    assert response.status_code == 200
    assert calls == [0.0]
    assert _video_ids(response) == {"v1", "v2", "v3"}


def test_query_uses_env_default_when_request_omits_it(client, monkeypatch):
    test_client, calls = client
    monkeypatch.setattr(server.settings, "SEARCH_MIN_PEAK_SCORE", 0.1)
    response = test_client.post("/query", json=[{"query_id": "q1", "query": "x"}])
    assert calls == [0.1]
    assert _video_ids(response) == {"v1", "v2"}
