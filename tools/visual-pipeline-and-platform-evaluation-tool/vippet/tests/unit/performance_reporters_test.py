# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for perf_helpers.reporters.

Covers three previously-reported issues in the --report-only HTML renderer:

* Untrusted result-JSON text (pipeline/variant names, status, system info)
  must be HTML-escaped, and data embedded in the inline <script> block must
  be encoded so it cannot terminate the script early ("</script>" injection).
* Multi-run reports must keep each run's measurements distinct instead of
  one run silently overwriting another's when pipeline/variant/stream-count
  match across runs.
* A dangling (broken) result-JSON symlink must raise the documented
  ReportInputError (exit code 2 at the CLI), not an uncaught OSError.
"""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.performance.perf_helpers.reporters import (
    ReportInputError,
    generate_html_report,
    load_result,
    resolve_result_json,
)
from tests.performance.perf_helpers.run_config import build_config_block
from tests.performance.perf_helpers.settings import resolve_settings

_CONFIG: dict[str, Any] = build_config_block(
    resolve_settings("default", env={}),
    matrix=None,
    selection=[
        {"pipeline_id": "od", "variant_id": "cpu", "streams": 1, "test_id": "t1"}
    ],
    revisions={"suite": "abc123", "vippet": "9.9"},
    pytest_args=["-m", "perf"],
    filter_problem=None,
    replay=None,
)

_BASE_RESULT: dict[str, Any] = {
    "benchmark_id": "bench_20260101_000000",
    "timestamp": "2026-01-01T00:00:00",
    "duration_seconds": 10.0,
    "test_cases": [
        {
            "pipeline_name": "Object Detection",
            "pipeline_id": "od",
            "variant_id": "cpu",
            "variant_name": "CPU",
            "streams": 1,
            "status": "success",
            "total_fps": 30.0,
            "per_stream_fps": 30.0,
            "hw_metrics": {"cpu_util_pct_avg": 50.0, "gpu_power_w_avg": 5.0},
        },
    ],
    "summary": {"total": 1, "success": 1, "failed": 0, "skipped": 0},
    "hardware": {"CPU": ["Test CPU"]},
    "system_info": {"system": {"Processor": "Test CPU"}},
    "config": _CONFIG,
}


class TestHtmlEscaping(unittest.TestCase):
    """--report-only renders untrusted result JSON; it must not let field
    content inject markup or break out of the embedded <script> block."""

    def test_html_tag_in_text_fields_is_escaped(self) -> None:
        payload = "<img src=x onerror=alert(1)>"
        result = copy.deepcopy(_BASE_RESULT)
        result["test_cases"][0]["pipeline_name"] = payload
        result["system_info"]["system"]["Processor"] = payload

        html_out = generate_html_report([result])

        self.assertNotIn(payload, html_out)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html_out)

    def test_script_closing_payload_cannot_break_out_of_script_block(self) -> None:
        payload = "</script><script>window.pwned = true;</script>"
        result = copy.deepcopy(_BASE_RESULT)
        result["test_cases"][0]["variant_name"] = payload

        html_out = generate_html_report([result])

        # Only the report's own two legitimate <script> tags (the Chart.js
        # CDN include and the inline chart-init block) may appear; the
        # payload's "</script><script>" must not introduce extra ones.
        self.assertEqual(html_out.count("<script"), 2)
        self.assertEqual(html_out.count("</script>"), 2)
        self.assertNotIn("</script><script>window.pwned", html_out)

    def test_system_info_values_are_escaped(self) -> None:
        payload = '"><svg onload=alert(1)>'
        result = copy.deepcopy(_BASE_RESULT)
        result["system_info"]["system"]["Note"] = payload

        html_out = generate_html_report([result])

        self.assertNotIn(payload, html_out)

    def test_variant_name_cannot_break_table_attribute(self) -> None:
        payload = '"><script>alert(1)</script>'
        result = copy.deepcopy(_BASE_RESULT)
        result["test_cases"][0]["variant_name"] = payload

        html_out = generate_html_report([result])

        self.assertNotIn(payload, html_out)
        self.assertEqual(html_out.count("<script"), 2)


class TestMultiRunAggregation(unittest.TestCase):
    """Two runs sharing pipeline/variant/stream-count must not have one
    run's measurements silently overwrite the other's."""

    def test_fps_values_from_both_runs_are_present(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run1["test_cases"][0]["total_fps"] = 30.0

        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["test_cases"][0]["total_fps"] = 60.0

        html_out = generate_html_report([run1, run2])

        self.assertIn("30.0", html_out)
        self.assertIn("60.0", html_out)
        self.assertIn("bench_run_1", html_out)
        self.assertIn("bench_run_2", html_out)

    def test_utilization_values_from_both_runs_are_present(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run1["test_cases"][0]["hw_metrics"]["cpu_util_pct_avg"] = 11.0

        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["test_cases"][0]["hw_metrics"]["cpu_util_pct_avg"] = 99.0

        html_out = generate_html_report([run1, run2])

        self.assertIn("11.0", html_out)
        self.assertIn("99.0", html_out)

    def test_power_values_from_both_runs_are_present(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run1["test_cases"][0]["hw_metrics"]["gpu_power_w_avg"] = 1.111

        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["test_cases"][0]["hw_metrics"]["gpu_power_w_avg"] = 9.999

        html_out = generate_html_report([run1, run2])

        self.assertIn("1.111", html_out)
        self.assertIn("9.999", html_out)

    def test_single_run_report_has_no_run_column(self) -> None:
        html_out = generate_html_report([_BASE_RESULT])
        self.assertNotIn("<th>Run</th>", html_out)

    def test_multi_run_report_has_run_column_and_row_identity(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"

        html_out = generate_html_report([run1, run2])

        self.assertIn("<th>Run</th>", html_out)
        self.assertIn("bench_run_1", html_out)
        self.assertIn("bench_run_2", html_out)


class TestPerRunSystemInfo(unittest.TestCase):
    """Comparing runs from different machines must show each run's own
    system/hardware details, not just the first run's."""

    def test_single_run_card_is_titled_by_benchmark_id(self) -> None:
        html_out = generate_html_report([_BASE_RESULT])

        self.assertIn("<h3>bench_20260101_000000</h3>", html_out)
        self.assertNotIn("<h3>System</h3>", html_out)
        self.assertIn("Test CPU", html_out)
        # Single-run title keeps the processor suffix.
        self.assertIn("Performance Summary — Test CPU", html_out)

    def test_both_runs_system_info_is_present(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run1["system_info"]["system"]["Processor"] = "Machine A CPU"
        run1["hardware"] = {"CPU": ["Machine A CPU"]}

        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["system_info"]["system"]["Processor"] = "Machine B CPU"
        run2["hardware"] = {"CPU": ["Machine B CPU"]}

        html_out = generate_html_report([run1, run2])

        self.assertIn("Machine A CPU", html_out)
        self.assertIn("Machine B CPU", html_out)
        # Each card is titled by its benchmark id.
        self.assertIn("<h3>bench_run_1</h3>", html_out)
        self.assertIn("<h3>bench_run_2</h3>", html_out)

    def test_multi_run_title_has_no_single_processor_suffix(self) -> None:
        run1 = copy.deepcopy(_BASE_RESULT)
        run1["benchmark_id"] = "bench_run_1"
        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["system_info"]["system"]["Processor"] = "Different CPU"

        html_out = generate_html_report([run1, run2])

        self.assertIn(">Performance Summary<", html_out)
        self.assertNotIn("Performance Summary — ", html_out)

    def test_devices_row_shown_when_hardware_present(self) -> None:
        result = copy.deepcopy(_BASE_RESULT)
        result["hardware"] = {"CPU": ["Test CPU"], "GPU": ["Test GPU A", "Test GPU B"]}

        html_out = generate_html_report([result])

        self.assertIn("<dt>Devices</dt>", html_out)
        self.assertIn("Test GPU A", html_out)
        self.assertIn("Test GPU B", html_out)


class TestLoadResultErrorHandling(unittest.TestCase):
    """A missing/dangling result file must raise ReportInputError, not a
    bare OSError/traceback, matching run_report_only's exit-code-2 contract."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _symlink(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")

    def test_dangling_symlink_raises_report_input_error(self) -> None:
        target = self.tmp / "missing.json"
        link = self.tmp / "dangling.json"
        self._symlink(link, target)

        with self.assertRaises(ReportInputError):
            load_result(link)

    def test_vanished_file_raises_report_input_error(self) -> None:
        # Simulates the file disappearing between being found and loaded.
        path = self.tmp / "vanishing.json"
        path.write_text("{}", encoding="utf-8")
        path.unlink()

        with self.assertRaises(ReportInputError):
            load_result(path)

    def test_dangling_json_symlink_in_run_dir_raises_report_input_error(self) -> None:
        # Mirrors the real failure mode: resolve_result_json's glob fallback
        # finds a *.json directory entry without dereferencing it, so it can
        # hand back a symlink whose target no longer exists.
        run_dir = self.tmp / "bench_broken"
        run_dir.mkdir()
        target = run_dir / "does_not_exist.json"
        link = run_dir / "result.json"
        self._symlink(link, target)

        resolved = resolve_result_json(run_dir)
        self.assertEqual(resolved, link)

        with self.assertRaises(ReportInputError):
            load_result(resolved)


class TestConfigBlock(unittest.TestCase):
    """The result's "config" block is required, checked and rendered."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _load(self, result: dict[str, Any]) -> dict[str, Any]:
        path = self.tmp / "result.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        return load_result(path)

    def test_valid_config_round_trips(self) -> None:
        self.assertEqual(
            self._load(_BASE_RESULT)["config"], json.loads(json.dumps(_CONFIG))
        )

    def test_missing_or_malformed_config_is_rejected(self) -> None:
        result = copy.deepcopy(_BASE_RESULT)
        del result["config"]
        with self.assertRaisesRegex(ReportInputError, "To fix: rerun the benchmark"):
            self._load(result)
        for key, value in (
            ("schema_version", 2),
            ("sources", {"vippet.timeout": 1}),
            ("selection", [{"pipeline_id": "od"}]),
            ("replay", {"benchmark_id": "b"}),
        ):
            with self.subTest(key=key):
                result = copy.deepcopy(_BASE_RESULT)
                result["config"][key] = value
                with self.assertRaisesRegex(ReportInputError, f"config.{key}"):
                    self._load(result)

    def test_settings_from_other_suite_versions_still_render(self) -> None:
        result = copy.deepcopy(_BASE_RESULT)
        result["config"]["values"]["old.setting"] = 1
        del result["config"]["values"]["vippet.timeout"]
        html_out = generate_html_report([self._load(result)])
        self.assertIn("old.setting", html_out)

    def test_single_run_lists_settings_sources_and_selection(self) -> None:
        html_out = generate_html_report([_BASE_RESULT])
        self.assertIn('href="#configuration"', html_out)
        self.assertIn("<details open><summary>Settings</summary>", html_out)
        self.assertIn(
            'vippet.base_url</td><td>http://localhost/api/v1 <span class="src">yaml</span>',
            html_out,
        )
        self.assertIn(
            'metrics.metrics_url</td><td>http://localhost/metrics/stream <span class="src">default</span>',
            html_out,
        )
        self.assertIn("<td>t1</td>", html_out)
        self.assertIn("abc123", html_out)
        self.assertNotIn("Different between runs", html_out)

    def test_multi_run_highlights_differing_settings_first(self) -> None:
        run2 = copy.deepcopy(_BASE_RESULT)
        run2["benchmark_id"] = "bench_run_2"
        run2["config"]["values"]["benchmark.stream_counts"] = [1, 5]
        html_out = generate_html_report([_BASE_RESULT, run2])
        self.assertIn("Different between runs (1)", html_out)
        self.assertIn('<tr class="diff"><td>benchmark.stream_counts</td>', html_out)
        self.assertLess(
            html_out.index("benchmark.stream_counts"), html_out.index("vippet.base_url")
        )

    def test_config_values_are_escaped(self) -> None:
        payload = "<img src=x onerror=alert(1)>"
        result = copy.deepcopy(_BASE_RESULT)
        result["config"]["values"]["benchmark.pipelines"] = [payload]
        result["config"]["selection"][0]["test_id"] = payload
        result["config"]["replay"] = {
            "benchmark_id": "bench_a",
            "sha256": "f00",
            "allow_matrix_drift": False,
            "setting_changes": [payload],
            "revision_changes": [],
            "matrix_drift": [],
            "notes": [],
        }
        html_out = generate_html_report([self._load(result)])
        self.assertNotIn(payload, html_out)
        self.assertIn("Replay of bench_a", html_out)


if __name__ == "__main__":
    unittest.main()
