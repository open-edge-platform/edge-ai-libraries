"""Robustness — malformed / oversized inputs to ContextCompressor (ATC-UNIT-010).

Hermetic: an injected in-memory backend means nothing here touches the network
(claw is disabled). Contract under test: ``compress()`` never raises on
shape-broken or very large input — it normalizes (see core/messages.py
``MessageAccessor.text``) and returns a ``CompressorResult``.

Empty / None message lists and malformed *backend responses* are already covered
(test_compressor.py); this file adds malformed *user input shapes* and oversized
payloads, matching tests/harness/test_robustness.py and tests/tool/test_robustness.py.
"""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.backends import NoopBackend
from adaptive_token_compressor.core.base import CompressionContext, CompressorResult
from adaptive_token_compressor.context.compressor import ContextCompressor


class ShrinkBackend:
    """Backend that always returns a shorter string; never raises."""

    cache_tag = "token_prune"

    def compress(self, text, *, mode=None, rate, force_tokens=None,
                 force_reserve_digit=False, digit_neighbor_radius=0, **_unused):
        return text[: max(1, len(text) // 4)]

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus

        return HealthStatus.healthy("shrink_backend")


def _compressor(backend, *, compress_min_chars: int = 100) -> ContextCompressor:
    comp = ContextCompressor(compress_min_chars=compress_min_chars, compression_mode='none')
    comp._backend = backend
    return comp


# ─────────────────────────────────────────────────────────────────────────────
# Malformed message shapes
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedMessages:
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
    def test_non_string_content_does_not_crash(self, content):
        comp = _compressor(NoopBackend())
        ctx = CompressionContext(messages=[{"role": "system", "content": content}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert isinstance(result.messages, list)

    def test_missing_content_key_does_not_crash(self):
        comp = _compressor(NoopBackend())
        ctx = CompressionContext(messages=[{"role": "system"}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)

    def test_missing_role_key_does_not_crash(self):
        comp = _compressor(NoopBackend())
        ctx = CompressionContext(messages=[{"content": "orphan text with no role"}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)

    def test_mixed_valid_and_malformed_messages(self):
        comp = _compressor(NoopBackend())
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
    def test_very_large_content_compresses_without_crash(self):
        # ContextCompressor passes a plain system message through (it targets
        # tool/assistant/web-search content), so we assert only the no-crash +
        # result-shape contract, not token accounting.
        comp = _compressor(ShrinkBackend())
        big = "some repeated clause about the system. " * 200_000  # ~7.8 MB
        ctx = CompressionContext(messages=[{"role": "system", "content": big}])
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert len(result.messages) == 1

    def test_many_messages_without_crash(self):
        comp = _compressor(NoopBackend())
        ctx = CompressionContext(
            messages=[{"role": "user", "content": f"message number {i}"} for i in range(5_000)]
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert len(result.messages) == 5_000