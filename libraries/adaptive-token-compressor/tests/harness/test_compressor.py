"""Tests for harness/compressor.py."""
from __future__ import annotations

import os
import threading

import cachetools
import pytest
import responses

from adaptive_token_compressor.core.backends import NoopBackend
from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.exceptions import BackendError, ConfigError
from adaptive_token_compressor.core.health import HealthState
from adaptive_token_compressor.core.messages import HARNESS_LIKE_ROLES
from adaptive_token_compressor.core.metrics import CompressionScope
from adaptive_token_compressor.harness.compressor import (
    HarnessCompressor,
    SectionDetail,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_long_content(prefix: str = "", n_chars: int = 1000) -> str:
    """Generate content above compress_min_chars threshold."""
    body = "Some text content here. " * (n_chars // 24 + 1)
    return prefix + body[:n_chars]


def make_openclaw_prompt() -> str:
    """Synthesize an openclaw-style system prompt with multiple sections."""
    return (
        "You are an AI assistant.\n"
        "## Tooling\n"
        "Tool descriptions go here. " * 30
        + "\n## Memory Recall\n"
        + "Long memory content that should be compressed. " * 50
        + "\n## Subagent Context\n"
        + "Subagent info preserved verbatim. " * 20
    )


class FakeBackend:
    """Mock backend that returns predictable compressed text."""

    cache_tag = "lingua"

    def __init__(self, suffix: str = " [compressed]"):
        self._suffix = suffix
        self.call_count = 0

    def compress(self, text, *, rate, force_tokens=None, force_reserve_digit=False, digit_neighbor_radius=0):
        self.call_count += 1
        # Return shorter version: keep first 30% + suffix
        truncated = text[: max(10, len(text) // 3)]
        return truncated + self._suffix

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus
        return HealthStatus.healthy("fake_backend")


class FailingBackend:
    """Mock backend that always raises BackendError."""

    cache_tag = "lingua"

    def compress(self, text, *, rate, force_tokens=None, force_reserve_digit=False, digit_neighbor_radius=0):
        raise BackendError(
            "Simulated failure", component="fake_backend"
        )

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus
        return HealthStatus.unhealthy("fake_backend", "always fails")


# ─────────────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────────────


class TestHarnessCompressorInit:
    def test_default_construction(self):
        comp = HarnessCompressor()
        assert comp.name == "harness"
        assert comp._compress_rate == 0.5
        assert comp._compress_min_chars == 500
        assert comp._cache is None
        assert comp._cache_lock is None
        assert comp._quantum_lock is None  # Default disabled

    def test_unknown_profile_raises_config_error(self):
        with pytest.raises(ConfigError, match="Unknown profile"):
            HarnessCompressor(profile="nonexistent")

    def test_generic_profile(self):
        comp = HarnessCompressor(profile="generic")
        assert comp._profile.name == "generic"

    def test_custom_rate_and_min_chars(self):
        comp = HarnessCompressor(compress_rate=0.3, compress_min_chars=100)
        assert comp._compress_rate == 0.3
        assert comp._compress_min_chars == 100

    def test_invalid_numeric_params_raise_config_error(self):
        with pytest.raises(ConfigError, match="compress_rate"):
            HarnessCompressor(compress_rate=1.5)
        with pytest.raises(ConfigError, match="compress_min_chars"):
            HarnessCompressor(compress_min_chars=-1)
        with pytest.raises(ConfigError, match="timeout"):
            HarnessCompressor(timeout=0)

    def test_quantum_lock_disabled_by_default(self):
        comp = HarnessCompressor()
        assert comp._quantum_lock is None

    def test_quantum_lock_enabled_without_extra_raises(self, monkeypatch):
        # Simulate claw_compactor missing by hiding it from import system
        import sys
        monkeypatch.setitem(sys.modules, "claw_compactor", None)
        monkeypatch.setitem(sys.modules, "claw_compactor.fusion", None)
        monkeypatch.setitem(sys.modules, "claw_compactor.fusion.quantum_lock", None)
        monkeypatch.setitem(sys.modules, "claw_compactor.fusion.base", None)
        with pytest.raises(ConfigError, match="claw-compactor"):
            HarnessCompressor(enable_quantum_lock=True)


# ─────────────────────────────────────────────────────────────────────────────
# set_cache
# ─────────────────────────────────────────────────────────────────────────────


class TestSetCache:
    def test_set_cache_stores_cache_and_lock(self):
        comp = HarnessCompressor()
        cache = cachetools.LRUCache(maxsize=8)
        lock = threading.Lock()
        comp.set_cache(cache, lock)
        assert comp._cache is cache
        assert comp._cache_lock is lock

    def test_set_cache_none_disables_cache(self):
        comp = HarnessCompressor()
        cache = cachetools.LRUCache(maxsize=8)
        lock = threading.Lock()
        comp.set_cache(cache, lock)
        comp.set_cache(None, None)
        assert comp._cache is None
        assert comp._cache_lock is None


# ─────────────────────────────────────────────────────────────────────────────
# compress() with NoopBackend - identity tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressNoop:
    def test_noop_preserves_content(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        content = make_long_content("System prompt: ", 500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": content}],
            tools=None,
        )
        result = comp.compress(ctx)
        # NoopBackend returns text unchanged → after compression equals original
        assert result.messages[0]["content"] == content
        assert result.metrics.scope == CompressionScope.HARNESS

    def test_short_content_skipped_by_min_chars(self):
        comp = HarnessCompressor(compress_min_chars=500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": "Short"}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.messages[0]["content"] == "Short"
        assert result.metrics.skip_reason == "min_chars"

    def test_non_harness_role_unchanged(self):
        comp = HarnessCompressor()
        long_content = make_long_content("", 1000)
        ctx = CompressionContext(
            messages=[
                {"role": "user", "content": long_content},
                {"role": "assistant", "content": long_content},
            ],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.messages[0]["content"] == long_content
        assert result.messages[1]["content"] == long_content

    def test_tools_passthrough(self):
        comp = HarnessCompressor()
        tools = [{"type": "function", "function": {"name": "test"}}]
        ctx = CompressionContext(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )
        result = comp.compress(ctx)
        assert result.tools == tools


# ─────────────────────────────────────────────────────────────────────────────
# compress() with FakeBackend - actual compression
# ─────────────────────────────────────────────────────────────────────────────


class TestCompressWithFakeBackend:
    def test_long_content_gets_compressed(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)

        content = make_long_content("Long: ", 500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": content}],
            tools=None,
        )
        result = comp.compress(ctx)
        # Backend was called
        assert fake.call_count == 1
        # Content actually shorter
        assert len(result.messages[0]["content"]) < len(content)

    def test_metrics_scope_is_harness(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result.metrics.scope == CompressionScope.HARNESS
        assert result.metrics.tokens_before > 0
        assert result.metrics.tokens_after > 0
        assert result.metrics.tokens_after <= result.metrics.tokens_before

    def test_section_details_recorded(self, monkeypatch):
        comp = HarnessCompressor(profile="openclaw", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        prompt = make_openclaw_prompt()
        ctx = CompressionContext(
            messages=[{"role": "system", "content": prompt}],
            tools=None,
        )
        result = comp.compress(ctx)
        details = result.metrics.details["section_details"]
        assert len(details) > 1  # Multiple sections
        # Each detail is a SectionDetail
        assert all(isinstance(d, SectionDetail) for d in details)

    def test_preserve_section_not_compressed(self, monkeypatch):
        comp = HarnessCompressor(profile="openclaw", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)

        prompt = make_openclaw_prompt()
        ctx = CompressionContext(
            messages=[{"role": "system", "content": prompt}],
            tools=None,
        )
        result = comp.compress(ctx)
        details = result.metrics.details["section_details"]
        # ## Tooling and ## Subagent Context are preserve_headings → not compressed
        tooling_details = [d for d in details if "Tooling" in d.name]
        subagent_details = [d for d in details if "Subagent" in d.name]
        if tooling_details:
            assert not tooling_details[0].compressed
        if subagent_details:
            assert not subagent_details[0].compressed


# ─────────────────────────────────────────────────────────────────────────────
# Cache integration
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheBehavior:
    def test_cache_hit_skips_backend(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)
        comp.set_cache(cachetools.LRUCache(maxsize=16), threading.Lock())

        content = make_long_content("Same: ", 500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": content}],
            tools=None,
        )

        # First call: cache miss
        result1 = comp.compress(ctx)
        first_call_count = fake.call_count
        assert first_call_count == 1
        assert result1.metrics.details["cache_hits"] == 0

        # Second call: cache hit (same content)
        result2 = comp.compress(ctx)
        assert fake.call_count == first_call_count  # No additional backend call
        assert result2.metrics.details["cache_hits"] == 1
        # Output identical (byte-stable)
        assert result1.messages[0]["content"] == result2.messages[0]["content"]

    def test_section_detail_marks_cache_hit(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        comp.set_cache(cachetools.LRUCache(maxsize=16), threading.Lock())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        comp.compress(ctx)  # populate cache
        result = comp.compress(ctx)  # second call → hit
        details = result.metrics.details["section_details"]
        assert any(d.cache_hit for d in details)

    def test_standalone_no_cache_always_calls_backend(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)
        # No set_cache called → standalone mode

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        comp.compress(ctx)
        comp.compress(ctx)
        assert fake.call_count == 2  # Backend called twice

    def test_repeated_compress_byte_identical_through_cache(self, monkeypatch):
        """N identical inputs → all outputs byte-identical, backend hit ONCE.

        Prefix-cache stability contract: same input produces byte-identical
        output across arbitrary repetitions. With cache injected, the cache
        absorbs any non-determinism in the backend (real lingua's BERT can
        have floating-point edge wobble across batches/restarts).
        """
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)
        comp.set_cache(cachetools.LRUCache(maxsize=16), threading.Lock())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("Same input: ", 1500)}],
            tools=None,
        )

        N = 10
        outputs = [comp.compress(ctx).messages[0]["content"] for _ in range(N)]

        # Backend invoked exactly once — first call writes cache, the other 9 hit it.
        assert fake.call_count == 1
        # Every output identical — byte-stable for downstream prefix cache.
        first = outputs[0]
        for i, out in enumerate(outputs[1:], start=2):
            assert out == first, f"output #{i} diverged from #1"


# ─────────────────────────────────────────────────────────────────────────────
# Workspace normalization integration
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceNormalization:
    def test_workspace_path_normalized_for_cache_key(self, monkeypatch):
        """Two prompts differing only in workspace path should hit cache."""
        comp = HarnessCompressor(profile="openclaw", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)
        comp.set_cache(cachetools.LRUCache(maxsize=16), threading.Lock())

        # Same content, different workspace paths
        body = ("Files in {ws} are important. " * 20)
        content_a = body.format(ws="/home/alice/.openclaw/workspace_a")
        content_b = body.format(ws="/home/bob/.openclaw/workspace_b")

        ctx_a = CompressionContext(
            messages=[{"role": "system", "content": content_a}], tools=None
        )
        ctx_b = CompressionContext(
            messages=[{"role": "system", "content": content_b}], tools=None
        )

        result_a = comp.compress(ctx_a)
        first_count = fake.call_count
        result_b = comp.compress(ctx_b)
        # Cache hit because workspace paths normalized to placeholder
        assert fake.call_count == first_count
        assert result_b.metrics.details["cache_hits"] >= 1

    def test_workspace_restored_per_session(self, monkeypatch):
        """Restored output uses each session's actual workspace path."""
        comp = HarnessCompressor(profile="openclaw", compress_min_chars=100)
        # NoopBackend returns text verbatim → easier to verify restore
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        body = ("Path: {ws} please use it. " * 30)
        content_a = body.format(ws="/home/alice/.openclaw/workspace_a")

        ctx_a = CompressionContext(
            messages=[{"role": "system", "content": content_a}], tools=None
        )
        result_a = comp.compress(ctx_a)
        out_a = result_a.messages[0]["content"]
        # Original workspace path restored (no placeholder leaked)
        assert "/home/alice/.openclaw/workspace_a" in out_a
        assert "__AGENT_WORKSPACE__" not in out_a


# ─────────────────────────────────────────────────────────────────────────────
# Backend error handling
# ─────────────────────────────────────────────────────────────────────────────


class TestBackendErrorHandling:
    def test_backend_failure_keeps_original_content(self, monkeypatch, caplog):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FailingBackend())

        content = make_long_content("", 500)
        ctx = CompressionContext(
            messages=[{"role": "system", "content": content}], tools=None
        )
        result = comp.compress(ctx)
        # On backend failure: section keeps original text
        assert result.messages[0]["content"] == content
        # Error surfaced via metrics
        assert result.metrics.error is not None
        assert "Simulated failure" in result.metrics.error

    def test_backend_failure_does_not_raise(self, monkeypatch):
        """compress() never raises — backend failures absorbed."""
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FailingBackend())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        # No exception raised
        result = comp.compress(ctx)
        assert result is not None

    def test_section_detail_records_backend_error(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FailingBackend())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        result = comp.compress(ctx)
        details = result.metrics.details["section_details"]
        # At least one section has backend_error recorded
        assert any(d.backend_error is not None for d in details)


# ─────────────────────────────────────────────────────────────────────────────
# health_check
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_health_check_forwards_to_backend(self, monkeypatch):
        comp = HarnessCompressor()
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        status = comp.health_check()
        assert status.state is HealthState.HEALTHY

    def test_health_check_unhealthy_backend(self, monkeypatch):
        comp = HarnessCompressor()
        monkeypatch.setattr(comp, "_backend", FailingBackend())
        status = comp.health_check()
        assert status.state is HealthState.UNHEALTHY


# ─────────────────────────────────────────────────────────────────────────────
# QuantumLock integration (mocked)
# ─────────────────────────────────────────────────────────────────────────────


class TestQuantumLockIntegration:
    def test_quantum_lock_disabled_skips_processing(self, monkeypatch):
        """When disabled, compress() does not invoke quantum_lock."""
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        # No quantum_lock
        assert comp._quantum_lock is None

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        result = comp.compress(ctx)
        assert result is not None  # Works without quantum_lock

    def test_quantum_lock_enabled_invokes_apply(self, monkeypatch):
        """When enabled, FusionStage.should_apply + apply are called per message."""

        class FakeFusionContext:
            def __init__(self, content, role):
                self.content = content
                self.role = role

        class FakeFusionResult:
            def __init__(self, content):
                self.content = content

        class FakeQuantumLock:
            def __init__(self):
                self.should_apply_calls = 0
                self.apply_calls = 0

            def should_apply(self, ctx):
                self.should_apply_calls += 1
                return True

            def apply(self, ctx):
                self.apply_calls += 1
                return FakeFusionResult(content=ctx.content)  # passthrough

        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        # Inject fake QuantumLock + FusionContext
        fake_ql = FakeQuantumLock()
        comp._quantum_lock = fake_ql
        comp._FusionContext = FakeFusionContext

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        comp.compress(ctx)
        assert fake_ql.should_apply_calls == 1
        assert fake_ql.apply_calls == 1

    def test_quantum_lock_skipped_when_should_apply_false(self, monkeypatch):
        """should_apply=False → apply is NOT called (no dynamic content)."""

        class FakeFusionContext:
            def __init__(self, content, role):
                self.content = content
                self.role = role

        class FakeQuantumLock:
            def __init__(self):
                self.apply_calls = 0

            def should_apply(self, ctx):
                return False

            def apply(self, ctx):
                self.apply_calls += 1
                raise AssertionError("apply must not be called when should_apply=False")

        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        fake_ql = FakeQuantumLock()
        comp._quantum_lock = fake_ql
        comp._FusionContext = FakeFusionContext

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        comp.compress(ctx)
        assert fake_ql.apply_calls == 0

    def test_quantum_lock_failure_falls_back_gracefully(self, monkeypatch, caplog):
        """If QuantumLock raises, compression continues with raw content."""

        class FakeFusionContext:
            def __init__(self, content, role):
                self.content = content
                self.role = role

        class FailingQuantumLock:
            def should_apply(self, ctx):
                return True

            def apply(self, ctx):
                raise RuntimeError("QL failure")

        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        comp._quantum_lock = FailingQuantumLock()
        comp._FusionContext = FakeFusionContext

        ctx = CompressionContext(
            messages=[{"role": "system", "content": make_long_content("", 500)}],
            tools=None,
        )
        # Should not raise; falls back to raw compression
        result = comp.compress(ctx)
        assert result is not None
        assert "QuantumLock failed" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# QuantumLock real behavior (requires claw-compactor extra)
# ─────────────────────────────────────────────────────────────────────────────


try:
    from claw_compactor.fusion.quantum_lock import (
        APPENDIX_END,
        APPENDIX_START,
        QuantumLock,
        get_prefix_hash,
    )
    HAS_CLAW_COMPACTOR = True
except ImportError:
    HAS_CLAW_COMPACTOR = False


@pytest.mark.skipif(not HAS_CLAW_COMPACTOR, reason="claw-compactor not installed")
class TestQuantumLockRealBehavior:
    """Verify the real QuantumLock FusionStage integrates correctly.

    QuantumLock replaces dynamic fragments (dates, UUIDs, JWTs, ...) with
    placeholders and appends a 'dynamic context' block at the end.
    """

    def test_real_instance_is_quantumlock_stage(self):
        """When enable_quantum_lock=True, a real QuantumLock stage is held."""
        comp = HarnessCompressor(
            profile="generic",
            enable_quantum_lock=True,
        )
        assert comp._quantum_lock is not None
        assert isinstance(comp._quantum_lock, QuantumLock)
        assert comp._quantum_lock.name == "quantum_lock"
        assert comp._quantum_lock.order == 3

    def test_stable_prefix_across_dynamic_values(self, monkeypatch):
        """Two prompts differing only in dates → identical stable prefix.

        QuantumLock's value lives at the LLM provider's prefix-cache layer
        (vLLM / SGLang / Anthropic — keyed on token prefix), NOT in our
        lingua HTTP cache (keyed on full-text MD5). After stabilize() the
        text is `<stable prefix> + <appendix containing originals>`; the
        appendices differ between requests, so the full-text MD5 differs,
        so the lingua HTTP cache misses by design. What QuantumLock
        guarantees is that the *prefix* (before the appendix) is
        byte-identical across requests with different dynamic values —
        which is what an LLM provider's prefix cache keys on.

        Verified via `get_prefix_hash` (claw-compactor's own SHA-256 over
        the stable prefix region).
        """
        comp = HarnessCompressor(
            profile="generic",
            compress_min_chars=100,
            enable_quantum_lock=True,
        )
        # NoopBackend so the output reflects QuantumLock's effect verbatim
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        # Same template, different ISO dates
        body = "You are an assistant. Today is {date}. Static instructions follow. " * 30
        content_a = body.format(date="2026-03-17")
        content_b = body.format(date="2027-01-01")

        ctx_a = CompressionContext(
            messages=[{"role": "system", "content": content_a}], tools=None
        )
        ctx_b = CompressionContext(
            messages=[{"role": "system", "content": content_b}], tools=None
        )

        out_a = comp.compress(ctx_a).messages[0]["content"]
        out_b = comp.compress(ctx_b).messages[0]["content"]

        # Prefixes (before the dynamic-context appendix) are byte-identical
        prefix_a = out_a.split(APPENDIX_START)[0]
        prefix_b = out_b.split(APPENDIX_START)[0]
        assert prefix_a == prefix_b
        # SHA-256 over stable prefix matches — what an LLM prefix cache keys on
        assert get_prefix_hash(content_a) == get_prefix_hash(content_b)

    def test_appendix_preserves_original_dynamic_values(self, monkeypatch):
        """Output retains original dynamic values via the appendix block."""
        comp = HarnessCompressor(
            profile="generic",
            compress_min_chars=100,
            enable_quantum_lock=True,
        )
        # NoopBackend = identity → easier to inspect QuantumLock's effect
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        original = (
            "You are a helpful assistant. "
            "Today is 2026-03-17. "
            "Session: 550e8400-e29b-41d4-a716-446655440000. "
            "Static instructions repeat. "
        ) * 10
        ctx = CompressionContext(
            messages=[{"role": "system", "content": original}], tools=None
        )
        result = comp.compress(ctx)
        output = result.messages[0]["content"]

        # Appendix is present
        assert APPENDIX_START in output
        assert APPENDIX_END in output
        # Original dynamic values preserved in the appendix
        assert "2026-03-17" in output
        assert "550e8400-e29b-41d4-a716-446655440000" in output
        # Placeholders appear in the stable prefix (before appendix)
        prefix = output.split(APPENDIX_START)[0]
        assert "<date>" in prefix
        assert "<uuid>" in prefix

    def test_no_dynamic_content_means_no_stabilization(self, monkeypatch):
        """When content has no dynamic fragments, QuantumLock skips entirely."""
        comp = HarnessCompressor(
            profile="generic",
            compress_min_chars=100,
            enable_quantum_lock=True,
        )
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        original = "Pure static instructions, no dates or UUIDs. " * 30
        ctx = CompressionContext(
            messages=[{"role": "system", "content": original}], tools=None
        )
        result = comp.compress(ctx)
        output = result.messages[0]["content"]

        # No appendix appended (should_apply returned False)
        assert APPENDIX_START not in output
        assert APPENDIX_END not in output


# ─────────────────────────────────────────────────────────────────────────────
# QuantumLock appendix bypass — keep the appendix verbatim across compression
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_CLAW_COMPACTOR, reason="claw-compactor not installed")
class TestQuantumLockAppendixBypass:
    """`HarnessCompressor._compress_message_content` strips the QLock appendix
    before sectioning so lingua never shreds it, then reattaches it byte-for-
    byte. Without the bypass, lingua's BERT treats the ``<!-- ... -->`` /
    ``unix_ts: ...`` lines as low-importance text and breaks the appendix →
    original-value mapping.
    """

    @staticmethod
    def _qlock_input() -> str:
        # Long enough to exceed compress_min_chars; embeds two unix_ts so
        # QuantumLock.should_apply returns True and stabilize() emits an appendix.
        body = (
            "Heartbeat email cadence reference. Last sync at 1703275200 "
            "and the prior sync at 1703260800. " * 30
        )
        return body

    def test_appendix_byte_identical_after_compression(self):
        """Compressed output ends with QuantumLock.apply()'s exact appendix."""
        from claw_compactor.fusion.base import FusionContext
        from claw_compactor.fusion.quantum_lock import QuantumLock

        # NoopBackend isolates the bypass logic from any lingua noise.
        comp = HarnessCompressor(
            profile="generic", compress_min_chars=100, enable_quantum_lock=True
        )
        comp._backend = NoopBackend()

        raw = self._qlock_input()
        # Pre-compute what QuantumLock would emit for this input so we know
        # the exact appendix bytes to look for in the final output.
        stabilized = QuantumLock().apply(
            FusionContext(content=raw, role="system")
        ).content
        assert APPENDIX_START in stabilized
        appendix_only = stabilized[stabilized.index(APPENDIX_START):]
        assert appendix_only.endswith(APPENDIX_END)

        ctx = CompressionContext(messages=[{"role": "system", "content": raw}], tools=None)
        out = comp.compress(ctx).messages[0]["content"]

        # Appendix region survives byte-for-byte at the tail of the output.
        assert out.endswith(appendix_only), (
            "tail of compressed output must equal QuantumLock's appendix verbatim"
        )

    def test_qlock_off_does_not_strip_lookalike_markers(self):
        """When QLock is disabled, user content with appendix-shaped markers
        must NOT be cut — the bypass logic only runs when QLock is enabled."""
        comp = HarnessCompressor(
            profile="generic", compress_min_chars=100, enable_quantum_lock=False
        )
        comp._backend = NoopBackend()

        # User content that LOOKS like a QLock appendix but isn't (QLock off).
        # Made long enough to exceed compress_min_chars so we exercise the
        # full sectioning + compression path, not the min_chars short-circuit.
        body = (
            "Document body with arbitrary prose that should be sent to "
            "lingua as a single unit. " * 20
        )
        fake_appendix = (
            "\n---\n" + APPENDIX_START
            + "\nunix_ts: 9999999999\n"
            + APPENDIX_END
        )
        raw = body + fake_appendix

        ctx = CompressionContext(messages=[{"role": "system", "content": raw}], tools=None)
        out = comp.compress(ctx).messages[0]["content"]

        # NoopBackend is identity; without QLock, no bypass either, so output
        # equals input verbatim — including the appendix-shaped tail.
        assert out == raw

    def test_qlock_enabled_repeated_compress_byte_identical(self):
        """N=10 repeats with QLock + cache → all outputs byte-identical AND
        the appendix tail is preserved verbatim every time."""
        comp = HarnessCompressor(
            profile="generic", compress_min_chars=100, enable_quantum_lock=True
        )
        comp._backend = FakeBackend()
        comp.set_cache(cachetools.LRUCache(maxsize=16), threading.Lock())

        ctx = CompressionContext(
            messages=[{"role": "system", "content": self._qlock_input()}],
            tools=None,
        )

        N = 10
        outputs = [comp.compress(ctx).messages[0]["content"] for _ in range(N)]
        first = outputs[0]
        # Every subsequent run produces the same bytes — prefix-cache stable.
        for i, out in enumerate(outputs[1:], start=2):
            assert out == first, f"output #{i} diverged from #1"
        # Appendix tail still intact in the cached output.
        assert APPENDIX_START in first
        assert first.rstrip().endswith(APPENDIX_END)


@pytest.mark.skipif(not HAS_CLAW_COMPACTOR, reason="claw-compactor not installed")
class TestQuantumLockAppendixBypassRealLingua:
    """Same contract verified against a running lingua server.

    Skipped when the server is unreachable. Without the bypass, real lingua
    on `rate=0.5` deletes the `<!-- ... -->` markers and individual
    ``unix_ts: ...`` lines; the assertions below would fail. With the
    bypass, the appendix is invisible to lingua and survives byte-for-byte.
    """

    LINGUA_URL = os.environ.get(
        "LINGUA_INTEGRATION_URL", "http://localhost:8001/compress"
    )

    @staticmethod
    def _server_reachable(url: str) -> bool:
        import requests

        health = url.rsplit("/", 1)[0] + "/health"
        try:
            return requests.get(health, timeout=2).status_code == 200
        except Exception:
            return False

    def test_appendix_survives_real_lingua_compression(self):
        if not self._server_reachable(self.LINGUA_URL):
            pytest.skip(f"Lingua server not reachable at {self.LINGUA_URL}")

        from claw_compactor.fusion.base import FusionContext
        from claw_compactor.fusion.quantum_lock import QuantumLock

        comp = HarnessCompressor(
            profile="generic",
            lingua_url=self.LINGUA_URL,
            compress_min_chars=100,
            compress_rate=0.5,
            enable_quantum_lock=True,
        )

        raw = TestQuantumLockAppendixBypass._qlock_input()
        appendix = QuantumLock().apply(
            FusionContext(content=raw, role="system")
        ).content
        appendix_tail = appendix[appendix.index(APPENDIX_START):]

        ctx = CompressionContext(messages=[{"role": "system", "content": raw}], tools=None)
        out = comp.compress(ctx).messages[0]["content"]

        # Originals + delimiter markers survived intact.
        assert APPENDIX_START in out
        assert APPENDIX_END in out
        assert "1703275200" in out
        assert "1703260800" in out
        # Tail byte-equal to QLock's appendix region.
        assert out.endswith(appendix_tail)
