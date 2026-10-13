# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for perf_helpers.reporters — specifically the CSV/HTML
surface that reflects HardwareMonitor's per-family kpi_status:

- CSV cells for a ``no_samples`` family show the literal ``NO_SAMPLES``
  marker instead of a blank string.
- CSV carries a ``kpi_warnings`` column.
- Idle families keep their real (zero) numeric values in the CSV — only
  ``kpi_warnings`` flags them.
"""

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.performance.perf_helpers import reporters
from tests.performance.perf_helpers.reporters import CSVReporter


def _test_case(
    *,
    pipeline_name="Object Detection",
    variant_name="NPU",
    variant_id="npu",
    streams=1,
    hw_metrics=None,
) -> dict:
    return {
        "pipeline_name": pipeline_name,
        "pipeline_id": "object-detection",
        "variant_name": variant_name,
        "variant_id": variant_id,
        "streams": streams,
        "status": "success",
        "total_fps": 30.0,
        "per_stream_fps": 30.0,
        "result": {},
        "hw_metrics": hw_metrics or {},
        "duration_seconds": 30.0,
        "job_id": "job-1",
        "error": None,
    }


def _read_csv_rows(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestFamilyForColumn(unittest.TestCase):
    def test_maps_avg_and_max_suffixes(self):
        self.assertEqual(reporters._family_for_column("npu_utilization_avg"), "NPU")
        self.assertEqual(reporters._family_for_column("npu_power_max"), "NPU")
        self.assertEqual(reporters._family_for_column("cpu_util_pct_avg"), "CPU")
        self.assertEqual(reporters._family_for_column("gpu_render_util_pct_max"), "GPU")

    def test_unknown_column_returns_none(self):
        self.assertIsNone(reporters._family_for_column("not_a_real_column_avg"))
        self.assertIsNone(reporters._family_for_column("no_suffix_at_all"))


class TestCSVReporterKpiMarkers(unittest.TestCase):
    def test_no_samples_family_writes_marker_not_blank(self):
        tc = _test_case(
            hw_metrics={
                "sample_count": 10,
                "cpu_util_pct_avg": 5.0,
                "cpu_util_pct_max": 7.0,
                "kpi_status": {"CPU": "ok", "NPU": "no_samples"},
                "kpi_warnings": "NPU:no_samples",
            }
        )
        result = {"test_cases": [tc]}

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.csv"
            CSVReporter.save(result, out)
            rows = _read_csv_rows(out)

        row = rows[0]
        self.assertEqual(row["npu_utilization_avg"], "NO_SAMPLES")
        self.assertEqual(row["npu_power_max"], "NO_SAMPLES")
        self.assertEqual(row["cpu_util_pct_avg"], "5.00")
        self.assertEqual(row["kpi_warnings"], "NPU:no_samples")

    def test_idle_family_keeps_real_zero_values(self):
        tc = _test_case(
            hw_metrics={
                "sample_count": 10,
                "npu_utilization_avg": 0.0,
                "npu_utilization_max": 0.0,
                "npu_power_avg": 0.0,
                "kpi_status": {"NPU": "idle"},
                "kpi_warnings": "NPU:idle",
            }
        )
        result = {"test_cases": [tc]}

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.csv"
            CSVReporter.save(result, out)
            rows = _read_csv_rows(out)

        row = rows[0]
        # Idle means real (zero) samples were collected — show the actual
        # numbers, not NO_SAMPLES; the warning lives in kpi_warnings only.
        self.assertEqual(row["npu_utilization_avg"], "0.00")
        self.assertEqual(row["kpi_warnings"], "NPU:idle")

    def test_ok_family_has_empty_kpi_warnings_and_no_marker(self):
        tc = _test_case(
            hw_metrics={
                "sample_count": 10,
                "npu_utilization_avg": 42.0,
                "kpi_status": {"NPU": "ok"},
                "kpi_warnings": "",
            }
        )
        result = {"test_cases": [tc]}

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.csv"
            CSVReporter.save(result, out)
            rows = _read_csv_rows(out)

        row = rows[0]
        self.assertEqual(row["npu_utilization_avg"], "42.00")
        self.assertEqual(row["kpi_warnings"], "")

    def test_missing_kpi_status_entirely_falls_back_to_blank(self):
        # Backward compatibility: hw_metrics without kpi_status at all
        # (e.g. an older result file) must not crash and must fall back to
        # a blank cell, matching the pre-existing behavior.
        tc = _test_case(hw_metrics={"sample_count": 5})
        result = {"test_cases": [tc]}

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.csv"
            CSVReporter.save(result, out)
            rows = _read_csv_rows(out)

        self.assertEqual(rows[0]["npu_utilization_avg"], "")

    def test_kpi_warnings_column_present_in_header(self):
        tc = _test_case(hw_metrics={"sample_count": 1})
        result = {"test_cases": [tc]}

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.csv"
            CSVReporter.save(result, out)
            with open(out, newline="") as f:
                header = next(csv.reader(f))

        self.assertIn("kpi_warnings", header)


class TestKpiBadge(unittest.TestCase):
    def test_ok_and_none_produce_no_badge(self):
        self.assertEqual(reporters._kpi_badge("ok"), "")
        self.assertEqual(reporters._kpi_badge(None), "")

    def test_no_samples_and_idle_produce_distinct_badges(self):
        no_samples_badge = reporters._kpi_badge("no_samples")
        idle_badge = reporters._kpi_badge("idle")
        self.assertIn("no samples", no_samples_badge)
        self.assertIn("idle", idle_badge)
        self.assertIn("badge warn", no_samples_badge)
        self.assertIn("badge warn", idle_badge)


class TestBuildSummaryRowsCarriesKpiStatus(unittest.TestCase):
    def test_summary_row_exposes_npu_freq_and_status(self):
        tc = _test_case(
            hw_metrics={
                "npu_frequency_avg": 1400.0,
                "kpi_status": {"NPU": "idle", "CPU": "ok"},
            }
        )
        rows = reporters._build_summary_rows([tc])
        self.assertEqual(rows[0]["npu_freq"], 1400.0)
        self.assertEqual(rows[0]["npu_status"], "idle")
        self.assertEqual(rows[0]["cpu_status"], "ok")


if __name__ == "__main__":
    unittest.main()
