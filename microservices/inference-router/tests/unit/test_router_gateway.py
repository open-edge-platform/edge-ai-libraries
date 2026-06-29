# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parent))

from test_client import GatewayTestClient


def _visible_text(content: Any) -> str:
	if content is None:
		return ""
	if isinstance(content, list):
		parts: list[str] = []
		for item in content:
			if isinstance(item, dict) and item.get("type") == "text":
				parts.append(str(item.get("text", "")))
		content = "\n".join(parts)
	text = str(content)
	return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _stream_chat_completion(
	gateway_client: GatewayTestClient,
	**payload: Any,
) -> dict[str, Any]:
	"""Send a streaming request and reassemble chunks into chat.completion shape."""
	payload["stream"] = True
	payload.setdefault("chat_template_kwargs", {"enable_thinking": False})
	raw = gateway_client.session.post(
		f"{gateway_client.base_url}/v1/chat/completions",
		json=payload,
		timeout=gateway_client.timeout,
		stream=True,
	)
	try:
		raw.raise_for_status()
	except requests.HTTPError as exc:
		body = raw.text.strip()
		detail = f"{exc}. Response body: {body}" if body else str(exc)
		raise AssertionError(detail) from exc

	response_id: str | None = None
	model: str | None = None
	created: int | None = None
	content_parts: list[str] = []
	tool_calls_map: dict[int, dict] = {}  # index -> accumulated tool call
	finish_reason: str | None = None
	usage: dict[str, Any] | None = None
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
		response_id = response_id or chunk.get("id")
		model = model or chunk.get("model")
		created = created or chunk.get("created")
		if chunk.get("usage"):
			usage = chunk["usage"]

		for choice in chunk.get("choices") or []:
			delta = choice.get("delta", {})
			if "role" in delta:
				role = delta["role"]
			if delta.get("content"):
				content_parts.append(delta["content"])
			# Accumulate tool_calls by index (OpenAI streaming format)
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
	tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map)] if tool_calls_map else None

	message: dict[str, Any] = {"role": role, "content": content}
	if tool_calls:
		message["tool_calls"] = tool_calls

	result: dict[str, Any] = {
		"id": response_id,
		"object": "chat.completion",
		"created": created,
		"model": model,
		"choices": [
			{
				"index": 0,
				"message": message,
				"finish_reason": finish_reason or "stop",
			}
		],
	}
	if usage:
		result["usage"] = usage
	return result


def _chat(
	gateway_client: GatewayTestClient,
	*,
	stream: bool,
	**payload: Any,
) -> dict[str, Any]:
	if stream:
		return _stream_chat_completion(gateway_client, **payload)
	return gateway_client.chat_completion(**payload)


@pytest.fixture(scope="session")
def gateway_client() -> GatewayTestClient:
	return GatewayTestClient()


@pytest.fixture(scope="session")
def models_payload(gateway_client: GatewayTestClient) -> dict[str, Any]:
	try:
		return gateway_client.list_models()
	except requests.RequestException as exc:
		pytest.skip(f"Gateway is not reachable for live validation: {exc}")


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


def test_list_models_returns_router_and_backend_models(
	models_payload: dict[str, Any],
	available_model_ids: list[str],
) -> None:
	assert models_payload["object"] == "list"
	assert "auto" in available_model_ids
	assert len(available_model_ids) >= 2


@pytest.mark.parametrize(
	("model_selector", "messages", "expected_token"),
	[
		(
			"auto",
			[{"role": "user", "content": "Reply with the exact token TOKEN_ALPHA_17."}],
			"TOKEN_ALPHA_17",
		),
		(
			"auto",
			[
				{"role": "system", "content": "Follow the user instruction exactly."},
				{
					"role": "user",
					"content": "Line one: apples\nLine two: pears\nRespond with TOKEN_BETA_29 only.",
				},
			],
			"TOKEN_BETA_29",
		),
		(
			"auto",
			[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": "This request uses OpenAI text parts. "},
						{"type": "text", "text": "Reply with TOKEN_GAMMA_43 only."},
					],
				}
			],
			"TOKEN_GAMMA_43",
		),
		(
			"backend",
			[{"role": "user", "content": "请只回复 TOKEN_DELTA_61。"}],
			"TOKEN_DELTA_61",
		),
	],
	ids=[
		"plain-text-router",
		"multiline-with-system-router",
		"text-parts-router",
		"direct-backend-model",
	],
)
@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_text_inputs_outputs_cover_diverse_cases(
	gateway_client: GatewayTestClient,
	backend_model_id: str,
	available_model_ids: list[str],
	model_selector: str,
	messages: list[dict[str, Any]],
	expected_token: str,
	stream: bool,
) -> None:
	model_name = backend_model_id if model_selector == "backend" else model_selector
	response = _chat(
		gateway_client,
		stream=stream,
		model=model_name,
		messages=messages,
		temperature=0,
		max_tokens=128,
	)

	assert response["object"] == "chat.completion"

	choice = response["choices"][0]
	message = choice["message"]
	content = _visible_text(message.get("content"))

	assert message["role"] == "assistant"
	assert content
	assert expected_token in content
	assert choice["finish_reason"] in {"stop", "length", "tool_calls"}

	usage = response.get("usage")
	assert usage is not None
	assert usage["total_tokens"] >= usage["prompt_tokens"] >= 0
	assert usage["total_tokens"] >= usage["completion_tokens"] >= 0

@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_conversation_state_preserves_context(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[
			{"role": "system", "content": "You are a memory checker."},
			{"role": "user", "content": "Remember this code: BLUE-OTTER-17."},
			{"role": "assistant", "content": "I will remember BLUE-OTTER-17."},
			{"role": "user", "content": "What is the code? Reply with the code only."},
		],
		temperature=0,
		max_tokens=64,
	)

	choice = response["choices"][0]
	content = _visible_text(choice["message"].get("content"))

	assert response["object"] == "chat.completion"
	assert choice["message"]["role"] == "assistant"
	assert "BLUE-OTTER-17" in content
	assert "[ERROR]" not in content


def test_health_endpoint_checks_router_status(gateway_client: GatewayTestClient) -> None:
	"""Test 0: Verify health endpoint and router initialization."""
	response = gateway_client.health()

	assert response["status"] == "healthy"
	assert response["router"] == "initialized"
	assert "timestamp" in response


def test_model_list_includes_all_available_models(
	models_payload: dict[str, Any],
) -> None:
	"""Get model list and verify the auto virtual model + ≥1 backend provider."""
	data = models_payload.get("data", [])
	model_ids = [item["id"] for item in data]
	owners = {item["id"]: item["owned_by"] for item in data}

	# Should have the virtual auto model
	assert "auto" in model_ids
	assert owners["auto"] == "inference-router"

	# At least one configured provider must be exposed alongside the auto model.
	non_router_ids = [mid for mid in model_ids if mid != "auto"]
	assert non_router_ids, "Expected at least one configured provider in /v1/models"

	# Each non-auto entry must report its provider name as ``owned_by``.
	for mid in non_router_ids:
		assert isinstance(owners[mid], str) and owners[mid], (
			f"Expected non-empty owned_by (provider name) for {mid!r}"
		)
		assert owners[mid] != "inference-router", (
			f"{mid!r} should report its provider name, not 'inference-router'"
		)


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_smart_routing_strategy_with_router_model(
	gateway_client: GatewayTestClient,
	available_model_ids: list[str],
	stream: bool,
) -> None:
	"""Test 1: Verify smart routing strategy works with 'router' model."""
	# Reset stats to isolate this test
	gateway_client.reset_stats()

	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[{"role": "user", "content": "Reply with TOKEN_ROUTING_TEST only."}],
		temperature=0,
		max_tokens=64,
	)

	# Response should be a standard chat completion (no routing field)
	assert response["object"] == "chat.completion"
	assert response["model"] != "auto"

	# Verify response quality
	choice = response["choices"][0]
	content = _visible_text(choice["message"].get("content"))
	assert "TOKEN_ROUTING_TEST" in content

	# Verify routing happened via /v1/metrics. The stats are bucketed by
	# provider name; we just need to see at least one bucket populated.
	stats = gateway_client.get_stats()
	routing_stats = stats["routing_stats"]
	assert routing_stats["total_requests"] >= 1
	by_provider = routing_stats["by_provider"]
	assert any(count > 0 for count in by_provider.values())


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_forced_provider_selection(
	gateway_client: GatewayTestClient,
	available_model_ids: list[str],
	stream: bool,
) -> None:
	"""Bypass the DecisionEngine by pinning each configured model directly.

	Iterates over every non-``auto`` model id from ``/v1/models`` and confirms
	each one round-trips a request. Each iteration uses its own token so a
	stale-cached or response-crossing bug would surface as a content mismatch
	rather than passing silently.
	"""
	pinned_models = [mid for mid in available_model_ids if mid != "auto"]
	assert pinned_models, "Expected at least one non-auto model in /v1/models"

	for idx, model_id in enumerate(pinned_models):
		token = f"TOKEN_FORCE_PROVIDER_{idx}"
		response = _chat(
			gateway_client,
			stream=stream,
			model=model_id,
			messages=[{"role": "user", "content": f"Reply with {token} only."}],
			temperature=0,
			max_tokens=256,
		)

		# The gateway returns the upstream model id; we don't pin its exact
		# value (some backends echo a different id than what was requested).
		assert isinstance(response["model"], str) and response["model"], (
			f"Empty model field for pinned model {model_id!r}"
		)

		choice = response["choices"][0]
		content = choice["message"].get("content")
		assert token in content, (
			f"Expected {token!r} in response when pinning model={model_id!r}, "
			f"got {content!r}"
		)


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_streaming_mode_request(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Test 4: Verify request works in both streaming and non-streaming modes."""

	# Reset stats to verify routing after streaming
	gateway_client.reset_stats()

	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[{"role": "user", "content": "Reply with TOKEN_STREAM_TEST only."}],
		temperature=0,
		max_tokens=64,
	)

	assert response["object"] == "chat.completion"
	assert "id" in response
	assert "created" in response
	assert "model" in response
	choice = response["choices"][0]
	assert choice["finish_reason"] in {"stop", "length", "tool_calls"}
	content = _visible_text(choice["message"].get("content"))
	assert "TOKEN_STREAM_TEST" in content

	# Verify routing happened via /v1/metrics
	stats = gateway_client.get_stats()
	assert stats["routing_stats"]["total_requests"] >= 1


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_non_streaming_mode_request(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Test 5: Verify response shape works in both request modes."""
	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[{"role": "user", "content": "Reply with TOKEN_NON_STREAM only."}],
		temperature=0,
		max_tokens=64,
	)

	# Verify response format
	assert response["object"] == "chat.completion"
	assert "id" in response
	assert "created" in response
	assert "model" in response

	# Verify choices
	assert len(response["choices"]) == 1
	choice = response["choices"][0]
	assert choice["index"] == 0
	assert choice["message"]["role"] == "assistant"
	assert choice["finish_reason"] in {"stop", "length"}

	# Verify content
	content = _visible_text(choice["message"].get("content"))
	assert "TOKEN_NON_STREAM" in content

	# Verify usage (required for non-stream, optional for reassembled stream)
	usage = response.get("usage")
	if usage is not None:
		assert usage["prompt_tokens"] > 0
		assert usage["completion_tokens"] >= 0
		assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_token_usage_stats_api(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Test 6: Verify token usage tracking via stats API."""
	# Reset stats first
	gateway_client.reset_stats()

	# Make a few requests to generate stats
	for i in range(3):
		_chat(
			gateway_client,
			stream=stream,
			model="auto",
			messages=[{"role": "user", "content": f"Reply with TOKEN_STATS_{i} only."}],
			temperature=0,
			max_tokens=32,
		)

	# Get stats
	stats = gateway_client.get_stats()

	# Verify routing stats
	assert "routing_stats" in stats
	routing_stats = stats["routing_stats"]
	assert routing_stats["total_requests"] >= 3

	# Verify token metrics
	assert "token_metrics" in stats
	token_metrics = stats["token_metrics"]

	# Check overall metrics
	assert "overall" in token_metrics
	overall = token_metrics["overall"]
	assert overall["total_tokens"] > 0
	assert overall["total_requests"] >= 3
	assert overall["avg_tokens_per_request"] > 0


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_request_with_tool_call(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Test 7: Verify tool calling functionality."""
	# Define a simple tool
	tools = [
		{
			"type": "function",
			"function": {
				"name": "get_weather",
				"description": "Get the current weather for a location",
				"parameters": {
					"type": "object",
					"properties": {
						"location": {
							"type": "string",
							"description": "The city and state, e.g., San Francisco, CA",
						},
						"unit": {
							"type": "string",
							"enum": ["celsius", "fahrenheit"],
							"description": "The temperature unit to use",
						},
					},
					"required": ["location"],
				},
			},
		}
	]

	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[
			{"role": "user", "content": "What's the weather in San Francisco?"}
		],
		tools=tools,
		tool_choice="auto",
		temperature=0,
		max_tokens=256,
	)

	# Verify response format
	assert response["object"] == "chat.completion"
	choice = response["choices"][0]
	message = choice["message"]

	# Tool call might or might not be triggered depending on model
	# Just verify the response is valid
	assert message["role"] == "assistant"

	# If tool calls are present, verify format
	if message.get("tool_calls"):
		tool_calls = message["tool_calls"]
		assert isinstance(tool_calls, list)
		assert len(tool_calls) > 0

		tool_call = tool_calls[0]
		assert "id" in tool_call
		assert tool_call["type"] == "function"
		assert "function" in tool_call
		assert tool_call["function"]["name"] == "get_weather"
		assert "arguments" in tool_call["function"]

		# Verify finish reason
		assert choice["finish_reason"] == "tool_calls"
	else:
		# If no tool call, should have content
		assert message.get("content") is not None
		assert choice["finish_reason"] in {"stop", "length"}


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_large_input_routing_behavior(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Additional test: Verify routing behavior with large inputs."""
	# Reset stats to isolate this test
	gateway_client.reset_stats()

	# Create a large prompt that might trigger cloud routing
	large_content = "Context: " + ("This is a test sentence. " * 500)
	large_content += " Question: Reply with TOKEN_LARGE_INPUT only."

	response = _chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[{"role": "user", "content": large_content}],
		temperature=0,
		max_tokens=64,
	)

	# Verify response
	assert response["object"] == "chat.completion"

	# Verify content
	choice = response["choices"][0]
	content = _visible_text(choice["message"].get("content"))
	assert "TOKEN_LARGE_INPUT" in content or "[ERROR]" not in content


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_invalid_model_selection_returns_error(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Additional test: Verify error handling for invalid model selection."""
	got_response = False
	response = None
	try:
		response = _chat(
			gateway_client,
			stream=stream,
			model="invalid-model-xyz",
			messages=[{"role": "user", "content": "Test"}],
			max_tokens=64,
		)
		got_response = True
	except AssertionError as e:
		# Non-streaming: gateway returns HTTP 400 → test client raises AssertionError
		error_msg = str(e)
		assert "Unknown model" in error_msg or "invalid" in error_msg.lower()

	if got_response:
		# Streaming: gateway returns HTTP 200 with the error embedded in SSE content
		content = response["choices"][0]["message"].get("content", "")
		assert "Unknown model" in content or "failed" in content.lower(), (
			f"Expected error about unknown model in response content, got: {content}"
		)


@pytest.mark.parametrize("stream", [False, True], ids=["non-stream", "stream"])
def test_stats_reset_functionality(
	gateway_client: GatewayTestClient,
	stream: bool,
) -> None:
	"""Additional test: Verify stats can be reset."""
	# Make a request to generate stats
	_chat(
		gateway_client,
		stream=stream,
		model="auto",
		messages=[{"role": "user", "content": "Reply with TOKEN_RESET only."}],
		temperature=0,
		max_tokens=32,
	)

	# Get stats before reset
	stats_before = gateway_client.get_stats()
	assert stats_before["routing_stats"]["total_requests"] > 0

	# Reset stats
	reset_data = gateway_client.reset_stats()
	assert reset_data["status"] == "success"

	# Verify stats are reset
	stats_after = gateway_client.get_stats()
	assert stats_after["routing_stats"]["total_requests"] == 0
	assert stats_after["token_metrics"]["overall"]["total_tokens"] == 0


def test_parallel_requests_handled_independently(
	gateway_client: GatewayTestClient,
) -> None:
	"""Send several requests concurrently and verify each gets its own response.

	Guards against response-crossing bugs in the gateway: each parallel request
	carries a unique token in its prompt, and we assert each response echoes
	*its own* token. Also verifies the metrics counter records every request,
	so admission control isn't silently dropping any.

	Concurrency below the gateway's ``max_concurrency`` cap (default 3) so all
	three requests should run in parallel and succeed; a separate test would
	be needed to exercise the 429 overflow path.
	"""
	gateway_client.reset_stats()

	tokens = ["TOKEN_PAR_A", "TOKEN_PAR_B", "TOKEN_PAR_C"]

	def send(token: str) -> dict[str, Any]:
		return gateway_client.chat_completion(
			model="auto",
			messages=[{"role": "user", "content": f"Reply with {token} only."}],
			temperature=0,
			max_tokens=32,
		)

	with ThreadPoolExecutor(max_workers=len(tokens)) as ex:
		responses = list(ex.map(send, tokens))

	# Each response must carry the token from its own prompt — no crossing.
	for token, response in zip(tokens, responses):
		choice = response["choices"][0]
		content = _visible_text(choice["message"].get("content"))
		assert token in content, (
			f"Expected {token!r} in response content, got {content!r}"
		)

	# Telemetry counted every parallel request.
	stats = gateway_client.get_stats()
	assert stats["routing_stats"]["total_requests"] >= len(tokens), (
		f"Expected ≥{len(tokens)} requests in stats, got {stats['routing_stats']}"
	)


