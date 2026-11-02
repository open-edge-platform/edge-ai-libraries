# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Two-stage task pipeline: plan instructions, then extract/merge/write OKF."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from . import stage1_extract, stage2_merge
from .agent import ExtractionResponseError
from .bundle import write_bundle
from .concept import Concept
from .config import Config
from .llmclient import LLMClient
from .planning import plan_instructions
from .schemas import TaskOptions
from .structure import FileInfo, Tree, _toc_insert
from .ui import UI


def _extraction_tree(tree: Tree, cfg: Config, root: Path) -> tuple[Tree, dict[str, str]]:
    """Deterministic, fully readable fragments; no capped read can hide a tail.

    The old file driver considered a file covered after its first capped read.
    Bound both lines and bytes BEFORE invoking it, then restore original source
    paths on concepts. This also handles a single extremely long text line.
    """
    char_limit = min(
        int(cfg.batch["per_file_read_bytes"]) // 8,
        int(cfg.read_input_budget() * float(cfg.batch["chars_per_token"]) / 4),
    )
    line_limit = int(cfg.batch["per_file_read_lines"]) // 2
    if char_limit < 1 or line_limit < 1:
        raise ValueError("Extraction read limits are too small")
    fragmented = Tree(root=root.resolve())
    sources: dict[str, str] = {}
    for source in tree.files:
        text = source.abs_path.read_text(encoding="utf-8")
        chunks: list[str] = []
        current = ""
        lines = 0
        for line in text.splitlines(keepends=True):
            for start in range(0, len(line), char_limit):
                piece = line[start:start + char_limit]
                if current and (len(current) + len(piece) > char_limit or lines >= line_limit):
                    chunks.append(current)
                    current, lines = "", 0
                current += piece
                lines += 1
        if current:
            chunks.append(current)
        for part, content in enumerate(chunks):
            rel = f"{source.rel_path}/{part:06d}.md"
            path = fragmented.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            fragmented.files.append(FileInfo(
                rel_path=rel, abs_path=path, size_bytes=len(content.encode("utf-8")),
                approx_tokens=int(len(content) / float(cfg.batch["chars_per_token"])), ext="md",
            ))
            _toc_insert(fragmented.toc, rel)
            sources[rel] = source.rel_path
    return fragmented, sources


def extract_bundle(
    cfg: Config, client: LLMClient, tree: Tree, output: Path,
    options: TaskOptions | None = None, ui: UI | None = None,
    interactive: bool = False, label: str = "",
) -> list[Concept]:
    """`tree` holds complete, normalized UTF-8 sources at their logical paths.
    `label` (e.g. the service's task ID) prefixes the stage headers, so tasks
    running side by side can be told apart in the log."""
    ui = ui or UI(enabled=False)
    prefix = f"[{label}] " if label else ""
    ui.stage(f"{prefix}Stage 1 — review all content and plan instructions "
             f"({len(tree.files)} source(s), ~{sum(f.approx_tokens for f in tree.files)} tokens)")
    instructions = plan_instructions(cfg, client, tree, options=options, ui=ui)
    raw_config = deepcopy(cfg.raw)
    raw_config["instructions"] = instructions
    # Files have already been decoded, including PDF/office inputs. A text blob
    # can retain its original .pdf name without exposing a binary reader to it.
    for name in ("read_pdf", "read_table", "read_docx"):
        raw_config["tools"][name] = {"enabled": False}
    raw_config["tools"]["read_text"] = {"enabled": True}
    task_config = Config(raw_config)

    ui.stage(f"{prefix}Stage 2 — extract OKF using the task instructions")
    findings: list[dict] = []
    with TemporaryDirectory(prefix="okf-fragments-") as temporary:
        fragments, source_paths = _extraction_tree(tree, task_config, Path(temporary))
        raw = stage1_extract.extract(
            task_config, client, fragments, ui=ui, interactive=interactive,
            findings=findings, instructions=instructions, strict=True,
        )
    for concept in raw:
        concept.source_files = list(dict.fromkeys(source_paths[path] for path in concept.source_files))
        concept.summaries = [(text, source_paths[path]) for text, path in concept.summaries]
    merged = stage2_merge.merge_same_title(raw)
    if task_config.merge.get("llm_canonicalize", False):
        merged = stage2_merge.canonicalize(
            task_config, client, merged, ui=ui, instructions=instructions,
        )
    links = stage2_merge.redirect_links(merged)
    ui.info(f"links: kept {links['kept']}, dropped {links['unresolved']} with unknown targets"
            + (f" (e.g. {'; '.join(links['examples'])})" if links["examples"] else ""))
    concepts = list(merged.values())
    if not concepts:
        raise ExtractionResponseError("Extraction produced no OKF concepts")
    write_bundle(output, concepts, tree)
    (output / "instructions.yaml").write_text(
        yaml.safe_dump({"instructions": instructions}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    if findings:
        (output / "findings.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in findings),
            encoding="utf-8",
        )
    return concepts