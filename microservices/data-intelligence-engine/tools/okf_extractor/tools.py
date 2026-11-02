# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool whitelist. These tools are the CLOSED choice that resolves the
half-open-agent / fully-LLM-format-choice tension: the LLM "decides the format"
ONLY by picking which whitelisted read_* tool + args to call — never free-form shell.

Budget accounting is the batching mechanism (decision 7). Every read_* handler:
  1. computes approx_tokens = len(text) / chars_per_token;
  2. if ctx.read_tokens + approx_tokens > ctx.read_budget -> HARD-REFUSE (return a
     "budget exhausted, emit write_concept now" string, set ctx.budget_exhausted),
     WITHOUT counting the refused read;
  3. else add to ctx.read_tokens, record files_read, and return the (line+byte-capped) text.

Per-call caps (lines/bytes) mirror opencode's read tool. A reader whose config
switch is off, or whose python package fails to import, is silently dropped from the
whitelist so the agent cannot select it.
"""
from __future__ import annotations

import importlib
from pathlib import Path

from .agent import ALREADY_RECORDED, AgentCtx, Tool
from .concept import Concept

# ------------------------------------------------------------------- path safety


def _resolve_in_root(ctx: AgentCtx, path: str) -> Path | None:
    """Resolve `path` (may be rel_path or absolute) under ctx.data_dir. Reject any
    escape outside the root (`..` traversal, absolute paths elsewhere)."""
    p = Path(path)
    ap = (p if p.is_absolute() else ctx.data_dir / p).resolve()
    try:
        ap.relative_to(ctx.data_dir)
    except ValueError:
        return None
    if ctx.assigned_files is not None:
        relative = ap.relative_to(ctx.data_dir).as_posix()
        prefix = "" if relative == "." else relative + "/"
        if relative not in ctx.assigned_files and not any(
            name.startswith(prefix) for name in ctx.assigned_files
        ):
            return None
    return ap


def _rel(ctx: AgentCtx, ap: Path) -> str:
    return ap.relative_to(ctx.data_dir).as_posix()


# ------------------------------------------------------------- budget accounting


def _charge(ctx: AgentCtx, text: str, cfg_batch: dict) -> str | None:
    """Charge `text` against the session read budget. Returns a refusal string if it
    would overflow (and flips budget_exhausted), else None (and adds to the counter)."""
    cpt = float(cfg_batch.get("chars_per_token", 3.0)) or 3.0
    approx = int(len(text) / cpt)
    if ctx.read_tokens + approx > ctx.read_budget:
        ctx.budget_exhausted = True
        return (
            "Read budget exhausted for this batch. Do not read more files. "
            "Emit the concepts you have gathered with write_concept now."
        )
    ctx.read_tokens += approx
    return None


def _cap_lines(text: str, max_lines: int, max_bytes: int, start_line: int = 1) -> tuple[str, bool]:
    """Number lines; stop at max_lines OR when accumulated bytes exceed max_bytes.
    Returns (rendered, capped?)."""
    out: list[str] = []
    total = 0
    lines = text.splitlines()
    n = 0
    for i, ln in enumerate(lines, start_line):
        piece = f"{i}: {ln}"
        b = len(piece.encode("utf-8")) + 1
        if n >= max_lines or total + b > max_bytes:
            return "\n".join(out), True
        out.append(piece)
        total += b
        n += 1
    return "\n".join(out), False


# --------------------------------------------------------------------- handlers
# Each _mk_* returns a handler closure bound to cfg; build_tools wires them up.


def _mk_list_dir(cfg):
    def handler(args: dict, ctx: AgentCtx) -> str:
        rel = args.get("path", "") or "."
        ap = _resolve_in_root(ctx, rel)
        if ap is None or not ap.exists():
            return f"Path not found or outside the data root: {rel!r}"
        if ap.is_file():
            ap = ap.parent
        rows: list[str] = []
        for child in sorted(ap.iterdir(), key=lambda c: (c.is_file(), c.name)):
            if child.name.startswith("."):
                continue
            r = _rel(ctx, child)
            if _resolve_in_root(ctx, r) is None:
                continue
            if child.is_dir():
                rows.append(f"[dir]  {r}/")
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0
                approx = int(size / (float(cfg.batch.get("chars_per_token", 3.0)) or 3.0))
                rows.append(f"[file] {r}  ({size} bytes, ~{approx} tok)")
        listing = "\n".join(rows) if rows else "(empty)"
        return f"Contents of {_rel(ctx, ap) or '.'}/:\n{listing}"

    return handler


def _read_text_file(ap: Path) -> str:
    return ap.read_text(encoding="utf-8", errors="replace")


def _offset_notice(offset: int, total: int, unit: str) -> str | None:
    if offset < 0:
        return "Tool input rejected: offset must be a non-negative integer."
    if offset >= total:
        return (
            f"End of file: offset={offset} is past the {total} {unit}. No content was read. "
            "Do not increase the offset; emit concepts from previous reads or read another assigned file."
        )
    return None


def _record_text_read(ctx: AgentCtx, relative: str, start: int, end: int, total: int) -> None:
    ranges = sorted([*ctx.text_read_ranges.get(relative, []), (start, end)])
    merged: list[tuple[int, int]] = []
    for first, last in ranges:
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))
    ctx.text_read_ranges[relative] = merged
    if relative not in ctx.files_read:
        ctx.files_read.append(relative)
    if merged == [(0, total)]:
        ctx.completed_files.add(relative)


def _mk_read_text(cfg):
    b = cfg.batch

    def handler(args: dict, ctx: AgentCtx) -> str:
        rel = args.get("path", "")
        offset = int(args.get("offset", 0) or 0)
        if offset < 0:
            return "Tool input rejected: offset must be a non-negative integer."
        ap = _resolve_in_root(ctx, rel)
        if ap is None or not ap.is_file():
            return f"File not found or outside the assigned batch/data root: {rel!r}"
        relative = _rel(ctx, ap)
        if relative in ctx.completed_files:
            return (
                f"Already read: the entire fragment {relative!r} is in this session's history. "
                "There is no next offset. Emit write_concept or read another unread assigned fragment."
            )
        try:
            raw = _read_text_file(ap)
        except Exception as e:
            return f"Could not read {rel!r} as text: {e}"
        lines = raw.splitlines()
        notice = _offset_notice(offset, len(lines), "lines")
        if notice:
            return notice
        ranges = ctx.text_read_ranges.get(relative, [])
        if any(first <= offset < last for first, last in ranges):
            next_offset = 0
            for first, last in ranges:
                if first > next_offset:
                    break
                next_offset = max(next_offset, last)
            return (
                f"Already read: offset={offset} of {relative!r} is already in this session's history. "
                f"The next unread range starts at offset={next_offset}; do not replay previous content."
            )
        # Retain a final empty line: joining ["text", ""] without the extra
        # newline would make _cap_lines count one line while coverage expects two.
        body = "\n".join(lines[offset:]) + "\n"
        rendered, capped = _cap_lines(
            body, b["per_file_read_lines"], b["per_file_read_bytes"], start_line=offset + 1,
        )
        if not rendered:
            return "Tool input rejected: a text line does not fit the configured read byte/line limit."
        refusal = _charge(ctx, rendered, b)
        if refusal:
            return refusal
        shown = rendered.count("\n") + 1
        _record_text_read(ctx, relative, offset, offset + shown, len(lines))
        note = _cap_note(rendered, capped, offset) if capped else (
            "\n\n(End of file. No further offset is needed for this fragment.)"
        )
        return f"{rel} (lines from {offset + 1}, {len(lines)} lines total):\n{rendered}{note}"

    return handler


def _cap_note(rendered: str, capped: bool, offset: int) -> str:
    if not capped:
        return ""
    shown = rendered.count("\n") + 1 if rendered else 0
    return f"\n\n(Output capped. Use offset={offset + shown} to continue.)"


def _mk_read_pdf(cfg):
    b = cfg.batch

    def handler(args: dict, ctx: AgentCtx) -> str:
        rel = args.get("path", "")
        offset = int(args.get("offset", 0) or 0)   # page offset
        ap = _resolve_in_root(ctx, rel)
        if ap is None or not ap.is_file():
            return f"File not found or outside the data root: {rel!r}"
        import pypdf  # guarded by build_tools; safe here
        # TODO(v1): PDF bookmark / internal-TOC extraction — out of scope; linear text only.
        try:
            reader = pypdf.PdfReader(str(ap))
        except Exception as e:
            return f"Could not open PDF {rel!r}: {e}"
        pages = reader.pages
        notice = _offset_notice(offset, len(pages), "pages")
        if notice:
            return notice
        chunks: list[str] = []
        total = 0
        capped = False
        for pi in range(offset, len(pages)):
            try:
                txt = pages[pi].extract_text() or ""
            except Exception:
                txt = ""
            piece = f"[page {pi + 1}]\n{txt}"
            bts = len(piece.encode("utf-8"))
            if total + bts > b["per_file_read_bytes"]:
                capped = True
                break
            chunks.append(piece)
            total += bts
        rendered = "\n\n".join(chunks)
        refusal = _charge(ctx, rendered, b)
        if refusal:
            return refusal
        ctx.files_read.append(_rel(ctx, ap))
        note = ""
        if capped:
            note = f"\n\n(PDF capped. Use offset={offset + len(chunks)} for more pages.)"
        return f"{rel} ({len(pages)} pages, from page {offset + 1}):\n{rendered}{note}"

    return handler


def _mk_read_table(cfg):
    b = cfg.batch

    def handler(args: dict, ctx: AgentCtx) -> str:
        rel = args.get("path", "")
        mode = args.get("mode", "text")
        sheet = args.get("sheet", 0)
        offset = int(args.get("offset", 0) or 0)       # row offset
        ap = _resolve_in_root(ctx, rel)
        if ap is None or not ap.is_file():
            return f"File not found or outside the data root: {rel!r}"
        import pandas as pd  # guarded by build_tools
        try:
            if ap.suffix.lower() in (".xlsx", ".xls"):
                df = pd.read_excel(ap, sheet_name=sheet)
            else:
                df = pd.read_csv(ap)
        except Exception as e:
            return f"Could not read table {rel!r}: {e}"
        nrows = len(df)
        notice = _offset_notice(offset, nrows, "rows")
        if notice:
            return notice
        window = df.iloc[offset:]
        # cap rows to fit the byte budget
        rows_out: list[str] = []
        total = 0
        shown = 0
        capped = False
        if mode == "rows":
            # one compact record per row (LLM emits one concept per row when apt)
            for idx, row in window.iterrows():
                rec = " | ".join(f"{c}={row[c]}" for c in df.columns)
                piece = f"row {idx}: {rec}"
                bts = len(piece.encode("utf-8"))
                if total + bts > b["per_file_read_bytes"]:
                    capped = True
                    break
                rows_out.append(piece)
                total += bts
                shown += 1
            rendered = "\n".join(rows_out)
        else:
            # markdown-ish text preview of the frame
            preview = window.to_string(max_rows=200)
            rendered, capped = preview[: b["per_file_read_bytes"]], len(
                preview.encode("utf-8")
            ) > b["per_file_read_bytes"]
            shown = min(len(window), 200)
        refusal = _charge(ctx, rendered, b)
        if refusal:
            return refusal
        ctx.files_read.append(_rel(ctx, ap))
        note = ""
        if capped:
            note = f"\n\n(Table capped. {nrows} rows total; use offset={offset + shown} to continue.)"
        header = f"{rel} [{mode}] cols={list(df.columns)} rows={nrows}, from row {offset}:"
        return f"{header}\n{rendered}{note}"

    return handler


def _mk_read_docx(cfg):
    b = cfg.batch

    def handler(args: dict, ctx: AgentCtx) -> str:
        rel = args.get("path", "")
        offset = int(args.get("offset", 0) or 0)   # paragraph offset
        ap = _resolve_in_root(ctx, rel)
        if ap is None or not ap.is_file():
            return f"File not found or outside the data root: {rel!r}"
        import docx  # python-docx; guarded by build_tools
        try:
            d = docx.Document(str(ap))
        except Exception as e:
            return f"Could not open docx {rel!r}: {e}"
        paras = [p.text for p in d.paragraphs]
        notice = _offset_notice(offset, len(paras), "paragraphs")
        if notice:
            return notice
        body = "\n".join(paras[offset:])
        rendered, capped = _cap_lines(
            body, b["per_file_read_lines"], b["per_file_read_bytes"]
        )
        refusal = _charge(ctx, rendered, b)
        if refusal:
            return refusal
        ctx.files_read.append(_rel(ctx, ap))
        note = _cap_note(rendered, capped, offset)
        return f"{rel} ({len(paras)} paragraphs, from {offset}):\n{rendered}{note}"

    return handler


def _mk_write_concept(cfg):
    def handler(args: dict, ctx: AgentCtx) -> str:  # write_concept
        ctype = (args.get("type") or "").strip()
        title = (args.get("title") or "").strip()
        summary = (args.get("summary") or "").strip()
        srcs = args.get("source_files") or []
        if not ctype or not title:
            return "Tool input rejected: write_concept needs non-empty type and title strings."
        if not isinstance(srcs, list) or not srcs or any(not isinstance(s, str) for s in srcs):
            return (
                "Tool input rejected: source_files must be a non-empty JSON array of exact "
                "fragment path strings, not one string or a containing source folder."
            )
        norm_srcs: list[str] = []
        bad: list[str] = []
        for s in srcs:
            ap = _resolve_in_root(ctx, str(s))
            if ap is None or not ap.is_file() or (
                ctx.assigned_files is not None and _rel(ctx, ap) not in ctx.files_read
            ):
                bad.append(str(s))
            else:
                r = _rel(ctx, ap)
                if r not in norm_srcs:
                    norm_srcs.append(r)
        if bad or not norm_srcs:
            return (
                f"Tool input rejected: source_files must cite files read in this batch; invalid paths: {bad}. "
                "Use the full fragment paths from read_text, including the numbered .md filename. "
                "No concept was recorded; rewrite this call."
            )
        # optional concept->concept relations (target title + relation word). Targets
        # are OTHER concept titles; they need not exist yet (Stage 2 resolves them by
        # title after merge and drops any that don't resolve). Self-links are dropped.
        links: list[tuple[str, str]] = []
        for ln in (args.get("links") or []):
            if not isinstance(ln, dict):
                continue
            to = (ln.get("to_title") or ln.get("to") or "").strip()
            rel = (ln.get("rel") or "related").strip().lower() or "related"
            if to and to.lower() != title.lower():
                pair = (to, rel)
                if pair not in links:
                    links.append(pair)
        concept = Concept(
            type=ctype, title=title,
            source_files=norm_srcs,
            summaries=[(summary, norm_srcs[0])] if summary else [],
            links=links,
        )
        if concept in ctx.sink:
            return f"{ALREADY_RECORDED}: identical title, sources, summary and links; emit another concept or finish."
        ctx.sink.append(concept)
        rels = f", {len(links)} link(s)" if links else ""
        return f"recorded concept: {ctype}/{title}{rels}"

    return handler


def _mk_ask_human(cfg):
    def handler(args: dict, ctx: AgentCtx) -> str:  # ask_human
        finding_type = (args.get("finding_type") or "note").strip()
        message = (args.get("message") or "").strip()
        options = args.get("options") or []
        if not isinstance(options, list):
            options = []
        options = [str(o) for o in options]
        if not message:
            return "ask_human needs a non-empty `message`. Please rewrite the input."
        # record the finding in BOTH modes (so a non-interactive run still surfaces it).
        record = {"finding_type": finding_type, "message": message, "options": options}
        # interactive + a real terminal: block for a human answer.
        if ctx.interactive and ctx.ui is not None and getattr(ctx.ui, "tty", False):
            answer = ctx.ui.ask(finding_type, message, options or None)
            record["answer"] = answer
            ctx.findings.append(record)
            if not answer:
                return "Human gave no answer; use your best judgment and continue."
            return f"Human answered: {answer}"
        # non-interactive (or no tty): do not block. Record it and let the agent proceed.
        record["answer"] = None
        ctx.findings.append(record)
        return (
            "Noted (non-interactive run — no human is available). This finding has been "
            "logged for later human review. Use your best default judgment and continue."
        )

    return handler


# ----------------------------------------------------------------- schemas + build

_PATH_OFFSET = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "file path shown by list_dir"},
        "offset": {"type": "integer", "minimum": 0, "description": "0-based start; default 0. Continue only at the exact offset returned by a capped read."},
    },
    "required": ["path"],
}

_SCHEMAS = {
    "list_dir": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "directory to list (default root)"}},
        "required": [],
    },
    "read_text": _PATH_OFFSET,
    "read_pdf": _PATH_OFFSET,
    "read_docx": _PATH_OFFSET,
    "read_table": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "mode": {"type": "string", "description": '"text" (frame preview) or "rows" (one record per row)'},
            "sheet": {"type": "string", "description": "sheet name or index (xlsx); default first"},
            "offset": {"type": "integer", "minimum": 0, "description": "0-based row offset; default 0"},
        },
        "required": ["path"],
    },
    "write_concept": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "minLength": 1, "description": "concept/entity type (e.g. Person, Decision)"},
            "title": {"type": "string", "minLength": 1, "description": "concise canonical title; REUSE identical titles across files for the same real thing"},
            "source_files": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}, "description": "REQUIRED on EVERY call: JSON array of supporting fragment paths actually read, including the numbered .md filename; never omit it or use a string or containing folder"},
            "summary": {"type": "string", "description": "one-line concept description (summarize, don't copy)"},
            "links": {
                "type": "array",
                "description": "optional relations from THIS concept to other concepts. Each is {to_title, rel}: to_title = the exact title of the related concept, rel = a short lowercase relation word (e.g. produces, works_with, resolves, adopts, supersedes).",
                "items": {
                    "type": "object",
                    "properties": {
                        "to_title": {"type": "string", "minLength": 1, "description": "title of the related concept"},
                        "rel": {"type": "string", "minLength": 1, "description": "short relation word"},
                    },
                    "required": ["to_title"],
                },
            },
        },
        "required": ["type", "title", "source_files"],
    },
    "ask_human": {
        "type": "object",
        "properties": {
            "finding_type": {"type": "string", "description": "short tag for the kind of finding (e.g. folder-structure, pdf-toc, human-summary, ambiguous)"},
            "message": {"type": "string", "description": "what you found and what you need decided"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "optional list of choices to offer the human"},
        },
        "required": ["message"],
    },
}

_DESCRIPTIONS = {
    "list_dir": "List a directory under the data root (dirs + files with byte size and approx token cost). Use it to see what's there and choose what to read next.",
    "read_text": "Read an assigned plain-text fragment once. Only continue when the output explicitly says Output capped and gives a next offset. End of file means the fragment is complete; do not reread it.",
    "read_pdf": "Extract linear text from a PDF, page by page (size-capped; use offset for more pages).",
    "read_table": "Read a spreadsheet/CSV. mode='rows' gives one compact record per row (emit one concept per row when each row is an entity); mode='text' gives a frame preview.",
    "read_docx": "Extract text from a .docx file (size-capped; offset by paragraph).",
    "write_concept": "Record ONE extracted concept: {type, title, summary, source_files, links?}. source_files MUST be non-empty. links (optional) are relations to other concepts by title. Call this repeatedly, once per concept.",
    "ask_human": "Ask a human to confirm or decide a genuine judgment call (see the escalation rules in your instructions). Provide a finding_type, a clear message, and optional choices. Do NOT use it for routine extractions.",
}

_MAKERS = {
    "list_dir": _mk_list_dir,
    "read_text": _mk_read_text,
    "read_pdf": _mk_read_pdf,
    "read_table": _mk_read_table,
    "read_docx": _mk_read_docx,
    "write_concept": _mk_write_concept,
    "ask_human": _mk_ask_human,
}


def build_tools(cfg, ctx: AgentCtx) -> list[Tool]:
    """Return the enabled tool subset. A switch that is off, or whose python package
    is not importable, is silently dropped (logged) so the agent can't select it."""
    tools: list[Tool] = []
    for name, spec in cfg.tools.items():
        if not spec.get("enabled", False):
            continue
        pkg = spec.get("package")
        if pkg:
            try:
                importlib.import_module(pkg)
            except ImportError:
                print(f"[okf] {name} disabled: package {pkg!r} not importable")
                continue
        maker = _MAKERS.get(name)
        if maker is None:
            continue
        tools.append(Tool(
            name=name,
            description=_DESCRIPTIONS[name],
            parameters=_SCHEMAS[name],
            handler=maker(cfg),
        ))
    return tools
