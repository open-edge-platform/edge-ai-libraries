# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import ProviderConfig, RouterConfig
from src.models import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamChunk,
    ChatCompletionUsage,
)
from src.observability import InMemoryTelemetry
from src.router.orchestrator import RouteInfo


class PluginManagerStub:
    def get_all_plugins_config(self) -> list[dict[str, Any]]:
        return []

    def get_plugin_by_name_and_node(self, _name: str, _node: str) -> None:
        return None


class RouterStub:
    def __init__(
        self,
        *,
        response: ChatCompletionResponse | None = None,
        response_factory: Callable[[ChatCompletionRequest], ChatCompletionResponse] | None = None,
        chunks: list[ChatCompletionStreamChunk] | None = None,
        chunk_factory: Callable[[ChatCompletionRequest], list[ChatCompletionStreamChunk]] | None = None,
        provider_health: dict[str, Any] | None = None,
        route_info: RouteInfo | None = None,
        chat_exception: Exception | None = None,
        stream_setup_exception: Exception | None = None,
        stream_iteration_exception: Exception | None = None,
        stream_started: threading.Event | None = None,
        stream_release: threading.Event | None = None,
    ) -> None:
        self.plugin_manager = PluginManagerStub()
        self.response = response or build_response()
        self.response_factory = response_factory
        self.chunks = chunks or build_stream_chunks()
        self.chunk_factory = chunk_factory
        self.provider_health = provider_health or {"provider-alpha": {"healthy": True}}
        self.route_info = route_info or RouteInfo(
            provider_name="provider-alpha",
            reason="stubbed",
            is_direct=False,
        )
        self.chat_exception = chat_exception
        self.stream_setup_exception = stream_setup_exception
        self.stream_iteration_exception = stream_iteration_exception
        self.stream_started = stream_started
        self.stream_release = stream_release
        self.chat_requests: list[ChatCompletionRequest] = []
        self.stream_requests: list[ChatCompletionRequest] = []

    async def chat(
        self, request: ChatCompletionRequest
    ) -> tuple[ChatCompletionResponse, RouteInfo]:
        self.chat_requests.append(request.model_copy(deep=True))
        if self.chat_exception is not None:
            raise self.chat_exception
        response = self.response_factory(request) if self.response_factory else self.response
        return response.model_copy(deep=True), self.route_info

    async def chat_stream(
        self, request: ChatCompletionRequest
    ) -> tuple[AsyncIterator[ChatCompletionStreamChunk], RouteInfo]:
        self.stream_requests.append(request.model_copy(deep=True))
        if self.stream_setup_exception is not None:
            raise self.stream_setup_exception

        chunks = self.chunk_factory(request) if self.chunk_factory else self.chunks

        async def _iter() -> AsyncIterator[ChatCompletionStreamChunk]:
            if self.stream_started is not None:
                self.stream_started.set()
            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0)
            if self.stream_release is not None:
                await asyncio.to_thread(self.stream_release.wait)
            if self.stream_iteration_exception is not None:
                raise self.stream_iteration_exception

        return _iter(), self.route_info

    async def health_check(self) -> dict[str, Any]:
        return self.provider_health


def build_router_config(
    *, providers: list[ProviderConfig] | None = None,
) -> RouterConfig:
    return RouterConfig(
        providers=providers or [
            ProviderConfig(name="provider-alpha", type="openai", model="shared-model", enabled=True),
            ProviderConfig(name="provider-disabled", type="openai", model="disabled-model", enabled=False),
            ProviderConfig(name="provider-beta", type="vllm", model="shared-model", enabled=True),
            ProviderConfig(name="provider-gamma", type="ollama", model="gamma-model", enabled=True),
        ]
    )


def build_response(
    *,
    content: str | None = "stub completion",
    model: str = "backend-model",
    prompt_tokens: int = 11,
    completion_tokens: int = 4,
    finish_reason: str = "stop",
    reasoning_content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="backend-response-id",
        created=1_717_000_000,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content,
                    reasoning_content=reasoning_content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def build_stream_chunks(
    *,
    model: str = "backend-stream-model",
    prompt_tokens: int = 9,
    completion_tokens: int = 3,
) -> list[ChatCompletionStreamChunk]:
    return [
        ChatCompletionStreamChunk(
            id="backend-chunk-id-1",
            created=1_717_000_001,
            model=model,
            choices=[
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "hello "},
                    "finish_reason": None,
                }
            ],
        ),
        ChatCompletionStreamChunk(
            id="backend-chunk-id-2",
            created=1_717_000_001,
            model=model,
            choices=[
                {
                    "index": 0,
                    "delta": {"content": "world"},
                    "finish_reason": "stop",
                }
            ],
        ),
        ChatCompletionStreamChunk(
            id="backend-chunk-id-3",
            created=1_717_000_001,
            model=model,
            choices=[],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        ),
    ]


def make_test_app(
    *,
    router: RouterStub | None = None,
    telemetry: InMemoryTelemetry | None = None,
    config: RouterConfig | None = None,
    config_path: Path | None = None,
    max_concurrency: int = 0,
):
    return create_app(
        router or RouterStub(),
        config or build_router_config(),
        telemetry if telemetry is not None else InMemoryTelemetry(),
        config_path=config_path,
        max_concurrency=max_concurrency,
    )


def make_test_client(
    *,
    router: RouterStub | None = None,
    telemetry: InMemoryTelemetry | None = None,
    config: RouterConfig | None = None,
    config_path: Path | None = None,
    max_concurrency: int = 0,
) -> TestClient:
    return TestClient(
        make_test_app(
            router=router,
            telemetry=telemetry,
            config=config,
            config_path=config_path,
            max_concurrency=max_concurrency,
        )
    )


def chat_payload(
    *,
    messages: list[dict[str, Any]] | None = None,
    model: str = "auto",
    stream: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages or [{"role": "user", "content": "hello"}],
        "stream": stream,
    }
    payload.update(extra)
    return payload


def read_sse_events(response) -> list[dict[str, Any]]:
    lines = [line for line in response.iter_lines() if line]
    return [json.loads(line[6:]) for line in lines[:-1]], lines[-1]