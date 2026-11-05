# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Write the OKF bundle. Adapted from extract_okf.write_bundle/_write_concept/
_write_index (L763-849), MINUS the links branch:
  - frontmatter = {type, title, source_files} ONLY (no `links`);
  - body = "# title" + one bullet per source summary;
  - index.md = per-type concept catalog + a `## Source structure` folder TOC
    (requirement d). The downstream parser skips index.md, so it is free-form.

Type subdirs are derived from the type string via slug(type) (no ontology). Each
type subdir is wiped before writing so a smaller re-run leaves no stale files.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

import yaml

from .concept import Concept, norm_title, slug
from .structure import Tree, render_toc_markdown


def _type_dir(ctype: str) -> str:
    return slug(ctype)


def _cid(c: Concept) -> str:
    return f"{_type_dir(c.type)}/{slug(c.title)}"


def _relpath(from_cid: str, to_cid: str) -> str:
    """Markdown link from one concept file to another, relative within the bundle
    (matches extract_okf._relpath and the downstream parser's resolution)."""
    depth = from_cid.count("/")
    return "../" * depth + to_cid + ".md"


def write_bundle(bundle: Path, concepts, tree: Tree | None = None) -> None:
    bundle = Path(bundle)
    concepts = list(concepts)

    # wipe the type subdirs we're about to (re)write — stale-file safety.
    for ctype in {c.type for c in concepts}:
        d = bundle / _type_dir(ctype)
        if d.exists():
            shutil.rmtree(d)
    bundle.mkdir(parents=True, exist_ok=True)

    # resolve link target titles -> Concept, for writing body markdown links.
    by_norm: dict[str, Concept] = {norm_title(c.title): c for c in concepts}

    per_type: dict[str, list[Concept]] = defaultdict(list)
    for c in concepts:
        per_type[c.type].append(c)
        _write_concept(bundle, c, by_norm)

    _write_index(bundle, per_type, tree)


def _write_concept(bundle: Path, c: Concept, by_norm: dict[str, Concept]) -> None:
    path = bundle / f"{_cid(c)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # yaml.safe_dump (not hand-built f-strings) so titles/paths with quotes or trailing
    # backslashes round-trip through the same parser the loader uses. NO links key in
    # frontmatter — edges live in the BODY as markdown links (the parser's source of truth).
    fm: dict = {"type": c.type, "title": c.title, "source_files": list(c.source_files)}
    fm_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    lines = ["---", fm_text.rstrip("\n"), "---", "", f"# {c.title}", ""]
    for summ, rp in c.summaries:
        lines.append(f"- {summ} （来源：`{rp}`）")
    # body relation links: resolve each target title to a surviving concept's cid.
    resolved = [(by_norm[norm_title(to)], rel) for to, rel in c.links
                if norm_title(to) in by_norm]
    if resolved:
        lines.append("")
        lines.append("## 关联")
        for tgt, rel in resolved:
            lines.append(f"- [{tgt.title}]({_relpath(_cid(c), _cid(tgt))}) — {rel}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gloss(c: Concept, max_len: int = 50) -> str:
    if not c.summaries:
        return ""
    best = max((s for s, _ in c.summaries), key=len, default="")
    best = " ".join(best.split())
    return best[:max_len] + ("…" if len(best) > max_len else "")


def _write_index(bundle: Path, per_type: dict[str, list[Concept]], tree: Tree | None) -> None:
    lines = ["# OKF Bundle Index", ""]
    for ctype in sorted(per_type):
        cs = sorted(per_type[ctype], key=lambda c: c.title)
        if not cs:
            continue
        lines.append(f"## {ctype}")
        for c in cs:
            text = _gloss(c) or c.title
            lines.append(f"- `{_cid(c)}` {text}")
        lines.append("")
    if tree is not None:
        lines.append("## Source structure")
        lines.append("")
        lines.append(render_toc_markdown(tree))
        lines.append("")
    (bundle / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
