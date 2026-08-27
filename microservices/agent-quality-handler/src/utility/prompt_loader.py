# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Prompt loader — reads section-based prompt files ([SYSTEM], [POLICY], etc.)."""

import re
from pathlib import Path

from .runtime_config import load_runtime_settings

_SECTION_RE = re.compile(r"^\[([A-Z_]+)\]", re.MULTILINE)


def load_prompt_file(use_case_id: str, prompts_dir: str | None = None) -> str:
    """Return raw text content of the prompt file for the given use-case id."""
    directory = prompts_dir or load_runtime_settings().prompts_dir
    path = Path(directory) / f"{use_case_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def get_section(
    use_case_id: str,
    section: str,
    prompts_dir: str | None = None,
    prompt_text: str | None = None,
) -> str:
    """Extract a named section (e.g. 'SYSTEM', 'POLICY') from the prompt file.

    Returns everything between [SECTION] and the next section marker (or EOF).
    """
    text = (
        prompt_text
        if prompt_text is not None
        else load_prompt_file(use_case_id, prompts_dir)
    )
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end():end].strip()

    if section not in sections:
        raise KeyError(f"Section [{section}] not found in prompt file for '{use_case_id}'")
    return sections[section]
