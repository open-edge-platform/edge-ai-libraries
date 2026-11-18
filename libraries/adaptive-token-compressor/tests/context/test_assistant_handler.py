"""Tests for context/assistant_handler.py — tool_call args digest replacement.

Covers §13 row `context/assistant_handler` + T7 (pure-function determinism):
  render_arg_value (all types + marker shape + line-aligned slicing) /
  build_completed_tool_call_ids / compress_single_tool_call (4 gates) /
  compress_assistant_message (no-mutation).
"""
from __future__ import annotations

import json

from adaptive_token_compressor.context.assistant_handler import (
    _ARGS_DIGEST_THRESHOLD,
    _VALUE_INLINE_LIMIT,
    build_completed_tool_call_ids,
    compact_arg_value,
    compress_assistant_message,
    compress_single_tool_call,
    render_arg_value,
)


def _tool_call(tc_id: str, args: dict, name: str = "write") -> dict:
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


# ─────────────────────────────────────────────────────────────────────────────
# render_arg_value — type dispatch + marker shape
# ─────────────────────────────────────────────────────────────────────────────


class TestRenderArgValue:
    def test_none(self):
        assert render_arg_value(None) == "null"

    def test_bool_before_int(self):
        # bool is an int subclass — must render true/false, not 1/0.
        assert render_arg_value(True) == "true"
        assert render_arg_value(False) == "false"

    def test_int_float(self):
        assert render_arg_value(42) == "42"
        assert render_arg_value(3.5) == "3.5"

    def test_short_str_verbatim(self):
        s = "x" * _VALUE_INLINE_LIMIT
        assert render_arg_value(s) == s

    def test_long_str_marker(self):
        s = "A" * 500
        m = render_arg_value(s)
        assert m.startswith("<arg_preview kind=str chars=500 preview=")
        assert m.endswith(">")
        assert len(m) < len(s)

    def test_long_str_marker_shrinks_below_limit(self):
        # Any value over the gate collapses to a fixed ~316-char marker.
        m = render_arg_value("B" * 5000)
        assert len(m) < _VALUE_INLINE_LIMIT + 60

    def test_dict_kind_json(self):
        m = render_arg_value({"k": "v" * 500})
        assert "kind=json" in m

    def test_dict_short_inline(self):
        # Small dict serializes below the limit → returned verbatim JSON.
        out = render_arg_value({"a": 1})
        assert out == json.dumps({"a": 1}, ensure_ascii=False, sort_keys=True)

    def test_line_aligned_slicing(self):
        # Multi-line payload: marker preview should carry head + tail fragments.
        s = "\n".join(f"line{i}" for i in range(200))
        m = render_arg_value(s)
        assert "line0" in m
        assert "line199" in m
        assert "[...elided" in m

    def test_pure_deterministic(self):
        s = "C" * 800
        assert render_arg_value(s) == render_arg_value(s)


# ─────────────────────────────────────────────────────────────────────────────
# build_completed_tool_call_ids
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildCompletedToolCallIds:
    def test_collects_tool_result_ids(self):
        messages = [
            {"role": "assistant", "tool_calls": [_tool_call("a", {})]},
            {"role": "tool", "tool_call_id": "a", "content": "done"},
            {"role": "tool", "tool_call_id": "b", "content": "done"},
        ]
        assert build_completed_tool_call_ids(messages) == {"a", "b"}

    def test_ignores_non_tool_roles(self):
        messages = [
            {"role": "assistant", "tool_calls": [_tool_call("a", {})]},
            {"role": "user", "content": "hi"},
        ]
        assert build_completed_tool_call_ids(messages) == set()

    def test_ignores_missing_id(self):
        messages = [{"role": "tool", "content": "no id"}]
        assert build_completed_tool_call_ids(messages) == set()

    def test_real_conversation(self, conversation_history):
        ids = build_completed_tool_call_ids(conversation_history)
        assert len(ids) == 10  # 10 tool-result messages in the 24-msg fixture


# ─────────────────────────────────────────────────────────────────────────────
# compress_single_tool_call — 4 gates
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressSingleToolCall:
    def test_not_completed_untouched(self):
        tc = _tool_call("x", {"content": "A" * 1000})
        new, saved = compress_single_tool_call(tc, completed_ids=set())
        assert new is tc and saved == 0

    def test_short_args_untouched(self):
        tc = _tool_call("x", {"content": "short"})
        assert len(tc["function"]["arguments"]) <= _ARGS_DIGEST_THRESHOLD
        new, saved = compress_single_tool_call(tc, {"x"})
        assert new is tc and saved == 0

    def test_non_json_dict_args_untouched(self):
        tc = {"id": "x", "function": {"name": "f", "arguments": "A" * 500}}
        new, saved = compress_single_tool_call(tc, {"x"})
        assert new is tc and saved == 0

    def test_json_array_args_untouched(self):
        tc = {"id": "x", "function": {"name": "f", "arguments": json.dumps(["A" * 500])}}
        new, saved = compress_single_tool_call(tc, {"x"})
        assert new is tc and saved == 0

    def test_long_completed_args_compressed(self):
        tc = _tool_call("x", {"content": "A" * 1000, "path": "/tmp/f"})
        new, saved = compress_single_tool_call(tc, {"x"})
        assert new is not tc
        assert saved > 0
        rebuilt = json.loads(new["function"]["arguments"])
        assert "arg_preview" in rebuilt["content"]  # long value → marker
        assert rebuilt["path"] == "/tmp/f"          # short value verbatim

    def test_sort_keys_in_rebuilt_args(self):
        tc = _tool_call("x", {"zzz": "A" * 1000, "aaa": "B" * 1000})
        new, _ = compress_single_tool_call(tc, {"x"})
        arg_str = new["function"]["arguments"]
        assert arg_str.index('"aaa"') < arg_str.index('"zzz"')  # sorted

    def test_no_mutation_of_input(self):
        tc = _tool_call("x", {"content": "A" * 1000})
        original = json.loads(json.dumps(tc))  # deep copy
        compress_single_tool_call(tc, {"x"})
        assert tc == original

    def test_deterministic(self):
        tc = _tool_call("x", {"content": "A" * 1000})
        n1, _ = compress_single_tool_call(tc, {"x"})
        n2, _ = compress_single_tool_call(tc, {"x"})
        assert n1 == n2

    def test_json_types_preserved(self):
        # v7 §7.3: scalars and short containers keep their JSON type.
        args = {"content": "A" * 1000, "limit": 100, "ratio": 0.5, "force": True,
                "cwd": None, "tags": ["a", "b"], "opts": {"k": 1}}
        new, _ = compress_single_tool_call(_tool_call("x", args), {"x"})
        rebuilt = json.loads(new["function"]["arguments"])
        assert rebuilt["limit"] == 100
        assert rebuilt["ratio"] == 0.5
        assert rebuilt["force"] is True
        assert rebuilt["cwd"] is None
        assert rebuilt["tags"] == ["a", "b"]
        assert rebuilt["opts"] == {"k": 1}
        assert rebuilt["content"].startswith("<arg_preview")

    def test_below_min_saving_untouched(self):
        # Just over the 400-char gate, but the only long value is barely over
        # the inline limit → marker saves < 128 chars → keep the original.
        tc = _tool_call("x", {"content": "A" * (_VALUE_INLINE_LIMIT + 5), "p": "q" * 60})
        assert len(tc["function"]["arguments"]) > _ARGS_DIGEST_THRESHOLD
        new, saved = compress_single_tool_call(tc, {"x"})
        assert new is tc and saved == 0


class TestCompactArgValue:
    def test_scalars_native(self):
        for v in (None, True, False, 0, 42, 3.5):
            assert compact_arg_value(v) is v

    def test_short_containers_native(self):
        v = {"a": [1, 2]}
        assert compact_arg_value(v) is v

    def test_long_values_marker(self):
        assert compact_arg_value("A" * 500).startswith("<arg_preview kind=str")
        assert compact_arg_value({"k": "v" * 500}).startswith("<arg_preview kind=json")


# ─────────────────────────────────────────────────────────────────────────────
# compress_assistant_message
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressAssistantMessage:
    def test_no_tool_calls_untouched(self):
        msg = {"role": "assistant", "content": "hi"}
        new, saved = compress_assistant_message(msg, set())
        assert new is msg and saved == 0

    def test_sums_savings_across_calls(self):
        msg = {
            "role": "assistant",
            "tool_calls": [
                _tool_call("a", {"content": "A" * 1000}),
                _tool_call("b", {"content": "B" * 1000}),
            ],
        }
        new, saved = compress_assistant_message(msg, {"a", "b"})
        assert saved > 0
        assert new is not msg
        assert len(new["tool_calls"]) == 2

    def test_unchanged_calls_return_same_message(self):
        # v7 §7.2: pending / short calls → the very same object, 0 saved.
        msg = {"role": "assistant", "tool_calls": [
            _tool_call("a", {"content": "A" * 1000}),      # pending (not completed)
            _tool_call("b", {"path": "/tmp/f"}),           # short
        ]}
        new, saved = compress_assistant_message(msg, {"b"})
        assert new is msg and saved == 0

    def test_no_mutation(self):
        msg = {"role": "assistant", "tool_calls": [_tool_call("a", {"content": "A" * 1000})]}
        original = json.loads(json.dumps(msg))
        compress_assistant_message(msg, {"a"})
        assert msg == original

    def test_real_conversation_saves_tokens(self, conversation_history):
        completed = build_completed_tool_call_ids(conversation_history)
        total = 0
        for m in conversation_history:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                _, saved = compress_assistant_message(m, completed)
                total += saved
        assert total > 0