"""Tests for tool/compressor.py — filter_tools / filter_tooling_section / ToolCompressor."""
from __future__ import annotations

import json
import logging

import pytest

from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.exceptions import ConfigError, PredictorError
from adaptive_token_compressor.core.metrics import CompressionScope
from adaptive_token_compressor.tool.compressor import (
    ToolCompressor,
    filter_tools,
    filter_tooling_section,
)
from adaptive_token_compressor.tool.predictor import ToolCandidate


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


URL = "http://localhost:8088/v1/chat/completions"


def _tool(name: str, description: str = "") -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description},
    }


class FakePredictor:
    """In-memory predictor for ToolCompressor tests.

    Constructed with a (candidates, raw_meta) pair OR an exception to raise.
    """

    name = "fake_predictor"

    def __init__(self, *, candidates=None, raw_meta=None, raise_exc: Exception | None = None):
        self._candidates = candidates or []
        self._meta = raw_meta or {}
        self._exc = raise_exc
        self.calls: list[dict] = []

    def predict(self, task, *, system_prompt):
        self.calls.append({"task": task, "system_prompt": system_prompt})
        if self._exc is not None:
            raise self._exc
        return list(self._candidates), dict(self._meta)

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus
        return HealthStatus.healthy("fake_predictor")


def _make_request(task: str = "Read the README.md file", tools: list[dict] | None = None):
    return CompressionContext(
        messages=[
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": task},
        ],
        tools=tools if tools is not None else [_tool("read", "Read"), _tool("write", "Write")],
    )


# ─────────────────────────────────────────────────────────────────────────────
# filter_tools — covers row §13 `tools/compressor (filter_tools)`
# ─────────────────────────────────────────────────────────────────────────────


class TestFilterTools:
    def test_simple_match(self):
        tools = [_tool("read"), _tool("write"), _tool("exec")]
        result = filter_tools(tools, ["read", "exec"])
        assert [t["function"]["name"] for t in result] == ["read", "exec"]

    def test_case_insensitive(self):
        # Schema preserves original casing; predicted names are lower.
        tools = [_tool("Read"), _tool("WRITE"), _tool("Exec")]
        result = filter_tools(tools, ["read", "exec"])
        # Original casing preserved on the kept entries.
        names = [t["function"]["name"] for t in result]
        assert names == ["Read", "Exec"]

    def test_preserve_input_order(self):
        tools = [_tool("a"), _tool("b"), _tool("c"), _tool("d")]
        # Predicted order = ['c', 'a'], but we keep tools-original order.
        result = filter_tools(tools, ["c", "a"])
        assert [t["function"]["name"] for t in result] == ["a", "c"]

    def test_predicted_name_not_in_tools_skipped(self):
        tools = [_tool("read")]
        result = filter_tools(tools, ["read", "nonexistent"])
        assert [t["function"]["name"] for t in result] == ["read"]

    def test_empty_predicted_returns_original(self):
        tools = [_tool("read"), _tool("write")]
        # Empty predicted_names → defensive return all (legacy behaviour).
        assert filter_tools(tools, []) == tools

    def test_empty_tools(self):
        assert filter_tools([], ["read"]) == []

    def test_byte_stable_across_runs(self):
        # Same tools + same predicted set → same output (prefix-cache friendly).
        tools = [_tool("a"), _tool("b"), _tool("c")]
        a = filter_tools(tools, ["a", "c"])
        b = filter_tools(tools, ["c", "a"])  # different predicted order
        assert a == b

    def test_does_not_mutate_input(self):
        tools = [_tool("read")]
        snapshot = json.dumps(tools)
        filter_tools(tools, ["read"])
        assert json.dumps(tools) == snapshot

    def test_non_function_type_skipped(self):
        tools = [
            _tool("read"),
            {"type": "code_interpreter"},
            _tool("write"),
        ]
        result = filter_tools(tools, ["read", "write"])
        assert [t["function"]["name"] for t in result] == ["read", "write"]

    def test_empty_schema_name_skipped(self):
        tools = [
            {"type": "function", "function": {"name": "", "description": ""}},
            _tool("read"),
        ]
        result = filter_tools(tools, ["read"])
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# filter_tooling_section — default-disabled path (covered for parity)
# ─────────────────────────────────────────────────────────────────────────────


class TestFilterToolingSection:
    def test_no_tooling_section_returns_unchanged(self):
        content = "## Other\n- read: x\n- write: y"
        assert filter_tooling_section(content, ["read"]) == content

    def test_filters_tool_lines(self):
        content = (
            "Header\n"
            "## Tooling\n"
            "- read: read files\n"
            "- write: write files\n"
            "- exec: run commands\n"
            "## Memory\n"
            "footer"
        )
        result = filter_tooling_section(content, ["read", "exec"])
        assert "- read: read files" in result
        assert "- exec: run commands" in result
        assert "- write: write files" not in result
        # Outside section preserved.
        assert "## Memory" in result
        assert "footer" in result

    def test_empty_predicted_returns_unchanged(self):
        content = "## Tooling\n- read: x\n## Memory\n"
        assert filter_tooling_section(content, []) == content

    def test_handles_escaped_newlines(self):
        content = "Pre\\n## Tooling\\n- read: x\\n- write: y\\n## Memory"
        result = filter_tooling_section(content, ["read"])
        assert "- read: x" in result
        assert "- write: y" not in result


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — construction
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorConstruction:
    def test_minimal_construction(self):
        comp = ToolCompressor(predictor_url=URL)
        assert comp.name == "tool"

    def test_invalid_prompt_mode_raises(self):
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, prompt_mode="invalid")  # type: ignore[arg-type]

    def test_invalid_tool_descriptions_mode_raises(self):
        with pytest.raises(ConfigError):
            ToolCompressor(
                predictor_url=URL, tool_descriptions_mode="bogus",  # type: ignore[arg-type]
            )

    def test_invalid_score_threshold_raises(self):
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, score_threshold=0.5)
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, score_threshold=6.0)

    def test_invalid_timeout_raises(self):
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, timeout=0)

    def test_invalid_placement_raises(self):
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, placement="bogus")  # type: ignore[arg-type]

    def test_default_placement_is_schema(self):
        comp = ToolCompressor(predictor_url=URL)
        assert comp._placement == "schema"


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor.compress — short-circuit paths (no_task / no_tools)
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorShortCircuit:
    def test_no_task_skip(self):
        comp = ToolCompressor(predictor_url=URL)
        fake = FakePredictor()
        comp._predictor = fake
        ctx = CompressionContext(
            messages=[{"role": "system", "content": "sys"}],  # no user message
            tools=[_tool("read")],
        )
        result = comp.compress(ctx)
        assert result.metrics.skip_reason == "no_task"
        assert result.metrics.error is None
        assert result.tools == ctx.tools  # untouched
        assert fake.calls == []  # predictor never called

    def test_no_tools_skip_when_none(self):
        comp = ToolCompressor(predictor_url=URL)
        fake = FakePredictor()
        comp._predictor = fake
        ctx = CompressionContext(
            messages=[{"role": "user", "content": "task"}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.metrics.skip_reason == "no_tools"
        assert result.tools is None
        assert fake.calls == []

    def test_no_tools_skip_when_empty(self):
        comp = ToolCompressor(predictor_url=URL)
        fake = FakePredictor()
        comp._predictor = fake
        ctx = CompressionContext(
            messages=[{"role": "user", "content": "task"}], tools=[],
        )
        result = comp.compress(ctx)
        assert result.metrics.skip_reason == "no_tools"
        assert result.tools == []
        assert fake.calls == []

    def test_skipped_metrics_have_zero_saved(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor()
        ctx = CompressionContext(messages=[], tools=None)
        result = comp.compress(ctx)
        assert result.metrics.tokens_before == result.metrics.tokens_after
        assert result.metrics.saved_tokens == 0


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor.compress — predictor failure
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorPredictorFailure:
    def test_predictor_error_kept_as_metrics_error(self, caplog):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(
            raise_exc=PredictorError("boom", component="x"),
        )
        ctx = _make_request()

        with caplog.at_level(logging.WARNING):
            result = comp.compress(ctx)

        assert result.metrics.error is not None
        assert "boom" in result.metrics.error
        assert result.metrics.skip_reason is None
        # Tools untouched on failure.
        assert result.tools == ctx.tools
        # Caplog WARNING contract.
        assert any("Predictor failed" in rec.message for rec in caplog.records)

    def test_predictor_error_does_not_propagate(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(
            raise_exc=PredictorError("boom", component="x"),
        )
        # Should NOT raise — must fold into metrics.error.
        result = comp.compress(_make_request())
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor.compress — empty / threshold-filtered candidates
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorNoToolsPredicted:
    def test_empty_candidates_short_circuits(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(candidates=[])
        result = comp.compress(_make_request())
        assert result.metrics.skip_reason == "no_tools_predicted"
        assert result.metrics.error is None
        # All tools kept.
        assert len(result.tools) == 2

    def test_all_below_threshold_short_circuits(self):
        comp = ToolCompressor(predictor_url=URL, score_threshold=4.0)
        comp._predictor = FakePredictor(
            candidates=[ToolCandidate(name="read", score=2)],
        )
        result = comp.compress(_make_request())
        assert result.metrics.skip_reason == "no_tools_predicted"
        assert len(result.tools) == 2  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor.compress — happy path
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorSuccess:
    def test_filters_below_threshold(self):
        comp = ToolCompressor(predictor_url=URL, score_threshold=3.0)
        comp._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=2),  # below threshold
            ],
        )
        result = comp.compress(_make_request())
        names = [t["function"]["name"] for t in result.tools]
        assert names == ["read"]
        assert result.metrics.skip_reason is None
        assert result.metrics.error is None
        assert result.metrics.succeeded
        assert result.metrics.scope == CompressionScope.TOOL

    def test_metrics_details_populated(self):
        comp = ToolCompressor(predictor_url=URL, score_threshold=3.0)
        comp._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=4),
                ToolCandidate(name="exec", score=2),  # below
            ],
        )
        ctx = _make_request(
            tools=[_tool("read"), _tool("write"), _tool("exec"), _tool("ping")],
        )
        result = comp.compress(ctx)
        d = result.metrics.details
        assert d["original_tool_count"] == 4
        assert d["compressed_tool_count"] == 2
        assert d["filtered_count"] == 2
        assert d["score_threshold"] == 3.0
        assert d["predicted_count"] == 2
        assert sorted(d["predicted_tools"]) == ["read", "write"]
        # Candidate dataclasses preserved (unfiltered) in details.
        assert len(d["candidates"]) == 3

    def test_messages_untouched(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(
            candidates=[ToolCandidate(name="read", score=5)],
        )
        ctx = _make_request()
        snapshot = json.dumps(ctx.messages)
        result = comp.compress(ctx)
        # ToolCompressor never touches messages.
        assert result.messages == ctx.messages
        assert json.dumps(ctx.messages) == snapshot

    def test_tokens_after_smaller_when_filtering_works(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(
            candidates=[ToolCandidate(name="read", score=5)],
        )
        big = [_tool(f"tool{i}", "X" * 300) for i in range(20)]
        big.append(_tool("read", "read description"))
        ctx = _make_request(tools=big)
        result = comp.compress(ctx)
        assert result.metrics.tokens_after < result.metrics.tokens_before
        assert result.metrics.compression_ratio < 1.0

    def test_repeated_calls_byte_stable(self):
        # Same task + same predicted set ⇒ identical filtered tools across
        # calls. Predictor is the only source of variability; here it's fixed.
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=4),
            ],
        )
        ctx = _make_request(tools=[_tool("read"), _tool("write"), _tool("exec")])
        a = comp.compress(ctx).tools
        b = comp.compress(ctx).tools
        assert json.dumps(a) == json.dumps(b)


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — prompt_mode / tool_descriptions_mode dimensions
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorDimensions:
    def test_static_mode_does_not_inject_history_section(self):
        comp = ToolCompressor(predictor_url=URL, prompt_mode="static")
        fake = FakePredictor(
            candidates=[ToolCandidate(name="read", score=5)],
        )
        comp._predictor = fake
        ctx = _make_request()
        comp.compress(ctx)
        prompt = fake.calls[0]["system_prompt"]
        # Static mode = focus_five template, NO history section.
        assert "EXACTLY 5 to 10 tools" in prompt
        assert "Completed tool calls so far" not in prompt
        assert "available skills" not in prompt

    def test_dynamic_mode_includes_call_history_when_present(self):
        # prompt_template is no longer user-overridable; dynamic mode picks
        # BASE_PROMPT internally. The assertion below verifies the dynamic
        # context (call_history section) is appended regardless of header.
        comp = ToolCompressor(
            predictor_url=URL,
            prompt_mode="dynamic",
        )
        fake = FakePredictor(
            candidates=[ToolCandidate(name="read", score=5)],
        )
        comp._predictor = fake
        ctx = CompressionContext(
            messages=[
                {"role": "user", "content": "task"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "exec", "arguments": '{"cmd": "ls"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": "result"},
            ],
            tools=[_tool("read")],
        )
        comp.compress(ctx)
        prompt = fake.calls[0]["system_prompt"]
        assert "Completed tool calls so far" in prompt
        assert "exec(cmd=ls)" in prompt

    def test_static_descriptions_uses_default_list(self):
        comp = ToolCompressor(
            predictor_url=URL,
            tool_descriptions_mode="static",
            prompt_mode="static",
        )
        fake = FakePredictor(candidates=[])
        comp._predictor = fake
        comp.compress(_make_request(tools=[_tool("custom_one"), _tool("custom_two")]))
        prompt = fake.calls[0]["system_prompt"]
        # Default list contains "sessions_spawn"; custom_one is NOT in default.
        assert "sessions_spawn" in prompt
        assert "custom_one" not in prompt

    def test_dynamic_descriptions_uses_request_tools(self):
        comp = ToolCompressor(
            predictor_url=URL,
            tool_descriptions_mode="dynamic",
            prompt_mode="static",
        )
        fake = FakePredictor(candidates=[])
        comp._predictor = fake
        comp.compress(
            _make_request(tools=[_tool("custom_one", "first"), _tool("custom_two", "second")])
        )
        prompt = fake.calls[0]["system_prompt"]
        assert "custom_one: first" in prompt
        assert "custom_two: second" in prompt
        # Default list NOT injected.
        assert "sessions_spawn" not in prompt


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor.health_check
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorHealthCheck:
    def test_delegates_to_predictor(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FakePredictor()
        status = comp.health_check()
        assert status.component == "fake_predictor"


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — placement="user_tail"
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorUserTailPlacement:
    """Verify the user_tail placement rewrites result.tools/messages so the
    tools block sits in a synthetic user-carrier message at the end of the
    messages list."""

    def _build(self):
        comp = ToolCompressor(predictor_url=URL, placement="user_tail")
        comp._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=4),
                ToolCandidate(name="exec", score=1.5),  # < threshold 2.0, dropped
            ],
        )
        return comp

    def test_result_tools_is_none(self):
        comp = self._build()
        result = comp.compress(_make_request())
        # tools field must be OMITTED (None, not []) so the chat template
        # doesn't render a `<tools>` block in system AND strict backends don't
        # reject an empty `tools: []` array (Qwen3.6: "`tools` must not be an
        # empty array. Either provide at least one tool or omit the field").
        assert result.tools is None

    def test_result_messages_appends_carrier_user(self):
        comp = self._build()
        ctx = _make_request()
        original_n = len(ctx.messages)
        result = comp.compress(ctx)
        assert len(result.messages) == original_n + 1
        carrier = result.messages[-1]
        assert carrier["role"] == "user"
        assert isinstance(carrier["content"], str)

    def test_carrier_content_has_tools_block(self):
        comp = self._build()
        result = comp.compress(_make_request())
        carrier_content = result.messages[-1]["content"]
        # All required block components present.
        assert carrier_content.startswith("# Tools\n\n")
        assert "You have access to the following functions:" in carrier_content
        assert "<tools>" in carrier_content
        assert "</tools>" in carrier_content
        # Calling-convention footer present (required for vLLM tool-call parser).
        assert "<tool_call>" in carrier_content
        assert carrier_content.endswith("</IMPORTANT>")

    def test_carrier_only_includes_predicted_tools(self):
        comp = self._build()
        ctx = _make_request(
            tools=[_tool("read"), _tool("write"), _tool("exec"), _tool("ping")],
        )
        result = comp.compress(ctx)
        carrier_content = result.messages[-1]["content"]
        # predicted = [read, write] (exec score=1.5 < threshold 2.0)
        assert json.dumps(_tool("read")) in carrier_content
        assert json.dumps(_tool("write")) in carrier_content
        # Excluded tools must NOT be in the carrier
        assert json.dumps(_tool("exec")) not in carrier_content
        assert json.dumps(_tool("ping")) not in carrier_content

    def test_does_not_mutate_ctx_messages(self):
        comp = self._build()
        ctx = _make_request()
        before_snapshot = json.dumps(ctx.messages)
        comp.compress(ctx)
        # ctx.messages must remain unchanged after compress
        assert json.dumps(ctx.messages) == before_snapshot

    def test_metrics_records_placement(self):
        comp = self._build()
        result = comp.compress(_make_request())
        assert result.metrics.details.get("placement") == "user_tail"

    def test_metrics_tokens_unchanged_by_placement(self):
        # `tokens_after` reports the SIZE OF THE PREDICTED SCHEMA SUBSET —
        # i.e. count_tools_tokens(filtered_tools) before placement rewrite.
        # The carrier-user content is a side artifact and intentionally not
        # counted here, so user_tail's `result.tools` being [] does NOT
        # zero out tokens_after. This keeps the metric comparable across
        # placements for the same predicted set.
        comp_schema = ToolCompressor(predictor_url=URL)
        comp_schema._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=4),
                ToolCandidate(name="exec", score=1.5),  # match _build (dropped)
            ],
        )
        comp_user_tail = self._build()

        ctx = _make_request()
        m_schema = comp_schema.compress(ctx).metrics
        m_user_tail = comp_user_tail.compress(ctx).metrics
        assert m_schema.tokens_after == m_user_tail.tokens_after

    def test_no_prediction_falls_back_to_full_carrier(self):
        # When nothing scores above threshold, trailing-carrier placements keep
        # placement CONSISTENT: the full schema is relocated into the carrier
        # with `tools` omitted — NOT a schema-style skip that would inject the
        # full tools up front and break the conversation's shared prefix.
        comp = ToolCompressor(predictor_url=URL, placement="user_tail")
        comp._predictor = FakePredictor(candidates=[])
        ctx = _make_request()  # tools=[read, write]
        original_n = len(ctx.messages)
        result = comp.compress(ctx)
        assert result.metrics.skip_reason is None
        assert result.metrics.details.get("no_prediction_fallback") is True
        assert result.tools is None
        # Full schema carried in a trailing carrier (both tools present).
        assert len(result.messages) == original_n + 1
        carrier = result.messages[-1]["content"]
        # _make_request() default tools carry descriptions "Read"/"Write".
        assert json.dumps(_tool("read", "Read")) in carrier
        assert json.dumps(_tool("write", "Write")) in carrier

    def test_genuine_skips_do_not_append_carrier(self):
        # no_task / no_tools remain clean skips (nothing to relocate).
        comp = ToolCompressor(predictor_url=URL, placement="user_tail")
        comp._predictor = FakePredictor(candidates=[])
        ctx = CompressionContext(
            messages=[{"role": "system", "content": "s"}],  # no user task
            tools=[_tool("read")],
        )
        result = comp.compress(ctx)
        assert result.metrics.skip_reason == "no_task"
        assert len(result.messages) == len(ctx.messages)
        assert result.tools == ctx.tools

    def test_predictor_failure_does_not_append_carrier(self):
        comp = ToolCompressor(predictor_url=URL, placement="user_tail")
        comp._predictor = FakePredictor(
            raise_exc=PredictorError("boom", component="x"),
        )
        ctx = _make_request()
        original_n = len(ctx.messages)
        result = comp.compress(ctx)
        assert result.metrics.error is not None
        assert len(result.messages) == original_n
        assert result.tools == ctx.tools

    def test_schema_placement_default_keeps_tools_in_field(self):
        comp = ToolCompressor(predictor_url=URL)  # default placement="schema"
        comp._predictor = FakePredictor(
            candidates=[ToolCandidate(name="read", score=5)],
        )
        ctx = _make_request()
        original_n = len(ctx.messages)
        result = comp.compress(ctx)
        # default schema mode: tools field carries predicted; messages untouched
        assert len(result.messages) == original_n
        assert len(result.tools) == 1
        assert result.tools[0]["function"]["name"] == "read"
        assert result.metrics.details.get("placement") == "schema"


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — placement="system_tail"
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorSystemTailPlacement:
    """system_tail puts the tools-block carrier at the messages tail with
    role=system. Avoids the user_tail OOD where Qwen/Qwen3.6-35B-A3B treats the
    trailing carrier as a fresh user request and re-executes the task."""

    def _build(self):
        comp = ToolCompressor(predictor_url=URL, placement="system_tail")
        comp._predictor = FakePredictor(
            candidates=[
                ToolCandidate(name="read", score=5),
                ToolCandidate(name="write", score=4),
            ],
        )
        return comp

    def test_result_tools_is_none(self):
        comp = self._build()
        result = comp.compress(_make_request())
        assert result.tools is None

    def test_carrier_role_is_system(self):
        comp = self._build()
        result = comp.compress(_make_request())
        assert result.messages[-1]["role"] == "system"

    def test_carrier_content_has_tools_block(self):
        comp = self._build()
        result = comp.compress(_make_request())
        carrier = result.messages[-1]["content"]
        # Same body as user_tail — disclaimer headers are NOT added (the
        # role itself signals "this is a system reminder, not a user req").
        assert carrier.startswith("# Tools\n\n")
        assert "<tools>" in carrier
        assert carrier.endswith("</IMPORTANT>")

    def test_metrics_records_placement(self):
        comp = self._build()
        result = comp.compress(_make_request())
        assert result.metrics.details.get("placement") == "system_tail"

    def test_no_prediction_falls_back_to_full_carrier(self):
        comp = ToolCompressor(predictor_url=URL, placement="system_tail")
        comp._predictor = FakePredictor(candidates=[])
        ctx = _make_request()
        original_n = len(ctx.messages)
        result = comp.compress(ctx)
        assert result.metrics.skip_reason is None
        assert result.metrics.details.get("no_prediction_fallback") is True
        assert result.tools is None
        carrier = result.messages[-1]
        assert carrier["role"] == "system"
        assert json.dumps(_tool("read", "Read")) in carrier["content"]
        assert len(result.messages) == original_n + 1


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — cumulative-append mode (accumulate=True)
# ─────────────────────────────────────────────────────────────────────────────


class _SeqPredictor:
    """Predictor returning a different candidate list on each successive call."""

    name = "seq_predictor"

    def __init__(self, sequences: list[list[str]]):
        self._seqs = sequences
        self.i = 0

    def predict(self, task, *, system_prompt):
        names = self._seqs[min(self.i, len(self._seqs) - 1)]
        self.i += 1
        return [ToolCandidate(name=n, score=5) for n in names], {}

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus
        return HealthStatus.healthy("seq")


def _convo(nturns: int, tools: list[dict]):
    msgs = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "research task X"},
    ]
    for _ in range(nturns):
        msgs += [{"role": "assistant", "content": "..."},
                 {"role": "tool", "content": "r"}]
    return CompressionContext(messages=msgs, tools=tools)


class TestToolCompressorAccumulate:
    ALL = [_tool("exec"), _tool("process"), _tool("web_search"),
           _tool("write"), _tool("read")]

    def _build(self, seqs, placement="schema"):
        comp = ToolCompressor(predictor_url=URL, placement=placement, accumulate=True)
        comp._predictor = _SeqPredictor(seqs)
        return comp

    def test_each_turn_strictly_extends_previous(self):
        # Emergent (web_search at turn 2) + reappearing (exec at turn 3) tools.
        comp = self._build([["exec"], ["process"], ["web_search"], ["exec", "write"]])
        prev: list[str] = []
        for t in range(4):
            result = comp.compress(_convo(t, self.ALL))
            names = [x["function"]["name"] for x in result.tools]
            assert names[:len(prev)] == prev, f"turn {t}: {names} not extension of {prev}"
            prev = names
        # Union accumulated, append order, no duplicates.
        assert prev == ["exec", "process", "web_search", "write"]

    def test_reappearing_tool_not_dropped(self):
        # Per-turn would drop exec on turn 1; accumulate keeps it.
        comp = self._build([["exec"], ["process"]])
        comp.compress(_convo(0, self.ALL))
        result = comp.compress(_convo(1, self.ALL))
        names = [x["function"]["name"] for x in result.tools]
        assert "exec" in names and "process" in names

    def test_separate_conversations_have_separate_state(self):
        comp = self._build([["exec"], ["write"]])
        r0 = comp.compress(_convo(0, self.ALL))  # conv A: [exec]
        # different first-user message → different conversation
        ctxB = CompressionContext(
            messages=[{"role": "system", "content": "You are an agent."},
                      {"role": "user", "content": "DIFFERENT task Y"}],
            tools=self.ALL)
        rB = comp.compress(ctxB)  # conv B: [write], must NOT include exec
        assert [x["function"]["name"] for x in r0.tools] == ["exec"]
        assert [x["function"]["name"] for x in rB.tools] == ["write"]

    def test_details_expose_accumulation(self):
        comp = self._build([["exec"], ["process"]])
        comp.compress(_convo(0, self.ALL))
        result = comp.compress(_convo(1, self.ALL))
        assert result.metrics.details.get("accumulate") is True
        assert result.metrics.details.get("accumulated_count") == 2
        assert result.metrics.details.get("predicted_count") == 1  # this turn only


# ─────────────────────────────────────────────────────────────────────────────
# render_tools_block helper
# ─────────────────────────────────────────────────────────────────────────────


class TestRenderToolsBlock:
    def test_empty_returns_empty(self):
        from adaptive_token_compressor.tool.compressor import render_tools_block
        assert render_tools_block([]) == ""

    def test_single_tool_structure(self):
        from adaptive_token_compressor.tool.compressor import render_tools_block
        block = render_tools_block([_tool("read", "Read a file")])
        # Header shape
        assert block.startswith("# Tools\n\nYou have access to the following functions:\n\n<tools>")
        # Single function entry
        assert json.dumps(_tool("read", "Read a file")) in block
        # Closing tag + footer
        assert "</tools>\n\nIf you choose to call a function" in block
        assert block.endswith("</IMPORTANT>")

    def test_byte_identical_to_chat_template(self):
        # If transformers is available, verify byte-equivalence to the
        # Qwen3.6 tokenizer's apply_chat_template output. This is a regression
        # canary — keeps render_tools_block aligned with Qwen/Qwen3.6-35B-A3B's
        # chat_template.jinja.
        pytest.importorskip("transformers")
        from pathlib import Path
        from transformers import AutoTokenizer
        from adaptive_token_compressor.tool.compressor import render_tools_block

        tok_path = (
            Path(__file__).resolve().parents[2]
            / "dev_tests" / "tokenizer_qwen3_coder"
        )
        if not tok_path.exists():
            pytest.skip(f"tokenizer fixture not at {tok_path}")
        tok = AutoTokenizer.from_pretrained(str(tok_path))

        tools = [
            _tool("read", "Read a file"),
            # Non-ASCII (→) + a nested schema key: guards ensure_ascii=False and
            # exact tojson serialization against the template.
            _tool("write", "Write a file → overwrites if it exists"),
        ]
        rendered = tok.apply_chat_template(
            [{"role": "system", "content": "X"}, {"role": "user", "content": "Y"}],
            tools=tools, tokenize=False, add_generation_prompt=False,
        )
        s = rendered.index("# Tools\n\n")
        e = rendered.index("</IMPORTANT>") + len("</IMPORTANT>")
        expected = rendered[s:e]
        assert render_tools_block(tools) == expected


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — placement="user_inline_delta" (delta carriers + hints)
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCompressorUserInlineDelta:
    ALL = [_tool("exec"), _tool("process"), _tool("web_search"),
           _tool("write"), _tool("read")]

    def _build(self, seqs):
        comp = ToolCompressor(
            predictor_url=URL, placement="user_inline_delta", accumulate=True,
        )
        comp._predictor = _SeqPredictor(seqs)
        return comp

    @staticmethod
    def _carriers(messages):
        """Raw `# Tools` carrier-content strings (delta or fallback)."""
        return [
            m["content"] for m in messages
            if m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("# Tools")
        ]

    def test_requires_accumulate_true(self):
        # Default accumulate=True is valid for this placement.
        ToolCompressor(predictor_url=URL, placement="user_inline_delta")
        # Explicit accumulate=False must be rejected for this placement.
        with pytest.raises(ConfigError):
            ToolCompressor(predictor_url=URL, placement="user_inline_delta",
                           accumulate=False)

    def test_result_tools_is_none_and_hints_injected(self):
        from adaptive_token_compressor.tool.compressor import (
            _INLINE_DELTA_SYSTEM_HINT, _INLINE_DELTA_TAIL_REMINDER,
        )
        comp = self._build([["exec"]])
        result = comp.compress(_convo(0, self.ALL))
        assert result.tools is None
        # Standing note appended to the system message (front, constant).
        sys_msg = next(m for m in result.messages if m["role"] == "system")
        assert sys_msg["content"].endswith(_INLINE_DELTA_SYSTEM_HINT)
        # Trailing recency reminder is the final message.
        assert result.messages[-1] == {
            "role": "user", "content": _INLINE_DELTA_TAIL_REMINDER,
        }

    def test_first_turn_carries_delta_tool(self):
        comp = self._build([["exec"]])
        result = comp.compress(_convo(0, self.ALL))
        assert json.dumps(_tool("exec")) in " ".join(self._carriers(result.messages))
        assert result.metrics.details["inline_delta_count"] == 1
        assert result.metrics.details["inline_carrier_count"] == 1
        assert result.metrics.details["accumulate"] is True

    def test_no_new_tool_turn_appends_no_carrier(self):
        # turn0 exec (new) → 1 carrier; turn1 exec again (nothing new) → still 1.
        comp = self._build([["exec"], ["exec"]])
        comp.compress(_convo(0, self.ALL))
        result = comp.compress(_convo(1, self.ALL))
        assert result.metrics.details["inline_delta_count"] == 0
        assert result.metrics.details["inline_carrier_count"] == 1
        # exec still visible mid-context via the replayed historical carrier.
        assert json.dumps(_tool("exec")) in " ".join(self._carriers(result.messages))

    def test_later_new_tool_carried_as_delta_only(self):
        comp = self._build([["exec"], ["process"]])
        comp.compress(_convo(0, self.ALL))
        result = comp.compress(_convo(1, self.ALL))
        assert result.metrics.details["inline_delta_count"] == 1
        assert result.metrics.details["inline_carrier_count"] == 2
        carriers = self._carriers(result.messages)
        joined = " ".join(carriers)
        assert json.dumps(_tool("exec")) in joined      # earlier carrier
        assert json.dumps(_tool("process")) in joined    # fresh delta carrier
        # No single carrier re-lists BOTH — proves delta split, not union re-list.
        assert not any(
            json.dumps(_tool("exec")) in c and json.dumps(_tool("process")) in c
            for c in carriers
        )

    @staticmethod
    def _strip_reminder(messages):
        from adaptive_token_compressor.tool.compressor import (
            _INLINE_DELTA_TAIL_REMINDER,
        )
        if (messages and messages[-1].get("role") == "user"
                and messages[-1].get("content") == _INLINE_DELTA_TAIL_REMINDER):
            return messages[:-1]
        return messages

    def test_strict_prefix_extension_across_turns(self):
        # Ignoring the (user-turn-gated) trailing reminder, each turn's message
        # list must be a strict prefix-extension of the previous turn's.
        comp = self._build([["exec"], ["process"], ["exec"]])
        prev_core = None
        for t in range(3):
            core = self._strip_reminder(comp.compress(_convo(t, self.ALL)).messages)
            if prev_core is not None:
                assert core[:len(prev_core)] == prev_core, f"turn {t} not extension"
            prev_core = core

    def test_reminder_gated_to_user_turns(self):
        from adaptive_token_compressor.tool.compressor import (
            _INLINE_DELTA_SYSTEM_HINT, _INLINE_DELTA_TAIL_REMINDER,
        )
        comp = self._build([["exec"], ["read"]])
        # turn 0: _convo(0) ends in the user task → genuine user turn → reminder.
        r0 = comp.compress(_convo(0, self.ALL))
        assert r0.messages[-1] == {
            "role": "user", "content": _INLINE_DELTA_TAIL_REMINDER,
        }
        # turn 1: _convo(1) ends in a tool result (mid-loop) → NO reminder,
        # but the system-front note is still injected.
        r1 = comp.compress(_convo(1, self.ALL))
        assert not (
            r1.messages[-1].get("role") == "user"
            and r1.messages[-1].get("content") == _INLINE_DELTA_TAIL_REMINDER
        )
        sys_msg = next(m for m in r1.messages if m["role"] == "system")
        assert sys_msg["content"].endswith(_INLINE_DELTA_SYSTEM_HINT)

    def test_no_prediction_fallback_shows_full_schema_unrecorded(self):
        comp = self._build([[]])  # predictor yields nothing
        result = comp.compress(_convo(0, self.ALL))
        assert result.tools is None
        assert result.metrics.details["no_prediction_fallback"] is True
        # Full schema carried, but NOT recorded (so it is not replayed forever).
        assert result.metrics.details["inline_carrier_count"] == 0
        joined = " ".join(self._carriers(result.messages))
        for tdef in self.ALL:
            assert json.dumps(tdef) in joined

    def test_does_not_mutate_ctx_messages(self):
        comp = self._build([["exec"]])
        ctx = _convo(0, self.ALL)
        before = json.dumps(ctx.messages)
        comp.compress(ctx)
        assert json.dumps(ctx.messages) == before

    # -- replay-reminder toggle (_INLINE_DELTA_REPLAY_REMINDER) --------------

    def test_replay_off_is_ephemeral(self, monkeypatch):
        # replay OFF: reminder is ephemeral (user-turn tail only), so a
        # subsequent mid-loop turn carries NO reminder anywhere.
        import adaptive_token_compressor.tool.compressor as C
        monkeypatch.setattr(C, "_INLINE_DELTA_REPLAY_REMINDER", False)
        from adaptive_token_compressor.tool.compressor import (
            _INLINE_DELTA_TAIL_REMINDER,
        )
        comp = self._build([["exec"], ["read"]])
        comp.compress(_convo(0, self.ALL))            # user turn (ends in user)
        r1 = comp.compress(_convo(1, self.ALL))       # mid-loop (ends in tool)
        assert not any(
            m.get("content") == _INLINE_DELTA_TAIL_REMINDER for m in r1.messages
        )

    def test_replay_on_persists_reminder_midcontext(self, monkeypatch):
        import adaptive_token_compressor.tool.compressor as C
        monkeypatch.setattr(C, "_INLINE_DELTA_REPLAY_REMINDER", True)
        comp = self._build([["exec"], ["read"]])
        # turn 0 (genuine user turn): reminder appears exactly once, at the tail.
        r0 = comp.compress(_convo(0, self.ALL))
        idx0 = [i for i, m in enumerate(r0.messages)
                if m.get("content") == C._INLINE_DELTA_TAIL_REMINDER]
        assert idx0 == [len(r0.messages) - 1]  # exactly one, at the tail
        # turn 1 (mid-loop, ends in tool): reminder REPLAYED once, mid-context,
        # NOT the final message → no trailing-carrier OOD.
        r1 = comp.compress(_convo(1, self.ALL))
        idx1 = [i for i, m in enumerate(r1.messages)
                if m.get("content") == C._INLINE_DELTA_TAIL_REMINDER]
        assert len(idx1) == 1, "replayed exactly once"
        assert idx1[0] < len(r1.messages) - 1, "mid-context, not the tail"
        # it sits right after the real user query (index of the first user msg).
        first_user = next(i for i, m in enumerate(r1.messages)
                          if m.get("role") == "user"
                          and not str(m.get("content", "")).startswith(("# Tools", "Reminder:")))
        assert idx1[0] > first_user
