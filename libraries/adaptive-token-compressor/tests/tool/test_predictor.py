"""Tests for tool/predictor.py — HTTPToolPredictor + tolerant JSON parser."""
from __future__ import annotations

import json

import pytest
import responses

from adaptive_token_compressor.core.exceptions import BackendError, PredictorError
from adaptive_token_compressor.core.health import HealthState
from adaptive_token_compressor.tool.predictor import (
    HTTPToolPredictor,
    RerankerToolPredictor,
    ToolCandidate,
    ToolDefinition,
    ToolPredictor,
    _extract_json_from_response,
)


URL = "http://localhost:8088/v1/chat/completions"
MODEL = "Qwen/Qwen3.6-35B-A3B"
RERANK_URL = "http://localhost:8090/rerank"
RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"


def _chat_payload(content: str) -> dict:
    """Build an OpenAI-compatible /v1/chat/completions response body."""
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# _extract_json_from_response
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractJsonFromResponse:
    def test_plain_json(self):
        assert _extract_json_from_response('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        text = '```json\n{"a": 2}\n```'
        assert _extract_json_from_response(text) == {"a": 2}

    def test_single_quotes_replaced(self):
        assert _extract_json_from_response("{'a': 3}") == {"a": 3}

    def test_extra_prose_around_json(self):
        text = "Sure, here is the JSON: {\"a\": 4} let me know."
        assert _extract_json_from_response(text) == {"a": 4}

    def test_no_json_returns_none(self):
        assert _extract_json_from_response("no json here") is None

    def test_non_dict_top_level_returns_none(self):
        # Top-level array is not what the predictor uses; return None.
        assert _extract_json_from_response('[1, 2, 3]') is None

    def test_invalid_json_returns_none(self):
        assert _extract_json_from_response("{invalid") is None

    def test_truncated_multiline_salvaged(self):
        # Real `raw_response` captured when stop=["}"] + max_tokens cut a
        # multi-line object mid-key ("get_credit_ca). Every complete pair must
        # survive; the severed tail is dropped (no "get_credit_ca" key).
        text = (
            '{\n "authenticate_travel": 5,\n "get_nearest_airport_by_city": 5,\n'
            ' "get_flight_cost": 5,\n "book_flight": 5,\n "get_all_credit_cards": 4,\n'
            ' "verify_traveler_information": 4,\n "travel_get_login_status": 3,\n'
            ' "get_booking_history": 2,\n "retrieve_invoice": 2,\n'
            ' "contact_customer_support": 2,\n "compute_exchange_rate": 1,\n'
            ' "list_all_airports": 1,\n "cancel_booking": 1,\n'
            ' "purchase_insurance": 1,\n "register_credit_card": 1,\n'
            ' "set_budget_limit": 1,\n "get_budget_fiscal_year": 1,\n "get_credit_ca'
        )
        result = _extract_json_from_response(text)
        assert result is not None
        assert "get_credit_ca" not in result
        assert result["authenticate_travel"] == 5
        assert result["get_budget_fiscal_year"] == 1
        assert len(result) == 17  # 18 emitted, final severed key dropped


# ─────────────────────────────────────────────────────────────────────────────
# HTTPToolPredictor — Protocol conformance
# ─────────────────────────────────────────────────────────────────────────────


class TestProtocol:
    def test_runtime_checkable(self):
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        assert isinstance(predictor, ToolPredictor)


# ─────────────────────────────────────────────────────────────────────────────
# HTTPToolPredictor.predict — happy paths
# ─────────────────────────────────────────────────────────────────────────────


class TestPredictHappy:
    @responses.activate
    def test_custom_max_output_tokens_is_sent(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5}'),
            status=200,
        )
        predictor = HTTPToolPredictor(
            url=URL, model=MODEL, max_output_tokens=1024,
        )

        predictor.predict("read a file", system_prompt="sys")

        posted = json.loads(responses.calls[0].request.body)
        assert posted["max_tokens"] == 1024

    @responses.activate
    def test_json_schema_mode_enforces_flat_score_map(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5}'),
            status=200,
        )
        predictor = HTTPToolPredictor(
            url=URL, model=MODEL, enforce_json_schema=True,
        )

        predictor.predict(
            "read a file", system_prompt="sys", tool_names=["read", "write"],
        )

        posted = json.loads(responses.calls[0].request.body)
        schema = posted["response_format"]["json_schema"]["schema"]
        assert schema["properties"] == {
            "read": {"type": "integer", "minimum": 1, "maximum": 5},
            "write": {"type": "integer", "minimum": 1, "maximum": 5},
        }
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["read", "write"]
        assert "stop" not in posted

    @responses.activate
    def test_json_schema_requires_every_unique_tool(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5, "write": 1}'),
            status=200,
        )
        names = [f"tool_{i}" for i in range(30)] + ["tool_0"]
        predictor = HTTPToolPredictor(
            url=URL, model=MODEL, enforce_json_schema=True,
        )

        predictor.predict("read a file", system_prompt="sys", tool_names=names)

        posted = json.loads(responses.calls[0].request.body)
        schema = posted["response_format"]["json_schema"]["schema"]
        assert schema["required"] == [f"tool_{i}" for i in range(30)]
        # 30 unique tools → floor 12*30+32 overrides the default 256.
        assert posted["max_tokens"] == 392

    @responses.activate
    def test_json_schema_keeps_larger_max_tokens(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5, "write": 1}'),
            status=200,
        )
        predictor = HTTPToolPredictor(
            url=URL, model=MODEL, enforce_json_schema=True,
            max_output_tokens=1024,
        )

        predictor.predict(
            "read a file", system_prompt="sys", tool_names=["read", "write"],
        )

        posted = json.loads(responses.calls[0].request.body)
        assert posted["max_tokens"] == 1024

    @responses.activate
    def test_normal_json_response(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5, "write": 3, "exec": 4}'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, meta = predictor.predict("write code", system_prompt="sys")
        # Sorted by descending score, then ascending name.
        assert candidates == [
            ToolCandidate(name="read", score=5),
            ToolCandidate(name="exec", score=4),
            ToolCandidate(name="write", score=3),
        ]
        assert meta["model"] == MODEL
        assert "latency_ms" in meta
        assert "raw_response" in meta

    @responses.activate
    def test_markdown_fenced_response(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('```json\n{"read": 5}\n```'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == [ToolCandidate(name="read", score=5)]

    @responses.activate
    def test_single_quotes_response(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload("{'read': 5}"),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == [ToolCandidate(name="read", score=5)]

    @responses.activate
    def test_stop_token_truncation_recovered(self):
        # vLLM with `stop=["}"]` returns content missing the closing brace.
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5, "write": 4'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == [
            ToolCandidate(name="read", score=5),
            ToolCandidate(name="write", score=4),
        ]

    @responses.activate
    def test_score_outside_1_to_5_dropped(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 5, "edit": 0, "exec": 7, "write": 3}'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        names = [c.name for c in candidates]
        # 0 and 7 dropped — only read=5 and write=3 survive.
        assert names == ["read", "write"]

    @responses.activate
    def test_non_int_score_dropped(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": "five", "exec": 4}'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == [ToolCandidate(name="exec", score=4)]

    @responses.activate
    def test_name_normalised_to_lower_strip(self):
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"  READ  ": 5}'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == [ToolCandidate(name="read", score=5)]

    @responses.activate
    def test_empty_response_returns_empty_list(self):
        # `{}` is a valid response with no predicted tools — must NOT raise.
        responses.add(
            responses.POST, URL,
            json=_chat_payload("{}"),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, meta = predictor.predict("t", system_prompt="s")
        assert candidates == []
        assert "raw_response" in meta

    @responses.activate
    def test_all_scores_invalid_returns_empty(self):
        # Valid JSON but all scores out of range — empty list, no raise.
        responses.add(
            responses.POST, URL,
            json=_chat_payload('{"read": 0, "exec": 9}'),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        candidates, _ = predictor.predict("t", system_prompt="s")
        assert candidates == []


# ─────────────────────────────────────────────────────────────────────────────
# HTTPToolPredictor.predict — failure paths (raise PredictorError)
# ─────────────────────────────────────────────────────────────────────────────


class TestPredictFailure:
    @responses.activate
    def test_http_500_raises_predictor_error(self):
        responses.add(responses.POST, URL, json={"error": "boom"}, status=500)
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        with pytest.raises(PredictorError) as exc_info:
            predictor.predict("t", system_prompt="s")
        # PredictorError is a BackendError subclass.
        assert isinstance(exc_info.value, BackendError)
        assert "HTTP request failed" in str(exc_info.value)

    @responses.activate
    def test_connection_error_raises(self):
        # No registered response → ConnectionError.
        predictor = HTTPToolPredictor(url=URL, model=MODEL, timeout=1)
        with pytest.raises(PredictorError):
            predictor.predict("t", system_prompt="s")

    @responses.activate
    def test_invalid_json_response_raises(self):
        responses.add(
            responses.POST, URL, body="not json", status=200,
            content_type="application/json",
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        with pytest.raises(PredictorError) as exc_info:
            predictor.predict("t", system_prompt="s")
        assert "Invalid JSON response" in str(exc_info.value)

    @responses.activate
    def test_missing_choices_raises(self):
        responses.add(
            responses.POST, URL, json={"id": "x"}, status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        with pytest.raises(PredictorError) as exc_info:
            predictor.predict("t", system_prompt="s")
        assert "Response missing choices[0]" in str(exc_info.value)

    @responses.activate
    def test_unparseable_content_raises(self):
        # Content is a string but contains nothing JSON-like.
        responses.add(
            responses.POST, URL,
            json=_chat_payload("just plain prose, no braces"),
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        with pytest.raises(PredictorError) as exc_info:
            predictor.predict("t", system_prompt="s")
        assert "Failed to parse JSON" in str(exc_info.value)


class TestRerankerPredictor:
    TOOLS = [
        ToolDefinition(name="read", description="Read files"),
        ToolDefinition(
            name="exec",
            description="Run commands",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        ),
    ]

    @responses.activate
    def test_batch_scores_map_back_by_index(self):
        responses.add(
            responses.POST,
            RERANK_URL,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.25},
                    {"index": 0, "relevance_score": 0.9},
                ]
            },
            status=200,
        )
        predictor = RerankerToolPredictor(
            url=RERANK_URL,
            model=RERANK_MODEL,
            instruction="Select tools needed to inspect source code.",
        )
        candidates, meta = predictor.predict(
            "inspect a file",
            system_prompt="The previous command failed.",
            tool_definitions=self.TOOLS,
        )

        assert candidates == [
            ToolCandidate(name="read", score=4.6),
            ToolCandidate(name="exec", score=2.0),
        ]
        assert meta["scores"] == {"read": 0.9, "exec": 0.25}
        request = responses.calls[0].request
        payload = request.body.decode() if isinstance(request.body, bytes) else request.body
        posted = __import__("json").loads(payload)
        assert posted["top_n"] == 2
        assert posted["query"].startswith(
            "Instruction:\nSelect tools needed to inspect source code.\n\n"
            "Task:\ninspect a file"
        )
        assert "Agent context" in posted["query"]
        assert posted["documents"][0].startswith("Tool name: read")
        assert "Parameters:" in posted["documents"][1]

    @responses.activate
    def test_logit_mode_uses_sigmoid(self):
        responses.add(
            responses.POST,
            RERANK_URL,
            json={"results": [{"index": 0, "relevance_score": 0.0}]},
            status=200,
        )
        predictor = RerankerToolPredictor(
            url=RERANK_URL, model=RERANK_MODEL, score_mode="logit",
        )
        candidates, _ = predictor.predict(
            "read", system_prompt="", tool_definitions=self.TOOLS[:1],
        )
        assert candidates == [ToolCandidate(name="read", score=3.0)]

    @responses.activate
    def test_incomplete_result_raises(self):
        responses.add(
            responses.POST,
            RERANK_URL,
            json={"results": [{"index": 0, "relevance_score": 0.9}]},
            status=200,
        )
        predictor = RerankerToolPredictor(url=RERANK_URL, model=RERANK_MODEL)
        with pytest.raises(PredictorError, match="missing indices: \\[1\\]"):
            predictor.predict(
                "read", system_prompt="", tool_definitions=self.TOOLS,
            )

    @responses.activate
    def test_probability_outside_range_raises(self):
        responses.add(
            responses.POST,
            RERANK_URL,
            json={"results": [{"index": 0, "relevance_score": 1.2}]},
            status=200,
        )
        predictor = RerankerToolPredictor(url=RERANK_URL, model=RERANK_MODEL)
        with pytest.raises(PredictorError, match="outside \\[0, 1\\]"):
            predictor.predict(
                "read", system_prompt="", tool_definitions=self.TOOLS[:1],
            )


# ─────────────────────────────────────────────────────────────────────────────
# HTTPToolPredictor.health_check
# ─────────────────────────────────────────────────────────────────────────────


HEALTH = "http://localhost:8088/v1/models"


class TestHealthCheck:
    def test_health_endpoint_derived_from_chat_url(self):
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        assert predictor._health_endpoint == HEALTH

    def test_health_endpoint_explicit(self):
        predictor = HTTPToolPredictor(
            url=URL, model=MODEL, health_endpoint="http://x/y",
        )
        assert predictor._health_endpoint == "http://x/y"

    @responses.activate
    def test_healthy_when_target_model_listed(self):
        responses.add(
            responses.GET, HEALTH,
            json={"data": [{"id": MODEL}, {"id": "other-model"}]},
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        status = predictor.health_check()
        assert status.state == HealthState.HEALTHY

    @responses.activate
    def test_degraded_when_target_model_missing(self):
        responses.add(
            responses.GET, HEALTH,
            json={"data": [{"id": "other-model"}]},
            status=200,
        )
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        status = predictor.health_check()
        assert status.state == HealthState.DEGRADED
        assert MODEL in (status.message or "")

    @responses.activate
    def test_degraded_when_no_data_field(self):
        responses.add(responses.GET, HEALTH, json={}, status=200)
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        status = predictor.health_check()
        assert status.state == HealthState.DEGRADED

    @responses.activate
    def test_unhealthy_on_500(self):
        responses.add(responses.GET, HEALTH, json={"err": "x"}, status=500)
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        status = predictor.health_check()
        assert status.state == HealthState.UNHEALTHY

    @responses.activate
    def test_unhealthy_on_unreachable(self):
        # No registered response → connection error.
        predictor = HTTPToolPredictor(url=URL, model=MODEL)
        status = predictor.health_check(timeout=0.5)
        assert status.state == HealthState.UNHEALTHY
