# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor profiles: bundle SectioningConfig + TextNormalizer."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.exceptions import ConfigError
from .normalizer import NullNormalizer, TextNormalizer, WorkspaceNormalizer
from .sectioning import SectioningConfig


@dataclass(frozen=True)
class CompressorProfile:
    name: str
    sectioning: SectioningConfig
    normalizer: TextNormalizer


# ---------------------------------------------------------------------------
# OPENCLAW — covers openclaw + pinchbench workspaces
# ---------------------------------------------------------------------------

_OPENCLAW_PRIMARY_HEADINGS: list[str] = [
    "## Tooling",
    "## Tool Call Style",
    "## Execution Bias",
    "## Safety",
    "## OpenClaw CLI Quick Reference",
    "## Skills (mandatory)",
    "## OpenClaw Self-Update",
    "## Memory Recall",
    "## Model Aliases",
    "## Workspace",
    "## Documentation",
    "## Current Date & Time",
    "## Workspace Files (injected)",
    "## Reply Tags",
    "## Messaging",
    "# Project Context",
    "## Silent Replies",
    "# Dynamic Project Context",
    "## Group Chat Context",
    "## Inbound Context (trusted metadata)",
    "## Heartbeats",
    "## Subagent Context",
    "## Session Context",
    "## Runtime",
]

_OPENCLAW_PRESERVE_HEADINGS: set[str] = {
    "## Tooling",
    "## Tool Call Style",
    "## Execution Bias",
    "## OpenClaw CLI Quick Reference",
    "## Skills (mandatory)",
    "## Workspace",
    "## Documentation",
    "## Model Aliases",
    "## Reply Tags",
    "## Silent Replies",
    "# Dynamic Project Context",
    "## Group Chat Context",
    "## Inbound Context (trusted metadata)",
    "## Subagent Context",
    "## Session Context",
    "## Runtime",
}

# Terminate path components on whitespace too (legacy used ``[^/]*`` which
# would greedily eat ``workspace are loaded.`` until the next ``/``).
_OPENCLAW_WORKSPACE_PATTERN: str = (
    r"(?:/tmp/pinchbench/\d{4}/agent_workspace"
    r"|/home/[^/\s]+/\.openclaw/workspace[^/\s]*)"
)


OPENCLAW_PROFILE: CompressorProfile = CompressorProfile(
    name="openclaw",
    sectioning=SectioningConfig(
        primary_headings=_OPENCLAW_PRIMARY_HEADINGS,
        preserve_headings=_OPENCLAW_PRESERVE_HEADINGS,
        workspace_path_pattern=_OPENCLAW_WORKSPACE_PATTERN,
    ),
    normalizer=WorkspaceNormalizer(
        pattern=_OPENCLAW_WORKSPACE_PATTERN,
        placeholder="__AGENT_WORKSPACE__",
    ),
)


# ---------------------------------------------------------------------------
# GENERIC — fallback for non-router prompts
# ---------------------------------------------------------------------------

GENERIC_PROFILE: CompressorProfile = CompressorProfile(
    name="generic",
    sectioning=SectioningConfig(
        primary_headings=[],
        preserve_headings=set(),
        workspace_path_pattern=None,
    ),
    normalizer=NullNormalizer(),
)


_PROFILES: dict[str, CompressorProfile] = {
    OPENCLAW_PROFILE.name: OPENCLAW_PROFILE,
    GENERIC_PROFILE.name: GENERIC_PROFILE,
}


def resolve_profile(name: str) -> CompressorProfile:
    if name not in _PROFILES:
        available = ", ".join(sorted(_PROFILES.keys()))
        raise ConfigError(
            f"Unknown profile '{name}'. Available profiles: {available}"
        )
    return _PROFILES[name]
