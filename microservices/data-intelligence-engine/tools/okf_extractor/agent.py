# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .concept import Concept
from .llmclient import LLMClient, approx_tokens
from .ui import UI

#: How `write_concept` answers a call identical to one already recorded.
ALREADY_RECORDED = "Already recorded concept"


class ExtractionResponseError(RuntimeError):
    """The model could not complete a valid, fully read extraction batch."""


@dataclass
class AgentCtx:
    """Per-session mutable state, shared with tool handlers."""
    data_dir: Path
    read_budget: int                                   # token budget for read_* this session
    already_seen: list[str] = field(default_factory=list)  # "type::title" dedup hints
    sink: list[Concept] = field(default_factory=list)      # concepts emitted this session
    files_read: list[str] = field(default_factory=list)    # rel_paths successfully read
    read_tokens: int = 0                               # running read-token counter
    budget_exhausted: bool = False
    assigned_files: set[str] | None = None             # None for unscoped sessions
    completed_files: set[str] = field(default_factory=set)
    text_read_ranges: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    last_tool_error: str = ""
    # human-in-the-loop
    interactive: bool = False                          # if True, ask_human blocks for stdin
    ui: "UI | None" = None                             # for ask_human's terminal prompt
    findings: list[dict] = field(default_factory=list)  # escalations recorded (both modes)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict                                   # JSON Schema (OpenAI function.parameters)
    handler: Callable[[dict, AgentCtx], str]           # returns model-facing tool-result string


def _read_source_paths(ctx: AgentCtx) -> list[str]:
    return sorted({
        path for path in ctx.files_read
        if ctx.assigned_files is None or path in ctx.assigned_files
    })


def _source_files_guidance(ctx: AgentCtx) -> str:
    paths = _read_source_paths(ctx)
    if not paths:
        return (
            "source_files is REQUIRED on EVERY write_concept call as a non-empty JSON array. "
            "No source files have been read successfully yet; read an assigned file before writing. "
            "Do not guess or invent provenance."
        )
    return (
        "source_files is REQUIRED on EVERY write_concept call as a non-empty JSON array "
        "of exact fragment paths. Successfully read paths: "
        + json.dumps(paths, ensure_ascii=False)
        + ". Select only the paths whose contents support this specific concept, not every path by default. "
        "Do not guess or invent provenance, use a parent folder, or reread completed fragments."
    )


def openai_tools(tools: list[Tool], ctx: AgentCtx | None = None) -> list[dict]:
    specs = []
    for tool in tools:
        parameters = deepcopy(tool.parameters)
        description = tool.description
        if tool.name == "write_concept" and ctx is not None:
            description += " " + _source_files_guidance(ctx)
            paths = _read_source_paths(ctx)
            if paths:
                parameters["properties"]["source_files"]["items"]["enum"] = paths
        specs.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": description,
                "parameters": parameters,
            },
        })
    return specs


def _tool_result(tc: dict, out: str) -> dict:
    return {"role": "tool", "tool_call_id": tc.get("id"), "content": out}


def _schema_error(value: Any, schema: dict, path: str = "arguments") -> str | None:
    """Validate against the small JSON Schema subset the tool schemas use."""
    types = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    kind = schema.get("type")
    expected = types.get(kind)
    if expected and (not isinstance(value, expected) or (
        kind in ("integer", "number") and isinstance(value, bool)
    )):
        return f"{path}: expected {kind}, got {type(value).__name__}"
    if isinstance(value, dict):
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            return f"{path}: missing required field(s): {', '.join(missing)}"
        for name, spec in schema.get("properties", {}).items():
            if name in value:
                error = _schema_error(value[name], spec, f"{path}.{name}")
                if error:
                    return error
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return f"{path}: must contain at least {schema['minItems']} item(s)"
        for index, item in enumerate(value):
            error = _schema_error(item, schema.get("items", {}), f"{path}[{index}]")
            if error:
                return error
    elif isinstance(value, str) and len(value.strip()) < schema.get("minLength", 0):
        return f"{path}: must be a non-empty string"
    elif isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        return f"{path}: must be at least {schema['minimum']}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: must be one of {schema['enum']}"
    return None


def _parse_and_validate(args_json: str | dict, schema: dict) -> tuple[dict | None, str | None]:
    try:
        args = args_json if isinstance(args_json, dict) else json.loads(args_json) if args_json else {}
    except (TypeError, ValueError):
        return None, "arguments: invalid JSON; return one complete JSON object matching the tool schema"
    if not isinstance(args, dict):
        return None, "arguments: expected one JSON object per tool call, not an array or a JSON string"
    error = _schema_error(args, schema)
    if error:
        return None, error + ". Rewrite this tool call using the declared field names and JSON types."
    return args, None


def _rejected_label(name: str, args_json: str | dict) -> str:
    try:
        args = args_json if isinstance(args_json, dict) else json.loads(args_json or "{}")
    except (TypeError, ValueError):
        return ""
    return f" ({_call_detail(name, args)})" if name == "write_concept" and isinstance(args, dict) else ""


def _tool_call_key(name: str, args_json: str | dict) -> tuple[str, ...]:
    """Key write_concept calls by (type, title) so a fix clears only that concept's error."""
    if name == "write_concept":
        try:
            args = args_json if isinstance(args_json, dict) else json.loads(args_json or "{}")
        except (TypeError, ValueError):
            args = None
        if isinstance(args, dict) and all(
            isinstance(args.get(field), str) and args[field].strip()
            for field in ("type", "title")
        ):
            return name, args["type"].strip(), args["title"].strip()
    return (name,)


def _write_repair_feedback(out: str, ctx: AgentCtx) -> str:
    return (
        out + "\nNo concept was recorded for this rejected call. Reissue the SAME type and title "
        "with all required fields; do not substitute a different concept. " + _source_files_guidance(ctx)
    )


def _call_detail(name: str, args: dict) -> str:
    if not isinstance(args, dict):
        return ""
    if name == "write_concept":
        return f"{args.get('type', '?')}: {args.get('title', '?')}"
    if name == "list_dir":
        return args.get("path", ".") or "."
    p = args.get("path")
    if p is not None:
        mode = args.get("mode")
        off = args.get("offset")
        extra = []
        if mode:
            extra.append(f"mode={mode}")
        if off:
            extra.append(f"offset={off}")
        return f"{p}" + (f"  ({', '.join(extra)})" if extra else "")
    return ""


def _result_note(name: str, out: str, ctx: AgentCtx) -> str:
    low = out.lower()
    if out.startswith("Read budget exhausted"):
        return "budget exhausted → emit"
    if out.startswith("Already read:"):
        return "already read → emit or next file"
    if out.startswith("End of file:"):
        return "EOF → emit or next file"
    if out.startswith(("Tool input rejected:", "Could not read", "Could not open")):
        return "rejected"
    if "not found" in low or "outside the data root" in low:
        return "not found"
    if name.startswith("read_"):
        state = "read complete" if "End of file." in out else "read ok"
        return f"{state} · {ctx.read_tokens}/{ctx.read_budget} tok used"
    if name == "list_dir":
        n = max(out.count("\n"), 0)
        return f"{n} entries"
    if name == "write_concept":
        if not out.startswith("recorded concept:"):
            return "not recorded"
        links = out.rsplit(", ", 1)[-1] if out.endswith("link(s)") else ""
        return f"recorded, {links}" if links else "recorded"
    return (out.splitlines()[0][:60] if out else "")


def _rejected(out: str) -> bool:
    return out.startswith((
        "Tool input rejected:", "File not found", "Path not found",
        "Could not read", "Could not open",
    ))


def run_agent(
    client: LLMClient,
    system: str,
    tools: list[Tool],
    ctx: AgentCtx,
    max_steps: int,
    first_user: str,
    ui: UI | None = None,
    history_limit: int = 0,
    chars_per_token: float = 3.0,
    output_tokens: int = 4096,
    max_response_tokens: int = 8192,
    max_idle_steps: int = 4,
    final_emit_steps: int = 4,
) -> str:
    """Drive one tool-loop session over `ctx`; returns how it ended ("natural", "soft_gate", "max_steps", ...)."""
    if max_steps <= 0 or output_tokens <= 0 or max_response_tokens <= 0:
        raise ValueError("Extraction step and output token limits must be positive")
    ui = ui or UI(enabled=False)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": first_user},
    ]
    reg = {t.name: t for t in tools}
    recent: list[tuple[str, str]] = []                 # (name, args_json) for doom-loop
    forced_final = False
    forced_reason = ""                                 # "soft_gate" if the soft-gate fired
    read_complete_notice = False
    links_notice = False
    idle_steps = 0
    repeat_steps = 0                                   # turns that only re-sent recorded concepts
    pending_errors: dict[tuple[str, ...], str] = {}
    emit_steps = min(max(1, final_emit_steps), max(1, max_steps // 5))

    for step in range(max_steps):
        progress = (ctx.read_tokens, len(ctx.completed_files), len(ctx.sink), len(ctx.findings))
        errors_before = len(pending_errors)
        all_read = ctx.assigned_files is not None and ctx.assigned_files <= ctx.completed_files
        if all_read and not read_complete_notice:
            read_complete_notice = True
            messages.append({"role": "user", "content": (
                "All assigned fragments have been read completely. Do not list or read them again. "
                "Emit the remaining concepts using write_concept (several separate calls per "
                "response are allowed), then finish. " + _source_files_guidance(ctx)
            )})
        # Soft-gate: force a final emit turn before the history overflows the context.
        over_history = (
            history_limit > 0
            and approx_tokens(messages, chars_per_token) > history_limit
        )
        if (step >= max_steps - emit_steps or over_history) and not forced_final:
            forced_final = True
            if over_history:
                forced_reason = "soft_gate"
            reason = "history near context limit" if over_history else "reserved final emit turns"
            ui.info(f"(forcing final emit: {reason})")
            messages.append({
                "role": "user",
                "content": (
                    "Stop reading now. Emit your remaining concepts with "
                    "write_concept, then finish."
                ),
            })

        emitting = forced_final or all_read
        active_tools = [tool for tool in tools if not emitting or tool.name in ("write_concept", "ask_human")]
        ceiling = max_response_tokens
        limit = min(output_tokens, ceiling)
        if history_limit > 0:
            headroom = history_limit - approx_tokens(messages, chars_per_token) - 256
            ceiling = min(ceiling, headroom)
            limit = min(limit, ceiling)
        if limit <= 0:
            return "soft_gate"
        # Retry truncated responses with a larger max_tokens instead of dispatching partial tool calls.
        while True:
            with ui.spinner(f"waiting for model · turn {step + 1} (limit {max_steps})"):
                choice = client.chat(
                    messages, tools=openai_tools(active_tools, ctx), tool_choice="auto", max_tokens=limit,
                )
            if choice.get("finish_reason") != "length":
                break
            increased = min(limit * 2, ceiling)
            if increased <= limit:
                ctx.last_tool_error = f"Model tool response truncated at max_tokens={limit}"
                ui.warn(ctx.last_tool_error)
                return "output_limit"
            ui.warn(f"tool response truncated at max_tokens={limit}; retrying same turn at {increased}")
            limit = increased
        output_tokens = limit
        msg = choice.get("message", {}) or {}
        tcs = msg.get("tool_calls") or []

        if not tcs:
            if choice.get("finish_reason") != "stop":
                ctx.last_tool_error = f"Model returned no usable tool calls (finish_reason={choice.get('finish_reason')})"
                return "invalid_response"
            if pending_errors:
                idle_steps += 1
                ctx.last_tool_error = next(reversed(pending_errors.values()))
                if idle_steps >= max(1, max_idle_steps):
                    ui.warn("model stopped with unresolved tool errors — retrying a smaller batch")
                    return "invalid_args"
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                outstanding = list(pending_errors.values())
                details = "\n".join(f"- {error}" for error in outstanding[:8])
                if len(outstanding) > 8:
                    details += f"\n- {len(outstanding) - 8} more rejected calls remain; correct each one."
                messages.append({"role": "user", "content": (
                    "Do not finish with unresolved rejected tool calls. Correct each rejected "
                    "write_concept using the SAME type and title; successful writes for other "
                    "concepts do not repair it.\n" + details + "\n" + _source_files_guidance(ctx)
                )})
                continue
            # Ask once for links if no recorded concept has any.
            if (not links_notice and len(ctx.sink) > 1 and step < max_steps - 1
                    and not any(concept.links for concept in ctx.sink)):
                links_notice = True
                ui.info("no relations recorded — asking for links once")
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                messages.append({"role": "user", "content": (
                    "None of the recorded concepts has links. Following the relation rules, "
                    "call write_concept again for each concept that has relations supported "
                    "by the text, with the same type, title, summary and source_files plus "
                    "`links` to the exact titles of the related concepts. Then finish."
                )})
                continue
            return forced_reason or "natural"

        # Some compatible servers return object-valued arguments; normalize to strings in history.
        for tc in tcs:
            fn = tc.get("function", {}) or {}
            if isinstance(fn.get("arguments"), dict):
                fn["arguments"] = json.dumps(fn["arguments"], ensure_ascii=False)
        messages.append(msg)
        only_repeats = True                            # every call this turn re-sent a recorded concept
        for tc in tcs:
            fn = tc.get("function", {}) or {}
            name = fn.get("name", "")
            args_json = fn.get("arguments", "") or ""
            call_key = _tool_call_key(name, args_json)
            try:
                arguments_key = json.dumps(
                    args_json if isinstance(args_json, dict) else json.loads(args_json),
                    sort_keys=True, ensure_ascii=False,
                )
            except (TypeError, ValueError):
                arguments_key = str(args_json)

            # Doom-loop breaker: 3 identical (name, args) calls in a row force an emit.
            recent.append((name, arguments_key))
            recent = recent[-3:]
            if len(recent) == 3 and len(set(recent)) == 1:
                ui.warn(f"{name}: repeated identical call — nudging to emit")
                only_repeats = only_repeats and name == "write_concept"
                feedback = pending_errors.get(call_key)
                messages.append(_tool_result(
                    tc,
                    _write_repair_feedback(feedback, ctx)
                    if feedback and name == "write_concept" else
                    "Repeated identical call detected. Stop reading and emit "
                    "write_concept now, or finish.",
                ))
                continue

            tool = reg.get(name)
            if tool is None:
                out = f"Unknown tool '{name}'. Choose one of: {', '.join(reg)}."
                ui.warn(f"unknown tool {name!r}")
                ctx.last_tool_error = f"Unknown extraction tool: {name}"
                pending_errors[call_key] = ctx.last_tool_error
            elif emitting and name not in ("write_concept", "ask_human"):
                out = "All assigned input is read or the read budget is closed. Emit write_concept, then finish."
                ui.info(f"{name}: reading is closed — emit concepts instead")
            else:
                args, err = _parse_and_validate(args_json, tool.parameters)
                if err:
                    out = _write_repair_feedback(err, ctx) if name == "write_concept" else err
                    ctx.last_tool_error = f"{name}{_rejected_label(name, args_json)}: {err}"
                    pending_errors[call_key] = ctx.last_tool_error
                    ui.warn(f"{name}: invalid args{_rejected_label(name, args_json)} — {err}")
                else:
                    out = tool.handler(args, ctx)
                    if _rejected(out):
                        ctx.last_tool_error = f"{name}{_rejected_label(name, args_json)}: {out}"
                        pending_errors[call_key] = ctx.last_tool_error
                        ui.warn(ctx.last_tool_error)
                        if name == "write_concept":
                            out = _write_repair_feedback(out, ctx)
                    else:
                        pending_errors.pop(call_key, None)
                        ctx.last_tool_error = next(reversed(pending_errors.values()), "")
                    ui.tool(name, _call_detail(name, args), _result_note(name, out, ctx))
            only_repeats = only_repeats and name == "write_concept" and out.startswith(ALREADY_RECORDED)
            messages.append(_tool_result(tc, out))

        updated = (ctx.read_tokens, len(ctx.completed_files), len(ctx.sink), len(ctx.findings))
        # All input read and only already-recorded concepts repeated: treat as finished.
        all_read = ctx.assigned_files is not None and ctx.assigned_files <= ctx.completed_files
        repeat_steps = repeat_steps + 1 if (all_read and only_repeats and updated == progress) else 0
        if repeat_steps >= 2 and not pending_errors:
            ui.info("model repeats recorded concepts only — batch complete")
            return "natural"
        repaired_error = len(pending_errors) < errors_before
        idle_steps = idle_steps + 1 if updated == progress and not repaired_error else 0
        if idle_steps >= max(1, max_idle_steps):
            ui.warn(f"no extraction progress for {idle_steps} turn(s) — retrying a smaller batch")
            return "invalid_args" if pending_errors else "stalled"

    return "invalid_args" if pending_errors else "max_steps"
