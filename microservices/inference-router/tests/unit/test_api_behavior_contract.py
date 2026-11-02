# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.observability import InMemoryTelemetry
from src.router.orchestrator import RouteInfo
from ._api_contract_support import (
    RouterStub,
    build_response,
    build_stream_chunks,
    chat_payload,
    make_test_client,
    read_sse_events,
)


pytestmark = pytest.mark.unit


def test_request_messages_are_forwarded_to_router_unchanged() -> None:
    router = RouterStub()
    client = make_test_client(router=router)
    messages = [
        {"role": "system", "content": "Follow the latest instruction exactly."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Part 1: keep context. "},
                {"type": "text", "text": "Part 2: reply with TOKEN_CTX only."},
            ],
        },
    ]

    response = client.post("/v1/chat/completions", json=chat_payload(messages=messages))

    assert response.status_code == 200
    assert len(router.chat_requests) == 1
    captured = router.chat_requests[0]
    assert [message.role.value for message in captured.messages] == ["system", "user"]
    assert captured.messages[1].content == messages[1]["content"]


def test_multi_turn_conversation_is_forwarded_with_order_preserved() -> None:
    router = RouterStub(
        response_factory=lambda request: build_response(
            content=str(request.messages[-1].content),
            model="backend-memory-model",
        )
    )
    client = make_test_client(router=router)
    messages = [
        {"role": "system", "content": "You are a memory checker."},
        {"role": "user", "content": "Remember this code: BLUE-OTTER-17."},
        {"role": "assistant", "content": "I will remember BLUE-OTTER-17."},
        {"role": "user", "content": "What is the code? Reply with the code only."},
    ]

    response = client.post("/v1/chat/completions", json=chat_payload(messages=messages))

    assert response.status_code == 200
    assert [message.role.value for message in router.chat_requests[0].messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert response.json()["choices"][0]["message"]["content"] == "What is the code? Reply with the code only."


def test_tool_call_response_is_forwarded_unchanged() -> None:
    tool_calls = [
        {
            "id": "call_weather_1",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "San Francisco"}',
            },
        }
    ]
    router = RouterStub(
        response=build_response(
            content=None,
            finish_reason="tool_calls",
            tool_calls=tool_calls,
            model="backend-tools-model",
        )
    )
    client = make_test_client(router=router)

    response = client.post(
        "/v1/chat/completions",
        json=chat_payload(
            messages=[{"role": "user", "content": "What's the weather in San Francisco?"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the current weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                            "required": ["location"],
                        },
                    },
                }
            ],
            tool_choice="auto",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["finish_reason"] == "tool_calls"
    assert body["choices"][0]["message"]["content"] is None
    assert body["choices"][0]["message"]["tool_calls"] == tool_calls


def test_reasoning_content_is_forwarded_unchanged() -> None:
    router = RouterStub(
        response=build_response(
            content="Final answer.",
            reasoning_content="Hidden reasoning fragment.",
            model="backend-reasoning-model",
        )
    )
    client = make_test_client(router=router)

    response = client.post("/v1/chat/completions", json=chat_payload())

    assert response.status_code == 200
    message = response.json()["choices"][0]["message"]
    assert message["content"] == "Final answer."
    assert message["reasoning_content"] == "Hidden reasoning fragment."


def test_streaming_tool_call_deltas_are_forwarded_verbatim() -> None:
    router = RouterStub(
        chunks=[
            build_stream_chunks()[0],
            build_stream_chunks()[1].model_copy(
                update={
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_tool_1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_weather",
                                            "arguments": '{"location": ',
                                        },
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ]
                }
            ),
            build_stream_chunks()[1].model_copy(
                update={
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": '"San Francisco"}'},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ),
        ],
        route_info=RouteInfo(provider_name="provider-alpha", reason="stubbed", is_direct=False),
    )
    client = make_test_client(router=router)

    with client.stream("POST", "/v1/chat/completions", json=chat_payload(stream=True)) as response:
        assert response.status_code == 200
        events, done = read_sse_events(response)

    assert done == "data: [DONE]"
    assert events[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert events[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '{"location": '
    assert events[2]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '"San Francisco"}'
    assert events[2]["choices"][0]["finish_reason"] == "tool_calls"


def test_parallel_in_process_requests_remain_isolated() -> None:
    router = RouterStub(
        response_factory=lambda request: build_response(
            content=str(request.messages[-1].content),
            model="backend-parallel-model",
        )
    )
    telemetry = InMemoryTelemetry()
    tokens = ["TOKEN_PAR_A", "TOKEN_PAR_B", "TOKEN_PAR_C"]

    def send(token: str) -> dict:
        with make_test_client(router=router, telemetry=telemetry) as client:
            response = client.post(
                "/v1/chat/completions",
                json=chat_payload(messages=[{"role": "user", "content": token}]),
            )
            return response.json()

    with ThreadPoolExecutor(max_workers=len(tokens)) as executor:
        responses = list(executor.map(send, tokens))

    for token, response in zip(tokens, responses):
        assert response["choices"][0]["message"]["content"] == token

    assert len(router.chat_requests) == len(tokens)


def test_direct_model_selection_records_metrics_with_provider_bucket() -> None:
    router = RouterStub(
        route_info=RouteInfo(
            provider_name="provider-alpha",
            reason="direct_model_selection",
            is_direct=True,
        ),
        response=build_response(content="TOKEN_FORCE_PROVIDER", model="shared-model"),
    )
    telemetry = InMemoryTelemetry()
    client = make_test_client(router=router, telemetry=telemetry)

    response = client.post(
        "/v1/chat/completions",
        json=chat_payload(model="shared-model", messages=[{"role": "user", "content": "TOKEN_FORCE_PROVIDER"}]),
    )
    metrics = client.get("/v1/metrics")

    assert response.status_code == 200
    assert metrics.status_code == 200
    assert metrics.json()["routing_stats"]["by_provider"] == {"provider-alpha/shared-model": 1}