# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor scope enum, single-call metrics, and token counters."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .messages import HARNESS_LIKE_ROLES, MessageAccessor


# Defensive against air-gapped envs where the wheel didn't install.
try:
    import tiktoken

    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _encoder = None


class CompressionScope(str, Enum):
    """Field range each compressor is responsible for. Mutually exclusive."""

    HARNESS = "harness"
    TOOL = "tool"


@dataclass
class CompressorMetrics:
    """Single-call snapshot. One per `compress()` invocation; immutable in spirit."""

    name: str
    scope: CompressionScope
    tokens_before: int
    tokens_after: int
    duration_ms: float
    error: str | None = None
    skip_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def saved_tokens(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def compression_ratio(self) -> float:
        """tokens_after / tokens_before; smaller = harder compression. 1.0 if no input tokens."""
        if self.tokens_before == 0:
            return 1.0
        return self.tokens_after / self.tokens_before

    @property
    def succeeded(self) -> bool:
        """True iff neither error nor skip_reason was set — actually ran end to end."""
        return self.error is None and self.skip_reason is None


def estimate_tokens(text: str) -> int:
    """tiktoken cl100k_base; falls back to len // 4 if tiktoken is unavailable at runtime."""
    if not text:
        return 0
    if _encoder is not None:
        return len(_encoder.encode(text))
    return max(1, len(text) // 4)


def _message_tokens(msg: dict) -> int:
    """content + (assistant only) sort_keys-serialized tool_calls.

    sort_keys keeps tool_calls' byte form stable so token accounting is
    deterministic across runs.
    """
    text = MessageAccessor.text(msg.get("content", "")).strip()
    tokens = estimate_tokens(text)
    if msg.get("role") == "assistant" and msg.get("tool_calls"):
        tc_text = json.dumps(msg["tool_calls"], ensure_ascii=False, sort_keys=True)
        tokens += estimate_tokens("TOOL_CALLS: " + tc_text)
    return tokens


def count_messages_tokens(
    messages: list[dict],
    *,
    roles: tuple[str, ...] | None = None,
) -> int:
    """Total tokens across `messages`, optionally filtered by role tuple.

    `roles=None` counts everything; `roles=()` counts nothing (explicit-empty rule).
    """
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


def count_tools_tokens(tools: list[dict] | None) -> int:
    """Total tokens of the `tools` schema array. 0 if `tools` is None or empty.

    indent=2 matches how vLLM / OpenAI render the schema in the actual prompt
    template; sort_keys keeps the byte form stable. Used only by ToolCompressor.
    """
    if not tools:
        return 0
    return estimate_tokens(
        json.dumps(tools, ensure_ascii=False, sort_keys=True, indent=2)
    )


def count_total_tokens(messages: list[dict], tools: list[dict] | None = None) -> int:
    """messages + tools combined; for callers computing pipeline-wide ratios."""
    return count_messages_tokens(messages) + count_tools_tokens(tools)


__all__ = [
    "CompressionScope",
    "CompressorMetrics",
    "estimate_tokens",
    "count_messages_tokens",
    "count_tools_tokens",
    "count_total_tokens",
    "HARNESS_LIKE_ROLES",
]
