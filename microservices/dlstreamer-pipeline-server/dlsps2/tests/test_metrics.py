# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.metrics: the DL Streamer bus-message contract and window merging."""

import logging
import math

import pytest

from core import metrics
from core.metrics import (
    SUPPORTED_VERSIONS,
    LatencyAccumulator,
    LatencyWindows,
    genai_values,
    metric_event,
)


def _window(count, sum_ms, min_ms, max_ms, source="src", sink="sink", window_ms=1000.0):
    return {
        "pipeline": "p",
        "source": source,
        "sink": sink,
        "window_ms": window_ms,
        "count": count,
        "sum_ms": sum_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
    }


class TestMetricEvent:
    def test_dlstreamer_message_becomes_metric_event(self):
        event = metric_event("inst", "sink", "dlstreamer/latency-window", {"version": 1, **_window(3, 30.0, 5.0, 15.0)})
        assert event == {
            "instance_id": "inst",
            "event": "metric",
            "kind": "latency-window",
            "element": "sink",
            "fields": _window(3, 30.0, 5.0, 15.0),
        }

    def test_other_element_messages_are_ignored(self):
        assert metric_event("inst", "level0", "level", {"version": 1}) is None

    def test_each_kind_is_checked_against_its_own_version(self):
        for kind in SUPPORTED_VERSIONS:
            event = metric_event("inst", "e", f"dlstreamer/{kind}", {"version": SUPPORTED_VERSIONS[kind], "x": 1})
            assert event["kind"] == kind and event["fields"] == {"x": 1}

    @pytest.mark.parametrize("version", [None, 0, 2, "1", True])
    def test_unsupported_schema_version_is_skipped(self, version):
        fields = {"count": 1} if version is None else {"version": version, "count": 1}
        assert metric_event("inst", "sink", "dlstreamer/latency-window", fields) is None

    def test_unknown_kind_is_skipped(self):
        assert metric_event("inst", "e", "dlstreamer/new-kind", {"version": 1}) is None


class TestUnsupportedSchemaWarning:
    @pytest.fixture(autouse=True)
    def _fresh_warnings(self, monkeypatch):
        monkeypatch.setattr(metrics, "_warned", set())

    @staticmethod
    def _warnings(caplog):
        return [r for r in caplog.records if r.name == "core.metrics" and r.levelno == logging.WARNING]

    def test_warns_once_per_kind_and_version(self, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        for _ in range(3):
            metric_event("inst", "sink", "dlstreamer/latency-window", {"version": 2})
            metric_event("inst", "sink", "dlstreamer/new-kind", {"version": 1})
        assert len(self._warnings(caplog)) == 2

        metric_event("inst", "sink", "dlstreamer/latency-window", {"version": 3})
        metric_event("inst", "sink", "dlstreamer/genai-request", {"version": 2})
        assert len(self._warnings(caplog)) == 4

    def test_supported_messages_do_not_warn(self, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        metric_event("inst", "sink", "dlstreamer/latency-window", {"version": 1, **_window(1, 1.0, 1.0, 1.0)})
        metric_event("inst", "sink", "level", {})
        assert self._warnings(caplog) == []


class TestLatencyAccumulator:
    def test_merge_is_exact_and_weighted_by_frame_count(self):
        acc = LatencyAccumulator()
        assert acc.add(_window(1, 100.0, 100.0, 100.0))
        assert acc.add(_window(3, 30.0, 5.0, 15.0))
        assert acc.count == 4
        # Weighted by frames: (100 + 30) / 4, not the mean of the two window means (55.0).
        assert acc.avg_ms == pytest.approx(32.5)
        assert acc.min_ms == 5.0
        assert acc.max_ms == 100.0
        assert acc.window_ms == 2000.0

    @pytest.mark.parametrize(
        "fields",
        [
            _window(0, 0.0, 0.0, 0.0),
            _window(1, math.nan, 1.0, 1.0),
            _window(1, 1.0, math.inf, 1.0),
            {**_window(1, 1.0, 1.0, 1.0), "window_ms": None},
            {"sum_ms": 1.0, "min_ms": 1.0, "max_ms": 1.0},
            _window("x", 1.0, 1.0, 1.0),
        ],
    )
    def test_malformed_window_is_rejected_without_side_effects(self, fields):
        acc = LatencyAccumulator()
        assert acc.add(_window(2, 4.0, 1.0, 3.0))
        assert not acc.add(fields)
        assert (acc.count, acc.sum_ms, acc.min_ms, acc.max_ms) == (2, 4.0, 1.0, 3.0)


class TestLatencyWindows:
    def test_instances_and_branches_are_never_mixed(self):
        windows = LatencyWindows()
        windows.add("a", _window(2, 20.0, 9.0, 11.0))
        windows.add("b", _window(1, 500.0, 500.0, 500.0))
        windows.add("a", _window(1, 7.0, 7.0, 7.0, source="src2"))
        by_key = {}
        for name, value, attrs in windows.drain():
            by_key.setdefault((attrs["pipeline_id"], attrs["source"], attrs["sink"]), {})[name] = value
        assert by_key[("a", "src", "sink")] == {
            "pipeline_latency_avg": 10.0,
            "pipeline_latency_min": 9.0,
            "pipeline_latency_max": 11.0,
            "pipeline_latency_frames": 2.0,
            "pipeline_latency_window": 1000.0,
        }
        assert by_key[("b", "src", "sink")]["pipeline_latency_avg"] == 500.0
        assert by_key[("a", "src2", "sink")]["pipeline_latency_frames"] == 1.0

    def test_drain_resets_so_a_restart_starts_clean(self):
        windows = LatencyWindows()
        windows.add("a", _window(1, 1000.0, 1000.0, 1000.0))
        assert windows.drain()
        assert windows.drain() == []
        # The same instance id restarted: nothing from the previous run survives.
        windows.add("a", _window(1, 10.0, 10.0, 10.0))
        values = {name: value for name, value, _ in windows.drain()}
        assert values["pipeline_latency_max"] == 10.0

    def test_malformed_first_window_creates_no_series(self):
        windows = LatencyWindows()
        windows.add("a", _window(0, 0.0, 0.0, 0.0))
        assert windows.drain() == []


def _dist_window(latencies, bounds, source="src", sink="sink"):
    """A latency-window with the distribution fields, computed from the given frame latencies."""
    counts = [0] * (len(bounds) + 1)
    for latency in latencies:
        counts[next((i for i, bound in enumerate(bounds) if latency <= bound), len(bounds))] += 1
    return {
        **_window(len(latencies), float(sum(latencies)), min(latencies), max(latencies), source, sink),
        "sum_sq_ms": float(sum(latency * latency for latency in latencies)),
        "bucket_bounds_ms": list(bounds),
        "bucket_counts": counts,
    }


def _drained(windows):
    return {name: value for name, value, _attrs in windows.drain()}


DISTRIBUTION_GAUGES = {
    "pipeline_latency_stddev", "pipeline_latency_p50", "pipeline_latency_p95", "pipeline_latency_p99",
}


class TestLatencyDistribution:
    @pytest.fixture(autouse=True)
    def _fresh_warnings(self, monkeypatch):
        monkeypatch.setattr(metrics, "_distribution_warned", set())

    @staticmethod
    def _warnings(caplog):
        return [r for r in caplog.records if r.name == "core.metrics" and r.levelno == logging.WARNING]

    def test_merge_adds_bucket_counts_and_squares(self):
        acc = LatencyAccumulator()
        assert acc.add(_dist_window([1.0, 2.0, 3.0], [2.0, 5.0]))
        assert acc.add(_dist_window([4.0, 10.0], [2.0, 5.0]))
        assert acc.bucket_counts == [2, 2, 1]
        assert acc.sum_sq_ms == 130.0
        assert acc.has_distribution

    def test_stddev_is_exact_population_stddev(self):
        acc = LatencyAccumulator()
        acc.add(_dist_window([1.0, 2.0, 3.0], [2.0, 5.0]))
        acc.add(_dist_window([4.0, 10.0], [2.0, 5.0]))
        # mean 4, mean of squares 26: variance 10
        assert acc.stddev_ms == pytest.approx(math.sqrt(10.0))

    def test_stddev_of_identical_latencies_is_zero_not_nan(self):
        acc = LatencyAccumulator()
        acc.add(_dist_window([0.1] * 3, [1.0]))
        assert acc.stddev_ms == 0.0

    def test_percentiles_interpolate_inside_the_bucket(self):
        acc = LatencyAccumulator()
        acc.add(_dist_window([1.0, 2.0, 3.0, 4.0, 10.0], [2.0, 5.0]))
        # rank 2.5 falls a quarter into (2, 5], which holds 2 frames
        assert acc.percentile_ms(0.5) == pytest.approx(2.75)
        # ranks 4.75 and 4.95 fall into the overflow bucket, whose upper edge is the maximum
        assert acc.percentile_ms(0.95) == pytest.approx(8.75)
        assert acc.percentile_ms(0.99) == pytest.approx(9.75)

    def test_first_bucket_starts_at_the_minimum(self):
        acc = LatencyAccumulator()
        acc.add(_dist_window([0.5, 1.5], [2.0, 5.0]))
        assert acc.percentile_ms(0.5) == pytest.approx(1.25)

    @pytest.mark.parametrize("latency", [3.0, 4.9])
    def test_percentiles_are_clamped_to_min_and_max(self, latency):
        acc = LatencyAccumulator()
        acc.add(_dist_window([latency, latency], [2.0, 5.0]))
        for quantile in (0.5, 0.95, 0.99):
            assert acc.percentile_ms(quantile) == latency

    def test_valid_period_exports_distribution_gauges(self):
        windows = LatencyWindows()
        windows.add("a", _dist_window([1.0, 2.0, 3.0], [2.0, 5.0]))
        windows.add("a", _dist_window([4.0, 10.0], [2.0, 5.0]))
        values = _drained(windows)
        assert values["pipeline_latency_avg"] == 4.0
        assert values["pipeline_latency_stddev"] == pytest.approx(math.sqrt(10.0))
        assert values["pipeline_latency_p50"] == pytest.approx(2.75)
        assert values["pipeline_latency_p95"] == pytest.approx(8.75)
        assert values["pipeline_latency_p99"] == pytest.approx(9.75)

    @pytest.mark.parametrize("old_first", [True, False])
    def test_window_without_distribution_drops_it_for_the_period(self, old_first, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        windows = LatencyWindows()
        old, new = _window(2, 4.0, 1.0, 3.0), _dist_window([4.0, 10.0], [2.0, 5.0])
        for fields in ((old, new) if old_first else (new, old)):
            windows.add("a", fields)
        values = _drained(windows)
        assert values["pipeline_latency_avg"] == 4.5
        assert values["pipeline_latency_frames"] == 4.0
        assert DISTRIBUTION_GAUGES.isdisjoint(values)
        assert len(self._warnings(caplog)) == 1

    def test_distribution_returns_once_every_window_of_a_period_has_it(self):
        windows = LatencyWindows()
        windows.add("a", _window(2, 4.0, 1.0, 3.0))
        windows.add("a", _dist_window([4.0], [2.0, 5.0]))
        assert DISTRIBUTION_GAUGES.isdisjoint(_drained(windows))
        windows.add("a", _dist_window([4.0], [2.0, 5.0]))
        assert DISTRIBUTION_GAUGES <= set(_drained(windows))

    def test_mismatched_bounds_drop_the_distribution_with_one_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        windows = LatencyWindows()
        for _ in range(2):
            windows.add("a", _dist_window([1.0, 2.0], [2.0, 5.0]))
            windows.add("a", _dist_window([1.0, 2.0], [2.0, 6.0]))
            windows.add("a", _dist_window([1.0, 2.0], [2.0, 5.0]))
            values = _drained(windows)
            assert values["pipeline_latency_avg"] == 1.5
            assert DISTRIBUTION_GAUGES.isdisjoint(values)
        warnings = self._warnings(caplog)
        assert len(warnings) == 1 and "different bucket bounds" in warnings[0].getMessage()

    def test_other_branches_keep_their_distribution(self):
        windows = LatencyWindows()
        windows.add("a", _dist_window([1.0], [2.0]))
        windows.add("a", _window(1, 1.0, 1.0, 1.0, source="src2"))
        names = {(attrs["source"], name) for name, _value, attrs in windows.drain()}
        assert ("src", "pipeline_latency_p50") in names
        assert ("src2", "pipeline_latency_p50") not in names

    @pytest.mark.parametrize(
        "change",
        [
            {"bucket_counts": [1, 1]},
            {"bucket_counts": [1, 1, 1, 0]},
            {"bucket_counts": [1, 1, 1]},
            {"bucket_counts": [3, -1, 0]},
            {"bucket_counts": [1.5, 0.5, 0]},
            {"bucket_counts": "<1,1,0>"},
            {"bucket_counts": None},
            {"bucket_bounds_ms": [5.0, 2.0]},
            {"bucket_bounds_ms": [2.0, 2.0]},
            {"bucket_bounds_ms": [2.0, math.nan]},
            {"bucket_bounds_ms": [2.0, "x"]},
            {"bucket_bounds_ms": [], "bucket_counts": [2]},
            {"sum_sq_ms": -1.0},
            {"sum_sq_ms": math.inf},
            {"sum_sq_ms": "x"},
        ],
    )
    def test_malformed_distribution_is_skipped_safely(self, change, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        windows = LatencyWindows()
        windows.add("a", {**_dist_window([1.0, 3.0], [2.0, 5.0]), **change})
        values = _drained(windows)
        assert values["pipeline_latency_avg"] == 2.0
        assert DISTRIBUTION_GAUGES.isdisjoint(values)
        assert len(self._warnings(caplog)) == 1

    def test_one_warning_per_reason(self, caplog):
        caplog.set_level(logging.WARNING, logger="core.metrics")
        windows = LatencyWindows()
        for _ in range(3):
            windows.add("a", _window(1, 1.0, 1.0, 1.0))
            windows.add("b", {**_dist_window([1.0], [2.0]), "bucket_counts": [1]})
            windows.add("c", _dist_window([1.0], [2.0]))
            windows.add("c", _dist_window([1.0], [3.0]))
            windows.drain()
        assert len(self._warnings(caplog)) == 3


class TestGenaiValues:
    def test_fields_map_to_histograms(self):
        fields = {
            "frames": 4,
            "ttft_ms": 120.5,
            "tpot_ms": 30.0,
            "generate_duration_ms": 500.0,
            "inference_duration_ms": 400.0,
            "prepare_embeddings_duration_ms": 50.0,
            "num_input_tokens": 900,
            "num_generated_tokens": 12,
        }
        assert dict(genai_values(fields)) == {
            "genai_ttft": 120.5,
            "genai_tpot": 30.0,
            "genai_generate_duration": 500.0,
            "genai_inference_duration": 400.0,
            "genai_prepare_embeddings_duration": 50.0,
            "genai_input_tokens": 900.0,
            "genai_generated_tokens": 12.0,
        }

    def test_missing_and_non_finite_fields_are_skipped(self):
        assert genai_values({"ttft_ms": math.nan, "tpot_ms": "n/a"}) == []
