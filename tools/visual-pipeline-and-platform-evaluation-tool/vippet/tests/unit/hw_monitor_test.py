# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance harness's HardwareMonitor.

Covers the parts that don't require a live metrics-manager / VIPPET
instance: edge trimming before averaging, and the per-family
ok / no_samples / idle classification used to flag missing or idle
device families in reports instead of leaving blank cells.
"""

import json
import unittest
import warnings
from unittest import mock

from tests.performance.perf_helpers.hw_monitor import (
    HardwareMonitor,
    _drop_npu_settle_sample,
    _family_kpi_status,
    _family_sample_count,
    _fetch_metrics_manager,
    _trim_edge_samples,
)


def _cpu_gpu_npu_sample(
    *, cpu: float = 10.0, gpu_video: float = 20.0, npu: float = 30.0
) -> dict[str, float]:
    return {
        "cpu_util_pct": cpu,
        "gpu_video_util_pct": gpu_video,
        "npu_utilization": npu,
    }


class TestTrimEdgeSamples(unittest.TestCase):
    def test_empty_input_returns_empty(self):
        self.assertEqual(_trim_edge_samples([], 0.1), [])

    def test_trims_from_both_ends(self):
        # 10 samples, 10% trim -> trim_count = 1 -> drop first/last.
        samples = [{"v": float(i)} for i in range(10)]
        trimmed = _trim_edge_samples(samples, 0.1)
        self.assertEqual([s["v"] for s in trimmed], [float(i) for i in range(1, 9)])

    def test_small_sample_count_is_not_trimmed(self):
        # 16 samples (2s interval over a 30s run) at 10% -> trim_count=1,
        # which is the documented "some startup idle may remain" case —
        # still only clips one sample per edge, not a no-op.
        samples = [{"v": float(i)} for i in range(16)]
        trimmed = _trim_edge_samples(samples, 0.1)
        self.assertEqual([s["v"] for s in trimmed], [float(i) for i in range(1, 15)])

    def test_trim_count_zero_returns_samples_unchanged(self):
        # 5 samples * 10% = 0 (int truncation) -> no trimming.
        samples = [{"v": float(i)} for i in range(5)]
        trimmed = _trim_edge_samples(samples, 0.1)
        self.assertEqual(trimmed, samples)

    def test_would_remove_everything_returns_samples_unchanged(self):
        # trim_count * 2 >= len(samples) guards against trimming to nothing.
        samples = [{"v": float(i)} for i in range(4)]
        trimmed = _trim_edge_samples(samples, 0.5)
        self.assertEqual(trimmed, samples)


class TestFamilySampleCount(unittest.TestCase):
    def test_counts_samples_with_any_family_key(self):
        samples = [
            {"npu_utilization": 0},
            {"cpu_util_pct": 5},
            {"npu_power": 1.2},
            {},
        ]
        self.assertEqual(_family_sample_count(samples, "NPU"), 2)
        self.assertEqual(_family_sample_count(samples, "CPU"), 1)

    def test_unknown_family_counts_zero(self):
        self.assertEqual(_family_sample_count([{"cpu_util_pct": 1}], "TPU"), 0)


class TestFamilyKpiStatus(unittest.TestCase):
    def test_no_samples_when_keys_never_present(self):
        samples = [{"cpu_util_pct": 10.0}, {"cpu_util_pct": 12.0}]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "no_samples")

    def test_no_samples_on_empty_sample_list(self):
        self.assertEqual(_family_kpi_status([], "NPU"), "no_samples")

    def test_idle_when_present_but_always_zero(self):
        # The "Defect Detection NPU" case: npu_utilization/frequency/power
        # all read 0 for the whole run even though samples exist.
        samples = [
            {"npu_utilization": 0.0, "npu_frequency_mhz": 0.0, "npu_power": 0.0},
            {"npu_utilization": 0.0, "npu_frequency_mhz": 0.0, "npu_power": 0.0},
        ]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "idle")

    def test_ok_when_primary_activity_key_is_nonzero(self):
        samples = [{"npu_utilization": 0.0}, {"npu_utilization": 42.0}]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "ok")

    def test_ok_falls_back_to_frequency_when_utilization_always_zero(self):
        # npu_utilization is 0 throughout, but npu_frequency_mhz proves the NPU
        # was actually clocked up and doing work.
        samples = [
            {"npu_utilization": 0.0, "npu_frequency_mhz": 0.0},
            {"npu_utilization": 0.0, "npu_frequency_mhz": 850.0},
        ]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "ok")

    def test_gpu_not_misclassified_idle_by_always_zero_render(self):
        # gpu_render_util_pct is always 0 on tested hardware (known issue);
        # gpu_video_util_pct shows real activity. GPU must still be "ok".
        samples = [
            {"gpu_render_util_pct": 0.0, "gpu_video_util_pct": 0.0},
            {"gpu_render_util_pct": 0.0, "gpu_video_util_pct": 35.0},
        ]
        self.assertEqual(_family_kpi_status(samples, "GPU"), "ok")

    def test_gpu_idle_when_all_engines_zero(self):
        samples = [
            {"gpu_render_util_pct": 0.0, "gpu_video_util_pct": 0.0},
            {"gpu_render_util_pct": 0.0, "gpu_video_util_pct": 0.0},
        ]
        self.assertEqual(_family_kpi_status(samples, "GPU"), "idle")


class TestAggregateTrimming(unittest.TestCase):
    """``_aggregate`` must trim _avg (and gpu_util_combined_avg) but not _min/_max."""

    def _monitor_with_samples(self, samples, trim_fraction=0.1):
        monitor = HardwareMonitor(trim_fraction=trim_fraction)
        monitor._samples = samples  # noqa: SLF001 - test seam, no public setter
        return monitor

    def test_avg_excludes_trimmed_edge_samples(self):
        # 10 samples: extreme warm-up (1000) and wind-down (1000) outliers
        # at the edges; 10% trim drops exactly those two.
        samples = [{"cpu_util_pct": 1000.0}]
        samples += [{"cpu_util_pct": 10.0} for _ in range(8)]
        samples += [{"cpu_util_pct": 1000.0}]
        monitor = self._monitor_with_samples(samples)

        agg = monitor._aggregate([])  # noqa: SLF001

        self.assertEqual(agg["cpu_util_pct_avg"], 10.0)

    def test_min_max_are_not_trimmed(self):
        samples = [{"cpu_util_pct": 1000.0}]
        samples += [{"cpu_util_pct": 10.0} for _ in range(8)]
        samples += [{"cpu_util_pct": 0.5}]
        monitor = self._monitor_with_samples(samples)

        agg = monitor._aggregate([])  # noqa: SLF001

        self.assertEqual(agg["cpu_util_pct_max"], 1000.0)
        self.assertEqual(agg["cpu_util_pct_min"], 0.5)

    def test_gpu_util_combined_avg_is_trimmed_but_max_is_not(self):
        samples = [{"gpu_render_util_pct": 99.0, "gpu_video_util_pct": 0.0}]
        samples += [
            {"gpu_render_util_pct": 10.0, "gpu_video_util_pct": 10.0} for _ in range(8)
        ]
        samples += [{"gpu_render_util_pct": 0.0, "gpu_video_util_pct": 0.0}]
        monitor = self._monitor_with_samples(samples)

        agg = monitor._aggregate([])  # noqa: SLF001

        self.assertEqual(agg["gpu_util_combined_avg"], 10.0)
        self.assertEqual(agg["gpu_util_combined_max"], 99.0)

    def test_sample_count_reflects_untrimmed_total(self):
        samples = [{"cpu_util_pct": 1.0} for _ in range(16)]
        monitor = self._monitor_with_samples(samples)

        agg = monitor._aggregate([])  # noqa: SLF001

        self.assertEqual(agg["sample_count"], 16)


class TestStopPerFamilyStatus(unittest.TestCase):
    """``HardwareMonitor.stop(families)`` end-to-end: status, counts, warnings."""

    def _monitor_with_samples(self, samples):
        monitor = HardwareMonitor()
        monitor._samples = samples  # noqa: SLF001
        monitor._thread = None
        return monitor

    def test_requested_family_with_no_samples_is_flagged(self):
        monitor = self._monitor_with_samples(
            [{"cpu_util_pct": 10.0}, {"cpu_util_pct": 12.0}]
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            stats = monitor.stop(["CPU", "NPU"])

        self.assertEqual(stats["kpi_status"]["CPU"], "ok")
        self.assertEqual(stats["kpi_status"]["NPU"], "no_samples")
        self.assertEqual(stats["npu_sample_count"], 0)
        self.assertIn("NPU:no_samples", stats["kpi_warnings"])
        self.assertTrue(
            any(
                "NPU" in str(w.message) and "no_samples" in str(w.message)
                for w in caught
            )
        )

    def test_idle_family_is_flagged_but_keeps_its_zero_values(self):
        monitor = self._monitor_with_samples(
            [
                {"npu_utilization": 0, "npu_frequency_mhz": 0, "npu_power": 0.0},
                {"npu_utilization": 0, "npu_frequency_mhz": 0, "npu_power": 0.0},
            ]
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            stats = monitor.stop(["NPU"])

        self.assertEqual(stats["kpi_status"]["NPU"], "idle")
        self.assertEqual(stats["npu_utilization_avg"], 0)
        self.assertEqual(stats["kpi_warnings"], "NPU:idle")

    def test_ok_family_produces_no_warning_and_empty_kpi_warnings(self):
        monitor = self._monitor_with_samples(
            [{"cpu_util_pct": 10.0}, {"cpu_util_pct": 20.0}]
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            stats = monitor.stop(["CPU"])

        self.assertEqual(stats["kpi_status"]["CPU"], "ok")
        self.assertEqual(stats["kpi_warnings"], "")
        self.assertEqual(len(caught), 0)

    def test_no_families_requested_keeps_legacy_shape(self):
        # Backward compatibility: callers that don't pass families (or pass
        # none) get the pre-existing aggregate shape without kpi_status.
        monitor = self._monitor_with_samples([])
        stats = monitor.stop()
        self.assertEqual(stats, {"sample_count": 0})


class TestNpuSettleSample(unittest.TestCase):
    """NPU readings carried over into the first sample must not count."""

    @staticmethod
    def _npu(active: bool) -> dict[str, float]:
        v = 1.0 if active else 0.0
        return {
            "cpu_util_pct": 50.0,
            "npu_utilization": 40.0 * v,
            "npu_frequency_mhz": 1400.0 * v,
            "npu_power": 2.5 * v,
        }

    def _stop(self, samples, families):
        monitor = HardwareMonitor()
        monitor._samples = samples  # noqa: SLF001
        monitor._thread = None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return monitor.stop(families)

    def test_carry_over_first_sample_then_zeros_is_idle(self):
        samples = [self._npu(True)] + [self._npu(False) for _ in range(4)]

        stats = self._stop(samples, ["CPU", "NPU"])

        self.assertEqual(stats["kpi_status"]["NPU"], "idle")
        self.assertEqual(stats["kpi_warnings"], "NPU:idle")
        self.assertEqual(stats["npu_settle_samples_dropped"], 1)
        self.assertEqual(stats["npu_sample_count"], 4)
        self.assertEqual(stats["npu_frequency_mhz_max"], 0)
        self.assertEqual(stats["npu_utilization_avg"], 0)

    def test_cpu_keys_of_first_sample_are_kept(self):
        samples = [self._npu(True)] + [self._npu(False) for _ in range(4)]
        samples[0]["cpu_util_pct"] = 100.0

        stats = self._stop(samples, ["CPU", "NPU"])

        self.assertEqual(stats["cpu_util_pct_max"], 100.0)
        self.assertEqual(stats["sample_count"], 5)

    def test_sustained_npu_activity_stays_ok(self):
        samples = [self._npu(True) for _ in range(5)]

        stats = self._stop(samples, ["NPU"])

        self.assertEqual(stats["kpi_status"]["NPU"], "ok")
        self.assertEqual(stats["npu_frequency_mhz_avg"], 1400.0)
        self.assertEqual(stats["npu_settle_samples_dropped"], 1)

    def test_fewer_than_three_samples_are_not_dropped(self):
        samples = [self._npu(True), self._npu(False)]

        stats = self._stop(samples, ["NPU"])

        self.assertEqual(stats["kpi_status"]["NPU"], "ok")
        self.assertEqual(stats["npu_settle_samples_dropped"], 0)
        self.assertEqual(stats["npu_sample_count"], 2)

    def test_helper_does_not_mutate_input(self):
        samples = [self._npu(True) for _ in range(3)]

        settled, dropped = _drop_npu_settle_sample(samples)

        self.assertEqual(dropped, 1)
        self.assertEqual(settled[0], {"cpu_util_pct": 50.0})
        self.assertIn("npu_utilization", samples[0])

    def test_first_sample_without_npu_keys_is_not_counted(self):
        samples = [{"cpu_util_pct": 1.0}] + [self._npu(False) for _ in range(3)]

        _, dropped = _drop_npu_settle_sample(samples)

        self.assertEqual(dropped, 0)


class TestCollectNativeCollectorMetrics(unittest.TestCase):
    """``_collect`` maps metrics-manager native-collector metrics to report KPIs."""

    def _collect_from(self, mm: dict[str, float]) -> dict[str, float]:
        monitor = HardwareMonitor()
        with mock.patch(
            "tests.performance.perf_helpers.hw_monitor._fetch_metrics_manager",
            return_value=mm,
        ):
            return monitor._collect()  # noqa: SLF001

    def test_npu_frequency_hz_is_reported_in_mhz(self):
        sample = self._collect_from({"npu_frequency_hz": 1.4e9, "npu_power_w": 1.5})
        self.assertEqual(sample["npu_frequency_mhz"], 1400.0)
        self.assertEqual(sample["npu_power"], 1.5)
        self.assertNotIn("npu_frequency_hz", sample)

    def test_missing_npu_frequency_is_omitted(self):
        sample = self._collect_from({"npu_power_w": 1.5})
        self.assertNotIn("npu_frequency_mhz", sample)

    def test_legacy_metric_names_are_ignored(self):
        # Names published before metrics-manager 2026.3.0 must not leak in.
        sample = self._collect_from(
            {
                "npu_frequency_mhz": 1400.0,
                "npu_frequency": 1.4e9,
                "npu_power": 1.5,
                "cpu_frequency_avg_frequency": 2_800_000.0,
                "gpu_frequency__cur_freq": 2350.0,
                "gpu_power__gpu_cur_power": 9.0,
            }
        )
        self.assertEqual(sample, {})

    def test_npu_kpis_keep_their_report_units(self):
        sample = self._collect_from(
            {
                "npu_utilization": 99.4,
                "npu_temperature_c": 48.0,
                "npu_memory_bytes": 128.0 * 1024 * 1024,
                "npu_bandwidth_bytes_per_second": 50_366e6,
            }
        )
        self.assertEqual(sample["npu_utilization"], 99.4)
        self.assertEqual(sample["npu_temperature"], 48.0)
        self.assertEqual(sample["npu_memory_mb"], 128.0)
        self.assertEqual(sample["npu_bandwidth"], 50_366.0)

    def test_cpu_and_gpu_frequency_hz_are_reported_in_mhz(self):
        sample = self._collect_from(
            {
                "cpu_frequency_avg_frequency_hz": 1_805_400_000.0,
                "gpu_frequency_cur_freq_hz__cur_freq": 2.35e9,
                "gpu_power_power_w__gpu_cur_power": 9.1,
                "gpu_power_power_w__pkg_cur_power": 27.7,
            }
        )
        self.assertEqual(sample["cpu_freq_mhz"], 1805.0)
        self.assertEqual(sample["gpu_freq_mhz"], 2350.0)
        self.assertEqual(sample["gpu_power_w"], 9.1)
        self.assertEqual(sample["pkg_power_w"], 27.7)


class TestFetchMetricsManager(unittest.TestCase):
    """``_fetch_metrics_manager`` flattens one SSE event into composite keys."""

    def _fetch(self, metrics: list[dict]) -> dict[str, float]:
        response = mock.MagicMock()
        response.iter_lines.return_value = ["data: " + json.dumps({"metrics": metrics})]
        stream = mock.MagicMock()
        stream.__enter__.return_value = response
        with mock.patch(
            "tests.performance.perf_helpers.hw_monitor.httpx.stream",
            return_value=stream,
        ):
            return _fetch_metrics_manager("http://mm/metrics/stream")

    @staticmethod
    def _freq(tile: str, value: float, gpu_id: str = "0") -> dict:
        return {
            "name": "gpu_frequency_cur_freq_hz",
            "labels": {"gpu_id": gpu_id, "type": "cur_freq", "tile": tile},
            "value": value,
        }

    def test_primary_tile_wins_regardless_of_order(self):
        for metrics in (
            [self._freq("gt0", 2.35e9), self._freq("gt1", 3.5e8)],
            [self._freq("gt1", 3.5e8), self._freq("gt0", 2.35e9)],
        ):
            result = self._fetch(metrics)
            self.assertEqual(result["gpu_frequency_cur_freq_hz__cur_freq"], 2.35e9)

    def test_non_primary_gpu_is_skipped(self):
        result = self._fetch([self._freq("gt0", 1.0e9, gpu_id="1")])
        self.assertEqual(result, {})

    def test_untiled_metrics_use_type_or_engine_suffix(self):
        result = self._fetch(
            [
                {
                    "name": "gpu_power_power_w",
                    "labels": {"gpu_id": "0", "type": "pkg_cur_power"},
                    "value": 27.7,
                },
                {"name": "npu_power_w", "labels": {}, "value": 5.9},
            ]
        )
        self.assertEqual(
            result, {"gpu_power_power_w__pkg_cur_power": 27.7, "npu_power_w": 5.9}
        )


if __name__ == "__main__":
    unittest.main()
