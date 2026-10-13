# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance harness's HardwareMonitor.

Covers the parts that don't require a live metrics-manager / VIPPET
instance: edge trimming before averaging, and the per-family
ok / no_samples / idle classification used to flag missing or idle
device families in reports instead of leaving blank cells.
"""

import unittest
import warnings

from tests.performance.perf_helpers.hw_monitor import (
    HardwareMonitor,
    _family_kpi_status,
    _family_sample_count,
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
            {"npu_utilization": 0.0, "npu_frequency": 0.0, "npu_power": 0.0},
            {"npu_utilization": 0.0, "npu_frequency": 0.0, "npu_power": 0.0},
        ]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "idle")

    def test_ok_when_primary_activity_key_is_nonzero(self):
        samples = [{"npu_utilization": 0.0}, {"npu_utilization": 42.0}]
        self.assertEqual(_family_kpi_status(samples, "NPU"), "ok")

    def test_ok_falls_back_to_frequency_when_utilization_always_zero(self):
        # npu_utilization is 0 throughout, but npu_frequency proves the NPU
        # was actually clocked up and doing work.
        samples = [
            {"npu_utilization": 0.0, "npu_frequency": 0.0},
            {"npu_utilization": 0.0, "npu_frequency": 850.0},
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
                {"npu_utilization": 0, "npu_frequency": 0, "npu_power": 0.0},
                {"npu_utilization": 0, "npu_frequency": 0, "npu_power": 0.0},
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


if __name__ == "__main__":
    unittest.main()
