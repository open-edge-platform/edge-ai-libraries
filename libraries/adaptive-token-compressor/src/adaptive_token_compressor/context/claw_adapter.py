# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Adapter for claw-compactor's Cortex (content_type detection) + FusionEngine,
used by ContextCompressor's OTHER branch in Claw-enabled compression modes.

Imported only via the inline import in ``ContextCompressor.__init__``, so
claw-compactor need not be installed unless the user opts in.
"""
from claw_compactor.fusion.base import FusionContext
from claw_compactor.fusion.cortex import Cortex
from claw_compactor.fusion.engine import FusionEngine
from claw_compactor.fusion.pipeline import FusionPipeline

# Stripped when disable_dangerous=True: nexus (no-torch fallback corrupts RAG
# numerics), abbrev (English abbreviation table can damage identifiers).
_DANGEROUS_STAGES = ("nexus", "abbrev")


def _build_safe_engine(*, disable_dangerous: bool = True) -> FusionEngine:
    """FusionEngine with the dangerous stages (nexus / abbrev) stripped."""
    engine = FusionEngine()
    if disable_dangerous:
        safe_stages = [
            s for s in engine.pipeline.transforms if s.name not in _DANGEROUS_STAGES
        ]
        engine._pipeline = FusionPipeline(safe_stages)
    return engine


class ContextClawAdapter:
    """Two responsibilities:
      - ``detect(content)`` — Cortex content_type detection.
      - ``compress_with_claw(content, content_type)`` — run the safe
        FusionEngine on code / diff / log / search content.

    Constructed lazily by ``ContextCompressor.__init__`` when
    the active policy selects ``claw_only`` or ``claw_with_backend``.
    """

    def __init__(self, *, disable_dangerous: bool = True) -> None:
        self._cortex = Cortex()
        self._engine = _build_safe_engine(disable_dangerous=disable_dangerous)

    def detect(self, content: str) -> str:
        """Run Cortex on ``content``; return the detected content_type
        ("text" / "json" / "code" / "diff" / "log" / "search"). Deterministic
        for the same input.
        """
        ctx = FusionContext(content=content, content_type="text", role="tool")
        updated = self._cortex.apply(ctx)
        return updated.context_updates.get("content_type", "text")

    def compress_with_claw(self, content: str, content_type: str) -> str:
        """Run the safe FusionEngine on ``content``.

        Caller MUST pass content_type ∈ {"code", "diff", "log", "search"}.
        Any FusionEngine exception propagates; the caller falls back to the
        backend only when the selected mode permits it.
        """
        result = self._engine.compress(
            text=content, content_type=content_type, role="tool"
        )
        return result["compressed"]
