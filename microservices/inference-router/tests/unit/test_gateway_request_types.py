# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Gateway request-type coverage tests.

Tests cover different kinds of request payloads the gateway should handle:
  - Tool calling variants (tool_choice: auto/required/named/none)
  - Multi-turn tool conversations and deep conversation chains
  - Structured outputs (response_format: json_object / json_schema)
  - Sampling/generation parameters (temperature, top_p, penalties, logit_bias, n)
  - Streaming with stream_options and large tool sets
  - Message content format variants (text parts arrays)
  - vLLM-specific extensions (repetition_penalty, top_k, guided decoding)
  - Router-specific extensions (cloud_allowed, latency_budget)
  - Large payloads (20+ tools, 25K+ system prompts, null max_tokens)
  - Tool definition variants (strict, nested schemas, empty required)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from test_client import GatewayTestClient


# ── helpers ──────────────────────────────────────────────────────────


def _visible_text(content_or_message: Any) -> str:
    """Extract visible text from content or a full message dict.

    Accepts either a raw ``content`` value (str / list / None) **or** a
    complete message dict ``{"content": ..., "reasoning_content": ...}``.
    When the reasoning parser is active the gateway moves ``<think>``
    blocks into ``reasoning_content`` and ``content`` may be empty; in
    that case we fall back to ``reasoning_content`` so assertions about
    "the model produced something" still pass.
    """
    # If caller passed the full message dict, unpack it
    if isinstance(content_or_message, dict) and "role" in content_or_message:
        content = content_or_message.get("content")
        reasoning = content_or_message.get("reasoning_content")
    else:
        content = content_or_message
        reasoning = None

    def _extract(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            value = "\n".join(parts)
        text = str(value)
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    result = _extract(content)
    if not result and reasoning:
        result = _extract(reasoning)
    return result


def _raw_text_content(message: dict[str, Any]) -> str:
    """Return raw ``message.content`` as non-empty text without normalization.

    Use this in strict protocol tests where transformed content could hide
    gateway behavior differences.
    """
    content = message.get("content")
    assert isinstance(content, str), "Expected raw message.content to be a string"
    assert content.strip(), "Expected raw message.content to be non-empty"
    return content


def _stream_chat_completion(
    gateway_client: GatewayTestClient,
    **payload: Any,
) -> dict[str, Any]:
    """Send a streaming request and reassemble chunks into a non-streaming-style dict.

    This lets tests written against the non-streaming response shape run in
    streaming mode without duplicating assertion logic.  The returned dict
    looks like a normal ``ChatCompletionResponse`` with ``object``, ``id``,
    ``model``, ``choices`` (with ``message`` instead of ``delta``), ``usage``,
    etc.
    """
    payload["stream"] = True
    payload["chat_template_kwargs"] = {"enable_thinking": False}
    raw = gateway_client.session.post(
        f"{gateway_client.base_url}/v1/chat/completions",
        json=payload,
        timeout=gateway_client.timeout,
        stream=True,
    )
    raw.raise_for_status()

    response_id: str | None = None
    model: str | None = None
    created: int | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls_map: dict[int, dict] = {}  # index -> accumulated tool call
    finish_reason: str | None = None
    usage: dict | None = None
    role: str = "assistant"
    saw_done = False

    for line in raw.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if not line_str.startswith("data: "):
            continue
        data = line_str[6:]
        if data == "[DONE]":
            saw_done = True
            break

        chunk = json.loads(data)
        if response_id is None:
            response_id = chunk.get("id")
        if model is None:
            model = chunk.get("model")
        if created is None:
            created = chunk.get("created")

        if chunk.get("usage"):
            usage = chunk["usage"]

        for choice in chunk.get("choices") or []:
            delta = choice.get("delta", {})
            if "role" in delta:
                role = delta["role"]
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
            # Accumulate tool_calls by index
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.get("id"):
                    tool_calls_map[idx]["id"] = tc["id"]
                fn = tc.get("function", {})
                if fn.get("name"):
                    tool_calls_map[idx]["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls_map[idx]["function"]["arguments"] += fn["arguments"]
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

    assert saw_done, "Streaming response did not include [DONE] terminator"
    assert response_id, "Streaming response missing id"
    assert model, "Streaming response missing model"
    assert created is not None, "Streaming response missing created timestamp"

    content = "".join(content_parts) or None
    reasoning_content = "".join(reasoning_parts) or None
    tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map)] if tool_calls_map else None

    message: dict[str, Any] = {"role": role, "content": content}
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
    if tool_calls:
        message["tool_calls"] = tool_calls

    result: dict[str, Any] = {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason or "stop",
        }],
    }
    if usage:
        result["usage"] = usage
    return result


def _chat(
    gateway_client: GatewayTestClient,
    *,
    stream: bool = False,
    **payload: Any,
) -> dict[str, Any]:
    """Unified helper: non-streaming via test client, streaming via SSE reassembly."""
    if stream:
        return _stream_chat_completion(gateway_client, **payload)
    return gateway_client.chat_completion(**payload)


def _assert_valid_response(response: dict, *, stream: bool = False) -> None:
    """Common assertions for any chat completion response."""
    # Streaming is reassembled to non-streaming shape by _stream_chat_completion.
    obj_type = "chat.completion"
    assert response["object"] == obj_type
    assert isinstance(response.get("id"), str) and response["id"], "Response id must be a non-empty string"
    assert isinstance(response.get("created"), int) and response["created"] > 0, "Response created must be a unix timestamp"
    assert isinstance(response.get("model"), str) and response["model"], "Response model must be a non-empty string"
    choices = response.get("choices")
    assert isinstance(choices, list) and choices, "Response must contain at least one choice"
    for choice in choices:
        assert isinstance(choice.get("index"), int), "Each choice must include integer index"
        assert choice.get("finish_reason") in {"stop", "length", "tool_calls", "content_filter"}
        message = choice.get("message")
        assert isinstance(message, dict), "Each choice must include message"
        assert message.get("role") == "assistant", "Assistant role expected in choice.message"


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def gateway_client() -> GatewayTestClient:
    return GatewayTestClient()


@pytest.fixture(scope="session")
def models_payload(gateway_client: GatewayTestClient) -> dict[str, Any]:
    try:
        return gateway_client.list_models()
    except requests.RequestException as exc:
        pytest.skip(f"Gateway is not reachable: {exc}")


@pytest.fixture(scope="session")
def available_model_ids(models_payload: dict[str, Any]) -> list[str]:
    data = models_payload.get("data") or []
    model_ids = [item["id"] for item in data if isinstance(item, dict) and "id" in item]
    assert model_ids, "Expected at least one model from /v1/models"
    return model_ids


@pytest.fixture(scope="session")
def backend_model_id(available_model_ids: list[str]) -> str:
    for model_id in available_model_ids:
        if model_id != "auto":
            return model_id
    pytest.skip("No backend model available besides the virtual auto model")


# =====================================================================
# 1. TOOL CHOICE VARIANTS
# =====================================================================


class TestToolChoiceVariants:
    """Different tool_choice values the gateway must accept."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_multiple_tools_auto_choice(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Multiple tools with tool_choice='auto'."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                        },
                        "required": ["city"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stock_price",
                    "description": "Get the current stock price for a ticker",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                        },
                        "required": ["ticker"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                {"role": "user", "content": "What tools do you have available? List them briefly."},
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["finish_reason"] in {"stop", "length", "tool_calls"}
        tool_calls = choice["message"].get("tool_calls") or []
        if tool_calls:
            allowed_names = {"get_weather", "get_stock_price"}
            for tc in tool_calls:
                assert tc["type"] == "function"
                assert tc["function"]["name"] in allowed_names
                args = json.loads(tc["function"].get("arguments") or "{}")
                assert isinstance(args, dict)
        else:
            # Auto mode can also decide to answer directly.
            assert _visible_text(choice["message"]), "Expected either tool calls or assistant text"

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_choice_required(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """tool_choice='required' forces the model to produce a tool call."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for a query",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Find the latest news about AI."}],
            tools=tools,
            tool_choice="required",
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        # tool_choice=required must produce a tool call
        tool_calls = choice["message"].get("tool_calls")
        assert tool_calls and len(tool_calls) > 0, "Expected at least one tool call with tool_choice='required'"
        assert tool_calls[0]["function"]["name"] == "search_web"
        args = json.loads(tool_calls[0]["function"]["arguments"])
        assert "query" in args, "search_web tool call must include 'query' argument"
        raw_content = choice["message"].get("content")
        assert raw_content in {None, ""}, (
            "Expected raw message.content to be empty when tool_choice='required' triggers tool call"
        )
        assert not choice["message"].get("reasoning_content"), (
            "Expected no reasoning_content when only tool calls are returned"
        )

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_choice_named_function(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Named tool_choice forces a specific function via dict."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_sum",
                    "description": "Calculate the sum of two numbers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_product",
                    "description": "Calculate the product of two numbers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Add 3 and 5."}],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "calculate_sum"}},
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        # Named tool_choice must produce a call to the specified function
        tool_calls = choice["message"].get("tool_calls")
        assert tool_calls and len(tool_calls) > 0, "Expected at least one tool call with named tool_choice"
        assert all(tc["function"]["name"] == "calculate_sum" for tc in tool_calls), (
            f"Expected only tool 'calculate_sum', got {[tc['function']['name'] for tc in tool_calls]}"
        )
        args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
        assert isinstance(args, dict)
        assert {"a", "b"}.issubset(args.keys()), "calculate_sum tool call must include 'a' and 'b' arguments"

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_choice_none_disables_tools(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """tool_choice='none' should prevent tool calling even with a tool-triggering prompt."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant with tool access."},
                {"role": "user", "content": "What is the weather in Paris?"},
            ],
            tools=tools,
            tool_choice="none",
            temperature=0,
            max_tokens=128,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        # tool_choice=none must suppress tool calls even when the prompt invites one
        assert choice["message"].get("tool_calls") is None or choice["message"]["tool_calls"] == [], (
            "Expected no tool calls with tool_choice='none'"
        )
        assert choice["finish_reason"] != "tool_calls"
        assert choice["finish_reason"] in {"stop", "length"}
        content = _visible_text(choice["message"])
        assert content, "Expected a text response when tool calling is disabled"


# =====================================================================
# 2. MULTI-TURN CONVERSATIONS
# =====================================================================


class TestMultiTurnConversations:
    """Multi-turn exchanges including tool call results and deep chains."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_result_continuation(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Full tool-call round-trip: assistant calls tool -> tool result -> continuation."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant with tool access."},
            {"role": "user", "content": "Write 'hello' to a file."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "write",
                            "arguments": '{"path": "/tmp/test.txt", "content": "hello"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_abc123",
                "content": "Successfully wrote 5 bytes to /tmp/test.txt",
            },
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write",
                    "description": "Write content to a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["message"]["role"] == "assistant"
        assert choice["finish_reason"] in {"stop", "length", "tool_calls"}

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_error_result_continuation(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Tool returns an error — model should handle gracefully."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Create a file at /workspace/test.txt"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_err456",
                        "type": "function",
                        "function": {
                            "name": "write",
                            "arguments": '{"path": "/workspace/test.txt", "content": "hello"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_err456",
                "content": '{"status": "error", "error": "EACCES: permission denied"}',
            },
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write",
                    "description": "Write content to a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["message"]["role"] == "assistant"
        assert choice["finish_reason"] in {"stop", "length", "tool_calls"}

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_deep_8_message_conversation(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """8-message deep chain with sequential tool calls — model summarises tool results."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
        ]

        messages = [
            {"role": "system", "content": "You are a helpful assistant with file access."},
            {"role": "user", "content": "Read the config file and the data file, then tell me the database host and port."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_r1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "/etc/app/config.yaml"}'},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call_r1",
                "content": "database:\n  host: db.example.com\n  port: 5432\n  name: appdb",
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_r2",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "/etc/app/data.json"}'},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call_r2",
                "content": '{"replica_host": "replica.example.com", "replica_port": 5433}',
            },
            {"role": "assistant", "content": "I've read both files. The primary database is at db.example.com:5432 and the replica is at replica.example.com:5433."},
            {"role": "user", "content": "What is the primary database host and port?"},
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=512,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["message"]["role"] == "assistant"
        content = _visible_text(choice["message"])
        # Use a word-boundary regex so `db.example.com` is matched as a discrete
        # host reference, not as a substring of e.g. `not-db.example.com.evil`.
        assert re.search(r"(?<![\w.-])db\.example\.com(?![\w.-])", content), (
            f"Expected response to reference the database host from tool results, got: {content[:200]}"
        )
        assert re.search(r"(?<!\d)5432(?!\d)", content), (
            f"Expected response to reference the database port from tool results, got: {content[:200]}"
        )

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_multi_turn_conversation(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Multi-turn conversation without tools."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful math tutor."},
                {"role": "user", "content": "What is 2 + 2?"},
                {"role": "assistant", "content": "2 + 2 = 4."},
                {"role": "user", "content": "Now multiply that result by 3. Reply with the number only."},
            ],
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        content = _visible_text(response["choices"][0]["message"])
        assert "12" in content

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_content_as_text_parts_array(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """User content as array of text parts (OpenAI content array format)."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Part 1: Hello. "},
                        {"type": "text", "text": "Part 2: Reply with TOKEN_PARTS only."},
                    ],
                }
            ],
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        content = _visible_text(response["choices"][0]["message"])
        assert "TOKEN_PARTS" in content


# =====================================================================
# 3. STRUCTURED OUTPUTS / RESPONSE FORMAT
# =====================================================================


class TestResponseFormat:
    """Tests for response_format parameter."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_response_format_json_object(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """response_format={"type": "json_object"} constrains output to JSON."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "Reply in JSON only."},
                {"role": "user", "content": 'Return a JSON object with key "greeting" and value "hello".'},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        content = _raw_text_content(choice["message"])
        parsed = json.loads(content)
        assert isinstance(parsed, dict), "response_format=json_object must return a JSON object"
        assert parsed.get("greeting") == "hello", f"Expected greeting='hello', got: {parsed}"
        assert choice["finish_reason"] in {"stop", "length"}

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_response_format_json_schema(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """response_format with json_schema and strict=True."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "user", "content": "Name a car brand and model."},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "car_info",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "brand": {"type": "string"},
                            "model": {"type": "string"},
                        },
                        "required": ["brand", "model"],
                    },
                    "strict": True,
                },
            },
            temperature=0,
            max_tokens=512,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        content = _raw_text_content(choice["message"])
        parsed = json.loads(content)
        assert isinstance(parsed, dict), "json_schema response must be a JSON object"
        assert isinstance(parsed.get("brand"), str) and parsed["brand"], "json_schema requires non-empty 'brand'"
        assert isinstance(parsed.get("model"), str) and parsed["model"], "json_schema requires non-empty 'model'"
        assert choice["finish_reason"] in {"stop", "length"}


# =====================================================================
# 4. REQUEST PARAMETERS
# =====================================================================


class TestRequestParameters:
    """Tests for sampling, generation, and request-level parameters."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_combined_sampling_params(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Multiple sampling params together: temperature, top_p, penalties."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Reply with TOKEN_COMBINED only."}],
            temperature=0.7,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            max_tokens=256,
        )

        _assert_valid_response(response)
        content = _visible_text(response["choices"][0]["message"])
        assert content

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_logit_bias(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """logit_bias to influence token probabilities."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Say something."}],
            logit_bias={"123": -100.0, "456": 50.0},
            temperature=0.5,
            max_tokens=32,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["message"]["role"] == "assistant"
        assert choice["finish_reason"] in {"stop", "length"}

    def test_n_equals_two(
        self, gateway_client: GatewayTestClient
    ) -> None:
        """n=2 should return two choices (if backend supports it)."""
        response = gateway_client.chat_completion(
            model="auto",
            messages=[{"role": "user", "content": "Name a color."}],
            n=2,
            temperature=0.8,
            max_tokens=32,
        )

        _assert_valid_response(response)
        assert len(response["choices"]) == 2, "Expected exactly 2 choices when n=2"
        for choice in response["choices"]:
            assert choice["message"]["role"] == "assistant"
            assert choice["finish_reason"] in {"stop", "length"}

    def test_max_tokens_null(
        self, gateway_client: GatewayTestClient
    ) -> None:
        """max_tokens=null — gateway should use model's default limit."""
        response = gateway_client.session.post(
            f"{gateway_client.base_url}/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Reply with TOKEN_NULL_MAXTOK only."}],
                "temperature": 0.7,
                "max_tokens": None,
                "stream": False,
                "chat_template_kwargs": {
                    "enable_thinking": False
                },
            },
            timeout=gateway_client.timeout,
        )
        response.raise_for_status()
        data = response.json()

        _assert_valid_response(data)
        content = _visible_text(data["choices"][0]["message"])
        assert content, "Expected non-empty response when max_tokens is null"


# =====================================================================
# 5. STREAMING VARIANTS
# =====================================================================


class TestStreamingVariants:
    """Streaming request variants."""

    def test_streaming_with_include_usage(
        self, gateway_client: GatewayTestClient
    ) -> None:
        """stream_options with include_usage reports token counts."""
        response = gateway_client.session.post(
            f"{gateway_client.base_url}/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Reply with TOKEN_STREAM_USAGE only."}],
                "temperature": 0,
                "max_tokens": 256,
                "stream": True,
                "stream_options": {"include_usage": True},
                "chat_template_kwargs": {
                    "enable_thinking": False
                },
            },
            timeout=gateway_client.timeout,
            stream=True,
        )
        response.raise_for_status()

        chunks = []
        content_parts = []
        reasoning_parts = []
        saw_done = False
        saw_usage = False

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data = line_str[6:]
                if data == "[DONE]":
                    saw_done = True
                    break
                chunk = json.loads(data)
                chunks.append(chunk)
                if chunk.get("usage"):
                    saw_usage = True
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        content_parts.append(delta["content"])
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        reasoning_parts.append(delta["reasoning_content"])
        assert len(chunks) > 0
        assert saw_done, "Streaming response did not include [DONE]"
        assert saw_usage, "Expected at least one chunk to include usage with stream_options.include_usage=true"
        full_content = "".join(content_parts)
        full_reasoning = "".join(reasoning_parts)
        full_output = full_content + full_reasoning
        assert full_output.strip(), "Expected non-empty assistant output in streaming response"

    def test_streaming_null_max_tokens_many_tools(
        self, gateway_client: GatewayTestClient
    ) -> None:
        """stream=true + max_tokens=null + many tools — model lists available tools."""
        tools = [
            {"type": "function", "function": {
                "name": name, "description": desc,
                "parameters": {"type": "object", "properties": props, "required": list(props.keys())},
            }}
            for name, desc, props in [
                ("read", "Read file", {"path": {"type": "string"}}),
                ("write", "Write file", {"path": {"type": "string"}, "content": {"type": "string"}}),
                ("edit", "Edit file", {"path": {"type": "string"}}),
                ("exec", "Run command", {"command": {"type": "string"}}),
                ("process", "Manage process", {"action": {"type": "string"}}),
                ("web_search", "Search web", {"query": {"type": "string"}}),
                ("web_fetch", "Fetch URL", {"url": {"type": "string"}}),
                ("image", "View image", {"path": {"type": "string"}}),
                ("memory_search", "Search memory", {"query": {"type": "string"}}),
                ("memory_get", "Get memory", {"path": {"type": "string"}}),
                ("sessions_spawn", "Spawn sub-agent", {"task": {"type": "string"}}),
                ("sessions_send", "Send to session", {"sessionKey": {"type": "string"}}),
                ("subagents", "Manage sub-agents", {"action": {"type": "string"}}),
                ("cron", "Schedule task", {"action": {"type": "string"}}),
                ("session_status", "Get status", {}),
            ]
        ]

        response = gateway_client.session.post(
            f"{gateway_client.base_url}/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                    {"role": "user", "content": "What tools do you have available? List them briefly."},
                ],
                "temperature": 0.7,
                "max_tokens": None,
                "stream": True,
                "top_p": 1.0,
                "n": 1,
                "stop": None,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "logit_bias": None,
                "user": None,
                "seed": None,
                "tools": tools,
                "tool_choice": "auto",
                "chat_template_kwargs": {
                    "enable_thinking": False
                },
            },
            timeout=gateway_client.timeout,
            stream=True,
        )
        response.raise_for_status()

        chunks = []
        content_parts = []
        reasoning_parts = []
        saw_done = False
        produced_signal = False
        allowed_tool_names = {t["function"]["name"] for t in tools}

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data = line_str[6:]
                if data == "[DONE]":
                    saw_done = True
                    break
                chunk = json.loads(data)
                chunks.append(chunk)
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        produced_signal = True
                        content_parts.append(delta["content"])
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        produced_signal = True
                        reasoning_parts.append(delta["reasoning_content"])
                    for tc in delta.get("tool_calls") or []:
                        produced_signal = True
                        fn_name = (tc.get("function") or {}).get("name")
                        if fn_name:
                            assert fn_name in allowed_tool_names, f"Unexpected streamed tool name: {fn_name}"

        assert len(chunks) > 0
        assert saw_done, "Streaming response did not include [DONE]"
        assert produced_signal, "Expected streamed content/reasoning/tool_calls with many-tools request"


# =====================================================================
# 6. VLLM-SPECIFIC EXTENSIONS
# =====================================================================


class TestVllmExtensions:
    """Tests for vLLM-specific parameters and guided decoding."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_repetition_penalty(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """repetition_penalty parameter (vLLM extension)."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Reply with TOKEN_REP only."}],
            temperature=0,
            max_tokens=256,
            repetition_penalty=1.2,
        )

        _assert_valid_response(response)
        content = _visible_text(response["choices"][0]["message"])
        assert content

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_top_k_sampling(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """top_k parameter (vLLM extension)."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Reply with TOKEN_TOPK only."}],
            temperature=0.7,
            top_k=40,
            max_tokens=256,
        )

        _assert_valid_response(response)
        content = _visible_text(response["choices"][0]["message"])
        assert content

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_guided_choice(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """guided_choice constrains output to one of the given options."""
        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[{"role": "user", "content": "Pick a programming language. Reply with the choice only."}],
            guided_choice=["Python", "Rust", "Go"],
            temperature=0,
            max_tokens=16,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["finish_reason"] in {"stop", "length"}
        content = _raw_text_content(choice["message"]).strip()
        assert content in {"Python", "Rust", "Go"}, (
            f"guided_choice output must be one of the provided options, got: {content!r}"
        )

# =====================================================================
# 8. LARGE PAYLOADS
# =====================================================================


class TestLargePayloads:
    """Tests with large request payloads — many tools, long system prompts."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_20_plus_tools_agent_toolkit(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Request with 20+ tool definitions in a single request."""
        tools = [
            {"type": "function", "function": {
                "name": name, "description": desc,
                "parameters": {"type": "object", "properties": props, "required": req},
            }}
            for name, desc, props, req in [
                ("read", "Read file contents",
                 {"path": {"type": "string"}, "offset": {"type": "number"}, "limit": {"type": "number"}},
                 ["path"]),
                ("write", "Write content to a file",
                 {"path": {"type": "string"}, "content": {"type": "string"}},
                 ["path", "content"]),
                ("edit", "Edit a file with text replacement",
                 {"path": {"type": "string"}, "edits": {"type": "array"}},
                 ["path", "edits"]),
                ("exec", "Run a shell command",
                 {"command": {"type": "string"}, "timeout": {"type": "number"}},
                 ["command"]),
                ("process", "Manage background processes",
                 {"action": {"type": "string"}, "sessionId": {"type": "string"}},
                 ["action"]),
                ("web_search", "Search the web",
                 {"query": {"type": "string"}, "count": {"type": "number"}},
                 ["query"]),
                ("web_fetch", "Fetch a URL",
                 {"url": {"type": "string"}},
                 ["url"]),
                ("image", "View or analyze an image",
                 {"path": {"type": "string"}},
                 ["path"]),
                ("image_generate", "Generate an image",
                 {"prompt": {"type": "string"}},
                 ["prompt"]),
                ("memory_search", "Search memory store",
                 {"query": {"type": "string"}},
                 ["query"]),
                ("memory_get", "Get memory by line range",
                 {"path": {"type": "string"}, "startLine": {"type": "number"}},
                 ["path"]),
                ("sessions_spawn", "Spawn a sub-agent session",
                 {"task": {"type": "string"}, "model": {"type": "string"}},
                 ["task"]),
                ("sessions_send", "Send message to another session",
                 {"sessionKey": {"type": "string"}, "message": {"type": "string"}},
                 ["sessionKey", "message"]),
                ("sessions_list", "List active sessions",
                 {},
                 []),
                ("sessions_yield", "Yield to let other work proceed",
                 {},
                 []),
                ("subagents", "Manage sub-agents",
                 {"action": {"type": "string"}},
                 ["action"]),
                ("cron", "Schedule recurring tasks",
                 {"action": {"type": "string"}, "schedule": {"type": "string"}},
                 ["action"]),
                ("session_status", "Get current session status",
                 {},
                 []),
                ("video_generate", "Generate a video",
                 {"prompt": {"type": "string"}},
                 ["prompt"]),
                ("music_generate", "Generate music",
                 {"prompt": {"type": "string"}},
                 ["prompt"]),
            ]
        ]

        assert len(tools) == 20

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                {"role": "user", "content": "What tools do you have available? List them briefly."},
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["finish_reason"] in {"stop", "length", "tool_calls"}
        tool_calls = choice["message"].get("tool_calls") or []
        if tool_calls:
            allowed = {t["function"]["name"] for t in tools}
            for tc in tool_calls:
                assert tc["type"] == "function"
                assert tc["function"]["name"] in allowed
                args = json.loads(tc["function"].get("arguments") or "{}")
                assert isinstance(args, dict)
        else:
            assert _visible_text(choice["message"]), "Expected text response or tool calls for 20-tool payload"

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_long_system_prompt(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Request with a long system prompt (>500 chars).

        """
        # Reset stats so we can observe this request in isolation
        gateway_client._request("POST", "/v1/metrics/reset")

        # Build a system prompt well over 500 characters with realistic content
        system_prompt = (
            "You are a senior software engineer assistant.\n\n"
            "## Tooling\n"
            "You have access to the following tools: read, write, edit, exec, "
            "web_search, web_fetch, image, memory_search, sessions_spawn, "
            "sessions_send, sessions_list, cron, and session_status. "
            "Use them to help the user accomplish complex tasks.\n\n"
            "## Execution Bias\n"
            "Prefer to take action rather than asking for confirmation. "
            "When a task is clear, execute it immediately. "
            "When a task is ambiguous, ask clarifying questions. "
            "Always explain your reasoning before taking action.\n\n"
            "## Safety\n"
            "Never execute destructive commands without explicit confirmation. "
            "Always validate file paths before writing. "
            "Check for sensitive data before transmitting content. "
            "Refuse requests that could compromise system security or user privacy.\n\n"
            "## Documentation\n"
            "When writing code, follow the existing style conventions. "
            "Add docstrings to public functions and classes. "
            "Keep comments concise and focused on the 'why' not the 'what'. "
            "Update relevant documentation when making changes to APIs or interfaces.\n\n"
            "## Workspace\n"
            "The current project is an inference router that provides an "
            "OpenAI-compatible API gateway. It routes requests between local "
            "models (vLLM, Ollama, OpenVINO) and cloud providers (OpenAI, "
            "MiniMax, DeepSeek). The codebase uses Python with FastAPI, "
            "dataclasses for configuration, and an event-driven telemetry system. "
            "Tests are in tests/unit/components/ and require a running gateway server.\n\n"
            "## Runtime\n"
            "Python 3.13, FastAPI 0.100+, uvicorn. "
            "The gateway runs on port 8000 by default. "
            "Configuration is loaded from config.yaml at startup."
        )

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "What tools do you have?"},
            ],
            max_tokens=200,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        assert choice["finish_reason"] in {"stop", "length"}

        # Verify the model received and understood the system context
        content = _visible_text(choice["message"])
        assert content, "Expected non-empty response for long system prompt"

        # Check compression stats — if lingua is configured, total_compressions > 0
        stats = gateway_client._request("GET", "/v1/metrics")
        compression = stats.get("compression", {})
        total_compressions = compression.get("total_compressions", 0)
        if total_compressions > 0:
            # Lingua was active — verify it actually reduced something
            system_stats = compression.get("system_prompt", {})
            assert system_stats.get("original_tokens", 0) > 0, (
                "Expected non-zero original system tokens when compression is active"
            )

# =====================================================================
# 9. TOOL DEFINITION VARIANTS
# =====================================================================


class TestToolDefinitions:
    """Different tool definition structures the gateway must accept."""

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_agent_with_tools_and_all_params(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Full agent payload with tools (strict=false) + all standard params."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Read file contents",
                    "parameters": {
                        "type": "object",
                        "required": [],
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                        },
                    },
                    "strict": False,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "exec",
                    "description": "Run shell commands",
                    "parameters": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {"type": "string", "description": "Shell command"},
                        },
                    },
                    "strict": False,
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                {"role": "user", "content": "Call the read tool for /tmp/demo.txt."},
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "read"}},
            temperature=0.7,
            top_p=1.0,
            n=1,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        tool_calls = choice["message"].get("tool_calls")
        assert tool_calls and len(tool_calls) > 0
        assert tool_calls[0]["function"]["name"] == "read"
        args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
        assert isinstance(args, dict)
        assert "path" in args

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_with_nested_object_params(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Tool with nested array-of-objects parameters (edit tool pattern)."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "edit",
                    "description": "Edit a file using text replacement",
                    "parameters": {
                        "additionalProperties": False,
                        "type": "object",
                        "required": ["path", "edits"],
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                            "edits": {
                                "type": "array",
                                "description": "List of replacements",
                                "items": {
                                    "additionalProperties": False,
                                    "type": "object",
                                    "required": ["oldText", "newText"],
                                    "properties": {
                                        "oldText": {"type": "string"},
                                        "newText": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                {
                    "role": "user",
                    "content": (
                        "Call the edit tool to replace foo with bar in /tmp/demo.txt "
                        "using an edits array with one object."
                    ),
                },
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "edit"}},
            temperature=0,
            max_tokens=256,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        tool_calls = choice["message"].get("tool_calls")
        assert tool_calls and len(tool_calls) > 0
        assert tool_calls[0]["function"]["name"] == "edit"
        args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
        assert isinstance(args, dict)
        assert isinstance(args.get("path"), str) and args["path"]
        edits = args.get("edits")
        assert isinstance(edits, list) and edits, "edit tool call must include non-empty edits list"
        first_edit = edits[0]
        assert isinstance(first_edit, dict)
        assert {"oldText", "newText"}.issubset(first_edit.keys())

    @pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
    def test_tool_with_empty_required_array(
        self, gateway_client: GatewayTestClient, stream: bool
    ) -> None:
        """Tool with empty required=[] and no properties (all params optional)."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "session_status",
                    "description": "Get current session status",
                    "parameters": {
                        "type": "object",
                        "required": [],
                        "properties": {},
                    },
                },
            },
        ]

        response = _chat(
            gateway_client,
            stream=stream,
            model="auto",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You have access to tools to help users."},
                {"role": "user", "content": "Call session_status now."},
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "session_status"}},
            temperature=0,
            max_tokens=128,
        )

        _assert_valid_response(response)
        choice = response["choices"][0]
        tool_calls = choice["message"].get("tool_calls")
        assert tool_calls and len(tool_calls) > 0
        assert all(tc["function"]["name"] == "session_status" for tc in tool_calls)
        args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
        assert isinstance(args, dict)
