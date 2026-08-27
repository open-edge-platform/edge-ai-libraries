"""Tests for tool/prompts.py — template constants + builder functions."""
from __future__ import annotations

from adaptive_token_compressor.tool.prompts import (
    BASE_PROMPT,
    FOCUS_FIVE_TOOL_PROMPT,
    build_dynamic_prediction_prompt,
    build_static_prediction_prompt,
)


# ─────────────────────────────────────────────────────────────────────────────
# Template constants
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplateConstants:
    def test_focus_five_has_placeholder(self):
        assert "{tool_descriptions}" in FOCUS_FIVE_TOOL_PROMPT

    def test_base_prompt_has_placeholder(self):
        assert "{tool_descriptions}" in BASE_PROMPT

    def test_focus_five_strict_count(self):
        # Must convey "exactly 5 to 10" — that's the benchmark guarantee.
        assert "EXACTLY 5 to 10 tools" in FOCUS_FIVE_TOOL_PROMPT

    def test_base_prompt_minimal_no_rules(self):
        # BASE_PROMPT is a *header* — rules are appended by the dynamic
        # builder. Check we haven't accidentally inlined them.
        assert "Output JSON only" not in BASE_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# build_static_prediction_prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildStaticPredictionPrompt:
    def test_fills_placeholder(self):
        result = build_static_prediction_prompt(
            template="HEADER\n{tool_descriptions}\nFOOTER",
            tool_descriptions="- read: x",
        )
        assert result == "HEADER\n- read: x\nFOOTER"

    def test_static_with_focus_five_template(self):
        result = build_static_prediction_prompt(
            template=FOCUS_FIVE_TOOL_PROMPT,
            tool_descriptions="- read: rd",
        )
        assert "- read: rd" in result
        assert "EXACTLY 5 to 10 tools" in result

    def test_no_extra_sections_appended(self):
        # Static path must NOT add the dynamic rules tail.
        result = build_static_prediction_prompt(
            template="X={tool_descriptions}",
            tool_descriptions="Y",
        )
        assert result == "X=Y"

    def test_pure_function_idempotent(self):
        a = build_static_prediction_prompt(
            template=FOCUS_FIVE_TOOL_PROMPT, tool_descriptions="- read: x",
        )
        b = build_static_prediction_prompt(
            template=FOCUS_FIVE_TOOL_PROMPT, tool_descriptions="- read: x",
        )
        assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# build_dynamic_prediction_prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildDynamicPredictionPrompt:
    def test_minimal_no_sections(self):
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="- read: rd",
        )
        # Header + tail only.
        assert "- read: rd" in result
        assert "Output JSON only" in result
        # No skills / history sections.
        assert "available skills" not in result
        assert "Completed tool calls" not in result

    def test_skills_section_appended(self):
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="- read: rd",
            skills=[("greet", "Say hello"), ("calc", "Do math")],
        )
        assert "available skills" in result
        assert "  - greet: Say hello" in result
        assert "  - calc: Do math" in result

    def test_skill_content_takes_precedence_over_skills(self):
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="- read: rd",
            skills=[("greet", "Say hello")],
            skill_content="This is the SKILL.md content.",
        )
        # skill_content branch: SKILL.md excerpt block, skills list NOT shown.
        assert "SKILL.md excerpt" in result
        assert "This is the SKILL.md content." in result
        assert "available skills" not in result

    def test_skill_content_subagent_hint_injected(self):
        # When the SKILL.md mentions Sub-agent, the hint goes after the *first* match.
        skill_content = "Step 1: Sub-agent X must run.\nStep 2: do thing."
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            skill_content=skill_content,
        )
        assert "必须调用sessions_spawn" in result

    def test_skill_content_no_match_no_hint(self):
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            skill_content="Just plain content with no agent references.",
        )
        assert "必须调用sessions_spawn" not in result

    def test_call_history_section(self):
        history = [
            {"name": "read", "args": {"path": "/foo"}, "result_preview": "ok"},
            {"name": "exec", "args": {"cmd": "ls"}, "result_preview": ""},
        ]
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            call_history=history,
        )
        assert "Completed tool calls so far" in result
        assert "  1. read(path=/foo) -> ok" in result
        # Empty result_preview suppresses the "-> ..." suffix.
        assert "  2. exec(cmd=ls)" in result
        assert "  2. exec(cmd=ls) ->" not in result

    def test_call_history_long_value_truncated(self):
        long_arg = "X" * 200
        history = [{"name": "write", "args": {"text": long_arg}, "result_preview": ""}]
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            call_history=history,
        )
        # Args truncated at 60 chars + '...'.
        assert "X" * 60 + "..." in result
        # Full 200-char value is NOT in the result.
        assert "X" * 200 not in result

    def test_call_history_long_result_truncated(self):
        long_result = "Y" * 200
        history = [{"name": "exec", "args": {"cmd": "x"}, "result_preview": long_result}]
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            call_history=history,
        )
        assert "Y" * 80 + "..." in result
        assert "Y" * 200 not in result

    def test_call_history_only_first_two_args(self):
        history = [
            {
                "name": "exec",
                "args": {"a": "1", "b": "2", "c": "3"},
                "result_preview": "",
            }
        ]
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
            call_history=history,
        )
        # Only first two args rendered.
        assert "a=1" in result
        assert "b=2" in result
        assert "c=3" not in result

    def test_pure_function_idempotent(self):
        kwargs = dict(
            template=BASE_PROMPT,
            tool_descriptions="- x: y",
            skills=[("s", "d")],
            call_history=[{"name": "exec", "args": {"cmd": "ls"}, "result_preview": "ok"}],
            skill_content=None,
        )
        a = build_dynamic_prediction_prompt(**kwargs)
        b = build_dynamic_prediction_prompt(**kwargs)
        assert a == b

    def test_rules_tail_always_present(self):
        result = build_dynamic_prediction_prompt(
            template=BASE_PROMPT,
            tool_descriptions="x",
        )
        assert "Output JSON only" in result
        assert "MUST also include read" in result
