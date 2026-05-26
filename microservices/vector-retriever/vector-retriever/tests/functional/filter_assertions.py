# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared assertion helpers for backend functional matrix tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import requests

from tests.functional.data import FILTER_CASES


def _execute_query(base_url: str, payload: dict) -> dict[str, Any]:
    """Execute one query request and return the full result block."""
    response = requests.post(f"{base_url}/query", json=[payload], timeout=60)
    assert response.status_code == 200, response.text

    body = response.json()
    assert not body["errors"], body["errors"]
    return body["results"][0]


def execute_filter_case(base_url: str, backend: str, case: dict) -> None:
    """Assert a single filter case against a live backend."""
    payload = {
        "query_id": case["name"],
        "query": "fixture retrieval anchor",
        "top_k": 100,
        "explain_filters": True,
    }
    payload.update(deepcopy(case["payload"]))

    result = _execute_query(base_url, payload)
    matched_ids = {item["metadata"]["video_id"] for item in result["items"]}
    assert matched_ids == case["expected_ids"], (
        f"backend={backend} case={case['name']} "
        f"expected={sorted(case['expected_ids'])} got={sorted(matched_ids)}"
    )


def assert_filter_matrix(backend_stack: dict) -> None:
    """Assert full filter parity matrix for one backend stack (single test node)."""
    base_url = backend_stack["base_url"]
    backend = backend_stack["backend"]
    for case in FILTER_CASES:
        execute_filter_case(base_url, backend, case)


def assert_ready(base_url: str) -> None:
    """Assert the /ready endpoint reports status=ready."""
    response = requests.get(f"{base_url}/ready", timeout=15)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("status") == "ready", f"unexpected /ready payload: {payload}"


def assert_filter_capabilities(base_url: str, backend: str) -> None:
    """Assert /capabilities/filters returns active backend and all supported backends."""
    response = requests.get(f"{base_url}/capabilities/filters", timeout=15)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("active_backend") == backend, (
        f"expected active_backend={backend!r}, got {payload.get('active_backend')!r}"
    )
    names = {b["backend"] for b in payload.get("backends", [])}
    assert backend in names, f"active backend {backend!r} missing from capabilities list: {names}"


def assert_batch_query(base_url: str) -> None:
    """Assert that two queries in a single batch both return results."""
    payload = [
        {
            "query_id": "batch-q1",
            "query": "fixture retrieval anchor",
            "where": {"field": "video_id", "op": "eq", "value": "vid-001"},
            "top_k": 10,
        },
        {
            "query_id": "batch-q2",
            "query": "fixture retrieval anchor",
            "where": {"field": "video_id", "op": "eq", "value": "vid-002"},
            "top_k": 10,
        },
    ]
    response = requests.post(f"{base_url}/query", json=payload, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    assert len(body["results"]) == 2, f"expected 2 results, got {len(body['results'])}"
    ids_q1 = {item["metadata"]["video_id"] for item in body["results"][0]["items"]}
    ids_q2 = {item["metadata"]["video_id"] for item in body["results"][1]["items"]}
    assert ids_q1 == {"vid-001"}, f"batch q1: expected {{vid-001}}, got {ids_q1}"
    assert ids_q2 == {"vid-002"}, f"batch q2: expected {{vid-002}}, got {ids_q2}"


def assert_explain_filters(base_url: str) -> None:
    """Assert explain_filters=True includes compiled_backend_filter in the response."""
    payload = [
        {
            "query_id": "explain-test",
            "query": "fixture retrieval anchor",
            "where": {"field": "frame_number", "op": "gte", "value": 50},
            "top_k": 10,
            "explain_filters": True,
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    applied = body["results"][0]["applied_filters"]
    assert applied.get("compiled_backend_filter") is not None, (
        "explain_filters=True should return compiled_backend_filter"
    )


def assert_top_k_limiting(base_url: str) -> None:
    """Assert that top_k=2 returns exactly 2 items when more matches exist."""
    payload = [
        {
            "query_id": "topk-limit",
            "query": "fixture retrieval anchor",
            "top_k": 2,
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    result = body["results"][0]
    assert result["count"] == 2, f"expected count=2 for top_k=2, got {result['count']}"
    assert len(result["items"]) == 2, f"expected 2 items, got {len(result['items'])}"


def assert_image_query(base_url: str) -> None:
    """Assert that image queries are accepted and return results via vector search.

    Uses a small, deterministic 1×1 red PNG encoded in base64 so the test
    works without network access.  The image embedding is generated by the
    same multimodal embedding service backing the stack, so we cannot predict
    exact match IDs — we only assert the API shape is correct and at least
    one result is returned.
    """
    # 1×1 red PNG (87 bytes) — self-contained, no network dependency.
    RED_1X1_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
        "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
    )

    # --- image_base64 query ---
    payload_b64 = [
        {
            "query_id": "image-base64-test",
            "image": {"type": "image_base64", "image_base64": RED_1X1_PNG_B64},
            "top_k": 5,
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload_b64, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    assert len(body["results"]) == 1, f"expected 1 result block, got {len(body['results'])}"
    result = body["results"][0]
    assert result["query_id"] == "image-base64-test"
    assert result["query"] == "[image_base64]", f"unexpected query label: {result['query']}"
    assert result["count"] >= 1, f"expected at least 1 match for image query, got {result['count']}"

    # --- image query with where filter ---
    payload_filtered = [
        {
            "query_id": "image-filtered-test",
            "image": {"type": "image_base64", "image_base64": RED_1X1_PNG_B64},
            "where": {"field": "video_id", "op": "eq", "value": "vid-001"},
            "top_k": 10,
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload_filtered, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    result = body["results"][0]
    matched_ids = {item["metadata"]["video_id"] for item in result["items"]}
    assert matched_ids <= {"vid-001"}, f"filter should restrict to vid-001, got {matched_ids}"

    # --- mutual exclusivity: both query and image should fail ---
    payload_invalid = [
        {
            "query_id": "invalid-both",
            "query": "person near car",
            "image": {"type": "image_base64", "image_base64": RED_1X1_PNG_B64},
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload_invalid, timeout=60)
    assert response.status_code == 422, (
        f"expected 422 for mutual exclusivity violation, got {response.status_code}"
    )
