# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure parsers over OpenAI-format messages — no mutation, no I/O.

ToolCompressor uses these to collect skills, recent tool calls, and the
most recent SKILL.md content for the dynamic prompt builder.
"""
from __future__ import annotations

import json
import re

from ..core.messages import HARNESS_LIKE_ROLES, MessageAccessor


# Regex for <skill> tags in system prompt.
_SKILL_RE: re.Pattern[str] = re.compile(
    r"<name>\s*(.*?)\s*</name>\s*<description>\s*(.*?)\s*</description>",
    re.DOTALL,
)

# Detect SKILL.md read paths (case-insensitive).
_SKILL_MD_RE: re.Pattern[str] = re.compile(r"SKILL\.md$", re.IGNORECASE)

# Result preview truncation length used by `extract_call_history`.
_RESULT_PREVIEW_MAX = 150


def extract_skills(messages: list[dict]) -> list[tuple[str, str]]:
    """Return `[(name, description), ...]` from `<skill>` tags in system/developer messages.

    Only the first message that has any tags wins.
    """
    for _, msg in MessageAccessor.iter_by_role(messages, *HARNESS_LIKE_ROLES):
        content = MessageAccessor.text(msg.get("content", ""))
        if not content:
            continue
        normalised = content.replace("\\n", "\n")
        skills = _SKILL_RE.findall(normalised)
        if skills:
            return [(name.strip(), desc.strip()) for name, desc in skills]
    return []


def extract_call_history(
    messages: list[dict],
    *,
    start_index: int = 0,
) -> list[dict]:
    """Return assistant tool calls + truncated result preview from `messages[start_index:]`.

    Each entry: `{name, args (JSON-parsed dict; {} on failure), result_preview
    (str, truncated to 150 chars + "...")}`.
    """
    if start_index < 0:
        start_index = 0
    tail = messages[start_index:]

    results_by_id: dict[str, str] = {}
    for msg in tail:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        tid = msg.get("tool_call_id", "")
        if not tid:
            continue
        content = MessageAccessor.text(msg.get("content", "")).strip()
        if len(content) > _RESULT_PREVIEW_MAX:
            content = content[:_RESULT_PREVIEW_MAX] + "..."
        results_by_id[tid] = content

    calls: list[dict] = []
    for msg in tail:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function", {}) or {}
            name = func.get("name", "")
            args_raw = func.get("arguments", "")
            try:
                args = json.loads(args_raw) if args_raw else {}
            except (json.JSONDecodeError, TypeError):
                args = {}
            tid = tc.get("id", "")
            calls.append({
                "name": name,
                "args": args,
                "result_preview": results_by_id.get(tid, ""),
            })
    return calls


def extract_skill_content(
    messages: list[dict],
    *,
    start_index: int = 0,
    max_chars: int | None = None,
) -> str | None:
    """Return the most recent `read(<path>SKILL.md)` tool result content (or None).

    Two-pass: collect `{tool_call_id -> content}` for tool messages, then walk
    assistant messages in reverse for the first matching `read` call.
    `max_chars=None` returns full content; positive int truncates with "...".
    """
    if start_index < 0:
        start_index = 0
    tail = messages[start_index:]

    full_results: dict[str, str] = {}
    for msg in tail:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        tid = msg.get("tool_call_id", "")
        if not tid:
            continue
        content = MessageAccessor.text(msg.get("content", "")).strip()
        full_results[tid] = content

    for msg in reversed(tail):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            continue
        for tc in reversed(tool_calls):
            if not isinstance(tc, dict):
                continue
            func = tc.get("function", {}) or {}
            if func.get("name") != "read":
                continue
            args_raw = func.get("arguments", "")
            try:
                args = json.loads(args_raw) if args_raw else {}
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(args, dict):
                continue
            path = args.get("path", "")
            if not isinstance(path, str):
                continue
            if not _SKILL_MD_RE.search(path):
                continue
            tid = tc.get("id", "")
            content = full_results.get(tid, "")
            if content:
                if max_chars is not None and len(content) > max_chars:
                    content = content[:max_chars] + "..."
                return content
    return None
