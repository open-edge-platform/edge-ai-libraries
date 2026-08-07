"""Tests for core/manager.py — covers plan §13 row `core/manager`."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.aggregator import (
    CallCount,
    CompressionRatio,
    TotalSaved,
    AvgSavedPerCall,
    AvgSavedPerRequest,
)
from adaptive_token_compressor.core.base import (
    BaseCompressor,
    CompressionContext,
    CompressorResult,
)
from adaptive_token_compressor.core.health import HealthState, HealthStatus
from adaptive_token_compressor.core.manager import CompressionManager, _RegisteredCompressor
from adaptive_token_compressor.core.metrics import CompressorMetrics, CompressionScope


# ─────────────────────────────────────────────────────────────────────────────
# Fake compressor (returns hardcoded CompressorResult for testing)
# ─────────────────────────────────────────────────────────────────────────────


class FakeCompressor(BaseCompressor):
    """Minimal compressor that returns a CompressorResult with controlled metrics."""

    def __init__(
        self,
        name: str = "fake",
        *,
        tokens_before: int = 100,
        tokens_after: int = 60,
        duration_ms: float = 10.0,
        health_state: HealthState = HealthState.HEALTHY,
        health_message: str = "",
    ) -> None:
        self.name = name
        self._tokens_before = tokens_before
        self._tokens_after = tokens_after
        self._duration_ms = duration_ms
        self._health_state = health_state
        self._health_message = health_message
        self._cache = None
        self._cache_lock = None

    def compress(self, ctx: CompressionContext) -> CompressorResult:
        metrics = CompressorMetrics(
            name=self.name,
            scope=CompressionScope.HARNESS,  # Fake uses HARNESS scope
            tokens_before=self._tokens_before,
            tokens_after=self._tokens_after,
            duration_ms=self._duration_ms,
        )
        return CompressorResult(
            messages=ctx.messages,
            tools=ctx.tools,
            metrics=metrics,
        )

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        if self._health_state is HealthState.HEALTHY:
            return HealthStatus.healthy(f"fake_compressor@{self.name}")
        elif self._health_state is HealthState.DEGRADED:
            return HealthStatus.degraded(f"fake_compressor@{self.name}", self._health_message)
        else:
            return HealthStatus.unhealthy(f"fake_compressor@{self.name}", self._health_message)

    def set_cache(self, cache, lock) -> None:
        """Optional cache injection — manager detects this via hasattr."""
        self._cache = cache
        self._cache_lock = lock


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestManagerInit:
    def test_default_cache_size(self):
        mgr = CompressionManager()
        assert mgr._cache_size == 4096

    def test_custom_cache_size(self):
        mgr = CompressionManager(cache_size=128)
        assert mgr._cache_size == 128

    def test_empty_compressors_registry(self):
        mgr = CompressionManager()
        assert len(mgr._compressors) == 0

    def test_empty_cache_slots(self):
        mgr = CompressionManager()
        assert len(mgr._cache_slots) == 0


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.register_compressor
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisterCompressor:
    def test_returns_wrapper(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        wrapper = mgr.register_compressor("src1", fake)
        assert isinstance(wrapper, _RegisteredCompressor)

    def test_wrapper_has_correct_name(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        wrapper = mgr.register_compressor("src1", fake)
        assert wrapper.name == "fake1"

    def test_duplicate_source_raises(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_compressor("src1", fake)

    def test_cache_injection_when_set_cache_exists(self):
        mgr = CompressionManager(cache_size=16)
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        assert fake._cache is not None
        assert fake._cache.maxsize == 16
        assert fake._cache_lock is not None

    def test_no_cache_injection_when_set_cache_missing(self):
        """Compressor without set_cache is still registered normally."""
        mgr = CompressionManager()

        class NoSetCache(BaseCompressor):
            name = "no_cache"

            def compress(self, ctx):
                return CompressorResult(
                    ctx.messages,
                    ctx.tools,
                    CompressorMetrics(name=self.name, scope=CompressionScope.HARNESS),
                )

            def health_check(self, *, timeout=5.0):
                return HealthStatus.healthy("no_cache")

        comp = NoSetCache()
        wrapper = mgr.register_compressor("src1", comp)
        assert isinstance(wrapper, _RegisteredCompressor)
        assert len(mgr._cache_slots) == 0

    def test_cache_slot_stored_in_manager(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        assert "src1" in mgr._cache_slots
        slot = mgr._cache_slots["src1"]
        assert slot.cache is fake._cache
        assert slot.lock is fake._cache_lock


# ─────────────────────────────────────────────────────────────────────────────
# _RegisteredCompressor.compress (auto-observe)
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisteredCompressorCompress:
    def test_compress_forwards_to_inner(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        ctx = CompressionContext(messages=[], tools=None)
        result = wrapper.compress(ctx)
        assert result.metrics.tokens_before == 100
        assert result.metrics.tokens_after == 60

    def test_compress_observes_metrics(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        ctx = CompressionContext(messages=[], tools=None)
        wrapper.compress(ctx)
        snapshot = mgr.snapshot()
        assert snapshot["saved"] == 40.0

    def test_compress_with_req_id_tracks_request(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        ctx = CompressionContext(messages=[], tools=None)
        wrapper.compress(ctx, req_id="r1")
        wrapper.compress(ctx, req_id="r2")
        assert mgr._aggregator.request_count() == 2

    def test_compress_req_id_not_passed_to_inner(self):
        """req_id is manager-level metadata; inner compressor never sees it."""
        mgr = CompressionManager()

        class SpyCompressor(BaseCompressor):
            name = "spy"
            called_with = None

            def compress(self, ctx):
                self.called_with = ctx
                return CompressorResult(
                    ctx.messages,
                    ctx.tools,
                    CompressorMetrics(
                        name=self.name,
                        scope=CompressionScope.HARNESS,
                        tokens_before=0,
                        tokens_after=0,
                        duration_ms=0.0,
                    ),
                )

            def health_check(self, *, timeout=5.0):
                return HealthStatus.healthy("spy")

        spy = SpyCompressor()
        wrapper = mgr.register_compressor("src1", spy)
        ctx = CompressionContext(messages=[], tools=None)
        wrapper.compress(ctx, req_id="r1")
        # Inner compressor receives only ctx, not req_id
        assert spy.called_with is ctx


# ─────────────────────────────────────────────────────────────────────────────
# _RegisteredCompressor.health_check
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisteredCompressorHealthCheck:
    def test_health_check_forwards_to_inner(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", health_state=HealthState.HEALTHY)
        wrapper = mgr.register_compressor("src1", fake)
        status = wrapper.health_check()
        assert status.state is HealthState.HEALTHY

    def test_health_check_timeout_forwarded(self):
        mgr = CompressionManager()

        class TimeoutSpyCompressor(BaseCompressor):
            name = "spy"
            timeout_received = None

            def compress(self, ctx):
                return CompressorResult(
                    ctx.messages,
                    ctx.tools,
                    CompressorMetrics(name=self.name, scope=CompressionScope.HARNESS),
                )

            def health_check(self, *, timeout=5.0):
                self.timeout_received = timeout
                return HealthStatus.healthy("spy")

        spy = TimeoutSpyCompressor()
        wrapper = mgr.register_compressor("src1", spy)
        wrapper.health_check(timeout=2.5)
        assert spy.timeout_received == 2.5


# ─────────────────────────────────────────────────────────────────────────────
# _RegisteredCompressor.inner (bypass property)
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisteredCompressorInner:
    def test_inner_property_returns_underlying_compressor(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        wrapper = mgr.register_compressor("src1", fake)
        assert wrapper.inner is fake


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.register_metric
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisterMetric:
    def test_register_metric_emits_rules(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        mgr.register_metric("calls", CallCount(sources="src1"))
        # Rule injected into aggregator
        assert len(mgr._aggregator._rules) == 1

    def test_register_metric_unknown_source_raises(self):
        mgr = CompressionManager()
        with pytest.raises(ValueError, match="unknown source"):
            mgr.register_metric("calls", CallCount(sources="unknown"))

    def test_register_metric_multi_source_validates_all(self):
        mgr = CompressionManager()
        mgr.register_compressor("src1", FakeCompressor("fake1"))
        with pytest.raises(ValueError, match="unknown source"):
            mgr.register_metric("saved", TotalSaved(sources=["src1", "src2"]))

    def test_register_per_request_metric_without_denominator_defers_to_snapshot(self):
        # Registration succeeds even without a denominator; the error surfaces
        # at snapshot(), where req_id / anchor are fully determined.
        mgr = CompressionManager()
        mgr.register_compressor("src1", FakeCompressor("fake1"))
        mgr.register_metric("avg", AvgSavedPerRequest(sources="src1"))
        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            mgr.snapshot()

    def test_register_per_request_metric_with_anchor_succeeds(self):
        mgr = CompressionManager()
        mgr.register_compressor("src1", FakeCompressor("fake1"))
        mgr.set_per_anchor("src1")
        mgr.register_metric("avg", AvgSavedPerRequest(sources="src1"))
        assert len(mgr._aggregator._rules) > 0


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.set_per_anchor
# ─────────────────────────────────────────────────────────────────────────────


class TestSetPerAnchor:
    def test_set_per_anchor_unknown_source_raises(self):
        mgr = CompressionManager()
        with pytest.raises(ValueError, match="not registered"):
            mgr.set_per_anchor("unknown")

    def test_set_per_anchor_sets_aggregator_anchor(self):
        mgr = CompressionManager()
        mgr.register_compressor("src1", FakeCompressor("fake1"))
        mgr.set_per_anchor("src1")
        assert mgr._aggregator._anchor == "src1"


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.__getitem__
# ─────────────────────────────────────────────────────────────────────────────


class TestManagerGetItem:
    def test_getitem_returns_wrapper(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        wrapper = mgr.register_compressor("src1", fake)
        assert mgr["src1"] is wrapper

    def test_getitem_unknown_source_raises(self):
        mgr = CompressionManager()
        with pytest.raises(KeyError):
            _ = mgr["unknown"]


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.snapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestManagerSnapshot:
    def test_snapshot_empty(self):
        mgr = CompressionManager()
        assert mgr.snapshot() == {}

    def test_snapshot_returns_aggregator_snapshot(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        ctx = CompressionContext(messages=[], tools=None)
        wrapper.compress(ctx)
        snapshot = mgr.snapshot()
        assert snapshot["saved"] == 40.0

    def test_snapshot_source_returns_source_scoped_metrics(self):
        mgr = CompressionManager()
        w1 = mgr.register_compressor("src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        w2 = mgr.register_compressor("src2", FakeCompressor("fake2", tokens_before=90, tokens_after=30))
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src2.saved", TotalSaved(sources="src2"))

        ctx = CompressionContext(messages=[], tools=None)
        w1.compress(ctx, req_id="r1")
        w2.compress(ctx, req_id="r1")

        assert mgr.snapshot(source="src1")["src1.saved"] == 40.0
        assert mgr.snapshot(source="src2")["src2.saved"] == 60.0


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.cache_stats
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheStats:
    def test_cache_stats_empty_when_no_cache_slots(self):
        mgr = CompressionManager()
        assert mgr.cache_stats() == {}

    def test_cache_stats_returns_currsize_maxsize(self):
        mgr = CompressionManager(cache_size=8)
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        stats = mgr.cache_stats()
        assert stats["src1"]["currsize"] == 0
        assert stats["src1"]["maxsize"] == 8

    def test_cache_stats_reflects_cache_usage(self):
        mgr = CompressionManager(cache_size=8)
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        # Write directly to cache to simulate usage
        fake._cache["key1"] = "value1"
        fake._cache["key2"] = "value2"
        stats = mgr.cache_stats()
        assert stats["src1"]["currsize"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.reset
# ─────────────────────────────────────────────────────────────────────────────


class TestManagerReset:
    def test_reset_clears_aggregator_buckets(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        ctx = CompressionContext(messages=[], tools=None)
        wrapper.compress(ctx)
        assert mgr.snapshot()["saved"] == 40.0
        mgr.reset()
        assert mgr.snapshot()["saved"] == 0.0

    def test_reset_clears_cache_slots(self):
        mgr = CompressionManager(cache_size=8)
        fake = FakeCompressor("fake1")
        mgr.register_compressor("src1", fake)
        fake._cache["key1"] = "value1"
        assert mgr.cache_stats()["src1"]["currsize"] == 1
        mgr.reset()
        assert mgr.cache_stats()["src1"]["currsize"] == 0

    def test_reset_preserves_registrations(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        wrapper = mgr.register_compressor("src1", fake)
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        mgr.reset()
        # Compressor still registered
        assert mgr["src1"] is wrapper
        # Metric rules still registered
        assert len(mgr._aggregator._rules) > 0

    def test_reset_source_only_clears_that_source_metrics(self):
        mgr = CompressionManager()
        w1 = mgr.register_compressor("src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        w2 = mgr.register_compressor("src2", FakeCompressor("fake2", tokens_before=90, tokens_after=30))
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src2.saved", TotalSaved(sources="src2"))
        mgr.register_metric("overall.saved", TotalSaved(sources=["src1", "src2"]))

        ctx = CompressionContext(messages=[], tools=None)
        w1.compress(ctx, req_id="r1")
        w2.compress(ctx, req_id="r1")
        assert mgr.snapshot()["overall.saved"] == 100.0

        mgr.reset(source="src1")

        assert mgr.snapshot(source="src1")["src1.saved"] == 0.0
        assert mgr.snapshot(source="src2")["src2.saved"] == 60.0
        assert mgr.snapshot()["overall.saved"] == 60.0

    def test_reset_source_only_clears_that_source_cache(self):
        mgr = CompressionManager(cache_size=8)
        fake1 = FakeCompressor("fake1")
        fake2 = FakeCompressor("fake2")
        mgr.register_compressor("src1", fake1)
        mgr.register_compressor("src2", fake2)

        fake1._cache["key1"] = "value1"
        fake2._cache["key2"] = "value2"
        mgr.reset(source="src1")

        stats = mgr.cache_stats()
        assert stats["src1"]["currsize"] == 0
        assert stats["src2"]["currsize"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# CompressionManager.check_backends
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckBackends:
    def test_check_backends_all_healthy_silent(self):
        mgr = CompressionManager()
        mgr.register_compressor("src1", FakeCompressor("fake1", health_state=HealthState.HEALTHY))
        mgr.check_backends()  # No exception

    def test_check_backends_degraded_logs_warning(self, caplog):
        mgr = CompressionManager()
        mgr.register_compressor(
            "src1", FakeCompressor("fake1", health_state=HealthState.DEGRADED, health_message="slow")
        )
        mgr.check_backends()
        assert "DEGRADED" in caplog.text
        assert "slow" in caplog.text

    def test_check_backends_unhealthy_raises(self):
        mgr = CompressionManager()
        mgr.register_compressor(
            "src1",
            FakeCompressor("fake1", health_state=HealthState.UNHEALTHY, health_message="down"),
        )
        with pytest.raises(RuntimeError, match="health check failed"):
            mgr.check_backends()

    def test_check_backends_collects_all_unhealthy(self):
        mgr = CompressionManager()
        mgr.register_compressor(
            "src1",
            FakeCompressor("fake1", health_state=HealthState.UNHEALTHY, health_message="err1"),
        )
        mgr.register_compressor(
            "src2",
            FakeCompressor("fake2", health_state=HealthState.UNHEALTHY, health_message="err2"),
        )
        with pytest.raises(RuntimeError, match="err1.*err2"):
            mgr.check_backends()

    def test_check_backends_timeout_forwarded(self):
        mgr = CompressionManager()

        class TimeoutSpyCompressor(BaseCompressor):
            name = "spy"
            timeout_received = None

            def compress(self, ctx):
                return CompressorResult(
                    ctx.messages,
                    ctx.tools,
                    CompressorMetrics(name=self.name, scope=CompressionScope.HARNESS),
                )

            def health_check(self, *, timeout=5.0):
                self.timeout_received = timeout
                return HealthStatus.healthy("spy")

        spy = TimeoutSpyCompressor()
        mgr.register_compressor("src1", spy)
        mgr.check_backends(timeout=3.0)
        assert spy.timeout_received == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: register → compress → observe → snapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_pipeline_with_three_metrics(self):
        """Full register → wrapper.compress → observe → snapshot chain."""
        mgr = CompressionManager()
        fake1 = FakeCompressor("fake1", tokens_before=100, tokens_after=60, duration_ms=10.0)
        fake2 = FakeCompressor("fake2", tokens_before=200, tokens_after=150, duration_ms=20.0)
        w1 = mgr.register_compressor("src1", fake1)
        w2 = mgr.register_compressor("src2", fake2)

        mgr.register_metric("calls_all", CallCount(sources=["src1", "src2"]))
        mgr.register_metric("saved_total", TotalSaved(sources=["src1", "src2"]))
        mgr.register_metric("ratio", CompressionRatio(sources=["src1", "src2"]))

        ctx = CompressionContext(messages=[], tools=None)
        w1.compress(ctx)
        w2.compress(ctx)

        snap = mgr.snapshot()
        assert snap["calls_all"] == 2.0
        assert snap["saved_total"] == 90.0  # (100-60) + (200-150)
        # ratio = (60 + 150) / (100 + 200) = 210 / 300 = 0.7
        assert snap["ratio"] == pytest.approx(0.7, abs=0.01)

    def test_full_pipeline_with_per_request_metric(self):
        """PerRequest metric using req_id denominator. Registration no longer
        needs a pre-established denominator — req_ids arrive afterwards and the
        denominator is resolved at snapshot()."""
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        wrapper = mgr.register_compressor("src1", fake)
        ctx = CompressionContext(messages=[], tools=None)

        mgr.register_metric("avg_saved_call", AvgSavedPerCall(sources="src1"))
        mgr.register_metric("avg_saved_req", AvgSavedPerRequest(sources="src1"))

        # Compress 3 times with 2 unique req_ids.
        wrapper.compress(ctx, req_id="r1")
        wrapper.compress(ctx, req_id="r1")  # Same req_id, deduped
        wrapper.compress(ctx, req_id="r2")  # New req_id

        snap = mgr.snapshot()
        # 3 calls, saved = 40 * 3 = 120
        assert snap["avg_saved_call"] == pytest.approx(40.0, abs=0.1)
        # 2 unique req_ids (r1, r2); saved = 120; avg = 120 / 2 = 60.0
        assert snap["avg_saved_req"] == pytest.approx(60.0, abs=0.1)
