# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Render task-specific semantic instructions inside a fixed tool contract.

Planning and operator overrides supply the seven instruction segments; the
template owns tool argument shapes, fragment provenance and read/emit workflow.
Missing/empty segments retain their generic defaults.
"""
from __future__ import annotations

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Editable instruction segments — the human-in-the-loop knobs. Defaults are lifted
# from the kernel's original hardcoded EXTRACT_SYSTEM / _CANON_PROMPT wording.
DEFAULT_INSTRUCTIONS: dict[str, str] = {
    # Soft type guidance injected by the web UI (sample->recommend->edit). Default empty:
    # no suggested-type list, agent picks types freely (the template's {TYPE_HINTS} section
    # is designed to read fine when this is blank). NOT enforced — free-text type is unchanged.
    "TYPE_HINTS": "",
    "DOMAIN": (
        "You are an OKF (Open Knowledge Format) extraction agent working over a folder "
        "of enterprise knowledge documents."
    ),
    "GRANULARITY": (
        "ONE real-world thing = ONE concept. Do not create near-duplicates, and do not "
        "split one thing into several. Prefer coarse over fine. A short form / "
        "abbreviation / nickname / alternate spelling of the same thing is ONE concept."
    ),
    "TITLE_RULES": (
        "Give each concept a concise canonical title and REUSE the exact same title "
        "across documents when they refer to the same real thing (this is how "
        "duplicates get merged later). People: use the name only. Companies: a short "
        "name. Events: no dates in the title."
    ),
    "MERGE_STANCE": (
        "Group rows ONLY when they denote the exact same real thing — never merge two "
        "genuinely different entities. A false merge is worse than a missed one; when "
        "unsure, keep them separate."
    ),
    "RELATION_RULES": (
        "Add a link when this document clearly expresses a relationship between two "
        "concepts. Use the related concept's exact title as `to_title`, and a concise "
        "lowercase relation verb as `rel` (decide the most fitting one; there is no fixed "
        "vocabulary).\n"
        "IMPORTANT — anchor relations on the ACTOR, and make the link OUTGOING from the "
        "active party. People and organizations are the actors: whenever a person or team "
        "does something to/with another concept, put the link ON THE PERSON'S concept "
        "pointing OUT to what they acted on — e.g. on Peter Lin: produces → 'PRD v0.5', "
        "authors → 'Competitive analysis', attends → 'Kickoff meeting', works_with → "
        "'青云科技', decides → 'Use Pinecone for MVP', owns → 'WeBot project'. Do NOT leave "
        "a person with zero links if the document shows them acting — a person is almost "
        "never isolated. Prefer active-voice direction (person → artifact), not the reverse "
        "(artifact → person). Non-actor relations are fine too (a decision resolves an "
        "issue, a version supersedes another, a technology adopts a framework).\n"
        "Only add relations actually supported by the text — do not invent connections."
    ),
    "ESCALATION_RULES": (
        "- The folder structure itself seems to carry meaning (e.g. subfolders form a "
        "natural table of contents, a chapter/section hierarchy, or a per-topic grouping) "
        "and you are unsure how to reflect it in the concepts.\n"
        "- A document contains an internal table of contents / outline (e.g. a PDF whose "
        "first pages list chapters) that suggests structure worth capturing.\n"
        "- A document contains a human-written summary / overview of a larger body of "
        "knowledge, and you want to confirm how to treat it (as its own concept, or as the "
        "authoritative summary of others).\n"
        "- You encounter something genuinely ambiguous or unexpected that a human should "
        "decide before you commit concepts."
    ),
}


def _load(name: str, override_path: str | Path | None = None) -> str:
    path = Path(override_path) if override_path else _TEMPLATE_DIR / name
    return path.read_text(encoding="utf-8")


def _fill_instructions(text: str, instructions: dict[str, str] | None) -> str:
    merged = dict(DEFAULT_INSTRUCTIONS)
    for k, v in (instructions or {}).items():
        if v and str(v).strip():          # non-empty override wins; else keep default
            merged[k] = str(v)
    for key, val in merged.items():
        text = text.replace("{" + key + "}", val)
    return text


def render_extract_system(
    instructions: dict[str, str] | None = None,
    template_path: str | Path | None = None,
) -> str:
    """Concept-extraction system prompt (task stage 2). Only instruction placeholders are filled here;
    the tool contract is fixed in the template."""
    return _fill_instructions(_load("extract.md", template_path), instructions)


def render_canonicalize(
    ctype: str,
    entities_block: str,
    instructions: dict[str, str] | None = None,
    template_path: str | Path | None = None,
) -> str:
    """Stage-2 per-type canonicalize prompt. Fills {MERGE_STANCE} plus the structural
    injection points {TYPE} / {ENTITIES}."""
    text = _fill_instructions(_load("canonicalize.md", template_path), instructions)
    return text.replace("{TYPE}", ctype).replace("{ENTITIES}", entities_block)
