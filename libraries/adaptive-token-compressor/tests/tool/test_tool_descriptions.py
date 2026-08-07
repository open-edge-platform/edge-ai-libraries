"""Tests for tool/tool_descriptions.py — covers default constant + dynamic builder."""
from __future__ import annotations

from adaptive_token_compressor.tool.tool_descriptions import (
    DEFAULT_TOOL_DESCRIPTIONS,
    build_dynamic_tool_descriptions,
)


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT_TOOL_DESCRIPTIONS — sanity checks (regression-friendly)
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultToolDescriptions:
    def test_starts_with_header(self):
        assert DEFAULT_TOOL_DESCRIPTIONS.startswith("Available tools (name: description):")

    def test_includes_core_tools(self):
        # A handful of representative tools from the legacy hardcoded list.
        for tool in ("read", "write", "exec", "web_search", "sessions_spawn"):
            assert f"\n- {tool}:" in DEFAULT_TOOL_DESCRIPTIONS

    def test_one_line_per_tool(self):
        # 22 tools + 1 header line; legacy list has the same count.
        lines = [ln for ln in DEFAULT_TOOL_DESCRIPTIONS.splitlines() if ln.strip()]
        assert len(lines) == 23
        # Every non-header line begins with "- ".
        for ln in lines[1:]:
            assert ln.startswith("- ")


# ─────────────────────────────────────────────────────────────────────────────
# build_dynamic_tool_descriptions
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildDynamicToolDescriptions:
    def test_none_returns_empty(self):
        assert build_dynamic_tool_descriptions(None) == ""

    def test_empty_list_returns_empty(self):
        assert build_dynamic_tool_descriptions([]) == ""

    def test_simple_pair(self):
        tools = [
            {"type": "function", "function": {"name": "read", "description": "Read a file"}},
            {"type": "function", "function": {"name": "write", "description": "Write a file"}},
        ]
        result = build_dynamic_tool_descriptions(tools)
        assert result == "- read: Read a file\n- write: Write a file"

    def test_empty_description_renders_name_only(self):
        tools = [{"type": "function", "function": {"name": "ping", "description": ""}}]
        assert build_dynamic_tool_descriptions(tools) == "- ping"

    def test_internal_newlines_collapsed_to_spaces(self):
        tools = [
            {
                "type": "function",
                "function": {"name": "edit", "description": "First line\nSecond line"},
            }
        ]
        assert build_dynamic_tool_descriptions(tools) == "- edit: First line Second line"

    def test_skips_non_function_entries(self):
        tools = [
            {"type": "code_interpreter"},
            {"type": "function", "function": {"name": "read", "description": "rd"}},
            "not-a-dict",  # type: ignore[list-item]
        ]
        assert build_dynamic_tool_descriptions(tools) == "- read: rd"

    def test_empty_name_skipped(self):
        tools = [
            {"type": "function", "function": {"name": "", "description": "anonymous"}},
            {"type": "function", "function": {"name": "real", "description": "ok"}},
        ]
        assert build_dynamic_tool_descriptions(tools) == "- real: ok"

    def test_name_is_stripped(self):
        tools = [
            {"type": "function", "function": {"name": "  read  ", "description": "x"}},
        ]
        assert build_dynamic_tool_descriptions(tools) == "- read: x"

    def test_input_order_preserved(self):
        tools = [
            {"type": "function", "function": {"name": "z_first", "description": "z"}},
            {"type": "function", "function": {"name": "a_second", "description": "a"}},
        ]
        # Output respects input order (no alphabetical sort).
        result = build_dynamic_tool_descriptions(tools)
        assert result.splitlines()[0].startswith("- z_first")
        assert result.splitlines()[1].startswith("- a_second")
