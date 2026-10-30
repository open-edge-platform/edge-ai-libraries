"""Tests for context/claw_adapter.py — Cortex detect + safe FusionEngine.

Covers §13 row `context/claw_adapter` + T8 (detect / compress_with_claw
determinism). Requires the claw-compactor core dependency; skipped if not installed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("claw_compactor")

from adaptive_token_compressor.context.claw_adapter import (  # noqa: E402
    _DANGEROUS_STAGES,
    ContextClawAdapter,
    _build_safe_engine,
)


CODE = "def foo(x):\n    return x + 1\n\nclass Bar:\n    def m(self):\n        return 42\n" * 3
DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n-old line one\n+new line one\n context\n" * 2
LOG = "\n".join(f"2026-01-01 12:00:{i:02d} ERROR task {i} failed with code {i}" for i in range(30))


# ─────────────────────────────────────────────────────────────────────────────
# _build_safe_engine — dangerous stages stripped
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildSafeEngine:
    def test_strips_nexus_and_abbrev(self):
        engine = _build_safe_engine(disable_dangerous=True)
        names = [s.name for s in engine.pipeline.transforms]
        assert "nexus" not in names
        assert "abbrev" not in names

    def test_dangerous_stages_constant(self):
        assert _DANGEROUS_STAGES == ("nexus", "abbrev")

    def test_keeps_semantic_dedup(self):
        # semantic_dedup uses Jaccard-over-shingles (integer set math, no
        # embeddings) → deterministic; retained per 集成点 4 P1.
        engine = _build_safe_engine(disable_dangerous=True)
        names = [s.name for s in engine.pipeline.transforms]
        assert "semantic_dedup" in names

    def test_disable_false_keeps_all(self):
        engine = _build_safe_engine(disable_dangerous=False)
        names = [s.name for s in engine.pipeline.transforms]
        assert "nexus" in names and "abbrev" in names


# ─────────────────────────────────────────────────────────────────────────────
# detect
# ─────────────────────────────────────────────────────────────────────────────


class TestDetect:
    def test_returns_valid_content_type(self):
        a = ContextClawAdapter()
        ct = a.detect(CODE)
        assert ct in {"text", "json", "code", "diff", "log", "search"}

    def test_code_detected(self):
        assert ContextClawAdapter().detect(CODE) == "code"

    def test_plaintext_is_text(self):
        a = ContextClawAdapter()
        assert a.detect("just some prose without any code structure at all") == "text"

    def test_deterministic(self):
        a = ContextClawAdapter()
        assert a.detect(CODE) == a.detect(CODE)  # T8


# ─────────────────────────────────────────────────────────────────────────────
# compress_with_claw — T8 determinism + shrinkage
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressWithClaw:
    @pytest.mark.parametrize("content,ct", [(CODE, "code"), (DIFF, "diff"), (LOG, "log")])
    def test_shrinks(self, content, ct):
        a = ContextClawAdapter()
        out = a.compress_with_claw(content, ct)
        assert isinstance(out, str)
        assert len(out) <= len(content)

    def test_deterministic_across_calls(self):
        # T8: same input → byte-identical output within a process.
        a = ContextClawAdapter()
        outs = {a.compress_with_claw(CODE, "code") for _ in range(5)}
        assert len(outs) == 1

    def test_two_adapters_agree(self):
        # Two fresh adapters give the same output for the same input.
        assert (
            ContextClawAdapter().compress_with_claw(LOG, "log")
            == ContextClawAdapter().compress_with_claw(LOG, "log")
        )