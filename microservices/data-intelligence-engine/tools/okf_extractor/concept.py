# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared Concept type + id helpers. `slug`/`norm_title` are copied verbatim from
extraction/extract_okf.py (L114-127) so bundle ids and the merge key match the
proven producer exactly (both keep CJK)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Concept:
    """One extracted concept. `source_files` (output_root-relative posix paths) is
    MANDATORY — the graph_arm back-projection join key. `links` are concept→concept
    edges (target title + relation word); bundle.py writes them as BODY markdown links
    (the downstream parser's single source of truth for edges — NOT frontmatter)."""
    type: str
    title: str                                          # first-seen surface form
    source_files: list[str] = field(default_factory=list)
    summaries: list[tuple[str, str]] = field(default_factory=list)  # (summary, rel_path)
    links: list[tuple[str, str]] = field(default_factory=list)      # (target_title, rel)


def slug(title: str) -> str:
    """Stable, filesystem/link-safe id fragment. Keeps CJK, collapses the rest."""
    s = title.strip().lower()
    s = re.sub(r"[\s/\\]+", "-", s)
    # \w matches CJK under Python's default Unicode mode, so 汉字 are kept without
    # an explicit range. Drop everything else (punctuation, full-width symbols, …).
    s = re.sub(r"[^\w-]", "", s)
    return s.strip("-") or "unnamed"


def norm_title(title: str) -> str:
    """Merge key: trim + lowercase; CJK unaffected. Dedup relies on the prompt
    telling the model to reuse identical titles across documents/batches."""
    return title.strip().lower()
