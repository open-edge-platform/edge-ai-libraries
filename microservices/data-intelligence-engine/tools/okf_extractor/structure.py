# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Folder scan + size estimate + folder table-of-contents.

Requirement d: the folder's organization is meaningful. We scan the tree, estimate
each file's token size (so the Stage-1 driver can hand the agent a budget and let it
self-batch), and render the subfolder hierarchy as a nested markdown TOC that
bundle.py embeds into index.md. PDF-internal TOC is OUT OF SCOPE for v1.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileInfo:
    rel_path: str          # posix, relative to the scan root (the source_files join key form)
    abs_path: Path
    size_bytes: int
    approx_tokens: int
    ext: str               # lowercased suffix without the dot ("" if none)


@dataclass
class Tree:
    root: Path
    files: list[FileInfo] = field(default_factory=list)
    toc: dict = field(default_factory=dict)   # nested {dirname: {...}, "__files__": [rel_path,...]}


def scan(data_dir: Path, chars_per_token: float) -> Tree:
    root = Path(data_dir).resolve()
    files: list[FileInfo] = []
    toc: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            ap = Path(dirpath) / fn
            try:
                size = ap.stat().st_size
            except OSError:
                continue
            rel = ap.relative_to(root).as_posix()
            ext = ap.suffix.lower().lstrip(".")
            files.append(FileInfo(
                rel_path=rel, abs_path=ap, size_bytes=size,
                approx_tokens=int(size / chars_per_token) if chars_per_token else size,
                ext=ext,
            ))
            _toc_insert(toc, rel)
    return Tree(root=root, files=files, toc=toc)


def _toc_insert(toc: dict, rel_path: str) -> None:
    parts = rel_path.split("/")
    node = toc
    for d in parts[:-1]:
        node = node.setdefault(d, {})
    node.setdefault("__files__", []).append(parts[-1])


def render_toc_markdown(tree: Tree) -> str:
    """Subfolder hierarchy -> nested bullet list. Captures directory structure that
    forms a natural table-of-contents (requirement d)."""
    lines: list[str] = []

    def walk(node: dict, depth: int) -> None:
        for name in sorted(k for k in node if k != "__files__"):
            lines.append(f"{'  ' * depth}- **{name}/**")
            walk(node[name], depth + 1)
        for fn in node.get("__files__", []):
            lines.append(f"{'  ' * depth}- {fn}")

    walk(tree.toc, 0)
    return "\n".join(lines) if lines else "- (flat: no subfolders)"
