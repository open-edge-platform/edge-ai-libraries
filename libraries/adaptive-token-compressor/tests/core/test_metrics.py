"""Tests for core/metrics.py — covers plan §13 row `core/metrics`."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.metrics import (
    HARNESS_LIKE_ROLES,
    CompressionScope,
    CompressorMetrics,
    count_messages_tokens,
    count_tools_tokens,
    count_total_tokens,
    estimate_tokens,
)


# ─────────────────────────────────────────────────────────────────────────────
# CompressorMetrics properties
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressorMetricsProperties:
    def _m(self, **overrides) -> CompressorMetrics:
        defaults = dict(
            name="test",
            scope=CompressionScope.HARNESS,
            tokens_before=100,
            tokens_after=60,
            duration_ms=5.0,
        )
        defaults.update(overrides)
        return CompressorMetrics(**defaults)

    def test_saved_tokens(self):
        m = self._m(tokens_before=100, tokens_after=60)
        assert m.saved_tokens == 40

    def test_saved_tokens_zero_input(self):
        m = self._m(tokens_before=0, tokens_after=0)
        assert m.saved_tokens == 0

    def test_saved_tokens_negative_when_inflated(self):
        # Library never produces this in practice, but the math should not lie.
        m = self._m(tokens_before=10, tokens_after=20)
        assert m.saved_tokens == -10

    def test_compression_ratio_normal(self):
        m = self._m(tokens_before=100, tokens_after=60)
        assert m.compression_ratio == 0.6

    def test_compression_ratio_zero_input_returns_one(self):
        m = self._m(tokens_before=0, tokens_after=0)
        assert m.compression_ratio == 1.0

    def test_compression_ratio_zero_input_with_nonzero_output(self):
        # Edge case: tokens_after > 0 with tokens_before == 0 still returns 1.0.
        m = self._m(tokens_before=0, tokens_after=10)
        assert m.compression_ratio == 1.0

    def test_compression_ratio_unchanged(self):
        m = self._m(tokens_before=100, tokens_after=100)
        assert m.compression_ratio == 1.0

    # succeeded truth table — plan §13 row explicitly enumerates all 4 cases.

    def test_succeeded_when_clean(self):
        m = self._m(error=None, skip_reason=None)
        assert m.succeeded is True

    def test_not_succeeded_when_error_set(self):
        m = self._m(error="backend_timeout", skip_reason=None)
        assert m.succeeded is False

    def test_not_succeeded_when_skip_reason_set(self):
        m = self._m(error=None, skip_reason="min_chars")
        assert m.succeeded is False

    def test_not_succeeded_when_both_set(self):
        m = self._m(error="x", skip_reason="y")
        assert m.succeeded is False

    def test_details_default_is_independent_dict(self):
        m1 = self._m()
        m2 = self._m()
        m1.details["x"] = 1
        # field(default_factory=dict) must give each instance its own dict.
        assert m2.details == {}


# ─────────────────────────────────────────────────────────────────────────────
# CompressionScope
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressionScope:
    def test_values(self):
        assert {s.value for s in CompressionScope} == {"harness", "tool"}

    def test_string_compatible(self):
        # str subclass — comparable to plain strings
        assert CompressionScope.HARNESS == "harness"


# ─────────────────────────────────────────────────────────────────────────────
# estimate_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        assert estimate_tokens("") == 0

    def test_none_treated_as_empty(self):
        # not str → falsy → 0; defensive for surprising callers.
        assert estimate_tokens(None) == 0  # type: ignore[arg-type]

    def test_short_text_returns_positive(self):
        assert estimate_tokens("hello world") > 0

    def test_longer_text_returns_more(self):
        a = estimate_tokens("hi")
        b = estimate_tokens("hello there how are you doing today")
        assert b > a

    def test_deterministic(self):
        # Same input → same output (essential for prefix-cache stability).
        s = "Hello, world! Some sample text for tokenization."
        assert estimate_tokens(s) == estimate_tokens(s)

    def test_fallback_path(self, monkeypatch):
        # Force the len // 4 fallback by removing the encoder.
        import adaptive_token_compressor.core.metrics as mod

        monkeypatch.setattr(mod, "_encoder", None)
        # 8 chars / 4 = 2
        assert mod.estimate_tokens("12345678") == 2

    def test_fallback_min_one_for_nonempty(self, monkeypatch):
        # max(1, len//4) — must not return 0 for non-empty text on fallback.
        import adaptive_token_compressor.core.metrics as mod

        monkeypatch.setattr(mod, "_encoder", None)
        assert mod.estimate_tokens("hi") == 1
        assert mod.estimate_tokens("a") == 1


# ─────────────────────────────────────────────────────────────────────────────
# count_messages_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestCountMessagesTokens:
    def test_no_filter_counts_all(self):
        msgs = [
            {"role": "system", "content": "system prompt here"},
            {"role": "user", "content": "user task"},
        ]
        total = count_messages_tokens(msgs)
        assert total > 0

    def test_role_filter_harness(self):
        msgs = [
            {"role": "system", "content": "abc"},
            {"role": "user", "content": "def"},
        ]
        # Only "abc" counted under harness roles.
        h = count_messages_tokens(msgs, roles=HARNESS_LIKE_ROLES)
        u = count_messages_tokens(msgs, roles=("user",))
        all_ = count_messages_tokens(msgs)
        assert h + u == all_

    def test_explicit_empty_roles_returns_zero(self):
        msgs = [{"role": "system", "content": "abc"}]
        assert count_messages_tokens(msgs, roles=()) == 0

    def test_assistant_tool_calls_counted(self):
        # tool_calls must contribute to the before/after token delta.
        with_calls = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "t1",
                        "function": {
                            "name": "exec",
                            "arguments": '{"cmd": "ls -la /tmp"}',
                        },
                    }
                ],
            }
        ]
        without_calls = [{"role": "assistant", "content": "", "tool_calls": []}]
        assert count_messages_tokens(with_calls) > count_messages_tokens(without_calls)

    def test_tool_call_args_change_reflected(self):
        # Compressing tool_calls.arguments must produce smaller token count.
        big_args = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "write", "arguments": "x" * 5000}}
            ],
        }
        small_args = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "write", "arguments": "<arg_preview>"}}],
        }
        assert count_messages_tokens([big_args]) > count_messages_tokens([small_args])

    def test_skips_non_dict_entries(self):
        # Defensive against caller serialization quirks.
        msgs = [
            {"role": "user", "content": "abc"},
            "not a dict",  # type: ignore[list-item]
            None,  # type: ignore[list-item]
        ]
        # Should not raise; non-dicts skipped.
        assert count_messages_tokens(msgs) > 0  # type: ignore[arg-type]

    def test_developer_role_counted_with_harness_filter(self):
        msgs = [{"role": "developer", "content": "instructions"}]
        h = count_messages_tokens(msgs, roles=HARNESS_LIKE_ROLES)
        assert h > 0

    def test_empty_messages(self):
        assert count_messages_tokens([]) == 0
        assert count_messages_tokens([], roles=("user",)) == 0

    def test_role_not_in_filter_excluded(self):
        msgs = [{"role": "tool", "content": "result"}]
        assert count_messages_tokens(msgs, roles=HARNESS_LIKE_ROLES) == 0


# ─────────────────────────────────────────────────────────────────────────────
# count_tools_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestCountToolsTokens:
    def test_none_returns_zero(self):
        assert count_tools_tokens(None) == 0

    def test_empty_list_returns_zero(self):
        assert count_tools_tokens([]) == 0

    def test_single_tool(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "exec",
                    "description": "Run shell command",
                    "parameters": {"type": "object"},
                },
            }
        ]
        assert count_tools_tokens(tools) > 0

    def test_more_tools_more_tokens(self):
        one = [{"type": "function", "function": {"name": "a", "description": "x"}}]
        two = [
            {"type": "function", "function": {"name": "a", "description": "x"}},
            {"type": "function", "function": {"name": "b", "description": "y"}},
        ]
        assert count_tools_tokens(two) > count_tools_tokens(one)

    def test_byte_stable(self):
        # sort_keys + indent=2 must produce identical token count across runs.
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "exec",
                    "parameters": {"type": "object", "properties": {"z": {}, "a": {}}},
                },
            }
        ]
        assert count_tools_tokens(tools) == count_tools_tokens(tools)


# ─────────────────────────────────────────────────────────────────────────────
# count_total_tokens
# ─────────────────────────────────────────────────────────────────────────────


class TestCountTotalTokens:
    def test_messages_plus_tools(self):
        msgs = [{"role": "user", "content": "hello"}]
        tools = [{"type": "function", "function": {"name": "x"}}]
        msg_count = count_messages_tokens(msgs)
        tool_count = count_tools_tokens(tools)
        assert count_total_tokens(msgs, tools) == msg_count + tool_count

    def test_no_tools_equals_messages_only(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert count_total_tokens(msgs) == count_messages_tokens(msgs)
        assert count_total_tokens(msgs, None) == count_messages_tokens(msgs)
        assert count_total_tokens(msgs, []) == count_messages_tokens(msgs)

    def test_empty_inputs(self):
        assert count_total_tokens([], None) == 0
        assert count_total_tokens([], []) == 0
