# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ToolCompressor: predict task-relevant tools and filter the tools schema array.

Pipeline: find user task → compose system prompt for predictor → predictor.predict →
score-threshold filter → filter_tools (preserves original order) → optional
placement rewrite (see `placement` kwarg).

Placement variants. Only `schema` is production-viable; the trailing-carrier
variants all OOD-fail on multi-turn agents (Qwen/Qwen3.6-35B-A3B treats the trailing
carrier as a fresh user request and re-executes the task — see layer-2
report for the full evidence). They stay in the API for reproducibility.

  schema (default)      PRODUCTION. Predicted subset returned via
                        `result.tools`; chat template renders it inside
                        the system message's `<tools>` block.
  user_tail             KNOWN-BROKEN on multi-turn. `result.tools=None`
                        (field omitted — an empty `[]` is rejected by
                        strict backends), full `# Tools\n...</IMPORTANT>`
                        text appended as a trailing user-role carrier.
  system_tail           KNOWN-BROKEN. Same trailing carrier with
                        role=system; collapses cleanly on stateless
                        single-task warm-up but regresses under
                        accumulated history.
  user_inline           EXPERIMENTAL. user_tail carrier, but persisted
                        per-conversation and re-spliced at its original
                        offset each turn (prefix-cache stable). Re-lists each
                        turn's FULL prediction → O(N²) token blow-up; see
                        user_inline_delta for the fix.
  user_inline_delta     EXPERIMENTAL. user_inline, delta-only (requires
                        accumulate=True). A carrier is appended ONLY on turns
                        that introduce NEW tools, carrying just the delta;
                        earlier tools persist via replayed carriers. Carrier
                        volume ≈ |union|, not Σ|prediction|. A standing note
                        is added to the system message (front, cached) so the
                        mid-context carriers stay usable, plus a recency
                        reminder gated to genuine user turns (adding it
                        mid-tool-loop makes the model re-execute). Toggle
                        `_INLINE_DELTA_REPLAY_REMINDER` persists+replays that
                        reminder at each user-query offset instead.

`accumulate` (cross-cutting flag, default False). Per-turn prediction changes
the tool set across turns of one conversation (measured: ~60% of turn
transitions differ), and since the chat template renders tools at the FRONT of
the prompt, every change breaks the prefix cache. With accumulate=True the
predicted names are UNIONED per conversation and rendered in append-only order
(never removed/reordered), so each turn's tool block is a strict prefix-extension
of the previous turn's — prefix-cache stable — while tools that only emerge in
later turns are still admitted (recall preserved; e.g. a `web_search` first
needed at turn 10 is appended, and a tool used early then re-predicted later is
never dropped). Conversation identity = hash(system + first user message), so
all turns of one growing conversation share accumulator state (bounded LRU).

This is the intended fix for the tool-instability-breaks-prefix problem and
makes the trailing-carrier placements unnecessary: accumulate keeps tools at the
FRONT (cacheable) AND stable, whereas user_tail traded cacheability (tools moved
to the never-reused tail) for stability. accumulate does NOT help the
trailing-carrier placements — their tool block sits after the growing
conversation and is missed every turn regardless of accumulation order.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Literal

from ..core.base import CompressionContext, CompressorResult
from ..core.exceptions import ConfigError, PredictorError
from ..core.health import HealthStatus
from ..core.messages import MessageAccessor
from ..core.metrics import CompressionScope, CompressorMetrics, count_tools_tokens
from .message_extractors import (
    extract_call_history,
    extract_skill_content,
    extract_skills,
)
from .predictor import HTTPToolPredictor, ToolCandidate, ToolPredictor
from .prompts import (
    BASE_PROMPT,
    FOCUS_FIVE_TOOL_PROMPT,
    build_dynamic_prediction_prompt,
    build_static_prediction_prompt,
)
from .tool_descriptions import DEFAULT_TOOL_DESCRIPTIONS, build_dynamic_tool_descriptions

logger = logging.getLogger("adaptive_token_compressor.tool.compressor")


def filter_tools(
    tools: list[dict],
    predicted_names: list[str],
) -> list[dict]:
    """Keep tools whose name (case-insensitive) appears in `predicted_names`;
    preserve `tools` schema order for prefix-cache stability."""
    if not tools or not predicted_names:
        return tools

    predicted_set = {n for n in predicted_names if isinstance(n, str)}
    if not predicted_set:
        return tools

    filtered: list[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            continue
        func = tool.get("function", {})
        if not isinstance(func, dict):
            continue
        raw_name = func.get("name", "")
        if not isinstance(raw_name, str):
            continue
        normalised = raw_name.strip().lower()
        if not normalised:
            continue
        if normalised in predicted_set:
            filtered.append(tool)
    return filtered


def order_tools_by_names(
    tools: list[dict],
    ordered_names: list[str],
) -> list[dict]:
    """Return the subset of `tools` named in `ordered_names`, emitted in
    `ordered_names` order (case-insensitive). Unlike `filter_tools`, the output
    order follows `ordered_names` rather than schema order — used by the
    cumulative-append mode so each turn's tool block is a strict prefix-extension
    of the previous turn's (append-only accumulation → prefix-cache stable)."""
    if not tools or not ordered_names:
        return []

    by_name: dict[str, dict] = {}
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        func = tool.get("function", {})
        if not isinstance(func, dict):
            continue
        raw_name = func.get("name", "")
        if not isinstance(raw_name, str):
            continue
        normalised = raw_name.strip().lower()
        if normalised and normalised not in by_name:
            by_name[normalised] = tool

    ordered: list[dict] = []
    for name in ordered_names:
        if not isinstance(name, str):
            continue
        tool = by_name.get(name.strip().lower())
        if tool is not None:
            ordered.append(tool)
    return ordered


# Tool list line shape inside `## Tooling`: "- read: Read file contents".
_TOOL_LINE_RE: re.Pattern[str] = re.compile(r"^-\s+(\w+):")


# ---------------------------------------------------------------------------
# Trailing-carrier placements — render Qwen/Qwen3.6-35B-A3B's tools block
# ---------------------------------------------------------------------------

# Calling-convention + IMPORTANT footer. Matches the Qwen3.6 chat template.
# Required so vLLM can parse the model's output under any user_tail* placement.
_TOOLS_BLOCK_FOOTER: str = (
    "\n\nIf you choose to call a function ONLY reply in the following format with NO suffix:\n\n"
    "<tool_call>\n<function=example_function_name>\n<parameter=example_parameter_1>\n"
    "value_1\n</parameter>\n<parameter=example_parameter_2>\n"
    "This is the value for the second parameter\nthat can span\nmultiple lines\n"
    "</parameter>\n</function>\n</tool_call>\n\n"
    "<IMPORTANT>\n"
    "Reminder:\n"
    "- Function calls MUST follow the specified format: an inner <function=...></function> block must be nested within <tool_call></tool_call> XML tags\n"
    "- Required parameters MUST be specified\n"
    "- You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after\n"
    "- If there is no function call available, answer the question like normal with your current knowledge and do not tell the user about function calls\n"
    "</IMPORTANT>"
)


# placement="user_inline_delta" hints. Two constant strings that tell the model
# the mid-context carriers stay callable: a standing note on the system message
# (front) and a recency reminder. Constant → never perturb the shared prefix;
# phrased as a reminder (not a task) to avoid trailing-carrier OOD re-execution.
_INLINE_DELTA_SYSTEM_HINT: str = (
    "\n\nTool definitions may appear in earlier messages of this conversation. "
    "Every tool defined anywhere above remains available to call at any turn, "
    "even if it is not repeated near the end of the conversation."
)
_INLINE_DELTA_TAIL_REMINDER: str = (
    "Reminder: any tool defined earlier in this conversation is still available "
    "to call now."
)

# Internal toggle (flip in code, not a config param). False: reminder is
# ephemeral, tail of user turns only. True: reminder is persisted and replayed
# at each user-query offset, so mid-loop reqs also see it (mid-context).
_INLINE_DELTA_REPLAY_REMINDER: bool = True


def _render_extra_keys(json_dict: dict, handled_keys: list[str]) -> str:
    """Port of the chat_template's `render_extra_keys` jinja macro.

    For each key in `json_dict` not in `handled_keys`, render
    `<key>value</key>`. Mappings / non-string sequences become JSON;
    everything else is stringified.
    """
    if not isinstance(json_dict, dict):
        return ""
    parts: list[str] = []
    for key in json_dict:
        if key in handled_keys:
            continue
        val = json_dict[key]
        if isinstance(val, dict) or (
            isinstance(val, (list, tuple)) and not isinstance(val, str)
        ):
            value_str = json.dumps(val)
        else:
            value_str = str(val)
        parts.append(f"\n<{key}>{value_str}</{key}>")
    return "".join(parts)


def render_tools_block(tools: list[dict]) -> str:
    """Render `tools` as Qwen/Qwen3.6-35B-A3B's `# Tools\n\n...</IMPORTANT>` block.

    This is the exact substring extracted by the regression test from the
    tokenizer's `apply_chat_template(..., tools=...)` output.
    Used by all trailing-carrier placements. Returns "" when `tools` is empty.
    """
    if not tools:
        return ""

    body = "# Tools\n\nYou have access to the following functions:\n\n<tools>"
    for tool in tools:
        body += "\n"
        body += json.dumps(tool, ensure_ascii=False)
    body += "\n</tools>"
    body += _TOOLS_BLOCK_FOOTER
    return body


def filter_tooling_section(content: str, predicted_names: list[str]) -> str:
    """Filter the natural-language `## Tooling` section inside a system message.

    v0.1: kept for future use; ToolCompressor.compress() does NOT call it.
    """
    if not predicted_names:
        return content

    predicted_set = {n.lower() for n in predicted_names if isinstance(n, str)}

    if "\n## Tooling\n" in content:
        nl = "\n"
    elif "\\n## Tooling\\n" in content:
        nl = "\\n"
    else:
        return content

    tooling_marker = f"{nl}## Tooling{nl}"
    tooling_pos = content.find(tooling_marker)
    section_start = tooling_pos + len(tooling_marker)

    next_heading_pos = content.find(f"{nl}## ", section_start)
    section_end = next_heading_pos if next_heading_pos != -1 else len(content)

    section_content = content[section_start:section_end]
    lines = section_content.split(nl)

    filtered_lines: list[str] = []
    for line in lines:
        match = _TOOL_LINE_RE.match(line.strip())
        if match:
            tool_name = match.group(1).lower()
            if tool_name in predicted_set:
                filtered_lines.append(line)
        else:
            filtered_lines.append(line)

    new_section = nl.join(filtered_lines)
    return content[:section_start] + new_section + content[section_end:]


class ToolCompressor:
    """Predict task-relevant tools and filter the tools schema array. Does
    not modify `messages` — preserves legacy `tool_compact` behaviour."""

    name: str = "tool"

    def __init__(
        self,
        *,
        predictor_url: str,
        predictor_model: str = "Qwen/Qwen3.6-35B-A3B",
        score_threshold: float = 2.0,
        timeout: int = 120,
        prompt_mode: Literal["static", "dynamic"] = "dynamic",
        tool_descriptions_mode: Literal["static", "dynamic"] = "dynamic",
        placement: Literal[
            "schema", "user_tail", "system_tail",
            "user_inline", "user_inline_delta",
        ] = "schema",
        accumulate: bool = True,
        accumulate_max_conversations: int = 1024,
    ) -> None:
        if prompt_mode not in ("static", "dynamic"):
            raise ConfigError(
                f"ToolCompressor: prompt_mode must be 'static' or 'dynamic', "
                f"got {prompt_mode!r}"
            )
        if tool_descriptions_mode not in ("static", "dynamic"):
            raise ConfigError(
                f"ToolCompressor: tool_descriptions_mode must be 'static' or "
                f"'dynamic', got {tool_descriptions_mode!r}"
            )
        if placement not in (
            "schema", "user_tail", "system_tail",
            "user_inline", "user_inline_delta",
        ):
            raise ConfigError(
                f"ToolCompressor: placement must be 'schema', 'user_tail', "
                f"'system_tail', 'user_inline', or 'user_inline_delta', "
                f"got {placement!r}"
            )
        # user_inline_delta needs the running union to compute the delta.
        if placement == "user_inline_delta" and not accumulate:
            raise ConfigError(
                "ToolCompressor: placement='user_inline_delta' requires "
                "accumulate=True (it emits per-turn tool deltas over the "
                "conversation's running union)."
            )
        if not (1.0 <= score_threshold <= 5.0):
            raise ConfigError(
                f"ToolCompressor: score_threshold must be in [1.0, 5.0], "
                f"got {score_threshold!r}"
            )
        if timeout <= 0:
            raise ConfigError(f"ToolCompressor: timeout must be > 0, got {timeout!r}")

        self._predictor: ToolPredictor = HTTPToolPredictor(
            url=predictor_url,
            model=predictor_model,
            timeout=timeout,
        )
        self._score_threshold = score_threshold
        self._prompt_template = (
            FOCUS_FIVE_TOOL_PROMPT if prompt_mode == "static" else BASE_PROMPT
        )
        self._prompt_mode = prompt_mode
        self._tool_descriptions_mode = tool_descriptions_mode
        self._placement = placement
        # Cumulative-append mode: accumulate the predicted tool set per
        # conversation (union, append-only, never remove/reorder) so each turn's
        # tool block strictly extends the previous turn's — prefix-cache stable
        # while still admitting tools that only emerge in later turns.
        self._accumulate = bool(accumulate)
        self._accum_max = max(1, int(accumulate_max_conversations))
        self._accum_lock = threading.Lock()
        # conversation_key -> ordered list of lower-cased tool names
        self._accum: "OrderedDict[str, list[str]]" = OrderedDict()
        # user_inline placement state: conversation_key -> ordered list of
        # (offset, carrier_content), where offset = number of *incoming*
        # (client) messages that precede the carrier. The client's history is
        # append-only within a conversation, so replaying every stored carrier
        # at its offset each turn reproduces a byte-identical interleaving —
        # the whole prior request becomes a strict prefix of the next
        # (prefix-cache stable). Bounded LRU over conversations (reuses
        # _accum_max as the conversation cap).
        self._inline_lock = threading.Lock()
        self._inline: "OrderedDict[str, list[tuple[int, str]]]" = OrderedDict()
        # replay-reminder state (only when _INLINE_DELTA_REPLAY_REMINDER):
        # conversation_key -> offsets (captured on user turns) after which the
        # reminder is re-spliced. Shares _inline_lock; bounded LRU.
        self._inline_reminder: "OrderedDict[str, list[int]]" = OrderedDict()

    def _resolve_tool_descriptions(self, tools: list[dict]) -> str:
        if self._tool_descriptions_mode == "static":
            return DEFAULT_TOOL_DESCRIPTIONS
        # Dynamic; fall back to the static list when the request carries no
        # usable tools entries.
        dynamic = build_dynamic_tool_descriptions(tools)
        return dynamic if dynamic else DEFAULT_TOOL_DESCRIPTIONS

    def _compose_system_prompt(
        self,
        tool_descriptions: str,
        *,
        skills: list[tuple[str, str]],
        call_history: list[dict],
        skill_content: str | None,
    ) -> str:
        if self._prompt_mode == "static":
            return build_static_prediction_prompt(
                template=self._prompt_template,
                tool_descriptions=tool_descriptions,
            )
        return build_dynamic_prediction_prompt(
            template=self._prompt_template,
            tool_descriptions=tool_descriptions,
            skills=skills,
            call_history=call_history,
            skill_content=skill_content,
        )

    @staticmethod
    def _skipped_result(
        ctx: CompressionContext,
        *,
        skip_reason: str,
        duration_ms: float,
        tokens_before: int,
        details: dict | None = None,
    ) -> CompressorResult:
        metrics = CompressorMetrics(
            name=ToolCompressor.name,
            scope=CompressionScope.TOOL,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            duration_ms=duration_ms,
            error=None,
            skip_reason=skip_reason,
            details=details or {},
        )
        return CompressorResult(
            messages=ctx.messages,
            tools=ctx.tools,
            metrics=metrics,
        )

    @staticmethod
    def _conversation_key(messages: list[dict]) -> str:
        """Stable id for a growing multi-turn conversation: hash of the system
        message + the FIRST user message (the task). Both stay byte-identical as
        the conversation grows, so all turns of one conversation share a key."""
        sys_c = ""
        first_user = ""
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role == "system" and not sys_c:
                sys_c = str(m.get("content", ""))
            elif role == "user":
                first_user = str(m.get("content", ""))
                break
        digest = hashlib.sha1(
            (sys_c + "\x00" + first_user).encode("utf-8", errors="ignore"),
            usedforsecurity=False,  # cache key only, not a security/crypto use
        )
        return digest.hexdigest()

    def _accumulate_names(
        self, messages: list[dict], predicted_names: list[str]
    ) -> tuple[list[str], list[str]]:
        """Merge this turn's `predicted_names` into the conversation's running
        ordered set (append-only). Returns `(merged, newly_added)` — the full
        accumulated list and the delta appended this turn. `newly_added` is an
        additive return (existing callers use only `merged`). Thread-safe;
        bounded LRU."""
        key = self._conversation_key(messages)
        with self._accum_lock:
            merged = list(self._accum.get(key, []))
            seen = set(merged)
            newly_added: list[str] = []
            for n in predicted_names:
                if not isinstance(n, str):
                    continue
                nl = n.strip().lower()
                if nl and nl not in seen:
                    merged.append(nl)
                    seen.add(nl)
                    newly_added.append(nl)
            self._accum[key] = merged
            self._accum.move_to_end(key)
            while len(self._accum) > self._accum_max:
                self._accum.popitem(last=False)
            return list(merged), newly_added

    def _record_and_reconstruct_inline(
        self,
        messages: list[dict],
        carrier_content: str,
        *,
        record: bool = True,
        record_reminder: bool = False,
    ) -> tuple[list[dict], int]:
        """Persist this turn's carrier and re-splice all stored carriers at their
        offsets. Returns (messages, carrier_count). Offsets stay valid because
        history is append-only → each turn is a strict prefix-extension.

        `record=False` (delta turns with no NEW tools): don't append a carrier,
        only replay stored ones. `record_reminder=True` (replay-reminder user
        turns): also anchor a constant reminder at offset=len, replayed like a
        carrier. Both streams replay regardless of this turn's record flags."""
        key = self._conversation_key(messages)
        offset = len(messages)
        with self._inline_lock:
            entries = list(self._inline.get(key, []))
            if record:
                if entries and entries[-1][0] == offset:
                    entries[-1] = (offset, carrier_content)  # same turn → replace
                else:
                    entries.append((offset, carrier_content))
                self._inline[key] = entries
                self._inline.move_to_end(key)
                while len(self._inline) > self._accum_max:
                    self._inline.popitem(last=False)
            elif key in self._inline:
                self._inline.move_to_end(key)  # touch LRU on read-only turns
            snapshot = list(entries)

            rem_offsets = list(self._inline_reminder.get(key, []))
            if record_reminder and offset not in rem_offsets:
                rem_offsets.append(offset)
                self._inline_reminder[key] = rem_offsets
                self._inline_reminder.move_to_end(key)
                while len(self._inline_reminder) > self._accum_max:
                    self._inline_reminder.popitem(last=False)
            elif key in self._inline_reminder:
                self._inline_reminder.move_to_end(key)
            rem_snapshot = set(rem_offsets)

        by_offset: dict[int, list[str]] = {}
        for off, content in snapshot:
            by_offset.setdefault(off, []).append(content)

        def _emit_at(out: list[dict], off: int) -> None:
            for content in by_offset.get(off, []):
                out.append({"role": "user", "content": content})
            if off in rem_snapshot:
                out.append(
                    {"role": "user", "content": _INLINE_DELTA_TAIL_REMINDER}
                )

        out: list[dict] = []
        _emit_at(out, 0)
        for i, msg in enumerate(messages):
            out.append(msg)
            _emit_at(out, i + 1)
        return out, len(snapshot)

    @staticmethod
    def _inject_inline_delta_hints(
        messages: list[dict], *, add_reminder: bool
    ) -> list[dict]:
        """Append the standing note to the first system message (always), and —
        when `add_reminder` — a trailing recency copy as the final user message.
        The reminder is gated to genuine user turns; adding it mid-tool-loop
        makes the model re-execute. Returns a new list; does not mutate inputs."""
        out: list[dict] = []
        injected = False
        for m in messages:
            if (
                not injected
                and isinstance(m, dict)
                and m.get("role") == "system"
            ):
                content = str(m.get("content", ""))
                out.append({**m, "content": content + _INLINE_DELTA_SYSTEM_HINT})
                injected = True
            else:
                out.append(m)
        if not injected:
            out.insert(
                0, {"role": "system", "content": _INLINE_DELTA_SYSTEM_HINT.strip()}
            )
        if add_reminder:
            out.append({"role": "user", "content": _INLINE_DELTA_TAIL_REMINDER})
        return out

    def compress(self, ctx: CompressionContext) -> CompressorResult:
        start = time.perf_counter()
        tokens_before = count_tools_tokens(ctx.tools)

        task_info = MessageAccessor.find_last_user_message(
            ctx.messages, skip_framework=True,
        )
        if task_info is None:
            return self._skipped_result(
                ctx,
                skip_reason="no_task",
                duration_ms=(time.perf_counter() - start) * 1000,
                tokens_before=tokens_before,
            )

        if not ctx.tools:
            return self._skipped_result(
                ctx,
                skip_reason="no_tools",
                duration_ms=(time.perf_counter() - start) * 1000,
                tokens_before=tokens_before,
            )

        task_idx, task_text = task_info
        original_tool_count = len(ctx.tools)

        # Always extract — the dynamic prompt builder uses these; the static
        # builder ignores them. Pure-function calls, low cost.
        skills = extract_skills(ctx.messages)
        call_history = extract_call_history(ctx.messages, start_index=task_idx)
        skill_content = extract_skill_content(ctx.messages, start_index=task_idx)

        tool_descriptions = self._resolve_tool_descriptions(ctx.tools)
        system_prompt = self._compose_system_prompt(
            tool_descriptions,
            skills=skills,
            call_history=call_history,
            skill_content=skill_content,
        )

        try:
            candidates, raw_meta = self._predictor.predict(
                task_text, system_prompt=system_prompt,
            )
        except PredictorError as e:
            logger.warning("Predictor failed: %s", e)
            duration_ms = (time.perf_counter() - start) * 1000
            metrics = CompressorMetrics(
                name=self.name,
                scope=CompressionScope.TOOL,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                duration_ms=duration_ms,
                error=str(e),
                skip_reason=None,
                details={
                    "original_tool_count": original_tool_count,
                    "compressed_tool_count": original_tool_count,
                },
            )
            return CompressorResult(
                messages=ctx.messages,
                tools=ctx.tools,
                metrics=metrics,
            )

        predicted: list[ToolCandidate] = [
            c for c in candidates if c.score >= self._score_threshold
        ]
        predicted_names = [c.name for c in predicted]

        # Cumulative-append mode: merge this turn's prediction into the
        # conversation's running ordered set (append-only). `effective_names`
        # drives filtering/placement; per-turn mode uses the raw prediction.
        if self._accumulate:
            effective_names, newly_added = self._accumulate_names(
                ctx.messages, predicted_names
            )
        else:
            effective_names = predicted_names
            newly_added = predicted_names

        if not effective_names:
            # Nothing scored above threshold. For schema placement, forward the
            # full tool schema unchanged (safe fallback). For trailing-carrier
            # placements, keep the placement CONSISTENT: relocate the full
            # schema into the carrier with `tools` omitted, so this turn keeps
            # the same prefix shape as the filtered turns. Otherwise a
            # schema-style request (full tools in the `tools` field, rendered in
            # the system slot) would be injected into an otherwise carrier-based
            # conversation and break its shared prefix / prefix-cache reuse.
            if self._placement not in (
                "user_tail", "system_tail",
                "user_inline", "user_inline_delta",
            ):
                duration_ms = (time.perf_counter() - start) * 1000
                details = {
                    "original_tool_count": original_tool_count,
                    "compressed_tool_count": original_tool_count,
                    "filtered_count": 0,
                    "score_threshold": self._score_threshold,
                    "predicted_count": 0,
                    "skills_found": len(skills),
                    "call_history_length": len(call_history),
                    "candidates": list(candidates),
                    "predictor_meta": raw_meta,
                }
                return self._skipped_result(
                    ctx,
                    skip_reason="no_tools_predicted",
                    duration_ms=duration_ms,
                    tokens_before=tokens_before,
                    details=details,
                )
            # Trailing-carrier fallback: carry the full schema, no filtering.
            filtered_tools = list(ctx.tools)
            no_prediction_fallback = True
        elif self._accumulate:
            # Emit in ACCUMULATED order so each turn's block strictly extends
            # the previous turn's (prefix-cache stable across turns).
            filtered_tools = order_tools_by_names(ctx.tools, effective_names)
            no_prediction_fallback = False
        else:
            filtered_tools = filter_tools(ctx.tools, predicted_names)
            no_prediction_fallback = False

        tokens_after = count_tools_tokens(filtered_tools)

        # Apply placement. Trailing-carrier variants clear `result.tools` so
        # the chat template doesn't ALSO render a `<tools>` block in system,
        # then append the rendered block as a final message whose role
        # (user / system) is chosen below.
        inline_carrier_count: int | None = None
        if self._placement == "user_inline":
            # Same tail carrier as user_tail, but persisted per-conversation and
            # re-spliced at its offset each turn → prefix-cache stable.
            carrier_content = render_tools_block(filtered_tools)
            result_messages, inline_carrier_count = (
                self._record_and_reconstruct_inline(ctx.messages, carrier_content)
            )
            result_tools: list[dict] | None = None
        elif self._placement == "user_inline_delta":
            # Delta mode (accumulate=True enforced): append a carrier only on
            # turns with NEW tools (just the delta); earlier tools persist via
            # replayed carriers. Reminder gated to user turns; replay ON records
            # it at the user-query offset, OFF appends it ephemerally at the tail.
            last_role = next(
                (m.get("role") for m in reversed(ctx.messages)
                 if isinstance(m, dict)),
                None,
            )
            is_user_turn = (last_role == "user")
            replay = _INLINE_DELTA_REPLAY_REMINDER
            record_reminder = replay and is_user_turn
            if no_prediction_fallback:
                # Union still empty (predictor produced nothing yet): show the
                # full schema this turn as a NON-recorded trailing carrier, so
                # it is not replayed forever once the predictor starts producing.
                result_messages, inline_carrier_count = (
                    self._record_and_reconstruct_inline(
                        ctx.messages, "", record=False,
                        record_reminder=record_reminder,
                    )
                )
                result_messages = list(result_messages) + [
                    {"role": "user", "content": render_tools_block(filtered_tools)}
                ]
            else:
                delta_tools = order_tools_by_names(ctx.tools, newly_added)
                carrier_content = render_tools_block(delta_tools)
                result_messages, inline_carrier_count = (
                    self._record_and_reconstruct_inline(
                        ctx.messages, carrier_content, record=bool(delta_tools),
                        record_reminder=record_reminder,
                    )
                )
            result_messages = self._inject_inline_delta_hints(
                result_messages,
                add_reminder=(is_user_turn and not replay),
            )
            result_tools: list[dict] | None = None
        elif self._placement in ("user_tail", "system_tail"):
            carrier_content = render_tools_block(filtered_tools)
            carrier_role = "system" if self._placement == "system_tail" else "user"
            result_messages = list(ctx.messages) + [
                {"role": carrier_role, "content": carrier_content}
            ]
            # Omit the `tools` field entirely (None, not []) — the tools now
            # live in the trailing carrier. An empty `tools=[]` array survives
            # `model_dump(exclude_none=True)` downstream and is rejected by
            # strict backends (Qwen3.6-35B-A3B: "`tools` must not be an empty
            # array. Either provide at least one tool or omit the field").
            result_tools: list[dict] | None = None
        else:
            result_messages = ctx.messages
            result_tools = filtered_tools

        duration_ms = (time.perf_counter() - start) * 1000

        metrics = CompressorMetrics(
            name=self.name,
            scope=CompressionScope.TOOL,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            duration_ms=duration_ms,
            error=None,
            skip_reason=None,
            details={
                "original_tool_count": original_tool_count,
                "compressed_tool_count": len(filtered_tools),
                "filtered_count": original_tool_count - len(filtered_tools),
                "score_threshold": self._score_threshold,
                "predicted_count": len(predicted_names),
                "predicted_tools": predicted_names,
                "placement": self._placement,
                "accumulate": self._accumulate,
                "accumulated_count": len(effective_names) if self._accumulate else None,
                "inline_carrier_count": inline_carrier_count,
                "inline_delta_count": (
                    len(newly_added)
                    if self._placement == "user_inline_delta"
                    else None
                ),
                "no_prediction_fallback": no_prediction_fallback,
                "skills_found": len(skills),
                "call_history_length": len(call_history),
                "candidates": list(candidates),
                "predictor_meta": raw_meta,
            },
        )

        return CompressorResult(
            messages=result_messages,
            tools=result_tools,
            metrics=metrics,
        )

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        return self._predictor.health_check(timeout=timeout)
