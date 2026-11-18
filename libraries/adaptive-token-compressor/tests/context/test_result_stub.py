"""Tests for context/result_stub.py — the historical large-result stub
(context_compressor_v0_1 plan step 7). Snapshot tests pin the stub format."""
from __future__ import annotations

import json

import pytest

from adaptive_token_compressor.context.result_stub import (
    MIN_SAVED_TOKENS,
    STUB_HEADER,
    content_text,
    edited_file_read_ids,
    make_stub,
    render_stub,
    stub_eligible_call_ids,
    stub_tool_message,
)
from adaptive_token_compressor.core.exceptions import ConfigError
from adaptive_token_compressor.core.metrics import estimate_tokens

_READ = "\n".join(f"line {i}: the quick brown fox jumps over the lazy dog" for i in range(200))

_READ_GUIDANCE = "recover: call the same tool with the same arguments to view the full output"
_EXEC_GUIDANCE = "recover: not reproducible"
_OTHER_GUIDANCE = "recover: not reproducible"
_RECOVERY_GUIDANCE = (
    "This content is NOT in your context. Before editing or quoting it, "
    "read it again (path/offset/limit) or rerun a read-only query."
)

_EXEC_FAILED = "\n".join([
    "Traceback (most recent call last):",
    '  File "/tmp/a.py", line 3, in <module>',
    "    re.compile(r'(')",
    "re.error: missing ), unterminated subpattern at position 0",
    "",
    "(Command exited with code 1)",
])

_EXEC_OK_HTML = "\n".join([
    "<html>",
    "<script>",
    "\t\terror: null",
    "\t\tform: null,",
    "</script>",
    "\t</body>",
    "</html>",
])


def _call(tc_id: str, name: str = "read") -> dict:
    return {"role": "assistant", "tool_calls": [{
        "id": tc_id, "type": "function", "function": {"name": name, "arguments": "{}"}}]}


class TestRenderStub:
    def test_read_snapshot(self):
        assert render_stub("read", _READ) == (
            f"{STUB_HEADER}\n"
            f"tool: read   status: ok   original: {estimate_tokens(_READ)} tokens / 200 lines\n"
            f"{_READ_GUIDANCE}"
        )

    def test_failed_exec_snapshot(self):
        assert render_stub("exec", _EXEC_FAILED) == (
            f"{STUB_HEADER}\n"
            f"tool: exec   status: error   exit code: 1   original: {estimate_tokens(_EXEC_FAILED)} tokens / 6 lines\n"
            "error lines:\n"
            "  Traceback (most recent call last):\n"
            "  re.error: missing ), unterminated subpattern at position 0\n"
            "last lines:\n"
            '    File "/tmp/a.py", line 3, in <module>\n'
            "      re.compile(r'(')\n"
            "  re.error: missing ), unterminated subpattern at position 0\n"
            f"{_EXEC_GUIDANCE}"
        )

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    @pytest.mark.parametrize("body", ["", "\n \t\n", "permission denied\n"])
    def test_failed_exec_without_matching_error_lines(self, guidance, body):
        text = body + "(Command exited with code 2)"
        expected = [
            STUB_HEADER,
            f"tool: exec   status: error   exit code: 2   "
            f"original: {estimate_tokens(text)} tokens / {len(text.splitlines())} lines",
        ]
        if guidance == "recovery":
            expected.append("target: exec {}")
        if body.strip():
            expected.extend(["last lines:", "  permission denied"])
        expected.append(_RECOVERY_GUIDANCE if guidance == "recovery" else _EXEC_GUIDANCE)
        assert render_stub("exec", text, guidance=guidance) == "\n".join(expected)

    def test_successful_exec_has_no_error_lines(self):
        # `error: null` in a successful command's output is data (2026-10-14
        # replay found it in a curl'd HTML page), not an error.
        stub = render_stub("exec", _EXEC_OK_HTML)
        assert "status: ok" in stub
        assert "error lines:" not in stub
        assert stub.endswith(f"last lines:\n  </script>\n  \t</body>\n  </html>\n{_EXEC_GUIDANCE}")

    def test_tail_bounded_to_300_chars(self):
        text = "\n".join(["a" * 200, "b" * 200, "c" * 400])
        stub = render_stub("exec", text)
        tail = stub.split("last lines:\n", 1)[1].rsplit("\nrecover:", 1)[0]
        assert tail == "  " + "c" * 300

    def test_extracted_lines_are_verbatim(self):
        stub = render_stub("exec", _EXEC_FAILED)
        body = stub.split("\n")[2:-1]
        for line in body:
            if line in ("error lines:", "last lines:"):
                continue
            assert line[2:].strip() in _EXEC_FAILED

    def test_error_json_status(self):
        err = '{"status":"error","tool":"web_fetch","error":"fetch failed"}'
        assert "status: error" in render_stub("web_fetch", err)

    def test_other_tools_use_safe_query_guidance(self):
        for name in ("web_fetch", "web_search", "get_order_details", "custom_tool"):
            assert render_stub(name, _READ).endswith(_OTHER_GUIDANCE)

    def test_deterministic(self):
        for name in ("read", "exec", "web_fetch"):
            assert render_stub(name, _READ) == render_stub(name, _READ)

    def test_guidance_is_independent_of_result_contents(self):
        for name, guidance in (
            ("read", _READ_GUIDANCE),
            ("exec", _EXEC_GUIDANCE),
            ("web_fetch", _OTHER_GUIDANCE),
        ):
            for text in (_READ, _EXEC_FAILED, _EXEC_OK_HTML):
                assert render_stub(name, text).endswith(guidance)

    def test_read_adds_no_outline_or_invented_location(self):
        text = "class Parser:\n    def parse(self):\n        pass"
        stub = render_stub("read", text)
        assert len(stub.splitlines()) == 3
        assert "class Parser" not in stub
        assert "def parse" not in stub


class TestMakeStub:
    def test_below_min_tokens_kept(self):
        assert make_stub("read", _READ, min_tokens=estimate_tokens(_READ) + 1) is None

    def test_at_min_tokens_stubbed(self):
        assert make_stub("read", _READ, min_tokens=estimate_tokens(_READ)).startswith(STUB_HEADER)

    def test_write_edit_and_unknown_never_stubbed(self):
        for name in ("write", "edit", None, ""):
            assert make_stub(name, _READ, min_tokens=1) is None

    def test_too_small_saving_kept(self):
        # A result barely larger than its own stub saves < MIN_SAVED_TOKENS.
        text = "x " * 40
        assert estimate_tokens(text) - estimate_tokens(render_stub("read", text)) < MIN_SAVED_TOKENS
        assert make_stub("read", text, min_tokens=1) is None


class TestRecoveryGuidance:
    @pytest.mark.parametrize("invalid", ["", "Recovery", "invalid", None, True, 1, [], {}])
    def test_invalid_guidance_rejected_by_helper_apis(self, invalid):
        with pytest.raises(ConfigError, match="large_result_stub_guidance"):
            render_stub("read", _READ, guidance=invalid)
        with pytest.raises(ConfigError, match="large_result_stub_guidance"):
            make_stub("write", _READ, 1, guidance=invalid)
        with pytest.raises(ConfigError, match="large_result_stub_guidance"):
            stub_tool_message({"content": []}, "read", 1, guidance=invalid)

    @pytest.mark.parametrize("tool_name", ["read", "exec", "web_fetch", "custom_tool"])
    @pytest.mark.parametrize("text", [_READ, _EXEC_FAILED, _EXEC_OK_HTML])
    def test_explicit_legacy_preserves_default(self, tool_name, text):
        call = {"function": {"arguments": '{"path":"src/a.py","offset":10,"limit":20}'}}
        assert render_stub(tool_name, text, tool_call=call, guidance="legacy") == \
            render_stub(tool_name, text)
        assert make_stub(tool_name, text, 1, tool_call=call, guidance="legacy") == \
            make_stub(tool_name, text, 1)

    def test_read_snapshot(self):
        call = {"function": {"arguments": '{"path":"src/a.py","offset":10,"limit":20}'}}
        assert render_stub("read", _READ, tool_call=call, guidance="recovery") == (
            f"{STUB_HEADER}\n"
            f"tool: read   status: ok   original: {estimate_tokens(_READ)} tokens / 200 lines\n"
            "target: read src/a.py offset=10 limit=20\n"
            f"{_RECOVERY_GUIDANCE}"
        )

    @pytest.mark.parametrize("text", [_EXEC_FAILED, _EXEC_OK_HTML])
    def test_exec_preserves_status_and_excerpts(self, text):
        call = {"function": {"arguments": {"command": "python /tmp/a.py", "timeout": 30}}}
        legacy_lines = render_stub("exec", text).splitlines()
        expected = "\n".join([
            *legacy_lines[:2],
            'target: exec {"command":"python /tmp/a.py","timeout":30}',
            *legacy_lines[2:-1],
            _RECOVERY_GUIDANCE,
        ])
        assert render_stub("exec", text, tool_call=call, guidance="recovery") == expected

    @pytest.mark.parametrize("arguments,target", [
        ({"path": "src/../a.py", "file_path": "ignored", "file": "ignored",
          "offset": 0, "limit": None}, "read src/../a.py offset=0 limit=None"),
        ({"path": "", "file_path": "/tmp/a.py", "offset": 10}, "read /tmp/a.py offset=10"),
        ({"file": "a.py", "limit": 20}, "read a.py limit=20"),
        ({"path": 123, "offset": "12", "limit": False}, "read 123 offset=12 limit=False"),
        ({"offset": 5}, "offset=5"),
        ({}, "read"),
    ])
    @pytest.mark.parametrize("encoded", [False, True])
    def test_read_targets_match_reference_semantics(self, arguments, target, encoded):
        call = {"function": {"arguments": json.dumps(arguments) if encoded else arguments}}
        stub = render_stub("read", _READ, tool_call=call, guidance="recovery")
        assert stub.splitlines()[2] == f"target: {target}"
        assert stub.endswith(_RECOVERY_GUIDANCE)

    @pytest.mark.parametrize("tool_name", ["exec", "web_search", "web_fetch", "custom_tool"])
    def test_other_targets_use_compact_sorted_json_truncated_at_80_chars(self, tool_name):
        args = {"z": "\u6587\u4ef6", "command": "query " + "x" * 100, "a": 1}
        expected = json.dumps(args, ensure_ascii=False, separators=(",", ":"), sort_keys=True)[:80]
        stub = render_stub(
            tool_name, _READ, tool_call={"function": {"arguments": args}}, guidance="recovery",
        )
        assert stub.splitlines()[2] == f"target: {tool_name} {expected}"
        assert stub.endswith(_RECOVERY_GUIDANCE)

    def test_other_target_preserves_non_ascii(self):
        stub = render_stub(
            "web_search", _READ,
            tool_call={"function": {"arguments": {"query": "\u6587\u4ef6"}}},
            guidance="recovery",
        )
        assert stub.splitlines()[2] == 'target: web_search {"query":"\u6587\u4ef6"}'

    @pytest.mark.parametrize("call", [
        None, {}, {"function": None}, {"function": {}},
        *[{"function": {"arguments": args}}
          for args in (None, "{broken", "null", "[]", "3", '""', [], 42, False)],
    ])
    @pytest.mark.parametrize("tool_name,target", [("read", "read"), ("exec", "exec {}")])
    def test_missing_and_malformed_arguments(self, call, tool_name, target):
        stub = render_stub(tool_name, _READ, tool_call=call, guidance="recovery")
        assert stub.splitlines()[2] == f"target: {target}"

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    @pytest.mark.parametrize("saved", [MIN_SAVED_TOKENS - 1, MIN_SAVED_TOKENS, MIN_SAVED_TOKENS + 1])
    def test_savings_boundary_uses_legacy_length(self, guidance, saved):
        text = next(
            text for n in range(64, 256)
            if estimate_tokens(text := "x " * n) -
            estimate_tokens(render_stub("read", text)) == saved
        )
        call = {"function": {"arguments": {"path": "long/path/" * 30, "offset": 10, "limit": 20}}}
        stub = make_stub("read", text, 1, tool_call=call, guidance=guidance)
        assert (stub is not None) == (saved >= MIN_SAVED_TOKENS)
        if stub is not None:
            assert stub == render_stub("read", text, tool_call=call, guidance=guidance)
            if guidance == "recovery":
                assert estimate_tokens(text) - estimate_tokens(stub) < MIN_SAVED_TOKENS

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    @pytest.mark.parametrize("threshold_delta", [-1, 0, 1])
    def test_original_token_threshold(self, guidance, threshold_delta):
        stub = make_stub("read", _READ, estimate_tokens(_READ) + threshold_delta, guidance=guidance)
        assert (stub is not None) == (threshold_delta <= 0)

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    @pytest.mark.parametrize("tool_name", ["write", "edit", None, ""])
    def test_non_participating_tools(self, guidance, tool_name):
        assert make_stub(tool_name, _READ, 1, guidance=guidance) is None


class TestContentShapes:
    def test_string(self):
        assert content_text("abc") == "abc"

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_single_text_part_keeps_list(self, guidance):
        msg = {"role": "tool", "tool_call_id": "r", "content": [{"type": "text", "text": _READ, "x": 1}]}
        out = stub_tool_message(msg, "read", min_tokens=1, guidance=guidance)
        assert isinstance(out["content"], list) and len(out["content"]) == 1
        assert out["content"][0]["x"] == 1
        assert out["content"][0]["text"].startswith(STUB_HEADER)
        assert out["content"][0]["text"] == render_stub("read", _READ, guidance=guidance)
        assert msg["content"][0]["text"] == _READ           # input not mutated

    def test_multi_part_unsupported(self):
        content = [{"type": "text", "text": _READ}, {"type": "text", "text": _READ}]
        assert content_text(content) is None
        assert stub_tool_message({"role": "tool", "content": content}, "read", 1) is None

    def test_only_content_changes(self):
        msg = {"role": "tool", "tool_call_id": "r", "name": "read", "content": _READ}
        out = stub_tool_message(msg, "read", min_tokens=1)
        assert {k: v for k, v in out.items() if k != "content"} == \
            {k: v for k, v in msg.items() if k != "content"}


class TestEligibility:
    def test_keep_one(self):
        msgs = [_call("a"), _call("b"), _call("c")]
        assert stub_eligible_call_ids(msgs, keep=1) == {"a", "b"}

    def test_keep_two(self):
        msgs = [_call("a"), _call("b"), _call("c")]
        assert stub_eligible_call_ids(msgs, keep=2) == {"a"}

    def test_fewer_turns_than_keep(self):
        assert stub_eligible_call_ids([_call("a")], keep=1) == set()

    def test_assistant_text_is_not_a_turn(self):
        msgs = [_call("a"), {"role": "assistant", "content": "done"}]
        assert stub_eligible_call_ids(msgs, keep=1) == set()

    @pytest.mark.parametrize("call_id", [None, "", 42])
    def test_missing_or_invalid_call_id_is_not_eligible(self, call_id):
        incomplete = _call("invalid")
        incomplete["tool_calls"][0]["id"] = call_id
        assert stub_eligible_call_ids([incomplete, _call("latest")], keep=1) == set()


class TestEditedFileReadIds:
    @pytest.mark.parametrize("arguments", [
        None, "{broken", "null", "[]", "42", '""', [], 42, False,
        {}, {"other": "a.py"}, {"path": "", "file_path": None, "file": 42},
    ])
    @pytest.mark.parametrize("invalid_tool", ["read", "edit"])
    def test_invalid_arguments_do_not_create_an_exemption(self, arguments, invalid_tool):
        read = _call("read", "read")
        edit = _call("edit", "edit")
        for message in (read, edit):
            message["tool_calls"][0]["function"]["arguments"] = {"path": "a.py"}
        invalid = read if invalid_tool == "read" else edit
        invalid["tool_calls"][0]["function"]["arguments"] = arguments
        assert edited_file_read_ids([read, edit]) == set()

    @pytest.mark.parametrize("path_key", ["path", "file_path", "file"])
    @pytest.mark.parametrize("encoded", [False, True])
    @pytest.mark.parametrize("action", ["write", "edit"])
    def test_path_aliases_and_normalization(self, path_key, encoded, action):
        read = _call("read", "read")
        edit = _call("edit", action)
        arguments = {path_key: "src/./a.py"}
        read["tool_calls"][0]["function"]["arguments"] = (
            json.dumps(arguments) if encoded else arguments
        )
        edit["tool_calls"][0]["function"]["arguments"] = {"path": "src/a.py"}
        assert edited_file_read_ids([read, edit]) == {"read"}
