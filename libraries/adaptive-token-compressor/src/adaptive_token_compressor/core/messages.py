# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-format messages: role constants + read / copy-update helpers."""
from __future__ import annotations

import json
import re
from typing import Any, Iterator


ROLE_SYSTEM = "system"
ROLE_DEVELOPER = "developer"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"

HARNESS_LIKE_ROLES: tuple[str, ...] = (ROLE_SYSTEM, ROLE_DEVELOPER)


# Markers used by find_last_user_message to skip OpenClaw runtime-injected
# user blocks (subagent results, session-startup notices, sender metadata).
_TIMESTAMP_PATTERN = re.compile(r"^\s*\[.*?\]\s*")
_SENDER_META_RE = re.compile(
    r"^Sender\s*\(untrusted metadata\)\s*:\s*```json\s*\{[^}]*\}\s*```\s*",
    re.DOTALL,
)
_INTERNAL_CONTEXT_MARKER = "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>"
_SESSION_STARTUP_PREFIX = "A new session was started"


class MessageAccessor:
    """Read-only / copy-update helpers over OpenAI-format `list[dict]` messages."""

    @staticmethod
    def text(content: Any) -> str:
        """Normalize string / multimodal list / dict / None content to a single string."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        parts.append(str(item.get("text", "")))
                    elif "content" in item:
                        parts.append(str(item.get("content", "")))
                    else:
                        # sort_keys for prefix-cache stability
                        parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                else:
                    parts.append(str(item))
            return "\n".join(p for p in parts if p)
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def iter_by_role(messages: list[dict], *roles: str) -> Iterator[tuple[int, dict]]:
        """Yield `(index, msg)` for every message whose role matches one of `roles`."""
        if not roles:
            return
        wanted = set(roles)
        for idx, msg in enumerate(messages):
            if msg.get("role") in wanted:
                yield idx, msg

    @staticmethod
    def find_last_user_message(
        messages: list[dict],
        *,
        skip_framework: bool = True,
    ) -> tuple[int, str] | None:
        """Locate the real user task; with `skip_framework=True`, skip framework-injected blocks.

        Returns `(index, text)` or None. Legacy `_find_task_message_index`
        returned `(0, "")` on miss; we return None to disambiguate from
        "empty task at index 0".
        """
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") != ROLE_USER:
                continue
            raw = MessageAccessor.text(msg.get("content", "")).strip()
            if not raw:
                continue
            if not skip_framework:
                return i, raw
            if _INTERNAL_CONTEXT_MARKER in raw:
                continue
            stripped = _TIMESTAMP_PATTERN.sub("", raw).strip()
            if stripped.startswith(_SESSION_STARTUP_PREFIX):
                continue
            stripped = _SENDER_META_RE.sub("", stripped).strip()
            stripped = _TIMESTAMP_PATTERN.sub("", stripped).strip()
            if stripped:
                return i, stripped
        return None

    @staticmethod
    def replace_content(messages: list[dict], idx: int, new_content: str) -> list[dict]:
        """Return a new list with `messages[idx].content` replaced; input not mutated."""
        if idx < 0 or idx >= len(messages):
            raise IndexError(
                f"replace_content: idx {idx} out of range (len={len(messages)})"
            )
        new_list = list(messages)
        new_list[idx] = {**messages[idx], "content": new_content}
        return new_list
