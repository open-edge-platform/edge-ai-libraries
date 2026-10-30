"""Tests for core/manager.py — covers plan §13 row `core/manager`."""
from __future__ import annotations

import threading

import pytest

from adaptive_token_compressor.core.aggregator import (
    CallCount,
    CompressionRatio,
    RequestCount,
    TotalInput,
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
from adaptive_token_compressor.core.manager import (
    OVERFLOW_METRICS_VALUE,
    CompressionManager,
    _RegisteredCompressor,
)
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


# ─────────────────────────────────────────────────────────────────────────────
# Keyed metrics: register(metrics_keys=[...]) + compress(metrics_values={...})
# → one aggregator per (key, value) bucket
# ─────────────────────────────────────────────────────────────────────────────


def _ctx() -> CompressionContext:
    return CompressionContext(messages=[], tools=None)


def _pv(value: str | None) -> dict[str, str | None]:
    """metrics_values for the single "provider" key used by most tests."""
    return {"provider": value}


def _reg(mgr, source, fake, keys=("provider",)):
    return mgr.register_compressor(source, fake, metrics_keys=list(keys))


class TestMultiKeyMetrics:
    def test_each_key_counts_the_call(self):
        """request1 vllm/alice saves 100, request2 openai/alice saves 50."""
        mgr = CompressionManager()
        fake = FakeCompressor("fake1", tokens_before=200, tokens_after=100)
        w = _reg(mgr, "src1", fake, keys=["provider", "user"])
        mgr.register_metric("saved", TotalSaved(sources="src1"))

        w.compress(_ctx(), req_id="r1", metrics_values={"provider": "vllm", "user": "alice"})
        fake._tokens_before, fake._tokens_after = 100, 50
        w.compress(_ctx(), req_id="r2", metrics_values={"provider": "openai", "user": "alice"})

        assert mgr.snapshot_by_keys() == {
            "provider": {"vllm": {"saved": 100.0}, "openai": {"saved": 50.0}},
            "user": {"alice": {"saved": 150.0}},
        }
        assert mgr.snapshot(key="provider", value="vllm") == {"saved": 100.0}
        assert mgr.snapshot(key="user", value="alice") == {"saved": 150.0}
        assert mgr.snapshot() == {"saved": 150.0}

    def test_same_value_under_different_keys_is_separate(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"), keys=["provider", "user"])
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1", metrics_values={"provider": "x", "user": "y"})
        w.compress(_ctx(), req_id="r2", metrics_values={"provider": "y", "user": "y"})
        assert mgr.snapshot(key="provider", value="y") == {"saved": 40.0}
        assert mgr.snapshot(key="user", value="y") == {"saved": 80.0}

    def test_undeclared_keys_ignored(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"), keys=["provider"])
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1", metrics_values={"provider": "vllm", "user": "alice"})
        assert set(mgr.snapshot_by_keys()) == {"provider"}

    def test_compressor_without_metrics_keys_only_global(self):
        mgr = CompressionManager()
        w = mgr.register_compressor("src1", FakeCompressor("fake1"))
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1", metrics_values={"provider": "vllm"})
        assert mgr.snapshot() == {"saved": 40.0}
        assert mgr.snapshot_by_keys() == {}
        assert mgr._keyed_aggs == {}

    @pytest.mark.parametrize("values", [{"provider": "vllm"}, {"provider": "vllm", "user": None},
                                        {"provider": "vllm", "user": ""}])
    def test_missing_value_skips_only_that_key(self, values):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"), keys=["provider", "user"])
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1", metrics_values=values)
        assert mgr.snapshot_by_keys() == {"provider": {"vllm": {"saved": 40.0}}}
        assert mgr.snapshot() == {"saved": 40.0}

    @pytest.mark.parametrize("values", ["vllm", ["provider"]])
    def test_non_mapping_values_rejected_before_compress(self, values):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        fake.compress = lambda ctx: pytest.fail("compressor must not run")
        w = _reg(mgr, "src1", fake)
        with pytest.raises(TypeError, match="mapping"):
            w.compress(_ctx(), metrics_values=values)

    def test_non_string_value_rejected_before_compress(self):
        mgr = CompressionManager()
        fake = FakeCompressor("fake1")
        fake.compress = lambda ctx: pytest.fail("compressor must not run")
        w = _reg(mgr, "src1", fake)
        with pytest.raises(TypeError, match="provider"):
            w.compress(_ctx(), metrics_values={"provider": 1})

    def test_old_metrics_key_argument_removed(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        with pytest.raises(TypeError):
            w.compress(_ctx(), metrics_key="vllm")
        assert not hasattr(mgr, "snapshot_by_key")

    def test_bare_string_metrics_keys_rejected(self):
        mgr = CompressionManager()
        with pytest.raises(TypeError, match="list"):
            mgr.register_compressor("src1", FakeCompressor("fake1"), metrics_keys="provider")
        assert "src1" not in mgr._compressors

    @pytest.mark.parametrize("keys", [["provider", "provider"], ["provider", ""], [1]])
    def test_invalid_metrics_keys_rejected(self, keys):
        mgr = CompressionManager()
        with pytest.raises(ValueError):
            mgr.register_compressor("src1", FakeCompressor("fake1"), metrics_keys=keys)
        assert mgr._cache_slots == {}

    def test_cross_source_metric_per_key_covers_declaring_compressors(self):
        mgr = CompressionManager()
        ctx_w = _reg(mgr, "context", FakeCompressor("c", tokens_before=100, tokens_after=60), ["provider"])
        har_w = _reg(mgr, "harness", FakeCompressor("h", tokens_before=50, tokens_after=20),
                     ["provider", "user"])
        mgr.register_metric("overall.saved", TotalSaved(sources=["context", "harness"]))
        values = {"provider": "vllm", "user": "alice"}
        ctx_w.compress(_ctx(), req_id="r1", metrics_values=values)
        har_w.compress(_ctx(), req_id="r1", metrics_values=values)

        assert mgr.snapshot(key="provider", value="vllm") == {"overall.saved": 70.0}
        assert mgr.snapshot(key="user", value="alice") == {"overall.saved": 30.0}  # harness only
        assert mgr.snapshot() == {"overall.saved": 70.0}

    def test_overflow_counted_per_key(self, caplog):
        mgr = CompressionManager(max_metric_values=1)
        w = _reg(mgr, "src1", FakeCompressor("fake1"), keys=["provider", "user"])
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        with caplog.at_level("WARNING", logger="adaptive_token_compressor.core.manager"):
            w.compress(_ctx(), req_id="r1", metrics_values={"provider": "p1", "user": "u1"})
            w.compress(_ctx(), req_id="r2", metrics_values={"provider": "p2", "user": "u1"})
        assert mgr.snapshot_by_keys() == {
            "provider": {"p1": {"saved": 40.0}, OVERFLOW_METRICS_VALUE: {"saved": 40.0}},
            "user": {"u1": {"saved": 80.0}},
        }
        assert [r.message for r in caplog.records if "limit" in r.message] == [
            "metrics value limit (1) reached for key 'provider'; "
            "further values are counted under 'other'"
        ]

    def test_snapshot_needs_key_and_value_together(self):
        mgr = CompressionManager()
        with pytest.raises(ValueError):
            mgr.snapshot(key="provider")
        with pytest.raises(ValueError):
            mgr.snapshot(value="vllm")

    def test_snapshot_by_keys_with_source(self):
        mgr = CompressionManager()
        w1 = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        w2 = _reg(mgr, "src2", FakeCompressor("fake2", tokens_before=50, tokens_after=20))
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src2.saved", TotalSaved(sources="src2"))
        mgr.register_metric("overall.saved", TotalSaved(sources=["src1", "src2"]))
        w1.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        w2.compress(_ctx(), req_id="r2", metrics_values=_pv("pB"))

        assert mgr.snapshot_by_keys(source="src1") == {"provider": {"pA": {"src1.saved": 40.0}}}
        assert mgr.snapshot_by_keys(source="src2") == {"provider": {"pB": {"src2.saved": 30.0}}}

    def test_reset_value_without_key_rejected(self):
        mgr = CompressionManager()
        with pytest.raises(ValueError):
            mgr.reset(value="vllm")


class TestKeyedMetrics:
    def test_metrics_grouped_by_value(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src1.calls", CallCount(sources="src1"))

        w.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        w.compress(_ctx(), req_id="r2", metrics_values=_pv("pA"))
        w.compress(_ctx(), req_id="r3", metrics_values=_pv("pB"))

        assert mgr.snapshot(key="provider", value="pA") == {"src1.saved": 80.0, "src1.calls": 2.0}
        assert mgr.snapshot(key="provider", value="pB") == {"src1.saved": 40.0, "src1.calls": 1.0}
        assert mgr.snapshot()["src1.saved"] == 120.0
        assert set(mgr.snapshot_by_keys()["provider"]) == {"pA", "pB"}

    def test_no_values_only_observes_global(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1")
        assert mgr.snapshot()["saved"] == 40.0
        assert mgr.snapshot_by_keys() == {}
        assert mgr._keyed_aggs == {}

    def test_unknown_bucket_snapshot_empty(self):
        mgr = CompressionManager()
        _reg(mgr, "src1", FakeCompressor("fake1"))
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        assert mgr.snapshot(key="provider", value="nope") == {}
        assert mgr.snapshot(key="nope", value="nope") == {}
        assert mgr.snapshot(source="src1", key="provider", value="nope") == {}

    def test_keyed_aggregator_shared_across_compressors(self):
        mgr = CompressionManager()
        w1 = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        w2 = _reg(mgr, "src2", FakeCompressor("fake2", tokens_before=50, tokens_after=20))
        mgr.register_metric("overall.saved", TotalSaved(sources=["src1", "src2"]))
        mgr.register_metric("overall.requests", RequestCount())

        w1.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        w2.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))

        assert len(mgr._keyed_aggs["provider"]) == 1
        snap = mgr.snapshot(key="provider", value="pA")
        assert snap["overall.saved"] == 70.0
        assert snap["overall.requests"] == 1.0  # same req_id deduped across sources

    def test_overflow_values_go_to_other(self, caplog):
        mgr = CompressionManager(max_metric_values=2)
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        mgr.register_metric("saved", TotalSaved(sources="src1"))

        with caplog.at_level("WARNING", logger="adaptive_token_compressor.core.manager"):
            for i, value in enumerate(["k1", "k2", "k3", "k4", "k1"]):
                w.compress(_ctx(), req_id=f"r{i}", metrics_values=_pv(value))

        assert set(mgr._keyed_aggs["provider"]) == {"k1", "k2", OVERFLOW_METRICS_VALUE}
        assert mgr.snapshot(key="provider", value="k1")["saved"] == 80.0
        assert mgr.snapshot(key="provider", value="k2")["saved"] == 40.0
        assert mgr.snapshot(key="provider", value=OVERFLOW_METRICS_VALUE)["saved"] == 80.0  # k3 + k4
        assert mgr.snapshot(key="provider", value="k3") == {}
        assert sum("limit" in r.message for r in caplog.records) == 1  # warned once

    def test_max_metric_values_must_be_positive(self):
        with pytest.raises(ValueError):
            CompressionManager(max_metric_values=0)

    def test_metric_registered_after_bucket_is_backfilled(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        mgr.register_metric("saved", TotalSaved(sources="src1"))
        w.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))

        mgr.register_metric("input", TotalInput(sources="src1"))
        w.compress(_ctx(), req_id="r2", metrics_values=_pv("pA"))

        snap = mgr.snapshot(key="provider", value="pA")
        assert snap["saved"] == 80.0
        assert snap["input"] == 100.0  # rule existed only for the second call
        assert mgr.snapshot()["input"] == 100.0

    def test_failed_register_metric_not_mirrored(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        w.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        with pytest.raises(ValueError):
            mgr.register_metric("bad", TotalSaved(sources="missing"))
        assert mgr._specs == []
        assert mgr._keyed_aggs["provider"]["pA"]._rules == []

    def test_anchor_synced_to_existing_and_new_buckets(self):
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        mgr.register_metric("avg_saved_req", AvgSavedPerRequest(sources="src1"))

        w.compress(_ctx(), metrics_values=_pv("pA"))  # created before the anchor
        mgr.set_per_anchor("src1")
        w.compress(_ctx(), metrics_values=_pv("pA"))
        w.compress(_ctx(), metrics_values=_pv("pB"))  # created after the anchor

        assert mgr._keyed_aggs["provider"]["pA"]._anchor == "src1"
        assert mgr._keyed_aggs["provider"]["pB"]._anchor == "src1"
        # No req_ids → anchor observe_count is the denominator.
        assert mgr.snapshot(key="provider", value="pA")["avg_saved_req"] == pytest.approx(40.0)
        assert mgr.snapshot(key="provider", value="pB")["avg_saved_req"] == pytest.approx(40.0)

    def test_per_request_without_denominator_raises_for_bucket(self):
        """Existing aggregator behavior carries over to keyed snapshots."""
        mgr = CompressionManager()
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        mgr.register_metric("requests", RequestCount())
        w.compress(_ctx(), metrics_values=_pv("pA"))
        with pytest.raises(RuntimeError):
            mgr.snapshot(key="provider", value="pA")

    def test_sources_never_seen_under_bucket_are_filtered(self):
        """Pre-routing sources (no values) must not appear as zeros in a bucket's snapshot."""
        mgr = CompressionManager()
        pre = _reg(mgr, "pre", FakeCompressor("pre", tokens_before=200, tokens_after=100))
        post = _reg(mgr, "post", FakeCompressor("post", tokens_before=100, tokens_after=60))
        mgr.register_metric("pre.saved", TotalSaved(sources="pre"))
        mgr.register_metric("pre.ratio", CompressionRatio(sources="pre"))
        mgr.register_metric("pre.avg_req", AvgSavedPerRequest(sources="pre"))
        mgr.register_metric("post.saved", TotalSaved(sources="post"))
        mgr.register_metric("post.ratio", CompressionRatio(sources="post"))
        mgr.register_metric("overall.saved", TotalSaved(sources=["pre", "post"]))
        mgr.register_metric("overall.requests", RequestCount())

        pre.compress(_ctx(), req_id="r1")
        post.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))

        assert mgr.snapshot(key="provider", value="pA") == {
            "post.saved": 40.0,
            "post.ratio": pytest.approx(0.6),
            "overall.saved": 40.0,  # excludes the pre-routing source
            "overall.requests": 1.0,
        }
        assert mgr.snapshot(source="post", key="provider", value="pA") == {
            "post.saved": 40.0,
            "post.ratio": pytest.approx(0.6),
        }
        assert mgr.snapshot(source="pre", key="provider", value="pA") == {}
        assert mgr.snapshot()["overall.saved"] == 140.0

    def test_keyed_source_snapshot_ignores_metric_names(self):
        mgr = CompressionManager()
        w = _reg(mgr, "post", FakeCompressor("post", tokens_before=100, tokens_after=60))
        mgr.register_metric("saved_after_routing", TotalSaved(sources="post"))
        mgr.register_metric("requests", RequestCount())
        w.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))

        assert mgr.snapshot(source="post", key="provider", value="pA") == {"saved_after_routing": 40.0}
        assert mgr.snapshot(key="provider", value="pA") == {
            "saved_after_routing": 40.0,
            "requests": 1.0,
        }

    def test_value_sums_and_request_counts_add_up_to_global(self):
        mgr = CompressionManager()
        keys = ["provider", "user"]
        w1 = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60), keys)
        w2 = _reg(mgr, "src2", FakeCompressor("fake2", tokens_before=80, tokens_after=50), keys)
        mgr.register_metric("overall.saved", TotalSaved(sources=["src1", "src2"]))
        mgr.register_metric("overall.input", TotalInput(sources=["src1", "src2"]))
        mgr.register_metric("overall.calls", CallCount(sources=["src1", "src2"]))
        mgr.register_metric("overall.requests", RequestCount())

        plan = [("r1", "pA", "u1"), ("r2", "pB", "u2"), ("r3", "pA", "u2"),
                ("r4", "pC", "u1"), ("r5", "pB", "u3")]
        for req_id, provider, user in plan:
            values = {"provider": provider, "user": user}
            w1.compress(_ctx(), req_id=req_id, metrics_values=values)
            w2.compress(_ctx(), req_id=req_id, metrics_values=values)

        glob = mgr.snapshot()
        by_keys = mgr.snapshot_by_keys()
        assert set(by_keys["provider"]) == {"pA", "pB", "pC"}
        assert set(by_keys["user"]) == {"u1", "u2", "u3"}
        for key in keys:
            for name in ("overall.saved", "overall.input", "overall.calls", "overall.requests"):
                assert sum(snap[name] for snap in by_keys[key].values()) == glob[name]
        assert glob["overall.requests"] == 5.0

    def test_concurrent_keyed_compress(self):
        mgr = CompressionManager(max_metric_values=4)
        keys = ["provider", "user"]
        w1 = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=10, tokens_after=4), keys)
        w2 = _reg(mgr, "src2", FakeCompressor("fake2", tokens_before=10, tokens_after=7), keys)
        mgr.register_metric("saved", TotalSaved(sources=["src1", "src2"]))
        mgr.register_metric("requests", RequestCount())
        errors: list[BaseException] = []

        def worker(t: int) -> None:
            # Both sources hit each new bucket concurrently → racing registrations.
            w = w1 if t % 2 else w2
            try:
                for i in range(200):
                    values = {"provider": f"p{i % 8}", "user": f"u{i % 3}"}
                    w.compress(_ctx(), req_id=f"t{t}-{i}", metrics_values=values)
            except BaseException as exc:  # noqa: BLE001 - re-raised via assert
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        by_keys = mgr.snapshot_by_keys()
        assert len(by_keys["provider"]) == 5  # 4 values + overflow
        assert len(by_keys["user"]) == 3
        for key in keys:
            snaps = by_keys[key].values()
            assert sum(s["saved"] for s in snaps) == mgr.snapshot()["saved"] == 4 * 200 * (6 + 3)
            assert sum(s["requests"] for s in snaps) == 8 * 200


class TestKeyedLazyRegistration:
    def _rule_names(self, mgr, value, key="provider"):
        return {
            r.name for r in mgr._keyed_aggs[key][value]._rules if not getattr(r, "hidden", False)
        }

    def test_bucket_starts_with_source_agnostic_metrics_only(self):
        mgr = CompressionManager()
        w = _reg(mgr, "post", FakeCompressor("post"))
        _reg(mgr, "pre", FakeCompressor("pre"))
        mgr.register_metric("pre.saved", TotalSaved(sources="pre"))
        mgr.register_metric("post.saved", TotalSaved(sources="post"))
        mgr.register_metric("requests", RequestCount())

        w.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        assert self._rule_names(mgr, "pA") == {"post.saved", "requests"}
        assert mgr._keyed_sources["provider"]["pA"] == {"post"}

    def test_cross_source_metric_registered_once(self):
        mgr = CompressionManager()
        w1 = _reg(mgr, "src1", FakeCompressor("fake1", tokens_before=100, tokens_after=60))
        w2 = _reg(mgr, "src2", FakeCompressor("fake2", tokens_before=50, tokens_after=20))
        mgr.register_metric("overall.saved", TotalSaved(sources=["src1", "src2"]))
        mgr.register_metric("overall.ratio", CompressionRatio(sources=["src1", "src2"]))

        w1.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))  # registers overall.*
        w2.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))  # must not register again
        w1.compress(_ctx(), req_id="r2", metrics_values=_pv("pA"))

        snap = mgr.snapshot(key="provider", value="pA")
        assert snap["overall.saved"] == 110.0  # 40 + 30 + 40: no call before registration lost
        assert snap["overall.ratio"] == pytest.approx(140 / 250)

    def test_late_metric_only_added_to_buckets_with_its_source(self):
        mgr = CompressionManager()
        w1 = _reg(mgr, "src1", FakeCompressor("fake1"))
        w2 = _reg(mgr, "src2", FakeCompressor("fake2"))
        w1.compress(_ctx(), req_id="r1", metrics_values=_pv("pA"))
        w2.compress(_ctx(), req_id="r2", metrics_values=_pv("pB"))

        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("requests", RequestCount())
        assert self._rule_names(mgr, "pA") == {"src1.saved", "requests"}
        assert self._rule_names(mgr, "pB") == {"requests"}

    def test_overflow_bucket_registers_per_source(self):
        mgr = CompressionManager(max_metric_values=1)
        w1 = _reg(mgr, "src1", FakeCompressor("fake1"))
        w2 = _reg(mgr, "src2", FakeCompressor("fake2"))
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src2.saved", TotalSaved(sources="src2"))

        w1.compress(_ctx(), req_id="r1", metrics_values=_pv("k1"))
        w1.compress(_ctx(), req_id="r2", metrics_values=_pv("k2"))
        w2.compress(_ctx(), req_id="r3", metrics_values=_pv("k3"))
        assert mgr.snapshot(key="provider", value="k1") == {"src1.saved": 40.0}
        assert mgr.snapshot(key="provider", value=OVERFLOW_METRICS_VALUE) == {
            "src1.saved": 40.0,
            "src2.saved": 40.0,
        }


class TestKeyedReset:
    def _setup(self):
        mgr = CompressionManager(cache_size=8)
        f1 = FakeCompressor("fake1", tokens_before=100, tokens_after=60)
        f2 = FakeCompressor("fake2", tokens_before=90, tokens_after=30)
        w1 = _reg(mgr, "src1", f1, keys=["provider", "user"])
        w2 = _reg(mgr, "src2", f2, keys=["provider", "user"])
        mgr.register_metric("src1.saved", TotalSaved(sources="src1"))
        mgr.register_metric("src2.saved", TotalSaved(sources="src2"))
        for provider in ("pA", "pB"):
            values = {"provider": provider, "user": "alice"}
            w1.compress(_ctx(), req_id=f"{provider}-r", metrics_values=values)
            w2.compress(_ctx(), req_id=f"{provider}-r", metrics_values=values)
        f1._cache["k"] = "v"
        return mgr, f1

    def _snap(self, mgr, value, source=None, key="provider"):
        return mgr.snapshot(source=source, key=key, value=value)

    def test_full_reset_clears_global_and_keyed(self):
        mgr, _ = self._setup()
        mgr.reset()
        assert mgr.snapshot()["src1.saved"] == 0.0
        assert mgr.snapshot_by_keys() == {}
        assert self._snap(mgr, "pA") == {}
        assert mgr.cache_stats()["src1"]["currsize"] == 0

    def test_source_reset_clears_source_in_global_and_keyed(self):
        mgr, _ = self._setup()
        mgr.reset(source="src1")
        assert mgr.snapshot()["src1.saved"] == 0.0
        assert mgr.snapshot()["src2.saved"] == 120.0
        for value in ("pA", "pB"):
            # Registered metrics stay, as in the global snapshot.
            assert self._snap(mgr, value) == {"src1.saved": 0.0, "src2.saved": 60.0}
            assert self._snap(mgr, value, source="src1") == {"src1.saved": 0.0}
        assert self._snap(mgr, "alice", key="user") == {"src1.saved": 0.0, "src2.saved": 120.0}
        assert mgr.cache_stats()["src1"]["currsize"] == 0

    def test_bucket_reset_only_touches_that_bucket(self):
        mgr, _ = self._setup()
        mgr.reset(key="provider", value="pA")
        assert self._snap(mgr, "pA") == {}
        assert self._snap(mgr, "pB") == {"src1.saved": 40.0, "src2.saved": 60.0}
        assert self._snap(mgr, "alice", key="user") == {"src1.saved": 80.0, "src2.saved": 120.0}
        assert mgr.snapshot()["src1.saved"] == 80.0  # global untouched
        assert mgr.cache_stats()["src1"]["currsize"] == 1  # cache untouched

    def test_key_reset_clears_every_value_of_that_key(self):
        mgr, _ = self._setup()
        mgr.reset(key="provider")
        assert set(mgr.snapshot_by_keys()) == {"user"}
        assert mgr.snapshot()["src1.saved"] == 80.0
        assert mgr.cache_stats()["src1"]["currsize"] == 1

    def test_bucket_and_source_reset(self):
        mgr, _ = self._setup()
        mgr.reset(source="src1", key="provider", value="pA")
        assert self._snap(mgr, "pA") == {"src1.saved": 0.0, "src2.saved": 60.0}
        assert self._snap(mgr, "pB") == {"src1.saved": 40.0, "src2.saved": 60.0}
        assert mgr.snapshot()["src1.saved"] == 80.0
        assert mgr.cache_stats()["src1"]["currsize"] == 1

    def test_key_and_source_reset(self):
        mgr, _ = self._setup()
        mgr.reset(source="src1", key="provider")
        for value in ("pA", "pB"):
            assert self._snap(mgr, value) == {"src1.saved": 0.0, "src2.saved": 60.0}
        assert self._snap(mgr, "alice", key="user") == {"src1.saved": 80.0, "src2.saved": 120.0}
        assert mgr.snapshot()["src1.saved"] == 80.0

    def test_reset_rearms_overflow_warning(self, caplog):
        mgr = CompressionManager(max_metric_values=1)
        w = _reg(mgr, "src1", FakeCompressor("fake1"))
        mgr.register_metric("saved", TotalSaved(sources="src1"))

        def overflow_warnings() -> int:
            return sum("limit" in r.message for r in caplog.records)

        def send(req_id: str, value: str) -> None:
            w.compress(_ctx(), req_id=req_id, metrics_values=_pv(value))

        with caplog.at_level("WARNING", logger="adaptive_token_compressor.core.manager"):
            send("r1", "k1")
            send("r2", "k2")
            send("r3", "k3")
            assert overflow_warnings() == 1

            mgr.reset(key="provider", value="k1")  # bucket-only reset keeps the flag
            send("r4", "k4")
            assert overflow_warnings() == 1

            mgr.reset(key="provider")  # whole key gone → rearmed
            send("r5", "k1")
            send("r6", "k2")
            assert overflow_warnings() == 2

            mgr.reset()
            send("r7", "k1")
            send("r8", "k2")
            assert overflow_warnings() == 3

    def test_bucket_with_every_source_reset_reads_empty(self):
        mgr, _ = self._setup()
        mgr.register_metric("requests", RequestCount())
        mgr.reset(source="src1")
        mgr.reset(source="src2")
        # Only RequestCount with no denominator would remain; no data → {}.
        assert self._snap(mgr, "pA") == {}
        assert mgr.snapshot_by_keys() == {}

    def test_bucket_reused_after_reset(self):
        mgr, _ = self._setup()
        mgr.reset()
        mgr["src1"].compress(_ctx(), req_id="r9", metrics_values=_pv("pA"))
        assert self._snap(mgr, "pA") == {"src1.saved": 40.0}
