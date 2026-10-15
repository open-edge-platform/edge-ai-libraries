# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Register MCP prompts backed by the model-download user skill."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from fastmcp import FastMCP

from src.utils.logging import logger

_SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "skills"
    / "model-download-user"
)
_EXAMPLES_DIR = _SKILL_DIR / "example-prompts"
_SKILL_FILE = _SKILL_DIR / "SKILL.md"
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)


def _prompt_name(path: Path) -> str:
    return path.stem.lower().replace("-", "_")


def _strip_html_comments(content: str) -> str:
    """Remove Markdown HTML comment blocks from content exposed to MCP clients."""

    return _HTML_COMMENT_PATTERN.sub("", content).strip()


def _description(content: str, fallback: str) -> str:
    for line in content.splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate:
            return candidate[:200]
    return fallback


def _prompt_function(content: str) -> Callable[[], str]:
    def render_prompt() -> str:
        return content

    return render_prompt


def _extract_section(content: str, heading: str) -> str | None:
    matches = list(_HEADING_PATTERN.finditer(content))
    for index, match in enumerate(matches):
        if match.group(1).strip().casefold() != heading.casefold():
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        return content[match.start() : end].strip()
    return None


def _register_prompt(
    mcp: FastMCP,
    *,
    name: str,
    content: str,
    description: str,
) -> None:
    prompt = _prompt_function(content)
    prompt.__name__ = name
    mcp.prompt(name=name, description=description)(prompt)


def register_skill_prompts(mcp: FastMCP) -> int:
    """Register example prompts and the supported-hubs guide when available."""

    count = 0
    if _EXAMPLES_DIR.is_dir():
        for prompt_path in sorted(_EXAMPLES_DIR.glob("*.md")):
            try:
                content = _strip_html_comments(
                    prompt_path.read_text(encoding="utf-8")
                )
            except OSError as exc:
                logger.warning(
                    "mcp_prompt_read_failed",
                    path=str(prompt_path),
                    error_type=type(exc).__name__,
                )
                continue
            if not content:
                continue
            name = _prompt_name(prompt_path)
            _register_prompt(
                mcp,
                name=name,
                content=content,
                description=_description(content, f"Model download workflow: {name}"),
            )
            count += 1

    if _SKILL_FILE.is_file():
        try:
            skill_content = _strip_html_comments(
                _SKILL_FILE.read_text(encoding="utf-8")
            )
        except OSError as exc:
            logger.warning(
                "mcp_skill_read_failed",
                path=str(_SKILL_FILE),
                error_type=type(exc).__name__,
            )
        else:
            hub_guide = _extract_section(skill_content, "Supported Hubs at a Glance")
            if hub_guide:
                _register_prompt(
                    mcp,
                    name="hub_guide",
                    content=hub_guide,
                    description="Show the model hubs supported by Model Download.",
                )
                count += 1

    return count
