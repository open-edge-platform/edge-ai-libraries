"""Tests for core/messages.py — covers plan §13 row `core/messages`."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.messages import (
    HARNESS_LIKE_ROLES,
    ROLE_ASSISTANT,
    ROLE_DEVELOPER,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    MessageAccessor,
)


# ─────────────────────────────────────────────────────────────────────────────
# MessageAccessor.text
# ─────────────────────────────────────────────────────────────────────────────


class TestText:
    def test_string_returns_verbatim(self):
        assert MessageAccessor.text("hello") == "hello"

    def test_empty_string(self):
        assert MessageAccessor.text("") == ""

    def test_none_returns_empty(self):
        assert MessageAccessor.text(None) == ""

    def test_multimodal_text_type(self):
        content = [{"type": "text", "text": "hi"}]
        assert MessageAccessor.text(content) == "hi"

    def test_multimodal_text_field_no_type(self):
        content = [{"text": "x", "lang": "en"}]
        assert MessageAccessor.text(content) == "x"

    def test_multimodal_content_field_fallback(self):
        content = [{"content": "y"}]
        assert MessageAccessor.text(content) == "y"

    def test_multimodal_unknown_dict_uses_sort_keys_json(self):
        # Dicts without text/content fall back to deterministic JSON dump.
        content = [{"foo": 1, "bar": 2}]
        result = MessageAccessor.text(content)
        # sort_keys=True → "bar" before "foo"
        assert result == '{"bar": 2, "foo": 1}'

    def test_multimodal_dict_dump_byte_stable(self):
        # Same input must produce byte-identical output across calls
        # (prefix-cache stability requirement).
        content = [{"z": 1, "a": 2, "m": 3}]
        a = MessageAccessor.text(content)
        b = MessageAccessor.text(content)
        assert a == b
        assert a == '{"a": 2, "m": 3, "z": 1}'

    def test_multimodal_mixed(self):
        content = [
            {"type": "text", "text": "a"},
            "raw",
            {"content": "b"},
            42,
        ]
        assert MessageAccessor.text(content) == "a\nraw\nb\n42"

    def test_multimodal_drops_empty_parts(self):
        # Empty parts shouldn't introduce "\n\n" gaps.
        content = [{"text": "a"}, {"text": ""}, {"text": "b"}]
        assert MessageAccessor.text(content) == "a\nb"

    def test_dict_fallback(self):
        # Non-list dict goes through str() — best-effort, not the common path.
        result = MessageAccessor.text({"role": "user", "content": "x"})
        assert "x" in result

    def test_int_fallback(self):
        assert MessageAccessor.text(42) == "42"


# ─────────────────────────────────────────────────────────────────────────────
# MessageAccessor.iter_by_role
# ─────────────────────────────────────────────────────────────────────────────


class TestIterByRole:
    def test_filters_by_single_role(self):
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
        result = list(MessageAccessor.iter_by_role(msgs, ROLE_USER))
        assert result == [(1, msgs[1])]

    def test_filters_by_multiple_roles(self):
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "developer", "content": "d"},
            {"role": "user", "content": "u"},
        ]
        result = list(MessageAccessor.iter_by_role(msgs, *HARNESS_LIKE_ROLES))
        assert [idx for idx, _ in result] == [0, 1]

    def test_yields_original_indices(self):
        # Indices must reference the original list, not a filtered subset.
        msgs = [{"role": "user"}, {"role": "tool"}, {"role": "user"}]
        result = list(MessageAccessor.iter_by_role(msgs, ROLE_USER))
        assert [idx for idx, _ in result] == [0, 2]

    def test_empty_roles_yields_nothing(self):
        msgs = [{"role": "user"}, {"role": "system"}]
        assert list(MessageAccessor.iter_by_role(msgs)) == []

    def test_empty_messages(self):
        assert list(MessageAccessor.iter_by_role([], ROLE_USER)) == []

    def test_no_match(self):
        msgs = [{"role": "tool"}]
        assert list(MessageAccessor.iter_by_role(msgs, ROLE_USER)) == []


# ─────────────────────────────────────────────────────────────────────────────
# MessageAccessor.find_last_user_message
# ─────────────────────────────────────────────────────────────────────────────


class TestFindLastUserMessage:
    def test_returns_last_user_message(self):
        msgs = [
            {"role": "user", "content": "first task"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second task"},
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (2, "second task")

    def test_skips_internal_context_marker(self):
        msgs = [
            {"role": "user", "content": "real task"},
            {
                "role": "user",
                "content": "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>\nsubagent result\n<<<END>>>",
            },
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "real task")

    def test_skips_session_startup(self):
        msgs = [
            {"role": "user", "content": "real task"},
            {"role": "user", "content": "[2026-04-16 02:00] A new session was started"},
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "real task")

    def test_strips_timestamp_prefix(self):
        msgs = [{"role": "user", "content": "[Thu 2026-04-16 02:00 GMT+8] do thing"}]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "do thing")

    def test_strips_sender_metadata(self):
        msgs = [
            {
                "role": "user",
                "content": (
                    'Sender (untrusted metadata): ```json\n{"label": "openclaw"}\n```\n'
                    "actual user request"
                ),
            }
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "actual user request")

    def test_strips_timestamp_after_sender(self):
        # Real-world ordering: sender metadata block, then timestamp, then text.
        msgs = [
            {
                "role": "user",
                "content": (
                    'Sender (untrusted metadata): ```json\n{"x": 1}\n```\n'
                    "[2026-04-16 02:00] inner task"
                ),
            }
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "inner task")

    def test_skips_empty_user_messages(self):
        msgs = [
            {"role": "user", "content": "real"},
            {"role": "user", "content": ""},
            {"role": "user", "content": "   "},
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "real")

    def test_returns_none_when_no_qualifying(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "ok"},
        ]
        assert MessageAccessor.find_last_user_message(msgs) is None

    def test_returns_none_when_only_framework_users(self):
        msgs = [
            {"role": "user", "content": "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>"},
            {"role": "user", "content": "[2026] A new session was started"},
        ]
        assert MessageAccessor.find_last_user_message(msgs) is None

    def test_skip_framework_false_returns_first_nonempty(self):
        msgs = [
            {"role": "user", "content": "real"},
            {"role": "user", "content": "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>"},
        ]
        # skip_framework=False: take last non-empty user verbatim.
        result = MessageAccessor.find_last_user_message(msgs, skip_framework=False)
        assert result == (1, "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>")

    def test_handles_multimodal_content(self):
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "[2026] hi there"}]}
        ]
        result = MessageAccessor.find_last_user_message(msgs)
        assert result == (0, "hi there")


# ─────────────────────────────────────────────────────────────────────────────
# MessageAccessor.replace_content
# ─────────────────────────────────────────────────────────────────────────────


class TestReplaceContent:
    def test_returns_new_list(self):
        msgs = [{"role": "user", "content": "x"}]
        result = MessageAccessor.replace_content(msgs, 0, "y")
        assert result is not msgs

    def test_does_not_mutate_input_list(self):
        msgs = [{"role": "user", "content": "x"}]
        snapshot = list(msgs)
        MessageAccessor.replace_content(msgs, 0, "y")
        assert msgs == snapshot

    def test_does_not_mutate_input_dict(self):
        original = {"role": "user", "content": "x"}
        msgs = [original]
        MessageAccessor.replace_content(msgs, 0, "y")
        assert original == {"role": "user", "content": "x"}

    def test_replaced_dict_is_new_object(self):
        msgs = [{"role": "user", "content": "x"}]
        result = MessageAccessor.replace_content(msgs, 0, "y")
        assert result[0] is not msgs[0]
        assert result[0]["content"] == "y"

    def test_other_dicts_share_reference(self):
        # Memory-efficient copy-on-write: only the replaced index gets a new dict.
        m0 = {"role": "system", "content": "s"}
        m1 = {"role": "user", "content": "u"}
        m2 = {"role": "assistant", "content": "a"}
        msgs = [m0, m1, m2]
        result = MessageAccessor.replace_content(msgs, 1, "U")
        assert result[0] is m0
        assert result[2] is m2

    def test_preserves_other_fields_in_replaced_msg(self):
        msgs = [{"role": "assistant", "content": "x", "tool_calls": [{"id": "t1"}]}]
        result = MessageAccessor.replace_content(msgs, 0, "y")
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"] == [{"id": "t1"}]
        assert result[0]["content"] == "y"

    def test_negative_idx_raises(self):
        with pytest.raises(IndexError):
            MessageAccessor.replace_content([{"role": "user"}], -1, "x")

    def test_out_of_range_raises(self):
        with pytest.raises(IndexError):
            MessageAccessor.replace_content([{"role": "user"}], 1, "x")

    def test_empty_list_raises(self):
        with pytest.raises(IndexError):
            MessageAccessor.replace_content([], 0, "x")


# ─────────────────────────────────────────────────────────────────────────────
# Role constants
# ─────────────────────────────────────────────────────────────────────────────


class TestRoleConstants:
    def test_role_values(self):
        assert ROLE_SYSTEM == "system"
        assert ROLE_DEVELOPER == "developer"
        assert ROLE_USER == "user"
        assert ROLE_ASSISTANT == "assistant"
        assert ROLE_TOOL == "tool"

    def test_harness_like_roles(self):
        assert HARNESS_LIKE_ROLES == ("system", "developer")
