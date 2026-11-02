# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Historical large-result stub (context_compressor_v0_1 plan step 7; design
v8 §7.1 / §7.3 without key facts).

A large tool result that the agent has already moved past (its tool turn is
followed by >= `keep` later tool turns) is replaced in place by a short,
fixed-format stub. Selection depends only on position and on the result's own
text, so a result once stubbed is byte-identical in every later request
(prefix-cache safe). Only the `content` is replaced: role, tool_call_id and the
message position stay, so call/result pairing is untouched.

Every line taken from the original output is a verbatim substring of it; the
stub never states anything the output does not show.

Recovery guidance additionally describes the originating call. Selection still
uses the legacy stub length; only the displayed text changes.

Optional edited-file exemption: once the history contains a write/edit call on
a file, every `read` result of that file stays verbatim, including reads that
an earlier request stubbed (restoring them breaks the prefix cache once).
"""
from __future__ import annotations

import json
import posixpath
import re
from typing import Any, Literal

from ..core.exceptions import ConfigError
from ..core.metrics import estimate_tokens
from .tool_handler import ToolContentCategory, classify

STUB_HEADER = (
    "[historical tool output omitted by context compressor — the original call completed]"
)
# State-changing tools: their results are short action evidence, never stubbed.
SKIP_TOOLS = frozenset({"write", "edit"})
# Tools whose results are file contents an edit may copy from.
READ_TOOLS = frozenset({"read"})
# Argument names OpenClaw's read/write/edit accept for the target file.
_PATH_KEYS = ("path", "file_path", "file")
# A stub must save at least this many tokens, otherwise the result stays.
MIN_SAVED_TOKENS = 64

StubGuidance = Literal["legacy", "recovery"]

_RECOVER_READ = "recover: call the same tool with the same arguments to view the full output"
_RECOVER_EXEC = "recover: not reproducible"
_RECOVER_OTHER = "recover: not reproducible"
_RECOVERY_GUIDANCE = (
    "This content is NOT in your context. Before editing or quoting it, "
    "read it again (path/offset/limit) or rerun a read-only query."
)

# OpenClaw appends this only for a non-zero exit.
_EXIT_RE = re.compile(r"\(Command exited with code (-?\d+)\)")
# Only scanned for a failed command: in a successful command's output, lines
# such as `error: null` (HTML / JS) or `[error]` (an apache log) are data.
_ERROR_LINE_RE = re.compile(r"Error|Exception|Traceback|FAILED|error:")
_MAX_ERROR_LINES = 3
_MAX_ERROR_LINE_CHARS = 200
_MAX_TAIL_LINES = 3
_MAX_TAIL_CHARS = 300


def validate_stub_guidance(guidance: StubGuidance) -> None:
    if guidance not in ("legacy", "recovery"):
        raise ConfigError(
            "ContextCompressor: large_result_stub_guidance must be one of "
            f"['legacy', 'recovery'], got {guidance!r}"
        )


def stub_eligible_call_ids(messages: list[dict], keep: int) -> set[str]:
    """tool_call ids of tool turns followed by >= `keep` later tool turns.

    A tool turn is an assistant message with non-empty tool_calls (the same
    definition as the window gate).
    """
    turns = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
    ids: set[str] = set()
    for m in turns[: max(len(turns) - keep, 0)]:
        for tc in m["tool_calls"]:
            tc_id = tc.get("id")
            if isinstance(tc_id, str) and tc_id:
                ids.add(tc_id)
    return ids


def _call_path(tool_call: dict) -> str | None:
    """Normalized target file of a read/write/edit call, or None."""
    args = (tool_call.get("function") or {}).get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    if not isinstance(args, dict):
        return None
    for key in _PATH_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return posixpath.normpath(value)
    return None


def edited_file_read_ids(messages: list[dict]) -> set[str]:
    """tool_call ids of `read` calls on a file that some write/edit call in
    the history targets (failed edits count: the call shows the intent)."""
    calls = [
        tc for m in messages if m.get("role") == "assistant"
        for tc in m.get("tool_calls") or []
    ]
    edited = {
        _call_path(tc) for tc in calls
        if (tc.get("function") or {}).get("name") in SKIP_TOOLS
    } - {None}
    return {
        tc["id"] for tc in calls
        if (tc.get("function") or {}).get("name") in READ_TOOLS
        and isinstance(tc.get("id"), str) and _call_path(tc) in edited
    }


def content_text(content: Any) -> str | None:
    """The text a stub replaces: a string, or the text of a single-text-part
    list. None for any other shape (multi-part, images, …) — left verbatim."""
    if isinstance(content, str):
        return content
    if (
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
        and isinstance(content[0].get("text"), str)
    ):
        return content[0]["text"]
    return None


def with_text(content: Any, text: str) -> Any:
    """`content` with its text replaced, keeping a single-part list a list."""
    if isinstance(content, str):
        return text
    return [{**content[0], "text": text}]


def _exec_lines(lines: list[str], code: str | None) -> list[str]:
    """Error lines (failed commands only) and the last non-empty lines."""
    out: list[str] = []
    if code is not None and code != "0":
        errors = [ln.strip()[:_MAX_ERROR_LINE_CHARS] for ln in lines if _ERROR_LINE_RE.search(ln)]
        if errors:
            out.append("error lines:")
            out.extend(f"  {ln}" for ln in errors[:_MAX_ERROR_LINES])
    tail = [ln for ln in lines if ln.strip() and not _EXIT_RE.fullmatch(ln.strip())]
    tail = tail[-_MAX_TAIL_LINES:]
    while len(tail) > 1 and sum(len(ln) for ln in tail) > _MAX_TAIL_CHARS:
        tail = tail[1:]
    if tail and len(tail[0]) > _MAX_TAIL_CHARS:
        tail = [tail[0][-_MAX_TAIL_CHARS:]]
    if tail:
        out.append("last lines:")
        out.extend(f"  {ln}" for ln in tail)
    return out


def _recovery_target(tool_name: str, tool_call: dict | None) -> str:
    """Describe the originating call without copying its result."""
    function = (tool_call or {}).get("function") or {}
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = None
    if not isinstance(arguments, dict):
        arguments = {}

    if tool_name == "read":
        parts = [f"read {arguments.get(key)}" for key in _PATH_KEYS if arguments.get(key)]
        parts = parts[:1]
        for key in ("offset", "limit"):
            if key in arguments:
                parts.append(f"{key}={arguments[key]}")
        return " ".join(parts) or "read"

    serialized = json.dumps(
        arguments, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return f"{tool_name} {serialized[:80]}".rstrip()


def render_stub(
    tool_name: str, text: str, *, tool_call: dict | None = None,
    guidance: StubGuidance = "legacy",
) -> str:
    """Fixed-format stub for one tool result (field order is part of the
    format: same input → same stub)."""
    validate_stub_guidance(guidance)
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    extra: list[str] = []
    recover = _RECOVER_OTHER
    if tool_name == "read":
        recover = _RECOVER_READ
    if tool_name == "exec":
        recover = _RECOVER_EXEC
        codes = _EXIT_RE.findall(text)
        code = codes[-1] if codes else None
        status = f"error   exit code: {code}" if code not in (None, "0") else "ok"
        extra = _exec_lines(lines, code)
    else:
        status = "error" if classify(text) is ToolContentCategory.ERROR else "ok"
    if guidance == "recovery":
        extra.insert(0, f"target: {_recovery_target(tool_name, tool_call)}")
    return "\n".join([
        STUB_HEADER,
        f"tool: {tool_name}   status: {status}   "
        f"original: {estimate_tokens(text)} tokens / {len(lines)} lines",
        *extra,
        _RECOVERY_GUIDANCE if guidance == "recovery" else recover,
    ])


def make_stub(
    tool_name: str | None, text: str, min_tokens: int,
    *, tool_call: dict | None = None, guidance: StubGuidance = "legacy",
) -> str | None:
    """Stub text for a result of `tool_name`, or None to keep it verbatim
    (unknown or state-changing tool, below `min_tokens`, or the stub would
    save < MIN_SAVED_TOKENS using the legacy text in both guidance modes)."""
    validate_stub_guidance(guidance)
    if not tool_name or tool_name in SKIP_TOOLS:
        return None
    original = estimate_tokens(text)
    if original < min_tokens:
        return None
    stub = render_stub(tool_name, text, tool_call=tool_call, guidance=guidance)
    selection_stub = render_stub(tool_name, text) if guidance == "recovery" else stub
    if original - estimate_tokens(selection_stub) < MIN_SAVED_TOKENS:
        return None
    return stub


def stub_tool_message(
    msg: dict, tool_name: str | None, min_tokens: int,
    *, tool_call: dict | None = None, guidance: StubGuidance = "legacy",
) -> dict | None:
    """The stubbed copy of tool message `msg`, or None to keep it verbatim
    (see make_stub; also None for an unsupported content shape)."""
    validate_stub_guidance(guidance)
    text = content_text(msg.get("content"))
    if text is None:
        return None
    stub = make_stub(tool_name, text, min_tokens, tool_call=tool_call, guidance=guidance)
    return None if stub is None else {**msg, "content": with_text(msg["content"], stub)}
