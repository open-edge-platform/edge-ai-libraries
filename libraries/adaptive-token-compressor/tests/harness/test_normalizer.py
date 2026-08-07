"""Tests for harness/normalizer.py."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.harness.normalizer import (
    CompositeNormalizer,
    NullNormalizer,
    TextNormalizer,
    WorkspaceNormalizer,
)


# ─────────────────────────────────────────────────────────────────────────────
# TextNormalizer Protocol
# ─────────────────────────────────────────────────────────────────────────────


class TestProtocolRuntimeCheck:
    def test_workspace_satisfies_protocol(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/test")
        assert isinstance(n, TextNormalizer)

    def test_null_satisfies_protocol(self):
        n = NullNormalizer()
        assert isinstance(n, TextNormalizer)

    def test_composite_satisfies_protocol(self):
        n = CompositeNormalizer([NullNormalizer()])
        assert isinstance(n, TextNormalizer)

    def test_object_without_methods_fails(self):
        class NotANormalizer:
            pass

        assert not isinstance(NotANormalizer(), TextNormalizer)


# ─────────────────────────────────────────────────────────────────────────────
# WorkspaceNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceNormalizer:
    def test_normalize_replaces_match(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/workspace_\w+")
        text = "Path: /tmp/workspace_abc/file.py"
        normalized, ctx = n.normalize(text)
        assert "/tmp/workspace_abc" not in normalized
        assert "__AGENT_WORKSPACE__" in normalized
        assert ctx == {"original": "/tmp/workspace_abc"}

    def test_normalize_no_match(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/workspace_\w+")
        text = "No workspace here"
        normalized, ctx = n.normalize(text)
        assert normalized == text
        assert ctx == {"original": None}

    def test_normalize_multiple_occurrences(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+")
        text = "/tmp/ws_a and /tmp/ws_a again"
        normalized, ctx = n.normalize(text)
        # First match captured as canonical original
        assert ctx["original"] == "/tmp/ws_a"
        # All occurrences replaced
        assert "/tmp/ws_a" not in normalized
        assert normalized.count("__AGENT_WORKSPACE__") == 2

    def test_restore_round_trip(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/workspace_\w+")
        original_text = "Files in /tmp/workspace_xyz/foo and /tmp/workspace_xyz/bar"
        normalized, ctx = n.normalize(original_text)
        restored = n.restore(normalized, ctx)
        assert restored == original_text

    def test_restore_passes_through_when_no_original(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/ws")
        ctx = {"original": None}
        text = "Some text without placeholder"
        assert n.restore(text, ctx) == text

    def test_custom_placeholder(self):
        n = WorkspaceNormalizer(
            pattern=r"/home/\w+", placeholder="__USER_HOME__"
        )
        normalized, ctx = n.normalize("/home/alice/.bashrc")
        assert "__USER_HOME__" in normalized
        assert "__AGENT_WORKSPACE__" not in normalized

    def test_sweep_residual_replaces_leaked_placeholder(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+")
        # Backend hallucinated a placeholder in section that didn't have one
        final = "Output: __AGENT_WORKSPACE__/foo"
        source = "Input: /tmp/ws_test/foo"
        result = n.sweep_residual(final, source)
        assert result == "Output: /tmp/ws_test/foo"

    def test_sweep_residual_no_placeholder_passes_through(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+")
        final = "Clean output"
        source = "/tmp/ws_test/foo"
        assert n.sweep_residual(final, source) == final

    def test_sweep_residual_no_match_in_source(self):
        n = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+")
        # Placeholder leaked but source has no actual match to recover
        final = "Output: __AGENT_WORKSPACE__/foo"
        source = "No workspace in source"
        # Cannot recover; passes through
        assert n.sweep_residual(final, source) == final


# ─────────────────────────────────────────────────────────────────────────────
# NullNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestNullNormalizer:
    def test_normalize_identity(self):
        n = NullNormalizer()
        normalized, ctx = n.normalize("any text")
        assert normalized == "any text"

    def test_restore_identity(self):
        n = NullNormalizer()
        _, ctx = n.normalize("text")
        assert n.restore("text", ctx) == "text"

    def test_sweep_residual_identity(self):
        n = NullNormalizer()
        assert n.sweep_residual("final", "source") == "final"


# ─────────────────────────────────────────────────────────────────────────────
# CompositeNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestCompositeNormalizer:
    def test_round_trip_with_two_normalizers(self):
        ws = WorkspaceNormalizer(
            pattern=r"/tmp/ws_\w+", placeholder="__WS__"
        )
        user = WorkspaceNormalizer(
            pattern=r"/home/\w+", placeholder="__USER__"
        )
        comp = CompositeNormalizer([ws, user])

        original = "Path /tmp/ws_a in /home/alice"
        normalized, ctx = comp.normalize(original)
        # Both placeholders present
        assert "__WS__" in normalized
        assert "__USER__" in normalized
        # Restore in reverse order
        restored = comp.restore(normalized, ctx)
        assert restored == original

    def test_normalize_returns_list_of_ctxs(self):
        ws = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+", placeholder="__WS__")
        null = NullNormalizer()
        comp = CompositeNormalizer([ws, null])
        _, ctx = comp.normalize("/tmp/ws_a")
        assert isinstance(ctx, list)
        assert len(ctx) == 2

    def test_restore_reverse_order(self):
        # Verify the reverse order matters: outer normalizer's placeholder
        # is restored BEFORE inner's
        ws = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+", placeholder="__WS__")
        null = NullNormalizer()
        comp = CompositeNormalizer([ws, null])
        original = "/tmp/ws_a content"
        normalized, ctx = comp.normalize(original)
        restored = comp.restore(normalized, ctx)
        assert restored == original

    def test_sweep_residual_runs_each_child(self):
        ws = WorkspaceNormalizer(pattern=r"/tmp/ws_\w+", placeholder="__WS__")
        user = WorkspaceNormalizer(pattern=r"/home/\w+", placeholder="__USER__")
        comp = CompositeNormalizer([ws, user])
        final = "Leaked __WS__ and __USER__"
        source = "Original /tmp/ws_test and /home/alice"
        result = comp.sweep_residual(final, source)
        assert "/tmp/ws_test" in result
        assert "/home/alice" in result
        assert "__WS__" not in result
        assert "__USER__" not in result

    def test_empty_composite(self):
        comp = CompositeNormalizer([])
        text = "any text"
        normalized, ctx = comp.normalize(text)
        assert normalized == text
        assert ctx == []
        assert comp.restore(normalized, ctx) == text
        assert comp.sweep_residual(text, text) == text
