# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import queue
import threading

import pytest
from fastapi.testclient import TestClient

from src.exceptions import RoutingError
from src.observability import InMemoryTelemetry
from ._api_contract_support import (
    RouterStub,
    chat_payload,
    make_test_app,
    make_test_client,
    read_sse_events,
)


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        ({}, "messages"),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": [{"type": "audio", "text": "bad"}]}],
            },
            "content",
        ),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": [{"type": "text"}]}],
            },
            "content",
        ),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": [{"type": "image_url"}]}],
            },
            "content",
        ),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 3.5,
            },
            "temperature",
        ),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hello"}],
                "top_logprobs": 21,
            },
            "top_logprobs",
        ),
        (
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hello"}],
                "n": 0,
            },
            "n",
        ),
    ],
)
def test_invalid_chat_payloads_return_custom_422_error(
    payload: dict[str, Any],
    expected_field: str,
) -> None:
    client = make_test_client()

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["type"] == "RequestValidationError"
    assert body["error"]["body"] is None
    details = body["error"]["detail"]
    assert any(expected_field in str(item.get("loc", "")) for item in details)


def test_chat_endpoint_returns_503_when_router_not_initialized() -> None:
    app = make_test_app(router=RouterStub(), telemetry=InMemoryTelemetry())
    app.state.router = None
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 503
    assert response.json() == {"detail": "Router not initialized"}


def test_models_endpoint_returns_503_when_config_missing() -> None:
    app = make_test_app(router=RouterStub(), telemetry=InMemoryTelemetry())
    app.state.config = None
    client = TestClient(app)

    response = client.get("/v1/models")

    assert response.status_code == 503
    assert response.json() == {"detail": "Router not initialized"}


def test_metrics_endpoint_returns_503_when_telemetry_not_initialized() -> None:
    app = make_test_app(router=RouterStub(), telemetry=InMemoryTelemetry())
    app.state.telemetry = None
    client = TestClient(app)

    response = client.get("/v1/metrics")

    assert response.status_code == 503
    assert response.json() == {"detail": "Telemetry not initialized"}


def test_metrics_reset_returns_503_when_telemetry_not_initialized() -> None:
    app = make_test_app(router=RouterStub(), telemetry=InMemoryTelemetry())
    app.state.telemetry = None
    client = TestClient(app)

    response = client.post("/v1/metrics/reset")

    assert response.status_code == 503
    assert response.json() == {"detail": "Telemetry not initialized"}


def test_non_streaming_routing_error_returns_http_400() -> None:
    client = make_test_client(
        router=RouterStub(chat_exception=RoutingError("Unknown model: 'bad-model'")),
        telemetry=InMemoryTelemetry(),
    )

    response = client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown model: 'bad-model'"}


def test_non_streaming_internal_error_returns_http_500_with_request_id() -> None:
    client = make_test_client(
        router=RouterStub(chat_exception=RuntimeError("backend exploded")),
        telemetry=InMemoryTelemetry(),
    )

    response = client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail.startswith("Inference error (request_id=chatcmpl-")
    assert detail.endswith(")")


def test_streaming_routing_error_returns_sse_error_chunk_and_done() -> None:
    client = make_test_client(
        router=RouterStub(stream_setup_exception=RoutingError("Unknown model: 'bad-model'")),
        telemetry=InMemoryTelemetry(),
    )

    with client.stream("POST", "/v1/chat/completions", json=chat_payload(stream=True)) as response:
        assert response.status_code == 200
        events, done = read_sse_events(response)

    assert done == "data: [DONE]"
    chunk = events[0]
    assert chunk["id"].startswith("chatcmpl-")
    assert chunk["model"] == "error"
    assert chunk["choices"][0]["delta"]["content"] == "[ERROR] Routing failed"
    assert chunk["choices"][0]["finish_reason"] == "error"


def test_streaming_internal_error_returns_sse_error_chunk_and_done() -> None:
    client = make_test_client(
        router=RouterStub(stream_setup_exception=RuntimeError("stream backend exploded")),
        telemetry=InMemoryTelemetry(),
    )

    with client.stream("POST", "/v1/chat/completions", json=chat_payload(stream=True)) as response:
        assert response.status_code == 200
        events, done = read_sse_events(response)

    assert done == "data: [DONE]"
    chunk = events[0]
    assert chunk["id"].startswith("chatcmpl-")
    assert chunk["model"] == "error"
    assert chunk["choices"][0]["delta"]["content"] == "[ERROR] Internal server error"
    assert chunk["choices"][0]["finish_reason"] == "error"


def test_concurrency_limit_returns_429_while_streaming_request_is_in_flight() -> None:
    started = threading.Event()
    release = threading.Event()
    router = RouterStub(stream_started=started, stream_release=release)
    app = make_test_app(router=router, telemetry=InMemoryTelemetry(), max_concurrency=1)

    failure_queue: queue.Queue[BaseException] = queue.Queue()

    def _hold_stream_open() -> None:
        try:
            with TestClient(app) as blocking_client:
                with blocking_client.stream(
                    "POST", "/v1/chat/completions", json=chat_payload(stream=True)
                ) as response:
                    if response.status_code != 200:
                        raise AssertionError(f"Unexpected status: {response.status_code}")
                    next(response.iter_lines())
                    release.wait(timeout=5)
        except BaseException as exc:  # pragma: no cover - propagated below
            failure_queue.put(exc)

    worker = threading.Thread(target=_hold_stream_open)
    worker.start()
    try:
        assert started.wait(timeout=5), "Streaming request never became active"

        with TestClient(app) as competing_client:
            response = competing_client.post("/v1/chat/completions", json=chat_payload())

        assert response.status_code == 429
        assert response.json() == {
            "detail": "Server busy: 1/1 concurrent requests. Retry later."
        }
    finally:
        release.set()
        worker.join(timeout=5)

    if not failure_queue.empty():
        raise failure_queue.get()