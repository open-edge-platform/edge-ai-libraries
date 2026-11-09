"""Tests for context/tool_handler.py — pure functions over tool-message content.

Covers §13 row `context/tool_handler` + T7 (pure-function determinism):
  classify (4 categories, order) / STATUS_PATTERNS / is_status_message /
  simplify_error / web_search_strip (+ _clean_snippet noise stripping).
"""
from __future__ import annotations

import json

from adaptive_token_compressor.context.tool_handler import (
    ToolContentCategory,
    classify,
    is_status_message,
    simplify_error,
    web_search_strip,
)


# ─────────────────────────────────────────────────────────────────────────────
# classify — 4 categories, order matters (first match wins)
# ─────────────────────────────────────────────────────────────────────────────


class TestClassify:
    def test_status_no_new_output(self):
        assert classify("(no new output)") is ToolContentCategory.STATUS

    def test_status_command_still_running(self):
        assert classify("Command still running after 30s") is ToolContentCategory.STATUS

    def test_status_no_output(self):
        assert classify("(no output)") is ToolContentCategory.STATUS

    def test_status_with_leading_trailing_whitespace(self):
        assert classify("  (no output)  \n") is ToolContentCategory.STATUS

    def test_error_json(self):
        c = '{"status":"error","tool":"bash","error":"boom"}'
        assert classify(c) is ToolContentCategory.ERROR

    def test_web_search_json(self):
        c = '{"query":"x","results":[{"title":"t","snippet":"s"}]}'
        assert classify(c) is ToolContentCategory.WEB_SEARCH

    def test_web_search_empty_results_still_web_search(self):
        assert classify('{"query":"x","results":[]}') is ToolContentCategory.WEB_SEARCH

    def test_error_wins_over_web_search(self):
        # A payload that is both status==error and has results[] → ERROR first.
        c = '{"status":"error","tool":"web","error":"rate limit","results":[]}'
        assert classify(c) is ToolContentCategory.ERROR

    def test_write_confirm_falls_into_other(self):
        # No separate WRITE_CONFIRM category — short template lands in OTHER
        # (main compressor's min_chars gate handles the passthrough).
        c = "Successfully wrote 9548 bytes to /home/x/report.html"
        assert classify(c) is ToolContentCategory.OTHER

    def test_plain_text_is_other(self):
        assert classify("根据您提供的资料...") is ToolContentCategory.OTHER

    def test_non_error_json_is_other(self):
        assert classify('{"status":"ok","value":1}') is ToolContentCategory.OTHER

    def test_json_list_not_dict_is_other(self):
        assert classify('[1, 2, 3]') is ToolContentCategory.OTHER

    def test_malformed_json_is_other(self):
        assert classify('{"status": "error"') is ToolContentCategory.OTHER

    def test_sample_A_idx5_poll_still_running_is_status(self):
        # Real prefix-cache sample A [5] (OpenClaw 2026.3.24 process poll).
        # Plan §6.6.1 kept it OTHER because STATUS used to be elided; v0_1
        # keeps a STATUS without a session verbatim, so it is STATUS now
        # (2026-10-16: the old `^\(no new output\)$` never matched real logs).
        c = "(no new output)\n\nProcess still running."
        assert classify(c) is ToolContentCategory.STATUS

    def test_poll_exited_is_other(self):
        # The exit outcome is information, not a status.
        for c in ["(no new output)\n\nProcess exited with code 0.",
                  "(no new output)\n\nProcess exited with code 1.",
                  "(no new output)\n\nProcess exited with signal SIGTERM."]:
            assert classify(c) is ToolContentCategory.OTHER

    def test_idempotent(self):
        for c in ["(no output)", '{"status":"error","tool":"x","error":"y"}', "plain"]:
            assert classify(c) is classify(c)


# ─────────────────────────────────────────────────────────────────────────────
# is_status_message — boundaries
# ─────────────────────────────────────────────────────────────────────────────


class TestIsStatusMessage:
    def test_matches_three_patterns(self):
        assert is_status_message("(no new output)")
        assert is_status_message("Command still running")
        assert is_status_message("(no output)")

    def test_command_still_running_prefix_match(self):
        # Pattern is a prefix (no `$`) — trailing detail still matches.
        assert is_status_message("Command still running for 45 seconds")

    def test_no_new_output_only_still_running_suffix(self):
        assert is_status_message("(no new output)\n\nProcess still running.")
        assert is_status_message("  (no new output)\nProcess still running.\n")
        assert not is_status_message("(no new output)\n\nProcess still running. pid 42")
        assert not is_status_message("(no new output)\nbut here is more")

    def test_no_output_must_be_exact(self):
        # `^\(no output\)$` — trailing content breaks the match.
        assert not is_status_message("(no output)\nbut here is more")

    def test_empty_string(self):
        assert not is_status_message("")

    def test_whitespace_only(self):
        assert not is_status_message("   \n  ")

    def test_plain_text(self):
        assert not is_status_message("some real tool output")


# ─────────────────────────────────────────────────────────────────────────────
# simplify_error
# ─────────────────────────────────────────────────────────────────────────────


class TestSimplifyError:
    def test_basic(self):
        c = '{"status":"error","tool":"bash","error":"command not found"}'
        assert simplify_error(c) == "bash failed: command not found"

    def test_missing_tool_defaults(self):
        c = '{"status":"error","error":"boom"}'
        assert simplify_error(c) == "tool failed: boom"

    def test_non_error_json_passthrough(self):
        c = '{"status":"ok","value":1}'
        assert simplify_error(c) == c

    def test_non_json_passthrough(self):
        assert simplify_error("just text") == "just text"

    def test_json_list_passthrough(self):
        assert simplify_error("[1,2,3]") == "[1,2,3]"

    def test_extra_fields_passthrough(self):
        # Dropping unknown fields would lose information → keep verbatim.
        c = '{"status":"error","tool":"exec","error":"boom","exitCode":2}'
        assert simplify_error(c) == c

    def test_non_string_error_passthrough(self):
        c = '{"status":"error","tool":"x","error":{"code":1}}'
        assert simplify_error(c) == c

    def test_idempotent(self):
        c = '{"status":"error","tool":"x","error":"y"}'
        once = simplify_error(c)
        assert simplify_error(once) == once  # 'x failed: y' is not error JSON

    def test_pure_same_input_same_output(self):
        c = '{"status":"error","tool":"grep","error":"no match"}'
        assert simplify_error(c) == simplify_error(c)


# ─────────────────────────────────────────────────────────────────────────────
# web_search_strip + _clean_snippet (real Tavily fixture)
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSearchStrip:
    def test_starts_with_query(self, tavily_content, tavily_payload):
        out = web_search_strip(tavily_content)
        assert out.startswith(f"Search: {tavily_payload['query']}")

    def test_strips_untrusted_tags(self, tavily_content):
        out = web_search_strip(tavily_content)
        assert "EXTERNAL_UNTRUSTED_CONTENT" not in out

    def test_strips_urls(self, tavily_content):
        out = web_search_strip(tavily_content)
        assert "http://" not in out and "https://" not in out

    def test_actually_shrinks(self, tavily_content):
        out = web_search_strip(tavily_content)
        assert len(out) < len(tavily_content) * 0.6  # observed ~76% saving

    def test_non_json_passthrough(self):
        assert web_search_strip("not json") == "not json"

    def test_pure_idempotent_on_plaintext(self, tavily_content):
        # Stripped output is plaintext (not JSON) → re-stripping returns it as-is.
        out = web_search_strip(tavily_content)
        assert web_search_strip(out) == out

    def test_deterministic(self, tavily_content):
        assert web_search_strip(tavily_content) == web_search_strip(tavily_content)

    def test_strips_markdown_and_nav_menu(self):
        content = json.dumps({
            "query": "q",
            "results": [{
                "title": "Title",
                "snippet": (
                    '<<<EXTERNAL_UNTRUSTED_CONTENT id="abc">>>\n'
                    "See ![img](https://x.com/a.png) and [link](https://y.com).\n"
                    "Skip to main content](https://z.com/#). Menu Cookie Settings.\n"
                    "Real content here.\n"
                    "<<<END_EXTERNAL_UNTRUSTED_CONTENT id=\"abc\">>>"
                ),
            }],
        })
        out = web_search_strip(content)
        assert "EXTERNAL_UNTRUSTED" not in out
        assert "https://" not in out
        assert "Skip to main content" not in out
        assert "Cookie Settings" not in out
        assert "link" in out          # md link text kept
        assert "Real content here." in out