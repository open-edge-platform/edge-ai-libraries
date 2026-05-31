# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Prompt loader — reads section-based prompt files ([SYSTEM], [POLICY], etc.)."""

import os
import re
from typing import Optional


_PROMPTS_DIR = os.environ.get("USE_CASE_PROMPTS_DIR", "/configs/prompts")
_SECTION_RE = re.compile(r"^\[([A-Z_]+)\]", re.MULTILINE)


def load_prompt_file(use_case_id: str, prompts_dir: str | None = None) -> str:
    """Return raw text content of the prompt file for the given use-case id."""
    directory = prompts_dir or _PROMPTS_DIR
    path = os.path.join(directory, f"{use_case_id}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r") as f:
        return f.read()


def get_section(
    use_case_id: str,
    section: str,
    prompts_dir: str | None = None,
    prompt_text: str | None = None,
) -> str:
    """Extract a named section (e.g. 'SYSTEM', 'POLICY') from the prompt file.

    Returns everything between [SECTION] and the next section marker (or EOF).
    """
    text = prompt_text or load_prompt_file(use_case_id, prompts_dir)
    sections: dict[str, str] = {}
    keys = []
    positions = []
    for m in _SECTION_RE.finditer(text):
        keys.append(m.group(1))
        positions.append(m.end())

    for i, key in enumerate(keys):
        start = positions[i]
        end = positions[i + 1] - len(f"[{keys[i + 1]}]") if i + 1 < len(keys) else len(text)
        sections[key] = text[start:end].strip()

    if section not in sections:
        raise KeyError(f"Section [{section}] not found in prompt file for '{use_case_id}'")
    return sections[section]
