# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batched concept extraction, used inside the task pipeline's second stage.

Spawns SHORT-LIVED extract-agent sessions until every file is covered. Never one giant
session (that is how codex overflowed). The DRIVER pre-slices each session's batch
deterministically — bounded by BOTH a token budget (cfg.read_input_budget()) AND a hard
file-count cap (cfg.batch.max_files_per_batch) — so a session can never swallow dozens
of tiny files and then under-extract. The agent is briefed on exactly that batch, reads
those files, and emits write_concept per concept. Only the assigned batch leaves the
`remaining` set — files are never silently dropped just because a session ran out of
steps. Batches share ONLY the already-extracted concept-title list (a dedup hint), never
source text. File order is preserved so subfolder groupings stay together in one batch.
"""
from __future__ import annotations

from .agent import AgentCtx, ExtractionResponseError, run_agent
from .concept import Concept
from .llmclient import ContextOverflowError
from .prompts import render_extract_system
from .structure import FileInfo, Tree
from .tools import build_tools
from .ui import UI

# adaptive fallback knobs (self-contained; not exposed in config for the POC)
_SHRINK = 0.5          # multiply the batch read budget by this on overflow, then retry
_BUDGET_FLOOR = 4000   # tokens; a strict single-file session fails rather than skipping it
_MAX_ATTEMPTS = 6      # hard cap on retries per batch — guarantees forward progress, no spin


def _plan_batch(ordered: list[FileInfo], budget: int, max_files: int = 8) -> list[FileInfo]:
    """Pick the next session's batch from the head of `ordered` (order preserved so
    subfolders stay grouped), by estimated token size against `budget`. Always returns
    at least one file (a single file bigger than the whole budget goes alone — the agent
    reads it in offset chunks; the floor guard prevents an infinite retry)."""
    batch: list[FileInfo] = []
    total = 0
    for f in ordered:
        if batch and (total + f.approx_tokens > budget or len(batch) >= max_files):
            break
        batch.append(f)
        total += f.approx_tokens
    return batch


def _batch_briefing(batch: list[FileInfo], seen_titles: list[str]) -> str:
    listing = "\n".join(
        f"- {f.rel_path}  (~{f.approx_tokens} tok, .{f.ext or '?'})" for f in batch
    )
    seen = "\n".join(f"- {s}" for s in seen_titles[-200:]) or "(none yet)"
    return (
        f"Extract concepts from THESE {len(batch)} file(s) — read every one of them, then "
        f"emit concepts at the granularity specified in the task instructions. "
        f"These are normalized text fragments, not separate real-world entities. "
        f"Read only the assigned files, once each, using read_text. Only request an "
        f"offset when a read explicitly says Output capped and supplies that offset. "
        f"End of file means no continuation is needed. Paths ending in a source "
        f"name and a numbered .md filename are fragments: cite that FULL path in "
        f"source_files, not its containing folder. The driver restores original "
        f"source names later. Several separate write_concept calls per response "
        f"are allowed; each call is one JSON object, never a list.\n\n"
        f"Files for this batch:\n{listing}\n\n"
        f"Concepts already extracted in earlier batches (REUSE these exact titles when the "
        f"same real thing appears again; do not re-create them unless this file adds new "
        f"information):\n{seen}"
    )


def _smaller_batch(
    remaining: list[FileInfo], batch: list[FileInfo], budget: int, floor: int,
) -> tuple[int, list[FileInfo]]:
    """Reduce workload, not just a token limit that may still select all files."""
    next_budget = max(floor, int(budget * _SHRINK))
    next_cap = max(1, len(batch) // 2)
    return next_budget, _plan_batch(remaining, next_budget, next_cap)


def extract(cfg, client, tree: Tree, ui: UI | None = None,
            interactive: bool = False, findings: list[dict] | None = None,
            instructions: dict | None = None, strict: bool = False) -> list[Concept]:
    ui = ui or UI(enabled=False)
    findings = findings if findings is not None else []
    seen_titles: list[str] = []
    all_concepts: list[Concept] = []
    session = 0

    # ordered work-list (preserves folder grouping); we consume from its head.
    # Optional batch.priority_globs (dataset-agnostic, default none): files matching these
    # globs are moved to the FRONT so entity-profile / definition files (which carry the
    # relations) are extracted before bulk record/log files. Without it, os.walk's
    # alphabetical order can bury the profiles behind hundreds of records so their
    # relations never enter an extraction session. Order within each partition preserved.
    remaining: list[FileInfo] = list(tree.files)
    prio_globs = cfg.batch.get("priority_globs") or []
    if prio_globs:
        from fnmatch import fnmatch
        def _is_prio(f):
            return any(fnmatch(f.rel_path, g) for g in prio_globs)
        head = [f for f in remaining if _is_prio(f)]
        tail = [f for f in remaining if not _is_prio(f)]
        if head:
            remaining = head + tail
            ui.info(f"priority: {len(head)} profile/definition file(s) extracted first")

    default_budget = cfg.read_input_budget()
    floor = min(_BUDGET_FLOOR, default_budget)
    max_files = max(1, int(cfg.batch.get("max_files_per_batch", 8)))
    ctx_window = int(cfg.llm["context_window"])
    reserve = int(cfg.batch["reserve_tokens"])
    cpt = float(cfg.batch["chars_per_token"])
    # history soft-gate: leave the model room to still emit after we stop reading.
    history_limit = ctx_window - reserve
    # Render task-specific extraction instructions once, not again on session retries.
    # `instructions` override (from the web UI's per-run edits) wins over config.yaml;
    # blank segments still fall back to prompts.py defaults inside _fill_instructions.
    extract_system = render_extract_system(
        instructions if instructions is not None else cfg.instructions,
        template_path=cfg.prompt_path("extract"),
    )

    while remaining:
        session += 1
        budget = default_budget           # each batch starts at default; shrinks only on failure
        batch = _plan_batch(remaining, budget, max_files)

        # Retire input only after complete reads and a natural model finish. A
        # failed batch shrinks in file count too (8 -> 4 -> 2 -> 1); shrinking
        # tokens alone can select the same eight small fragments repeatedly.
        attempt = 0
        while True:
            attempt += 1
            ui.session(f"session {session} attempt {attempt}: {len(batch)} file(s) @ budget "
                       f"{budget}, {len(remaining)} remaining")
            want = {f.rel_path for f in batch}
            ctx = AgentCtx(
                data_dir=tree.root,
                read_budget=budget,
                already_seen=list(seen_titles),
                assigned_files=want,
                interactive=interactive,
                ui=ui,
            )
            tools = build_tools(cfg, ctx)
            briefing = _batch_briefing(batch, seen_titles)

            try:
                reason = run_agent(
                    client, extract_system, tools, ctx,
                    max_steps=int(cfg.batch["max_steps"]), first_user=briefing,
                    ui=ui, history_limit=history_limit, chars_per_token=cpt,
                    output_tokens=int(cfg.llm.get("max_tokens", 4096)),
                    max_response_tokens=int(cfg.batch.get("max_response_tokens", 8192)),
                    max_idle_steps=int(cfg.batch.get("max_idle_steps", 4)),
                    final_emit_steps=int(cfg.batch.get("final_emit_steps", 4)),
                )
            except ContextOverflowError:
                reason = "context_overflow"
                ctx.last_tool_error = "Model rejected the extraction context size"
            covered = ctx.completed_files if strict else set(ctx.files_read)
            unread = want - covered
            accept = not unread and (
                reason == "natural" or (not strict and reason == "max_steps")
            )
            if accept:
                break
            detail = (
                f"ended={reason}, fully read {len(want - unread)}/{len(want)} file(s), "
                f"emitted {len(ctx.sink)} concept(s)"
            )
            if attempt >= _MAX_ATTEMPTS or (len(batch) == 1 and budget <= floor):
                if strict:
                    error = f"Extraction did not complete its assigned batch ({detail})"
                    if ctx.last_tool_error:
                        error += f"; {ctx.last_tool_error}"
                    raise ExtractionResponseError(error)
                ui.warn(f"accepting best-effort after bounded retries ({detail})")
                break
            previous_size = len(batch)
            budget, batch = _smaller_batch(remaining, batch, budget, floor)
            # Reuse the learned file cap for later sessions, instead of starting
            # every remaining group with the same over-large workload again.
            max_files = min(max_files, len(batch))
            ui.warn(
                f"batch incomplete ({detail}) — budget→{budget}, "
                f"batch {previous_size}→{len(batch)} file(s), retrying"
            )

        # the batch was read+extracted (or accepted best-effort at the floor): retire it.
        done = {f.rel_path for f in batch}
        remaining = [f for f in remaining if f.rel_path not in done]

        for c in ctx.sink:
            all_concepts.append(c)
            seen_titles.append(f"{c.type}::{c.title}")
        findings.extend(ctx.findings)
        ui.info(f"session {session}: covered {len(done)} file(s), "
                f"emitted {len(ctx.sink)} concept(s)")

    return all_concepts
