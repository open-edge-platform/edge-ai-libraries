"""Manager + Aggregator + HarnessCompressor end-to-end integration.

Mirrors the public-API usage from `ttt.py` (router-side client code) but
limited to the harness compressor:

  mgr = CompressionManager(...)
  hp = mgr.register_compressor("harness", HarnessCompressor(...))
  mgr.register_metric(...)
  mgr.check_backends()
  for each request:
      r = hp.compress(ctx, req_id=...)
  mgr.snapshot()

These tests exercise the real wiring (no monkeypatch on manager / aggregator)
and only stub the lingua HTTP backend so they run without a server.
"""
from __future__ import annotations

import pytest

from adaptive_token_compressor import (
    AvgDurationPerCall,
    AvgSavedPerRequest,
    CallCount,
    CompressionContext,
    CompressionManager,
    CompressionRatio,
    TotalSaved,
)
from adaptive_token_compressor.core.backends import NoopBackend
from adaptive_token_compressor.core.health import HealthState
from adaptive_token_compressor.harness import HarnessCompressor


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


class FakeBackend:
    """Stable fake: keeps first 1/3 of text + a tag so tokens drop predictably."""

    cache_tag = "lingua"

    def __init__(self, suffix: str = " [c]") -> None:
        self._suffix = suffix
        self.call_count = 0

    def compress(
        self,
        text: str,
        *,
        rate: float,
        force_tokens: list[str] | None = None,
        force_reserve_digit: bool = False,
        digit_neighbor_radius: int = 0,
    ) -> str:
        self.call_count += 1
        return text[: max(10, len(text) // 3)] + self._suffix

    def health_check(self, *, timeout: float = 5.0):
        from adaptive_token_compressor.core.health import HealthStatus
        return HealthStatus.healthy("fake_backend")


def _long_system_prompt(n_chars: int = 1500) -> str:
    body = (
        "The quick brown fox jumps over the lazy dog. "
        "LLMLingua-2 is a token compression model based on BERT. "
    ) * (n_chars // 100 + 1)
    return body[:n_chars]


def _ctx(content: str) -> CompressionContext:
    return CompressionContext(
        messages=[{"role": "system", "content": content}],
        tools=None,
    )


def _build_manager_no_per_request(compressor: HarnessCompressor):
    """Register harness + non-PerRequest metrics. Used by tests that don't
    exercise the PerRequest denominator path."""
    mgr = CompressionManager()
    hp = mgr.register_compressor("harness", compressor)
    mgr.register_metric("harness_calls", CallCount(sources="harness"))
    mgr.register_metric("harness_ratio", CompressionRatio(sources="harness"))
    mgr.register_metric("harness_avg_dur", AvgDurationPerCall(sources="harness"))
    mgr.register_metric("harness_total_saved", TotalSaved(sources="harness"))
    return mgr, hp


# ─────────────────────────────────────────────────────────────────────────────
# Registration & wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_returns_wrapper_with_inner(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        mgr = CompressionManager()
        wrapper = mgr.register_compressor("harness", comp)

        assert wrapper.name == "harness"
        assert wrapper.inner is comp
        assert mgr["harness"] is wrapper

    def test_set_cache_was_called_by_register(self, monkeypatch):
        """Registration must inject (cache, lock) via HarnessCompressor.set_cache."""
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        assert comp._cache is None  # unset before registration

        mgr = CompressionManager(cache_size=64)
        mgr.register_compressor("harness", comp)

        assert comp._cache is not None
        assert comp._cache_lock is not None
        assert comp._cache.maxsize == 64

    def test_double_register_raises(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        mgr = CompressionManager()
        mgr.register_compressor("harness", comp)
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_compressor("harness", comp)


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper compress → aggregator observe
# ─────────────────────────────────────────────────────────────────────────────


class TestWrapperCompress:
    def test_compress_through_wrapper_records_into_aggregator(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        mgr, hp = _build_manager_no_per_request(comp)

        snap_before = mgr.snapshot()
        assert snap_before["harness_calls"] == 0
        assert snap_before["harness_ratio"] == 0.0
        assert snap_before["harness_total_saved"] == 0

        ctx = _ctx(_long_system_prompt(1500))
        result = hp.compress(ctx, req_id="req-1")

        # CompressorResult is the raw inner output — wrapper does NOT mutate.
        assert result.metrics.tokens_before > 0
        assert result.metrics.tokens_after > 0
        assert result.metrics.tokens_after < result.metrics.tokens_before

        snap = mgr.snapshot()
        assert snap["harness_calls"] == 1
        assert 0.0 < snap["harness_ratio"] < 1.0
        assert snap["harness_total_saved"] > 0
        assert snap["harness_avg_dur"] > 0

    def test_inner_compress_call_signature_matches_baseCompressor(self, monkeypatch):
        """Wrapper must NOT pass req_id into inner.compress (BaseCompressor
        signature is compress(ctx) only)."""
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())
        mgr, hp = _build_manager_no_per_request(comp)

        observed_kwargs: dict = {}
        original = comp.compress

        def spy(ctx, **kwargs):
            observed_kwargs.update(kwargs)
            return original(ctx)

        monkeypatch.setattr(comp, "compress", spy)
        hp.compress(_ctx("Short prompt"), req_id="req-X")

        assert "req_id" not in observed_kwargs


# ─────────────────────────────────────────────────────────────────────────────
# AvgSavedPerRequest — two denominator paths
# ─────────────────────────────────────────────────────────────────────────────


class TestPerRequestViaAnchor:
    """Anchor fallback: `mgr.set_per_anchor("harness")` → denominator = anchor's
    CallCount. Used when caller can't thread req_id through compress()."""

    def test_three_compress_calls_no_req_id(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        mgr = CompressionManager()
        hp = mgr.register_compressor("harness", comp)
        mgr.set_per_anchor("harness")
        mgr.register_metric("calls", CallCount(sources="harness"))
        mgr.register_metric("saved", TotalSaved(sources="harness"))
        mgr.register_metric(
            "avg_saved_per_req", AvgSavedPerRequest(sources="harness")
        )

        for i in range(3):
            # Critical: NO req_id — anchor fallback supplies the denominator.
            hp.compress(_ctx(_long_system_prompt(1500) + f" #{i}"))

        snap = mgr.snapshot()
        assert snap["calls"] == 3
        # Denominator = anchor source's CallCount = 3.
        assert abs(snap["avg_saved_per_req"] - snap["saved"] / 3) < 1e-6

    def test_per_request_without_anchor_or_req_id_raises_at_snapshot(
        self, monkeypatch
    ):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())

        mgr = CompressionManager()
        mgr.register_compressor("harness", comp)
        # Registration succeeds; the missing-denominator error surfaces at
        # snapshot() instead.
        mgr.register_metric(
            "avg_saved_per_req", AvgSavedPerRequest(sources="harness")
        )
        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            mgr.snapshot()


class TestPerRequestViaReqId:
    """req_id path: aggregator dedups `_seen_req_ids`; denominator = its size."""

    def test_three_distinct_req_ids(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        mgr = CompressionManager()
        hp = mgr.register_compressor("harness", comp)

        # Seed _seen_req_ids before registering the PerRequest metric so the
        # register-time denominator check passes. The seed call hits min_chars
        # skip (cheap) but still calls aggregator.observe with req_id.
        hp.compress(_ctx("seed"), req_id="seed-id")

        mgr.register_metric("calls", CallCount(sources="harness"))
        mgr.register_metric("saved", TotalSaved(sources="harness"))
        mgr.register_metric(
            "avg_saved_per_req", AvgSavedPerRequest(sources="harness")
        )

        # Reset clears buckets AND _seen_req_ids; the registered metrics
        # remain. After this the loop below is the only contributor.
        mgr.reset()

        for i in range(3):
            hp.compress(
                _ctx(_long_system_prompt(1500) + f" #{i}"),
                req_id=f"chatcmpl-{i:03d}",
            )

        snap = mgr.snapshot()
        assert snap["calls"] == 3
        # Three distinct req_ids → denominator = 3.
        assert abs(snap["avg_saved_per_req"] - snap["saved"] / 3) < 1e-6

    def test_repeated_req_id_dedups_denominator(self, monkeypatch):
        """Same req_id observed twice ⇒ unique-set size 1, not 2."""
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        mgr = CompressionManager()
        hp = mgr.register_compressor("harness", comp)
        hp.compress(_ctx("seed"), req_id="seed-id")
        mgr.register_metric("calls", CallCount(sources="harness"))
        mgr.register_metric("saved", TotalSaved(sources="harness"))
        mgr.register_metric(
            "avg_saved_per_req", AvgSavedPerRequest(sources="harness")
        )
        mgr.reset()

        # Two compresses with the SAME req_id.
        hp.compress(_ctx(_long_system_prompt(1500)), req_id="same-id")
        hp.compress(_ctx(_long_system_prompt(1500) + " mod"), req_id="same-id")

        snap = mgr.snapshot()
        # CallCount counts every observe.
        assert snap["calls"] == 2
        # Denominator is unique req_ids (1) → PerRequest = total_saved.
        assert abs(snap["avg_saved_per_req"] - snap["saved"]) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Cache slot wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheWiring:
    def test_second_call_byte_identical_via_manager_cache(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        fake = FakeBackend()
        monkeypatch.setattr(comp, "_backend", fake)
        mgr, hp = _build_manager_no_per_request(comp)

        ctx = _ctx(_long_system_prompt(1500))
        r1 = hp.compress(ctx, req_id="req-1")
        first_calls = fake.call_count
        r2 = hp.compress(ctx, req_id="req-2")

        # Cache injected by manager → second call hits, backend not re-invoked.
        assert fake.call_count == first_calls
        assert r2.metrics.details["cache_hits"] >= 1
        # Byte-identical compressed messages.
        assert r1.messages[0]["content"] == r2.messages[0]["content"]

    def test_cache_stats_reflects_writes(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        mgr, hp = _build_manager_no_per_request(comp)

        # Force at least one cache write.
        hp.compress(_ctx(_long_system_prompt(1500)), req_id="req-1")

        stats = mgr.cache_stats()
        assert "harness" in stats
        assert stats["harness"]["currsize"] >= 1
        assert stats["harness"]["maxsize"] == 4096

    def test_reset_clears_aggregator_and_caches(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())
        mgr, hp = _build_manager_no_per_request(comp)

        hp.compress(_ctx(_long_system_prompt(1500)), req_id="req-1")
        assert mgr.snapshot()["harness_calls"] == 1
        assert mgr.cache_stats()["harness"]["currsize"] >= 1

        mgr.reset()
        assert mgr.snapshot()["harness_calls"] == 0
        assert mgr.cache_stats()["harness"]["currsize"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Health check forwarding
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_check_backends_passes_for_healthy_backend(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())
        mgr, _ = _build_manager_no_per_request(comp)

        # Should not raise.
        mgr.check_backends(timeout=2.0)

    def test_wrapper_health_check_forwards_to_inner(self, monkeypatch):
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", NoopBackend())
        mgr, hp = _build_manager_no_per_request(comp)

        status = hp.health_check(timeout=2.0)
        assert status.state is HealthState.HEALTHY


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end smoke (mirrors ttt.py shape)
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndShape:
    def test_full_workflow_like_ttt(self, monkeypatch):
        """Full register → check_backends → compress loop → snapshot.

        Mirrors ttt.py shape: register compressor, set anchor, declare metrics,
        check backends, run a request loop with req_id, read snapshot.
        """
        comp = HarnessCompressor(profile="generic", compress_min_chars=100)
        monkeypatch.setattr(comp, "_backend", FakeBackend())

        mgr = CompressionManager()
        hp = mgr.register_compressor("harness", comp)
        mgr.set_per_anchor("harness")  # PerRequest fallback denominator
        mgr.check_backends(timeout=2.0)

        mgr.register_metric("ratio", CompressionRatio(sources="harness"))
        mgr.register_metric("avg_dur", AvgDurationPerCall(sources="harness"))
        mgr.register_metric("saved", TotalSaved(sources="harness"))
        mgr.register_metric(
            "avg_saved_per_req", AvgSavedPerRequest(sources="harness")
        )

        # Three distinct requests with req_id; once req_ids are seen the
        # aggregator switches denominator from anchor count to len(_seen_req_ids)
        # — both are 3 here so the snapshot value is the same either way.
        for i in range(3):
            ctx = _ctx(_long_system_prompt(1500) + f" #{i}")
            hp.compress(ctx, req_id=f"chatcmpl-{i:03d}")

        snap = mgr.snapshot()

        assert set(snap.keys()) == {
            "ratio",
            "avg_dur",
            "saved",
            "avg_saved_per_req",
        }
        assert 0.0 < snap["ratio"] < 1.0
        assert snap["avg_dur"] > 0
        assert snap["saved"] > 0
        assert (
            abs(snap["avg_saved_per_req"] - snap["saved"] / 3) < 1e-6
        )
