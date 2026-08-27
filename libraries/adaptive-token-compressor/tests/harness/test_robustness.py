"""Robustness — malformed / oversized inputs to HarnessCompressor (ATC-UNIT-010).

Hermetic: an injected in-memory backend means nothing here touches the network.
Contract under test: ``compress()`` never raises on shape-broken or very large
input — it normalizes (see core/messages.py ``MessageAccessor.text``) and returns
a ``CompressorResult``.

Empty inputs and malformed *backend responses* are already covered
(test_compressor.py); this file adds malformed *user input shapes* and oversized
payloads.
"""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.backends import NoopBackend
from adaptive_token_compressor.core.base import CompressionContext, CompressorResult
from adaptive_token_compressor.harness.compressor import HarnessCompressor


class ShrinkBackend:
    """Backend that always returns a shorter string; never raises."""

    cache_tag = "lingua"

    def compress(self, text, *, rate, force_tokens=None,
                 force_reserve_digit=False, digit_neighbor_radius=0):
        return text[: max(1, len(text) // 4)]

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus

        return HealthStatus.healthy("shrink_backend")


# ─────────────────────────────────────────────────────────────────────────────
# Malformed message shapes
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedMessages:
    def _compressor(self, monkeypatch) -> HarnessCompressor:
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())
        return comp

    @pytest.mark.parametrize(
        "content",
        [
            None,                                    # null content
            12345,                                   # int content
            {"nested": "dict"},                      # dict content
            [{"type": "text", "text": "hi there"}],  # multimodal list
            [{"type": "image", "url": "x"}],         # list w/o text field
            b"bytes payload",                        # bytes content
        ],
        ids=["none", "int", "dict", "multimodal", "list-no-text", "bytes"],
    )
    def test_non_string_content_does_not_crash(self, monkeypatch, content):
        comp = self._compressor(monkeypatch)
        ctx = CompressionContext(messages=[{"role": "system", "content": content}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert isinstance(result.messages, list)

    def test_missing_content_key_does_not_crash(self, monkeypatch):
        comp = self._compressor(monkeypatch)
        ctx = CompressionContext(messages=[{"role": "system"}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)

    def test_missing_role_key_does_not_crash(self, monkeypatch):
        comp = self._compressor(monkeypatch)
        ctx = CompressionContext(messages=[{"content": "orphan text with no role"}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)

    def test_mixed_valid_and_malformed_messages(self, monkeypatch):
        comp = self._compressor(monkeypatch)
        ctx = CompressionContext(
            messages=[
                {"role": "system", "content": None},
                {"role": "user", "content": "a normal question"},
                {"role": "assistant"},               # missing content
                {"content": "no role here"},          # missing role
                {"role": "tool", "content": 42},      # non-string
            ]
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert len(result.messages) == len(ctx.messages)


# ─────────────────────────────────────────────────────────────────────────────
# Oversized input
# ─────────────────────────────────────────────────────────────────────────────


class TestOversized:
    def test_very_large_content_compresses_without_crash(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", ShrinkBackend())
        big = "some repeated clause about the system. " * 200_000  # ~7.8 MB
        ctx = CompressionContext(messages=[{"role": "system", "content": big}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert result.metrics.tokens_before > 0

    def test_many_messages_without_crash(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())
        ctx = CompressionContext(
            messages=[{"role": "user", "content": f"message number {i}"} for i in range(5_000)]
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert len(result.messages) == 5_000