# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.observability import InMemoryTelemetry, RequestCompletedEvent
from ._api_contract_support import (
    RouterStub,
    build_router_config,
    chat_payload,
    make_test_app,
    make_test_client,
    read_sse_events,
)


pytestmark = pytest.mark.unit


def test_root_endpoint_advertises_router_api() -> None:
    client = make_test_client()

    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Inference Router API"
    assert data["status"] == "running"
    assert data["endpoints"] == {
        "health": "/health",
        "chat": "/v1/chat/completions",
        "models": "/v1/models",
        "metrics": "/v1/metrics",
        "config": "/v1/config",
        "routing": "/v1/routing",
        "providers": "/v1/providers",
        "policies": "/v1/policies",
        "strategies": "/v1/strategies",
        "audio_transcriptions": "/v1/audio/transcriptions",
        "audio_speech": "/v1/audio/speech",
        "embeddings": "/v1/embeddings",
        "rerank": "/v1/rerank",
        "ocr": "/v1/ocr",
    }


def test_health_endpoint_reports_configured_concurrency() -> None:
    client = make_test_client(max_concurrency=3)

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["router"] == "initialized"
    assert data["concurrency"] == {"active_requests": 0, "max_concurrency": 3}


def test_health_endpoint_reports_unlimited_concurrency() -> None:
    client = make_test_client(max_concurrency=0)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["concurrency"]["max_concurrency"] == "unlimited"


def test_health_detailed_reports_provider_statuses() -> None:
    router = RouterStub(
        provider_health={
            "provider-alpha": {"healthy": True},
            "provider-beta": {"healthy": False, "error": "timeout"},
        }
    )
    client = make_test_client(router=router)

    response = client.get("/health/detailed")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "providers": {
            "provider-alpha": {"healthy": True},
            "provider-beta": {"healthy": False, "error": "timeout"},
        },
    }


def test_models_endpoint_filters_disabled_providers_and_preserves_duplicate_models() -> None:
    client = make_test_client()

    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"

    provider_entries = [item for item in body["data"] if item["id"] != "auto"]
    assert len(provider_entries) == 3
    assert all(item["owned_by"] != "provider-disabled" for item in provider_entries)

    shared_entries = [item for item in provider_entries if item["id"] == "shared-model"]
    assert len(shared_entries) == 2
    assert {item["owned_by"] for item in shared_entries} == {"provider-alpha", "provider-beta"}

    auto_entry = next(item for item in body["data"] if item["id"] == "auto")
    assert auto_entry["owned_by"] == "inference-router"


def test_metrics_endpoint_returns_zeroed_shape_when_no_events_recorded() -> None:
    client = make_test_client(telemetry=InMemoryTelemetry())

    response = client.get("/v1/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "routing_stats": {"total_requests": 0, "by_provider": {}},
        "token_metrics": {
            "by_provider": {},
            "overall": {
                "total_tokens": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_requests": 0,
                "avg_tokens_per_request": 0.0,
            },
            # Token breakdown before/after router plugins (compressor effect).
            # Zeroed when no requests have flowed through yet.
            "before_router": {
                "system_prompt_tokens": 0,
                "tool_schema_tokens": 0,
                "context_tokens": 0,
                "overall_tokens": 0,
            },
            "after_router": {
                "system_prompt_tokens": 0,
                "tool_schema_tokens": 0,
                "context_tokens": 0,
                "overall_tokens": 0,
            },
        },
        "latency_metrics": {
            "by_provider": {},
            "overall": {
                "avg_latency_ms": 0.0,
                "avg_ttft_ms": 0.0,
                "avg_tpot_ms": 0.0,
                "ttft_count": 0,
                "tpot_count": 0,
            },
        },
    }


def test_metrics_endpoint_aggregates_provider_shares_and_latencies() -> None:
    telemetry = InMemoryTelemetry()
    telemetry.record_event(
        RequestCompletedEvent(
            provider_name="provider-alpha",
            final_model="model-a",
            models_used=["model-a"],
            total_input_tokens=10,
            total_output_tokens=5,
            total_latency_ms=100.0,
            ttft_ms=20.0,
            tpot_ms=5.0,
        )
    )
    telemetry.record_event(
        RequestCompletedEvent(
            provider_name="provider-beta",
            final_model="model-b",
            models_used=["model-b"],
            total_input_tokens=20,
            total_output_tokens=10,
            total_latency_ms=200.0,
            ttft_ms=40.0,
            tpot_ms=2.0,
        )
    )
    telemetry.record_event(
        RequestCompletedEvent(
            provider_name="provider-beta",
            final_model="model-b",
            models_used=["model-b"],
            total_input_tokens=5,
            total_output_tokens=5,
            total_latency_ms=100.0,
            ttft_ms=10.0,
            tpot_ms=1.0,
        )
    )
    client = make_test_client(telemetry=telemetry)

    response = client.get("/v1/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["routing_stats"] == {
        "total_requests": 3,
        "by_provider": {"provider-alpha/model-a": 1, "provider-beta/model-b": 2},
    }
    assert body["token_metrics"]["overall"] == {
        "total_tokens": 55,
        "total_input_tokens": 35,
        "total_output_tokens": 20,
        "total_requests": 3,
        "avg_tokens_per_request": 18.3,
    }
    assert body["token_metrics"]["by_provider"]["provider-alpha/model-a"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "request_count": 1,
        "avg_tokens_per_request": 15.0,
        "request_share": 0.333,
        "token_share": 0.273,
    }
    assert body["token_metrics"]["by_provider"]["provider-beta/model-b"] == {
        "input_tokens": 25,
        "output_tokens": 15,
        "total_tokens": 40,
        "request_count": 2,
        "avg_tokens_per_request": 20.0,
        "request_share": 0.667,
        "token_share": 0.727,
    }
    assert body["latency_metrics"]["overall"] == {
        "avg_latency_ms": 133.33,
        "avg_ttft_ms": 23.33,
        "avg_tpot_ms": 2.6667,
        "ttft_count": 3,
        "tpot_count": 3,
    }
    assert body["latency_metrics"]["by_provider"]["provider-beta/model-b"] == {
        "avg_latency_ms": 150.0,
        "avg_ttft_ms": 25.0,
        "avg_tpot_ms": 1.5,
        "ttft_count": 2,
        "tpot_count": 2,
    }


def test_metrics_reset_endpoint_clears_existing_events() -> None:
    telemetry = InMemoryTelemetry()
    telemetry.record_event(
        RequestCompletedEvent(
            provider_name="provider-alpha",
            final_model="model-a",
            models_used=["model-a"],
            total_input_tokens=1,
            total_output_tokens=1,
        )
    )
    client = make_test_client(telemetry=telemetry)

    reset_response = client.post("/v1/metrics/reset")
    metrics_response = client.get("/v1/metrics")

    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "success"
    assert metrics_response.json()["routing_stats"]["total_requests"] == 0


def test_chat_completions_rewrites_gateway_request_id_and_preserves_backend_fields() -> None:
    telemetry = InMemoryTelemetry()
    client = make_test_client(telemetry=telemetry)

    response = client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["id"] != "backend-response-id"
    assert body["model"] == "backend-model"
    assert body["choices"][0]["message"]["content"] == "stub completion"
    assert body["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
    }

    metrics = client.get("/v1/metrics").json()
    assert metrics["routing_stats"]["total_requests"] == 1
    assert metrics["routing_stats"]["by_provider"] == {"provider-alpha/backend-model": 1}


def test_streaming_chat_protocol_rewrites_chunk_ids_emits_usage_and_done() -> None:
    telemetry = InMemoryTelemetry()
    client = make_test_client(telemetry=telemetry)

    with client.stream("POST", "/v1/chat/completions", json=chat_payload(stream=True)) as response:
        assert response.status_code == 200
        events, done = read_sse_events(response)

    assert done == "data: [DONE]"
    gateway_ids = {event["id"] for event in events}
    assert len(gateway_ids) == 1
    gateway_id = next(iter(gateway_ids))
    assert gateway_id.startswith("chatcmpl-")
    assert gateway_id not in {"backend-chunk-id-1", "backend-chunk-id-2", "backend-chunk-id-3"}
    assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": "hello "}
    assert events[1]["choices"][0]["delta"] == {"content": "world"}
    assert events[1]["choices"][0]["finish_reason"] == "stop"
    assert events[2]["choices"] == []
    assert events[2]["usage"] == {
        "prompt_tokens": 9,
        "completion_tokens": 3,
        "total_tokens": 12,
    }

    metrics = client.get("/v1/metrics").json()
    assert metrics["routing_stats"]["total_requests"] == 1
    assert metrics["routing_stats"]["by_provider"] == {"provider-alpha/backend-stream-model": 1}