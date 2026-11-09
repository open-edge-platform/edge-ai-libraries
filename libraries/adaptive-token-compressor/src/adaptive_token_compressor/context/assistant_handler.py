# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Assistant message handler: tool_call args digest replacement.

Replaces an assistant message's `tool_calls[i].function.arguments` with a
length-bounded marker (`<arg_preview kind=... chars=N preview='...'>`), but
ONLY when both hold (else the tool_call is returned unchanged):
  1. The tool_call's id has a matching `role="tool"` result later in the
     messages list — the call already executed, so arguments is historical
     fact. Pending calls in the request tail keep verbatim arguments.
  2. `len(arguments)` exceeds `_ARGS_DIGEST_THRESHOLD` — the threshold sits
     above the marker "expansion zone", so any value that crosses it is
     guaranteed to shrink (no per-tool whitelist needed).

A rewrite is kept only if it saves at least `_MIN_SAVED_CHARS` chars and
`_MIN_SAVED_RATIO` of the original (v7 §7.5); otherwise the tool_call (and,
if nothing changed, the whole message) is returned as the same object.

Layout: value-rendering primitives first, then the public flow functions
(`build_completed_tool_call_ids`, `compress_single_tool_call`,
`compress_assistant_message`).
"""
from __future__ import annotations

import json
from typing import Any


# Thresholds (module-level; not exposed as ContextCompressor kwargs).

# Rebuild args via `render_arg_value` above this `len(arguments)`. Sits above
# the marker "expansion zone" (~240–320 chars) with an ~80-char safety margin.
_ARGS_DIGEST_THRESHOLD: int = 400

# Values shorter than this stay verbatim. Above the head+tail width to keep
# "marker is always shorter than the value" per-field.
_VALUE_INLINE_LIMIT: int = 320

# Head / tail excerpt widths (sum 240).
_EXCERPT_HEAD_CHARS: int = 120
_EXCERPT_TAIL_CHARS: int = 120

# Minimum real gain for a rebuild to be kept (v7 §7.5).
_MIN_SAVED_CHARS: int = 128
_MIN_SAVED_RATIO: float = 0.20

# Marker prefix; also used by ContextCompressor to detect leaks (the model
# copying a marker into a real call).
ARG_PREVIEW_MARKER: str = "<arg_preview"


def _line_aligned_excerpt(rendered: str) -> tuple[str, str]:
    """Slice `rendered` into a (head, tail) pair on line boundaries.

    Takes whole lines from each end until adding the next would exceed the
    head/tail width, falling back to a byte slice if the first/last line is
    already too long. Only valid when `len(rendered) > _VALUE_INLINE_LIMIT`
    (else head/tail may overlap). Line-aligned so the model never reads a
    half-cut tag / identifier.
    """
    lines = rendered.split("\n")

    head_parts: list[str] = []
    head_used = 0
    for line in lines:
        cost = len(line) + (1 if head_parts else 0)
        if head_used + cost > _EXCERPT_HEAD_CHARS:
            break
        head_parts.append(line)
        head_used += cost
    head = "\n".join(head_parts) if head_parts else rendered[:_EXCERPT_HEAD_CHARS]

    tail_parts: list[str] = []
    tail_used = 0
    for line in reversed(lines):
        cost = len(line) + (1 if tail_parts else 0)
        if tail_used + cost > _EXCERPT_TAIL_CHARS:
            break
        tail_parts.append(line)
        tail_used += cost
    tail = "\n".join(reversed(tail_parts)) if tail_parts else rendered[-_EXCERPT_TAIL_CHARS:]

    return head, tail


def render_arg_value(value: Any) -> str:
    """Render one tool_call argument value into a length-bounded marker.

    Dispatch by type (first match wins): None → "null"; bool → "true"/"false";
    int/float → str; str/json below `_VALUE_INLINE_LIMIT` → verbatim; above →
    `<arg_preview kind=... chars=N preview='...'>`. Scalars use JSON spelling
    (not Python repr) to match the surrounding arguments JSON.

    Pure / deterministic (prefix-cache friendly). `bool` is checked before
    `int/float` since `bool` is an `int` subclass.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, str):
        rendered = value
        kind = "str"
    else:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        kind = "json"

    if len(rendered) <= _VALUE_INLINE_LIMIT:
        return rendered

    head, tail = _line_aligned_excerpt(rendered)
    elided = len(rendered) - len(head) - len(tail)
    preview = f"{head}\n[...elided {elided} chars...]\n{tail}"
    return f"{ARG_PREVIEW_MARKER} kind={kind} chars={len(rendered)} preview={preview!r}>"


def compact_arg_value(value: Any) -> Any:
    """Return `value` itself unless it is too long to keep inline, in which
    case return its `render_arg_value` marker string.

    Keeps JSON types intact (v7 §7.3): null / bool / numbers and short
    str / list / dict stay native values, so `{"limit": 100}` never becomes
    `{"limit": "100"}`. Only long str / json values become markers.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(rendered) <= _VALUE_INLINE_LIMIT:
        return value
    return render_arg_value(value)


def build_completed_tool_call_ids(messages: list[dict]) -> set[str]:
    """Return the `tool_call_id` values that already have a matching
    `role="tool"` result — i.e. executed calls whose `arguments` is safe to
    rewrite. Ids not in the set are pending and must stay verbatim.
    """
    completed: set[str] = set()
    for m in messages:
        if m.get("role") != "tool":
            continue
        tc_id = m.get("tool_call_id")
        if isinstance(tc_id, str) and tc_id:
            completed.add(tc_id)
    return completed


def _estimate_tokens(s: str) -> int:
    """Cheap token estimate (`len // 4`, floor 1). Local helper to keep this
    module free of the tiktoken dependency on a hot path.
    """
    return max(1, len(s) // 4)


def compress_single_tool_call(
    tc: dict,
    completed_ids: set[str],
) -> tuple[dict, int]:
    """Decide whether to rebuild one tool_call's `arguments`.

    Returns `(new_tool_call, tokens_saved)`. Left unchanged (same object,
    saved=0) if the call is not yet executed, arguments is below the gate, is
    not a JSON dict, or the rebuild saves less than the minimum gain;
    otherwise each value is passed through `compact_arg_value`. Never mutates
    the input `tc`.
    """
    tc_id = tc.get("id")
    if tc_id not in completed_ids:
        return tc, 0
    fn = tc.get("function") or {}
    args_str = fn.get("arguments") or ""
    if len(args_str) <= _ARGS_DIGEST_THRESHOLD:
        return tc, 0
    try:
        args = json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return tc, 0
    if not isinstance(args, dict):
        return tc, 0

    rebuilt = {k: compact_arg_value(v) for k, v in args.items()}
    new_args_str = json.dumps(rebuilt, ensure_ascii=False, sort_keys=True)
    saved_chars = len(args_str) - len(new_args_str)
    if saved_chars < _MIN_SAVED_CHARS or saved_chars / len(args_str) < _MIN_SAVED_RATIO:
        return tc, 0
    saved = max(0, _estimate_tokens(args_str) - _estimate_tokens(new_args_str))
    new_tc = {
        **tc,
        "function": {**fn, "arguments": new_args_str},
    }
    return new_tc, saved


def compress_assistant_message(
    msg: dict,
    completed_ids: set[str],
) -> tuple[dict, int]:
    """Run every tool_call in one assistant message through
    `compress_single_tool_call`, summing tokens saved. Returns the same `msg`
    object with 0 saved if no tool_call changed (v7 §7.2), so callers can use
    `new is msg` as "untouched". Never mutates the input.
    """
    tcs = msg.get("tool_calls")
    if not tcs:
        return msg, 0
    new_tcs: list[dict] = []
    total_saved = 0
    changed = False
    for tc in tcs:
        new_tc, saved = compress_single_tool_call(tc, completed_ids)
        new_tcs.append(new_tc)
        total_saved += saved
        changed = changed or new_tc is not tc
    if not changed:
        return msg, 0
    new_msg = {**msg, "tool_calls": new_tcs}
    return new_msg, total_saved
