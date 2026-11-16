# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Concept:
    """One extracted concept; `source_files` (output_root-relative posix paths) is mandatory."""
    type: str
    title: str                                          # first-seen surface form
    source_files: list[str] = field(default_factory=list)
    summaries: list[tuple[str, str]] = field(default_factory=list)  # (summary, rel_path)
    links: list[tuple[str, str]] = field(default_factory=list)      # (target_title, rel)


def slug(title: str) -> str:
    """Stable, filesystem/link-safe id fragment. Keeps CJK, collapses the rest."""
    s = title.strip().lower()
    s = re.sub(r"[\s/\\]+", "-", s)
    # \w matches CJK in Unicode mode, so CJK characters are kept.
    s =re.sub(r"[^\w-]", "", s)
    return s.strip("-") or "unnamed"


def norm_title(title: str) -> str:
    """Merge key: trimmed, lowercased title."""
    return title.strip().lower()
