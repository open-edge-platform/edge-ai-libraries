"""Tests for core/aggregator.py — covers plan §13 row `core/aggregator`."""
from __future__ import annotations

import random
import threading

import pytest

from adaptive_token_compressor.core.aggregator import (
    AvgDurationPerCall,
    AvgDurationPerRequest,
    AvgInputPerCall,
    AvgInputPerRequest,
    AvgOutputPerCall,
    AvgOutputPerRequest,
    AvgSavedPerCall,
    AvgSavedPerRequest,
    CallCount,
    CompressionRatio,
    MetricsAggregator,
    RequestCount,
    TotalDuration,
    TotalInput,
    TotalOutput,
    TotalSaved,
    _to_set,
)
from adaptive_token_compressor.core.metrics import CompressorMetrics, CompressionScope


# ─────────────────────────────────────────────────────────────────────────────
# Helper: create CompressorMetrics
# ─────────────────────────────────────────────────────────────────────────────


def _metrics(
    tokens_before: int = 100,
    tokens_after: int = 60,
    duration_ms: float = 10.0,
) -> CompressorMetrics:
    return CompressorMetrics(
        name="test",
        scope=CompressionScope.HARNESS,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        duration_ms=duration_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _to_set helper
# ─────────────────────────────────────────────────────────────────────────────


class TestToSet:
    def test_string_to_frozenset(self):
        assert _to_set("harness") == frozenset(["harness"])

    def test_list_to_frozenset(self):
        assert _to_set(["harness", "tools"]) == frozenset(["harness", "tools"])

    def test_empty_list(self):
        assert _to_set([]) == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — rule injection validation
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorRuleValidation:
    def test_add_sum_invalid_field_raises(self):
        agg = MetricsAggregator()
        with pytest.raises(ValueError, match="Invalid field"):
            agg._add_sum("test", "invalid_field", ["harness"])

    def test_add_sum_duplicate_name_raises(self):
        agg = MetricsAggregator()
        agg._add_sum("total", "tokens_before", ["harness"])
        with pytest.raises(ValueError, match="Duplicate rule name"):
            agg._add_sum("total", "tokens_after", ["tools"])

    def test_add_count_duplicate_name_raises(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        with pytest.raises(ValueError, match="Duplicate rule name"):
            agg._add_count("calls", ["tools"])

    def test_add_ratio_unknown_numerator_raises(self):
        agg = MetricsAggregator()
        agg._add_sum("den", "tokens_before", ["harness"])
        with pytest.raises(ValueError, match="numerator.*unknown bucket"):
            agg._add_ratio("ratio", "unknown_num", "den")

    def test_add_ratio_unknown_denominator_raises(self):
        agg = MetricsAggregator()
        agg._add_sum("num", "tokens_after", ["harness"])
        with pytest.raises(ValueError, match="denominator.*unknown bucket"):
            agg._add_ratio("ratio", "num", "unknown_den")

    def test_add_request_ratio_unknown_numerator_raises(self):
        agg = MetricsAggregator()
        with pytest.raises(ValueError, match="numerator.*unknown bucket"):
            agg._add_request_ratio("avg", "unknown_num")


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — observe + snapshot (engine behavior)
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorObserve:
    def test_sum_rule_accumulates(self):
        agg = MetricsAggregator()
        agg._add_sum("total_in", "tokens_before", ["harness"])
        agg.observe("harness", _metrics(tokens_before=100))
        agg.observe("harness", _metrics(tokens_before=50))
        assert agg.snapshot() == {"total_in": 150.0}

    def test_sum_rule_skips_non_matching_source(self):
        agg = MetricsAggregator()
        agg._add_sum("total_in", "tokens_before", ["harness"])
        agg.observe("tools", _metrics(tokens_before=100))
        assert agg.snapshot() == {"total_in": 0.0}

    def test_count_rule_increments(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        agg.observe("harness", _metrics())
        agg.observe("harness", _metrics())
        assert agg.snapshot() == {"calls": 2.0}

    def test_count_rule_skips_non_matching_source(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        agg.observe("tools", _metrics())
        assert agg.snapshot() == {"calls": 0.0}

    def test_ratio_rule_computed_at_snapshot(self):
        agg = MetricsAggregator()
        agg._add_sum("num", "tokens_after", ["harness"])
        agg._add_sum("den", "tokens_before", ["harness"])
        agg._add_ratio("ratio", "num", "den")
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=40))
        # ratio = (60+40) / (100+100) = 100 / 200 = 0.5
        assert agg.snapshot()["ratio"] == 0.5

    def test_ratio_rule_returns_zero_when_denominator_zero(self):
        agg = MetricsAggregator()
        agg._add_sum("num", "tokens_after", ["harness"])
        agg._add_sum("den", "tokens_before", ["harness"])
        agg._add_ratio("ratio", "num", "den")
        # No observations → den=0
        assert agg.snapshot()["ratio"] == 0.0

    def test_hidden_buckets_excluded_from_snapshot(self):
        agg = MetricsAggregator()
        agg._add_sum("visible", "tokens_before", ["harness"])
        agg._add_sum("__hidden", "tokens_after", ["harness"], hidden=True)
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        snap = agg.snapshot()
        assert "visible" in snap
        assert "__hidden" not in snap

    def test_multi_source_sum_rule(self):
        agg = MetricsAggregator()
        agg._add_sum("total", "tokens_before", ["harness", "tools"])
        agg.observe("harness", _metrics(tokens_before=100))
        agg.observe("tools", _metrics(tokens_before=50))
        agg.observe("context", _metrics(tokens_before=30))  # not in sources
        assert agg.snapshot()["total"] == 150.0


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — req_id tracking
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorReqId:
    def test_observe_with_req_id_adds_to_seen(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="req1")
        assert agg.request_count() == 1

    def test_observe_same_req_id_twice_deduped(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="req1")
        agg.observe("tools", _metrics(), req_id="req1")
        assert agg.request_count() == 1

    def test_observe_different_req_ids(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="req1")
        agg.observe("harness", _metrics(), req_id="req2")
        assert agg.request_count() == 2

    def test_observe_without_req_id_does_not_affect_count(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics())
        agg.observe("harness", _metrics())
        # No req_id seen, no anchor set → count=0
        assert agg.request_count() == 0

    def test_reset_clears_seen_req_ids(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="req1")
        assert agg.request_count() == 1
        agg.reset()
        assert agg.request_count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — anchor fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorAnchor:
    def test_set_anchor_fallback_for_request_count(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        agg._set_anchor("harness")
        agg.observe("harness", _metrics())
        agg.observe("harness", _metrics())
        # No req_id seen → fallback to anchor count
        assert agg.request_count() == 2

    def test_set_anchor_idempotent_same_source(self):
        agg = MetricsAggregator()
        agg._set_anchor("harness")
        agg._set_anchor("harness")  # No error

    def test_set_anchor_raises_on_different_source(self):
        agg = MetricsAggregator()
        agg._set_anchor("harness")
        with pytest.raises(RuntimeError, match="Anchor already set"):
            agg._set_anchor("tools")

    def test_req_id_takes_precedence_over_anchor(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        agg._set_anchor("harness")
        agg.observe("harness", _metrics())
        agg.observe("harness", _metrics())
        agg.observe("harness", _metrics(), req_id="req1")
        # req_id seen → request_count = 1 (not 3 from anchor)
        assert agg.request_count() == 1

    def test_has_denominator_false_when_neither_set(self):
        agg = MetricsAggregator()
        assert agg._has_denominator() is False

    def test_has_denominator_true_with_req_id(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="req1")
        assert agg._has_denominator() is True

    def test_has_denominator_true_with_anchor(self):
        agg = MetricsAggregator()
        agg._set_anchor("harness")
        assert agg._has_denominator() is True


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — request_ratio rule
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorRequestRatioRule:
    def test_request_ratio_divides_by_req_id_count(self):
        agg = MetricsAggregator()
        agg._add_sum("saved", "saved_tokens", ["harness"])
        agg._add_request_ratio("avg_per_req", "saved")
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60), req_id="r1")
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=50), req_id="r2")
        # saved = 40 + 50 = 90; requests = 2; avg = 45.0
        assert agg.snapshot()["avg_per_req"] == 45.0

    def test_request_ratio_raises_when_no_denominator(self):
        agg = MetricsAggregator()
        agg._add_sum("saved", "saved_tokens", ["harness"])
        agg._add_request_ratio("avg_per_req", "saved")
        # No req_id, no anchor → snapshot raises (denominator undefined).
        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            agg.snapshot()

    def test_request_ratio_uses_anchor_fallback(self):
        agg = MetricsAggregator()
        agg._add_count("calls", ["harness"])
        agg._add_sum("saved", "saved_tokens", ["harness"])
        agg._set_anchor("harness")
        agg._add_request_ratio("avg_per_req", "saved")
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=50))
        # saved = 40 + 50 = 90; anchor count = 2; avg = 45.0
        assert agg.snapshot()["avg_per_req"] == 45.0


# ─────────────────────────────────────────────────────────────────────────────
# MetricsAggregator — reset
# ─────────────────────────────────────────────────────────────────────────────


class TestAggregatorReset:
    def test_reset_clears_buckets(self):
        agg = MetricsAggregator()
        agg._add_sum("total", "tokens_before", ["harness"])
        agg.observe("harness", _metrics(tokens_before=100))
        assert agg.snapshot()["total"] == 100.0
        agg.reset()
        assert agg.snapshot()["total"] == 0.0

    def test_reset_preserves_rules(self):
        agg = MetricsAggregator()
        agg._add_sum("total", "tokens_before", ["harness"])
        agg.reset()
        agg.observe("harness", _metrics(tokens_before=50))
        assert agg.snapshot()["total"] == 50.0

    def test_reset_source_only_clears_that_source(self):
        agg = MetricsAggregator()
        agg._add_sum("src1.total_in", "tokens_before", ["src1"])
        agg._add_sum("src2.total_in", "tokens_before", ["src2"])
        agg.observe("src1", _metrics(tokens_before=100))
        agg.observe("src2", _metrics(tokens_before=70))

        assert agg.snapshot(source="src1")["src1.total_in"] == 100.0
        assert agg.snapshot(source="src2")["src2.total_in"] == 70.0

        agg.reset(source="src1")
        assert agg.snapshot(source="src1")["src1.total_in"] == 0.0
        assert agg.snapshot(source="src2")["src2.total_in"] == 70.0

    def test_snapshot_source_filters_to_source_prefixed_metrics(self):
        agg = MetricsAggregator()
        agg._add_sum("src1.total_in", "tokens_before", ["src1"])
        agg._add_sum("overall.total_in", "tokens_before", ["src1", "src2"])
        agg.observe("src1", _metrics(tokens_before=123))

        snap = agg.snapshot(source="src1")
        assert "src1.total_in" in snap
        assert "overall.total_in" not in snap

    def test_global_snapshot_rebuilds_after_source_reset(self):
        agg = MetricsAggregator()
        agg._add_sum("overall.saved", "saved_tokens", ["src1", "src2"])

        agg.observe("src1", _metrics(tokens_before=100, tokens_after=70), req_id="r1")
        agg.observe("src2", _metrics(tokens_before=100, tokens_after=50), req_id="r1")
        assert agg.snapshot()["overall.saved"] == 80.0

        agg.reset(source="src1")
        agg.observe("src2", _metrics(tokens_before=90, tokens_after=30), req_id="r2")

        snap = agg.snapshot()
        assert snap["overall.saved"] == 110.0

    def test_global_ratio_rebuilds_correctly_after_source_reset(self):
        agg = MetricsAggregator()
        CompressionRatio(sources=["src1", "src2"])._emit_rules("overall.ratio", agg)

        agg.observe("src1", _metrics(tokens_before=100, tokens_after=40), req_id="r1")
        agg.observe("src2", _metrics(tokens_before=200, tokens_after=100), req_id="r1")
        assert agg.snapshot()["overall.ratio"] == pytest.approx(140 / 300, abs=0.001)

        agg.reset(source="src1")
        snap = agg.snapshot()
        assert snap["overall.ratio"] == pytest.approx(0.5, abs=0.001)

    def test_global_avg_duration_per_request_rebuilds_after_source_reset(self):
        agg = MetricsAggregator()
        AvgDurationPerRequest(sources=["src1", "src2"])._emit_rules(
            "overall.avg_dur_req", agg
        )

        agg.observe("src1", _metrics(duration_ms=10.0), req_id="r1")
        agg.observe("src2", _metrics(duration_ms=20.0), req_id="r1")
        agg.observe("src1", _metrics(duration_ms=30.0), req_id="r2")
        agg.observe("src2", _metrics(duration_ms=40.0), req_id="r2")
        assert agg.snapshot()["overall.avg_dur_req"] == pytest.approx(50.0, abs=0.001)

        agg.reset(source="src1")
        snap = agg.snapshot()
        assert snap["overall.avg_dur_req"] == pytest.approx(30.0, abs=0.001)

    def test_request_count_union_updates_after_source_reset(self):
        agg = MetricsAggregator()
        agg.observe("src1", _metrics(), req_id="r1")
        agg.observe("src1", _metrics(), req_id="r2")
        agg.observe("src2", _metrics(), req_id="r2")
        agg.observe("src2", _metrics(), req_id="r3")
        assert agg.request_count() == 3

        agg.reset(source="src1")
        assert agg.request_count() == 2

    def test_source_snapshot_includes_derived_metrics(self):
        agg = MetricsAggregator()
        CompressionRatio(sources="src1")._emit_rules("src1.ratio", agg)
        AvgSavedPerCall(sources="src1")._emit_rules("src1.avg_saved_call", agg)
        AvgSavedPerRequest(sources="src1")._emit_rules("src1.avg_saved_req", agg)

        agg.observe("src1", _metrics(tokens_before=100, tokens_after=60), req_id="r1")
        agg.observe("src1", _metrics(tokens_before=100, tokens_after=50), req_id="r2")

        snap = agg.snapshot(source="src1")
        assert snap["src1.ratio"] == pytest.approx(0.55, abs=0.001)
        assert snap["src1.avg_saved_call"] == pytest.approx(45.0, abs=0.001)
        assert snap["src1.avg_saved_req"] == pytest.approx(45.0, abs=0.001)

    def test_source_snapshot_after_other_source_observe_while_global_dirty(self):
        agg = MetricsAggregator()
        TotalSaved(sources="src1")._emit_rules("src1.saved", agg)
        TotalSaved(sources="src2")._emit_rules("src2.saved", agg)

        agg.observe("src1", _metrics(tokens_before=100, tokens_after=60), req_id="r1")
        agg.observe("src2", _metrics(tokens_before=100, tokens_after=50), req_id="r1")
        agg.reset(source="src1")
        agg.observe("src2", _metrics(tokens_before=90, tokens_after=30), req_id="r2")

        snap = agg.snapshot(source="src2")
        assert snap["src2.saved"] == 110.0


# ─────────────────────────────────────────────────────────────────────────────
# MetricSpec — 14 dataclasses expansion
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricSpecExpansion:
    def test_call_count_emits_one_count_rule(self):
        agg = MetricsAggregator()
        CallCount(sources="harness")._emit_rules("calls", agg)
        agg.observe("harness", _metrics())
        assert agg.snapshot()["calls"] == 1.0

    def test_total_input_emits_one_sum_rule(self):
        agg = MetricsAggregator()
        TotalInput(sources="harness")._emit_rules("total_in", agg)
        agg.observe("harness", _metrics(tokens_before=100))
        assert agg.snapshot()["total_in"] == 100.0

    def test_total_output_emits_one_sum_rule(self):
        agg = MetricsAggregator()
        TotalOutput(sources="harness")._emit_rules("total_out", agg)
        agg.observe("harness", _metrics(tokens_after=60))
        assert agg.snapshot()["total_out"] == 60.0

    def test_total_saved_emits_one_sum_rule(self):
        agg = MetricsAggregator()
        TotalSaved(sources="harness")._emit_rules("total_saved", agg)
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        assert agg.snapshot()["total_saved"] == 40.0

    def test_total_duration_emits_one_sum_rule(self):
        agg = MetricsAggregator()
        TotalDuration(sources="harness")._emit_rules("total_dur", agg)
        agg.observe("harness", _metrics(duration_ms=10.0))
        assert agg.snapshot()["total_dur"] == 10.0

    def test_compression_ratio_emits_hidden_buckets_plus_ratio(self):
        agg = MetricsAggregator()
        CompressionRatio(sources="harness")._emit_rules("ratio", agg)
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        snap = agg.snapshot()
        assert snap["ratio"] == 0.6
        # Hidden buckets not in snapshot
        assert "__ratio_in" not in snap
        assert "__ratio_out" not in snap

    def test_avg_saved_per_call_emits_hidden_sum_count_ratio(self):
        agg = MetricsAggregator()
        AvgSavedPerCall(sources="harness")._emit_rules("avg_saved", agg)
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60))
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=50))
        # saved = 40 + 50 = 90; calls = 2; avg = 45.0
        assert agg.snapshot()["avg_saved"] == 45.0

    def test_avg_duration_per_call(self):
        agg = MetricsAggregator()
        AvgDurationPerCall(sources="harness")._emit_rules("avg_dur", agg)
        agg.observe("harness", _metrics(duration_ms=10.0))
        agg.observe("harness", _metrics(duration_ms=20.0))
        # total_dur = 30.0; calls = 2; avg = 15.0
        assert agg.snapshot()["avg_dur"] == 15.0

    def test_avg_input_per_call(self):
        agg = MetricsAggregator()
        AvgInputPerCall(sources="harness")._emit_rules("avg_in", agg)
        agg.observe("harness", _metrics(tokens_before=100))
        agg.observe("harness", _metrics(tokens_before=200))
        # total_in = 300; calls = 2; avg = 150.0
        assert agg.snapshot()["avg_in"] == 150.0

    def test_avg_output_per_call(self):
        agg = MetricsAggregator()
        AvgOutputPerCall(sources="harness")._emit_rules("avg_out", agg)
        agg.observe("harness", _metrics(tokens_after=60))
        agg.observe("harness", _metrics(tokens_after=80))
        # total_out = 140; calls = 2; avg = 70.0
        assert agg.snapshot()["avg_out"] == 70.0

    def test_avg_saved_per_request_requires_denominator(self):
        # Registration (_emit_rules) no longer raises — the check is deferred
        # to snapshot(), where req_id / anchor are fully determined.
        agg = MetricsAggregator()
        AvgSavedPerRequest(sources="harness")._emit_rules("avg_per_req", agg)
        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            agg.snapshot()

    def test_avg_saved_per_request_with_req_id(self):
        agg = MetricsAggregator()
        agg.observe("harness", _metrics(), req_id="r1")  # Establish req_id
        AvgSavedPerRequest(sources="harness")._emit_rules("avg_per_req", agg)
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=60), req_id="r1")
        agg.observe("harness", _metrics(tokens_before=100, tokens_after=50), req_id="r2")
        # saved = 40 + 50 = 90; requests = 2; avg = 45.0
        assert agg.snapshot()["avg_per_req"] == 45.0

    def test_avg_duration_per_request_with_anchor(self):
        agg = MetricsAggregator()
        agg._set_anchor("harness")
        AvgDurationPerRequest(sources="harness")._emit_rules("avg_dur_req", agg)
        agg.observe("harness", _metrics(duration_ms=10.0))
        agg.observe("harness", _metrics(duration_ms=20.0))
        # total_dur = 30.0; anchor_count = 2; avg = 15.0
        assert agg.snapshot()["avg_dur_req"] == 15.0

    def test_avg_input_per_request(self):
        agg = MetricsAggregator()
        agg.observe("h", _metrics(), req_id="r1")
        AvgInputPerRequest(sources="h")._emit_rules("avg_in_req", agg)
        agg.observe("h", _metrics(tokens_before=100), req_id="r1")
        agg.observe("h", _metrics(tokens_before=200), req_id="r2")
        # total_in = 300; requests = 2; avg = 150.0
        assert agg.snapshot()["avg_in_req"] == 150.0

    def test_avg_output_per_request(self):
        agg = MetricsAggregator()
        agg.observe("h", _metrics(), req_id="r1")
        AvgOutputPerRequest(sources="h")._emit_rules("avg_out_req", agg)
        agg.observe("h", _metrics(tokens_after=60), req_id="r1")
        agg.observe("h", _metrics(tokens_after=80), req_id="r2")
        # total_out = 140; requests = 2; avg = 70.0
        assert agg.snapshot()["avg_out_req"] == 70.0


# ─────────────────────────────────────────────────────────────────────────────
# 3-request fixture walkthrough (plan §3.5 table)
# ─────────────────────────────────────────────────────────────────────────────


class TestParallelMultiSourceScenario:
    """Test parallel multi-source compression (router real-world scenario).

    harness/tools/context process different fields of the same request:
    - harness: compresses system/developer messages
    - tools: compresses tools schema
    - context: compresses user/assistant/tool messages
    """

    def test_parallel_three_compressors_end_to_end(self):
        """Full end-to-end test with harness + tools + context in parallel."""
        agg = MetricsAggregator()
        agg._set_anchor("harness")

        # Register metrics for parallel compression
        CompressionRatio(sources=["harness", "tools", "context"])._emit_rules("ratio_total", agg)
        TotalSaved(sources=["harness", "tools", "context"])._emit_rules("saved_total", agg)
        AvgSavedPerRequest(sources=["harness", "tools", "context"])._emit_rules("avg_saved_req", agg)

        # R1: harness(1000→600), tools(500→400), context(800→600)
        agg.observe("harness", _metrics(tokens_before=1000, tokens_after=600), req_id="r1")
        agg.observe("tools", _metrics(tokens_before=500, tokens_after=400), req_id="r1")
        agg.observe("context", _metrics(tokens_before=800, tokens_after=600), req_id="r1")

        # R2: harness(2000→1400), tools(800→700), context(1500→1200)
        agg.observe("harness", _metrics(tokens_before=2000, tokens_after=1400), req_id="r2")
        agg.observe("tools", _metrics(tokens_before=800, tokens_after=700), req_id="r2")
        agg.observe("context", _metrics(tokens_before=1500, tokens_after=1200), req_id="r2")

        snap = agg.snapshot()

        # ratio_total = (600+400+600+1400+700+1200) / (1000+500+800+2000+800+1500)
        #             = 4900 / 6600 ≈ 0.7424
        assert snap["ratio_total"] == pytest.approx(0.7424, abs=0.001)

        # saved_total = (400+100+200) + (600+100+300) = 1700
        assert snap["saved_total"] == 1700.0

        # avg_saved_req = 1700 / 2 = 850.0
        assert snap["avg_saved_req"] == 850.0


class TestThreeRequestFixture:
    """Walkthrough from plan §3.5: 3 requests with harness/tools compression.

    Fixture:
      R1: harness (1000→600, 10ms) + tools (500→400, 20ms)
      R2: harness (2000→1200, 20ms) + tools (800→700, 30ms)
      R3: harness (3000→2000, 30ms) + tools (1000→900, 40ms)

    Expected metrics:
      - ratio_harness = (600+1200+2000) / (1000+2000+3000) = 3800/6000 ≈ 0.633
      - saved_harness_tools = (1000-600+500-400) + (2000-1200+800-700) + (3000-2000+1000-900)
                            = 500 + 900 + 1100 = 2500
      - tools_avg_dur (per call) = (20+30+40) / 3 = 30.0
      - avg_saved_per_req = 2500 / 3 ≈ 833.3
    """

    def test_three_request_fixture_metrics(self):
        agg = MetricsAggregator()
        # Set anchor to allow PerRequest metric registration
        agg._set_anchor("harness")

        # Register all metrics upfront (before any observe)
        CompressionRatio(sources="harness")._emit_rules("ratio_harness", agg)
        AvgDurationPerCall(sources="tools")._emit_rules("tools_avg_dur", agg)
        TotalSaved(sources=["harness", "tools"])._emit_rules("saved_harness_tools", agg)
        AvgSavedPerRequest(sources=["harness", "tools"])._emit_rules("avg_saved_per_req", agg)

        # R1
        agg.observe("harness", _metrics(tokens_before=1000, tokens_after=600, duration_ms=10.0), req_id="r1")
        agg.observe("tools", _metrics(tokens_before=500, tokens_after=400, duration_ms=20.0), req_id="r1")

        # R2
        agg.observe("harness", _metrics(tokens_before=2000, tokens_after=1200, duration_ms=20.0), req_id="r2")
        agg.observe("tools", _metrics(tokens_before=800, tokens_after=700, duration_ms=30.0), req_id="r2")

        # R3
        agg.observe("harness", _metrics(tokens_before=3000, tokens_after=2000, duration_ms=30.0), req_id="r3")
        agg.observe("tools", _metrics(tokens_before=1000, tokens_after=900, duration_ms=40.0), req_id="r3")

        snap = agg.snapshot()

        # Verify calculated values
        assert snap["ratio_harness"] == pytest.approx(0.633, abs=0.01)
        assert snap["saved_harness_tools"] == 2500.0
        assert snap["tools_avg_dur"] == 30.0
        assert snap["avg_saved_per_req"] == pytest.approx(833.3, abs=0.1)


class _BlockingMetrics:
    """Duck-typed CompressorMetrics whose `tokens_before` read blocks until a
    gate is set. Lets a test hold `observe()` *inside* its critical section
    (observe does `getattr(metrics, rule.field)` under the lock) so a second
    caller's blocking-vs-not behaviour reveals whether the lock exists.
    """

    def __init__(self, gate: "threading.Event", order: list[str]) -> None:
        self.scope = CompressionScope.HARNESS
        self._gate = gate
        self._order = order

    @property
    def tokens_before(self) -> int:
        self._order.append("A-in-crit")
        self._gate.wait(3)
        self._order.append("A-leaving-crit")
        return 100


class TestConcurrentObserve:
    """Thread-safety of the aggregator (plan §3.5: compressors may run off the
    event loop in worker threads, so observe/snapshot/reset are serialized by
    `_lock`).

    These assert the lock *serializes* access deterministically — holding it in
    one thread must block the other — rather than relying on a data race to
    manifest, which CPython's GIL makes too flaky to test reliably.
    """

    def test_observe_serialized_by_lock(self):
        import time

        agg = MetricsAggregator()
        TotalInput(sources="test")._emit_rules("tot", agg)
        order: list[str] = []
        gate = threading.Event()
        normal = _metrics(tokens_before=5, tokens_after=1)

        def hold_lock() -> None:
            agg.observe("test", _BlockingMetrics(gate, order))  # blocks in crit

        def contend() -> None:
            time.sleep(0.15)                # let hold_lock enter the lock first
            order.append("B-enter")
            agg.observe("test", normal)     # must block until lock released
            order.append("B-done")

        t1 = threading.Thread(target=hold_lock)
        t2 = threading.Thread(target=contend)
        t1.start(); t2.start()
        time.sleep(0.5)                     # both threads now live; A holds lock
        during = list(order)
        gate.set()                          # release A's critical section
        t1.join(); t2.join()

        # While A held the lock, B reached its call site but could NOT complete.
        assert "A-in-crit" in during
        assert "B-enter" in during
        assert "B-done" not in during       # ← fails if observe isn't locked
        # After release, both finish and the aggregate reflects both observes.
        assert agg.snapshot()["tot"] == 105.0

    def test_snapshot_blocks_during_observe(self):
        import time

        agg = MetricsAggregator()
        TotalInput(sources="test")._emit_rules("tot", agg)
        order: list[str] = []
        gate = threading.Event()

        def hold_lock() -> None:
            agg.observe("test", _BlockingMetrics(gate, order))

        result: dict = {}

        def snap() -> None:
            time.sleep(0.15)
            order.append("snap-enter")
            result["val"] = agg.snapshot()["tot"]   # must wait for observe's lock
            order.append("snap-done")

        t1 = threading.Thread(target=hold_lock)
        t2 = threading.Thread(target=snap)
        t1.start(); t2.start()
        time.sleep(0.5)
        during = list(order)
        gate.set()
        t1.join(); t2.join()

        assert "snap-enter" in during
        assert "snap-done" not in during    # snapshot blocked while observe held lock
        assert result["val"] == 100.0       # sees the completed observe, not a torn state


class TestAggregatorSourceDenominatorBoundaries:
    def test_source_snapshot_raises_when_other_source_has_only_req_id(self):
        agg = MetricsAggregator()
        AvgSavedPerRequest(sources="src1")._emit_rules("src1.avg_saved_req", agg)

        agg.observe("src2", _metrics(tokens_before=100, tokens_after=50), req_id="r1")

        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            agg.snapshot(source="src1")

    def test_source_snapshot_raises_when_anchor_not_in_selected_source(self):
        agg = MetricsAggregator()
        agg._set_anchor("src1")
        AvgSavedPerRequest(sources="src2")._emit_rules("src2.avg_saved_req", agg)
        agg.observe("src2", _metrics(tokens_before=100, tokens_after=80))

        with pytest.raises(RuntimeError, match="PerRequest metric requires"):
            agg.snapshot(source="src2")

    def test_source_request_count_uses_union_not_sum(self):
        agg = MetricsAggregator()
        RequestCount()._emit_rules("src2.req_count", agg)

        agg.observe("src2", _metrics(), req_id="r1")
        agg.observe("src2", _metrics(), req_id="r1")
        agg.observe("src2", _metrics(), req_id="r2")

        snap = agg.snapshot(source="src2")
        assert snap["src2.req_count"] == 2.0


class TestAggregatorRandomizedInvariants:
    def test_randomized_observe_and_source_reset_invariants(self):
        rng = random.Random(20260721)
        sources = ["src1", "src2", "src3"]

        agg = MetricsAggregator()
        agg._set_anchor("src1")

        for src in sources:
            TotalInput(sources=src)._emit_rules(f"{src}.in", agg)
            TotalOutput(sources=src)._emit_rules(f"{src}.out", agg)
            TotalSaved(sources=src)._emit_rules(f"{src}.saved", agg)
            CallCount(sources=src)._emit_rules(f"{src}.calls", agg)

        TotalInput(sources=sources)._emit_rules("overall.in", agg)
        TotalOutput(sources=sources)._emit_rules("overall.out", agg)
        TotalSaved(sources=sources)._emit_rules("overall.saved", agg)
        CallCount(sources=sources)._emit_rules("overall.calls", agg)
        CompressionRatio(sources=sources)._emit_rules("overall.ratio", agg)
        AvgSavedPerRequest(sources=sources)._emit_rules("overall.avg_saved_req", agg)
        RequestCount()._emit_rules("overall.req_count", agg)

        manual = {
            src: {
                "in": 0.0,
                "out": 0.0,
                "saved": 0.0,
                "calls": 0.0,
                "req_ids": set(),
            }
            for src in sources
        }

        def _validate() -> None:
            snap = agg.snapshot()

            total_in = sum(manual[s]["in"] for s in sources)
            total_out = sum(manual[s]["out"] for s in sources)
            total_saved = sum(manual[s]["saved"] for s in sources)
            total_calls = sum(manual[s]["calls"] for s in sources)

            req_union: set[str] = set()
            for s in sources:
                req_union.update(manual[s]["req_ids"])
            req_count = float(len(req_union))

            assert snap["overall.in"] == total_in
            assert snap["overall.out"] == total_out
            assert snap["overall.saved"] == total_saved
            assert snap["overall.calls"] == total_calls
            assert snap["overall.req_count"] == req_count

            expected_ratio = 0.0 if total_in == 0 else total_out / total_in
            assert snap["overall.ratio"] == pytest.approx(expected_ratio, abs=1e-12)

            expected_avg_saved_req = 0.0 if req_count == 0 else total_saved / req_count
            assert snap["overall.avg_saved_req"] == pytest.approx(
                expected_avg_saved_req, abs=1e-12
            )

            for src in sources:
                src_snap = agg.snapshot(source=src)
                assert src_snap[f"{src}.in"] == manual[src]["in"]
                assert src_snap[f"{src}.out"] == manual[src]["out"]
                assert src_snap[f"{src}.saved"] == manual[src]["saved"]
                assert src_snap[f"{src}.calls"] == manual[src]["calls"]

        for _ in range(300):
            if rng.random() < 0.82:
                src = rng.choice(sources)
                before = rng.randint(1, 4000)
                after = rng.randint(0, before)
                req_id = f"r{rng.randint(1, 40)}"

                agg.observe(
                    src,
                    _metrics(tokens_before=before, tokens_after=after, duration_ms=1.0),
                    req_id=req_id,
                )

                manual[src]["in"] += float(before)
                manual[src]["out"] += float(after)
                manual[src]["saved"] += float(before - after)
                manual[src]["calls"] += 1.0
                manual[src]["req_ids"].add(req_id)
            else:
                src = rng.choice(sources)
                agg.reset(source=src)
                manual[src]["in"] = 0.0
                manual[src]["out"] = 0.0
                manual[src]["saved"] = 0.0
                manual[src]["calls"] = 0.0
                manual[src]["req_ids"].clear()

            _validate()
