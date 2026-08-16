# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Baseline token accounting for incoming requests.

Splits a request's tokens into system-prompt / tool-schema / context so
telemetry can report an uncompressed baseline. Reuses the compressor library's
token counters so the numbers are directly comparable to compressor metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - fallback for air-gapped / partial installs
    _ENCODER = None

from src.models import ChatCompletionRequest


ROLE_SYSTEM = "system"
ROLE_DEVELOPER = "developer"
HARNESS_LIKE_ROLES: tuple[str, ...] = (ROLE_SYSTEM, ROLE_DEVELOPER)


def _message_text(content: Any) -> str:
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
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _estimate_tokens(text: str) -> int:
    """tiktoken cl100k_base; falls back to len // 4 if tiktoken is unavailable."""
    if not text:
        return 0
    if _ENCODER is not None:
        return len(_ENCODER.encode(text))
    return max(1, len(text) // 4)


def _message_tokens(msg: dict[str, Any]) -> int:
    """content + (assistant only) sort_keys-serialized tool_calls."""
    text = _message_text(msg.get("content", "")).strip()
    tokens = _estimate_tokens(text)
    if msg.get("role") == "assistant" and msg.get("tool_calls"):
        tc_text = json.dumps(msg["tool_calls"], ensure_ascii=False, sort_keys=True)
        tokens += _estimate_tokens("TOOL_CALLS: " + tc_text)
    return tokens


def count_messages_tokens(messages: list[dict[str, Any]], *, roles: tuple[str, ...] | None = None) -> int:
    """Total tokens across `messages`, optionally filtered by role tuple."""
    if roles is not None and not roles:
        return 0
    wanted = set(roles) if roles is not None else None
    total = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if wanted is not None and msg.get("role") not in wanted:
            continue
        total += _message_tokens(msg)
    return total


def count_tools_tokens(tools: list[dict[str, Any]] | None) -> int:
    """Total tokens of the `tools` schema array. 0 if `tools` is None or empty."""
    if not tools:
        return 0
    return _estimate_tokens(json.dumps(tools, ensure_ascii=False, sort_keys=True, indent=2))


@dataclass
class TokenBreakdown:
    """Token breakdown of one request (system / tool / context / overall).

    Neutral — used for both the pre-compression request (``before_router``)
    and the compressed request actually forwarded (``after_router``). Both
    use the same tiktoken counter, so before/after are same-unit comparable
    (unlike vLLM's ``prompt_tokens``, which uses the model's own tokenizer).
    """

    system: int = 0    # system + developer messages
    tool: int = 0      # request.tools schema
    context: int = 0   # all other messages (user / assistant / tool)
    overall: int = 0   # system + tool + context


# Back-compat alias — some callers imported the old name.
BaselineTokens = TokenBreakdown


def compute_token_breakdown(request: ChatCompletionRequest) -> TokenBreakdown:
    """Count system-prompt / tool-schema / context tokens for ``request``."""
    messages = [m.model_dump(mode="json", exclude_none=True) for m in request.messages]

    system = count_messages_tokens(messages, roles=HARNESS_LIKE_ROLES)
    tool = count_tools_tokens(request.tools)
    # Context = every message NOT counted as system/developer.
    context = count_messages_tokens(messages) - system

    return TokenBreakdown(
        system=system,
        tool=tool,
        context=context,
        overall=system + tool + context,
    )