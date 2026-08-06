"""Tests for tool/message_extractors.py — pure function parsers over messages."""
from __future__ import annotations

import json

from adaptive_token_compressor.tool.message_extractors import (
    extract_call_history,
    extract_skill_content,
    extract_skills,
)


# ─────────────────────────────────────────────────────────────────────────────
# extract_skills
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractSkills:
    def test_simple_match(self):
        messages = [
            {
                "role": "system",
                "content": (
                    "Header.\n"
                    "<name>greet</name><description>Say hello</description>\n"
                    "<name>calc</name><description>Math</description>"
                ),
            }
        ]
        assert extract_skills(messages) == [("greet", "Say hello"), ("calc", "Math")]

    def test_developer_role_also_scanned(self):
        messages = [
            {
                "role": "developer",
                "content": "<name>foo</name><description>bar</description>",
            }
        ]
        assert extract_skills(messages) == [("foo", "bar")]

    def test_user_role_ignored(self):
        messages = [
            {
                "role": "user",
                "content": "<name>foo</name><description>bar</description>",
            }
        ]
        assert extract_skills(messages) == []

    def test_first_match_wins(self):
        # When multiple system messages have skills, first non-empty match wins.
        messages = [
            {
                "role": "system",
                "content": "<name>first</name><description>a</description>",
            },
            {
                "role": "system",
                "content": "<name>second</name><description>b</description>",
            },
        ]
        assert extract_skills(messages) == [("first", "a")]

    def test_no_match(self):
        assert extract_skills([{"role": "system", "content": "no skills here"}]) == []

    def test_empty_messages(self):
        assert extract_skills([]) == []

    def test_handles_literal_backslash_n(self):
        # JSON-encoded newline appears as the two characters '\\n'.
        messages = [
            {
                "role": "system",
                "content": "<name>x</name>\\n<description>y</description>",
            }
        ]
        assert extract_skills(messages) == [("x", "y")]

    def test_strips_whitespace(self):
        messages = [
            {
                "role": "system",
                "content": "<name>  spaced  </name><description>  desc  </description>",
            }
        ]
        assert extract_skills(messages) == [("spaced", "desc")]


# ─────────────────────────────────────────────────────────────────────────────
# extract_call_history
# ─────────────────────────────────────────────────────────────────────────────


def _ass_msg(tool_calls):
    return {"role": "assistant", "content": "", "tool_calls": tool_calls}


def _tc(tid, name, args):
    return {
        "id": tid,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _tool_result(tid, content):
    return {"role": "tool", "tool_call_id": tid, "content": content}


class TestExtractCallHistory:
    def test_basic_pairing(self):
        messages = [
            {"role": "user", "content": "task"},
            _ass_msg([_tc("c1", "read", {"path": "/foo"})]),
            _tool_result("c1", "file contents"),
            _ass_msg([_tc("c2", "exec", {"cmd": "ls"})]),
            _tool_result("c2", "output"),
        ]
        history = extract_call_history(messages)
        assert len(history) == 2
        assert history[0] == {
            "name": "read",
            "args": {"path": "/foo"},
            "result_preview": "file contents",
        }
        assert history[1] == {
            "name": "exec",
            "args": {"cmd": "ls"},
            "result_preview": "output",
        }

    def test_start_index_filters(self):
        messages = [
            _ass_msg([_tc("old", "exec", {"cmd": "x"})]),
            _tool_result("old", "old result"),
            {"role": "user", "content": "new task"},
            _ass_msg([_tc("new", "read", {"path": "/p"})]),
            _tool_result("new", "new result"),
        ]
        # start_index=2 keeps only the new task and after.
        history = extract_call_history(messages, start_index=2)
        assert len(history) == 1
        assert history[0]["name"] == "read"

    def test_negative_start_index_treated_as_zero(self):
        messages = [
            _ass_msg([_tc("c", "exec", {"cmd": "x"})]),
            _tool_result("c", "ok"),
        ]
        assert extract_call_history(messages, start_index=-5) == [
            {"name": "exec", "args": {"cmd": "x"}, "result_preview": "ok"}
        ]

    def test_result_preview_truncated_at_150(self):
        big = "Z" * 300
        messages = [
            _ass_msg([_tc("c", "exec", {"cmd": "x"})]),
            _tool_result("c", big),
        ]
        history = extract_call_history(messages)
        assert history[0]["result_preview"] == "Z" * 150 + "..."

    def test_invalid_args_become_empty_dict(self):
        messages = [
            _ass_msg([
                {
                    "id": "c",
                    "type": "function",
                    "function": {"name": "exec", "arguments": "not json"},
                }
            ]),
            _tool_result("c", "ok"),
        ]
        history = extract_call_history(messages)
        assert history[0]["args"] == {}

    def test_missing_tool_result_yields_empty_preview(self):
        messages = [
            _ass_msg([_tc("c", "read", {"p": "x"})]),
            # No matching tool message.
        ]
        history = extract_call_history(messages)
        assert history[0]["result_preview"] == ""

    def test_assistant_without_tool_calls_skipped(self):
        messages = [
            {"role": "assistant", "content": "hi"},  # no tool_calls field
            _ass_msg([]),  # empty tool_calls list
        ]
        assert extract_call_history(messages) == []


# ─────────────────────────────────────────────────────────────────────────────
# extract_skill_content
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractSkillContent:
    def test_finds_recent_skill_md(self):
        messages = [
            {"role": "user", "content": "task"},
            _ass_msg([_tc("c1", "read", {"path": "/skills/foo/SKILL.md"})]),
            _tool_result("c1", "Skill body."),
        ]
        assert extract_skill_content(messages) == "Skill body."

    def test_case_insensitive_match(self):
        messages = [
            _ass_msg([_tc("c", "read", {"path": "/X/skill.md"})]),
            _tool_result("c", "lowercase"),
        ]
        assert extract_skill_content(messages) == "lowercase"

    def test_returns_most_recent(self):
        messages = [
            _ass_msg([_tc("c1", "read", {"path": "/a/SKILL.md"})]),
            _tool_result("c1", "first"),
            _ass_msg([_tc("c2", "read", {"path": "/b/SKILL.md"})]),
            _tool_result("c2", "second"),
        ]
        # Reverse scan returns the *latest* read.
        assert extract_skill_content(messages) == "second"

    def test_non_skill_read_ignored(self):
        messages = [
            _ass_msg([_tc("c", "read", {"path": "/regular/file.py"})]),
            _tool_result("c", "code"),
        ]
        assert extract_skill_content(messages) is None

    def test_non_read_tool_ignored(self):
        messages = [
            _ass_msg([_tc("c", "edit", {"path": "/x/SKILL.md"})]),
            _tool_result("c", "edited"),
        ]
        assert extract_skill_content(messages) is None

    def test_max_chars_truncation(self):
        big = "A" * 1000
        messages = [
            _ass_msg([_tc("c", "read", {"path": "/x/SKILL.md"})]),
            _tool_result("c", big),
        ]
        assert extract_skill_content(messages, max_chars=10) == "A" * 10 + "..."

    def test_max_chars_none_returns_full(self):
        big = "B" * 1000
        messages = [
            _ass_msg([_tc("c", "read", {"path": "/x/SKILL.md"})]),
            _tool_result("c", big),
        ]
        assert extract_skill_content(messages, max_chars=None) == big

    def test_start_index_filter(self):
        messages = [
            _ass_msg([_tc("old", "read", {"path": "/old/SKILL.md"})]),
            _tool_result("old", "old skill"),
            {"role": "user", "content": "new"},
        ]
        # start_index=2 drops the old read entirely.
        assert extract_skill_content(messages, start_index=2) is None

    def test_no_messages(self):
        assert extract_skill_content([]) is None

    def test_empty_tool_result_returns_none(self):
        messages = [
            _ass_msg([_tc("c", "read", {"path": "/x/SKILL.md"})]),
            _tool_result("c", ""),
        ]
        assert extract_skill_content(messages) is None
