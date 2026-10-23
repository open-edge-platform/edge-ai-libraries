# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-benchmark CLI."""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from tests.performance.perf_helpers import cli
from tests.performance.perf_helpers import reporters
from tests.performance.perf_helpers.matrix import MatrixFilters, build_matrix
from tests.performance.perf_helpers.preflight import PreflightError
from tests.performance.perf_helpers.reporters import generate_html_report
from tests.performance.perf_helpers.settings import (
    ENV_CONFIG_FILE,
    SPECS,
    resolve_settings,
)

_PIPELINES = [
    {
        "id": "od",
        "name": "Object Detection",
        "variants": [{"id": "1", "name": "CPU"}, {"id": "2", "name": "NPU"}],
    },
    {"id": "lpr", "name": "LPR", "variants": [{"id": "3", "name": "CPU"}]},
    {"id": "sp", "name": "Parking", "variants": [{"id": "4", "name": "CPU"}]},
]


def _parse(*argv: str) -> Any:
    return cli.build_parser().parse_args(list(argv))


class TestParser(unittest.TestCase):
    def test_every_setting_has_a_flag(self) -> None:
        parser = cli.build_parser()
        options = {opt for action in parser._actions for opt in action.option_strings}
        for spec in SPECS:
            with self.subTest(key=spec.key):
                self.assertIn(spec.flag, options)

    def test_required_flags_present(self) -> None:
        options = {
            opt
            for action in cli.build_parser()._actions
            for opt in action.option_strings
        }
        for flag in (
            "--config",
            "--base-url",
            "--metrics-url",
            "--pipelines",
            "--variants",
            "--streams",
            "--results-dir",
            "--dry-run",
            "--report-only",
            "--report-output",
        ):
            self.assertIn(flag, options)

    def test_flags_map_to_overrides(self) -> None:
        ns = _parse(
            "--base-url",
            "http://h:1/api/v1",
            "--streams",
            "1,5",
            "--pipelines",
            "a,b",
            "--no-skip-missing-models",
        )
        self.assertEqual(
            cli.cli_overrides(ns),
            {
                "vippet.base_url": "http://h:1/api/v1",
                "benchmark.stream_counts": [1, 5],
                "benchmark.pipelines": ["a", "b"],
                "benchmark.filters.skip_missing_models": False,
            },
        )

    def test_unset_flags_do_not_override(self) -> None:
        self.assertEqual(cli.cli_overrides(_parse()), {})

    def test_invalid_values_rejected(self) -> None:
        for argv in (
            ["--streams", "0"],
            ["--base-url", "file:///etc/passwd"],
            ["--output-mode", "stdout"],
            ["--dry-run", "--report-only"],
            ["--dry-run", "--report-only", "x"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit):
                    with patch("sys.stderr", io.StringIO()):
                        _parse(*argv)

    def test_split_passthrough(self) -> None:
        self.assertEqual(
            cli.split_passthrough(["--dry-run", "--", "-k", "x", "--"]),
            (["--dry-run"], ["-k", "x", "--"]),
        )
        self.assertEqual(cli.split_passthrough(["--dry-run"]), (["--dry-run"], []))

    def test_report_only_paths(self) -> None:
        self.assertIsNone(_parse().report_only)
        self.assertEqual(_parse("--report-only").report_only, [])
        self.assertEqual(_parse("--report-only", "a", "b").report_only, ["a", "b"])

    def test_report_output_requires_report_only(self) -> None:
        with patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--report-output", "x.html"])
        self.assertEqual(ctx.exception.code, 2)


class TestDryRun(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = resolve_settings(
            "default",
            env={},
            cli_overrides={"benchmark.filters.skip_pipelines": ["sp"]},
        )

    def _discover(self, settings: Any) -> Any:
        return build_matrix(
            _PIPELINES,
            [{"device_family": "CPU"}],
            {"lpr": {"LPR Net"}},
            MatrixFilters.from_settings(settings),
        )

    def test_prints_matrix_with_reasons_and_never_runs_pytest(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        preflight = Mock()
        rc = cli.run_dry_run(
            self.settings,
            discover=self._discover,
            preflight=preflight,
            stdout=out,
            stderr=err,
        )
        self.assertEqual(rc, 0)
        preflight.assert_called_once()
        text = out.getvalue()
        self.assertIn("Matrix: 2 run(s)", text)
        self.assertIn("object_detection_cpu_x1", text)
        self.assertIn("object_detection_cpu_x3", text)
        self.assertIn("unsupported_family", text)
        self.assertIn("skip_pipelines", text)
        self.assertIn("Skipped at run time: missing_models: 2 run(s)", text)
        self.assertIn("LPR Net", text)
        self.assertIn("benchmark.filters.skip_pipelines", text)

    def test_main_dry_run_does_not_submit_jobs(self) -> None:
        runner = Mock()
        with (
            patch.object(cli, "run_pytest", runner),
            patch.object(cli, "run_dry_run", return_value=0) as dry,
        ):
            self.assertEqual(cli.main(["--dry-run", "--config", "quick"]), 0)
        dry.assert_called_once()
        runner.assert_not_called()

    def test_preflight_failure_exits_2(self) -> None:
        err = io.StringIO()
        rc = cli.run_dry_run(
            self.settings,
            discover=Mock(),
            preflight=Mock(side_effect=PreflightError("down")),
            stdout=io.StringIO(),
            stderr=err,
        )
        self.assertEqual(rc, 2)
        self.assertIn("down", err.getvalue())

    def test_discovery_failure_exits_2(self) -> None:
        rc = cli.run_dry_run(
            self.settings,
            discover=Mock(side_effect=RuntimeError("boom")),
            preflight=Mock(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(rc, 2)


_RESULT: dict[str, Any] = {
    "benchmark_id": "bench_20260101_000000",
    "timestamp": "2026-01-01T00:00:00",
    "duration_seconds": 12.5,
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
            "hw_metrics": {"cpu_util_pct_avg": 50.0},
        },
        {
            "pipeline_name": "LPR",
            "pipeline_id": "lpr",
            "variant_id": "cpu",
            "variant_name": "CPU",
            "streams": 1,
            "status": "skipped",
        },
    ],
    "summary": {"total": 2, "success": 1, "failed": 0, "skipped": 1},
    "hardware": {"CPU": ["Test CPU"]},
    "system_info": {"system": {"Processor": "Test CPU"}},
}


def _write_run(root: Path, result: dict[str, Any]) -> Path:
    """Create root/<id>/<id>.json, mirroring JSONReporter's output, return the run dir."""
    benchmark_id = result["benchmark_id"]
    run_dir = root / benchmark_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / f"{benchmark_id}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return run_dir


class TestReportOnly(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.settings = resolve_settings(
            "default", env={}, cli_overrides={"results.output_dir": str(self.tmp)}
        )
        self.out, self.err = io.StringIO(), io.StringIO()

    def _run(self, *inputs: str, output: str | None = None) -> int:
        return cli.run_report_only(
            self.settings, list(inputs), output, stdout=self.out, stderr=self.err
        )

    def _link_latest(self, run_dir: Path) -> None:
        try:
            (self.tmp / "latest").symlink_to(run_dir.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")

    def test_latest_matches_live_html(self) -> None:
        run_dir = _write_run(self.tmp, _RESULT)
        self._link_latest(run_dir)

        rc = self._run(str(self.tmp / "latest"))

        self.assertEqual(rc, 0)
        html_path = run_dir / f"{_RESULT['benchmark_id']}.html"
        self.assertEqual(
            html_path.read_text(encoding="utf-8"), generate_html_report([_RESULT])
        )
        self.assertIn("HTML report:", self.out.getvalue())

    def test_defaults_to_latest(self) -> None:
        run_dir = _write_run(self.tmp, _RESULT)
        self._link_latest(run_dir)

        rc = self._run()

        self.assertEqual(rc, 0)
        html_path = run_dir / f"{_RESULT['benchmark_id']}.html"
        self.assertTrue(html_path.exists())

    def test_accepts_file_and_directory(self) -> None:
        run_dir = _write_run(self.tmp, _RESULT)
        json_path = run_dir / f"{_RESULT['benchmark_id']}.json"

        self.assertEqual(self._run(str(json_path)), 0)
        self.assertEqual(self._run(str(run_dir)), 0)

    def test_multiple_runs_render_together(self) -> None:
        run1_result = dict(_RESULT, benchmark_id="bench_20260101_000001")
        run2_result = dict(_RESULT, benchmark_id="bench_20260101_000002")
        run1_dir = _write_run(self.tmp, run1_result)
        run2_dir = _write_run(self.tmp, run2_result)

        rc = self._run(str(run1_dir), str(run2_dir), str(run1_dir))

        self.assertEqual(rc, 0)
        reports = list(self.tmp.glob("report_*.html"))
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text(encoding="utf-8")
        self.assertIn(run1_result["benchmark_id"], text)
        self.assertIn(run2_result["benchmark_id"], text)
        self.assertEqual(text, generate_html_report([run1_result, run2_result]))

    def test_report_output_override(self) -> None:
        run_dir = _write_run(self.tmp, _RESULT)
        output = self.tmp / "sub" / "cmp.html"

        rc = self._run(str(run_dir), output=str(output))

        self.assertEqual(rc, 0)
        self.assertTrue(output.exists())

    def test_invalid_inputs_exit_2(self) -> None:
        with self.subTest("missing path"):
            self.assertEqual(self._run(str(self.tmp / "nope")), 2)
            self.assertIn("error:", self.err.getvalue())
            # An explicit (user-supplied) path that is missing gets the
            # plain not-found error, no implicit-default hint.
            self.assertNotIn("Run a benchmark first", self.err.getvalue())

    def test_missing_default_target_gives_helpful_hint(self) -> None:
        # No inputs and no "latest" symlink: the implicit default target
        # is missing, which should nudge the user toward running a
        # benchmark first instead of a bare "not found" error.
        rc = self._run()

        self.assertEqual(rc, 2)
        message = self.err.getvalue()
        self.assertIn("error:", message)
        self.assertIn("Run a benchmark first", message)
        self.assertIn("--report-only PATH", message)

        with self.subTest("directory with no JSON"):
            empty_dir = self.tmp / "bench_empty"
            empty_dir.mkdir()
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(empty_dir)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())
            self.assertIn("--formats json", err.getvalue())

        with self.subTest("directory with two JSON files"):
            two_dir = self.tmp / "bench_two"
            two_dir.mkdir()
            (two_dir / "a.json").write_text("{}", encoding="utf-8")
            (two_dir / "b.json").write_text("{}", encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(two_dir)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

    def test_missing_default_target_hints_at_running_a_benchmark(self) -> None:
        # No inputs given and no "latest" link exists: nothing has been
        # benchmarked yet in self.tmp. The error should explain that,
        # instead of just reporting a bare "not found".
        rc = self._run()

        self.assertEqual(rc, 2)
        message = self.err.getvalue()
        self.assertIn("error:", message)
        self.assertIn("result path not found", message)
        self.assertIn(str(self.tmp), message)
        self.assertIn("make test-performance", message)

    def test_explicit_missing_path_has_no_benchmark_hint(self) -> None:
        # The hint only makes sense for the implicit <results-dir>/latest
        # default; an explicit, user-supplied path that is missing should
        # not claim "no benchmark results yet".
        rc = self._run(str(self.tmp / "nope"))

        self.assertEqual(rc, 2)
        self.assertNotIn("make test-performance", self.err.getvalue())

        with self.subTest(".txt file"):
            txt_path = self.tmp / "result.txt"
            txt_path.write_text("{}", encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(txt_path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

        with self.subTest("malformed JSON"):
            bad_path = self.tmp / "bad.json"
            bad_path.write_text("{not json", encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(bad_path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

        with self.subTest("top-level list"):
            list_path = self.tmp / "list.json"
            list_path.write_text("[]", encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(list_path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

        with self.subTest("test_cases item missing status"):
            result = {
                "benchmark_id": "bench_bad1",
                "test_cases": [
                    {
                        "pipeline_name": "x",
                        "variant_id": "cpu",
                        "variant_name": "CPU",
                        "streams": 1,
                    }
                ],
            }
            path = self.tmp / "bad1.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

        with self.subTest("streams as a string"):
            result = {
                "benchmark_id": "bench_bad2",
                "test_cases": [
                    {
                        "pipeline_name": "x",
                        "variant_id": "cpu",
                        "variant_name": "CPU",
                        "status": "success",
                        "streams": "1",
                    }
                ],
            }
            path = self.tmp / "bad2.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())

        with self.subTest("benchmark_id path traversal"):
            result = {"benchmark_id": "../evil", "test_cases": []}
            path = self.tmp / "evil.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            err = io.StringIO()
            rc = cli.run_report_only(
                self.settings, [str(path)], None, stdout=io.StringIO(), stderr=err
            )
            self.assertEqual(rc, 2)
            self.assertIn("error:", err.getvalue())
            outside_html = list(self.tmp.parent.glob("*.html"))
            self.assertEqual(outside_html, [])

        with self.subTest("file above size limit"):
            big_path = self.tmp / "big.json"
            big_path.write_text(json.dumps(_RESULT), encoding="utf-8")
            with patch.object(reporters, "MAX_RESULT_JSON_BYTES", 10):
                err = io.StringIO()
                rc = cli.run_report_only(
                    self.settings,
                    [str(big_path)],
                    None,
                    stdout=io.StringIO(),
                    stderr=err,
                )
                self.assertEqual(rc, 2)
                self.assertIn("error:", err.getvalue())

    def test_main_report_only_never_contacts_vippet(self) -> None:
        run_dir = _write_run(self.tmp, _RESULT)
        pytest_mock = Mock()
        dry_run_mock = Mock()
        preflight_mock = Mock()
        with (
            patch.object(cli, "run_pytest", pytest_mock),
            patch.object(cli, "run_dry_run", dry_run_mock),
            patch.object(cli, "wait_for_vippet_ready", preflight_mock),
            patch("sys.stdout", io.StringIO()),
        ):
            rc = cli.main(
                ["--report-only", str(run_dir), "--results-dir", str(self.tmp)]
            )
        self.assertEqual(rc, 0)
        pytest_mock.assert_not_called()
        dry_run_mock.assert_not_called()
        preflight_mock.assert_not_called()


class TestRunPytest(unittest.TestCase):
    def test_passes_resolved_config_to_pytest(self) -> None:
        settings = resolve_settings(
            "quick",
            env={},
            cli_overrides={
                "vippet.base_url": "http://cli:9/api/v1",
                "benchmark.stream_counts": [7],
            },
        )
        seen: dict[str, Any] = {}

        def runner(cmd: list[str], env: dict[str, str], check: bool) -> Any:
            path = Path(env[ENV_CONFIG_FILE])
            seen["cmd"] = cmd
            seen["env"] = env
            seen["path"] = path
            seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
            seen["reloaded"] = resolve_settings(env=env)
            return subprocess.CompletedProcess(cmd, 5)

        rc = cli.run_pytest(settings, ["-k", "x"], base_env={}, runner=runner)

        self.assertEqual(rc, 5)
        self.assertEqual(seen["cmd"][1:5], ["-m", "pytest", "-m", "perf"])
        self.assertEqual(seen["cmd"][-2:], ["-k", "x"])
        self.assertIn(str(cli.PERF_DIR), seen["cmd"])
        self.assertEqual(seen["env"]["VIPPET_BASE_URL"], "http://cli:9/api/v1")
        self.assertEqual(seen["reloaded"]["benchmark.stream_counts"], [7])
        self.assertEqual(dict(seen["reloaded"].values), dict(settings.values))
        if os.name == "posix":
            self.assertEqual(seen["mode"], 0o600)
        self.assertFalse(seen["path"].exists(), "temp config must be removed")

    def test_perf_dir_always_passed_before_passthrough(self) -> None:
        test_file = str(cli.PERF_DIR / "test_pipeline_performance.py")
        for args in (
            [],
            ["-k", "cpu"],
            ["--ignore", test_file],
            ["--junitxml", "results/perf.xml"],
            ["--rootdir", str(cli.PERF_DIR)],
            [f"{test_file}::test_pipeline_performance"],
        ):
            with self.subTest(args=args):
                cmd = cli.build_pytest_command(args)
                self.assertEqual(
                    cmd[1:], ["-m", "pytest", "-m", "perf", str(cli.PERF_DIR), *args]
                )


class TestSettingsEnv(unittest.TestCase):
    def test_exports_every_env_backed_key(self) -> None:
        settings = resolve_settings(
            "default", env={}, cli_overrides={"vippet.max_job_duration": 42}
        )
        env = cli.settings_env(settings)
        self.assertEqual(set(env), {spec.env for spec in SPECS if spec.env})
        # helpers.config parses this with int(); must not be "42.0".
        self.assertEqual(env["VIPPET_JOB_TIMEOUT_SECONDS"], "42")

    def test_user_env_is_resolved_not_clobbered(self) -> None:
        user_env = {
            "VIPPET_JOB_TIMEOUT_SECONDS": "77",
            "VIPPET_JOB_POLL_INTERVAL": "0.5",
        }
        settings = resolve_settings("default", env=user_env)
        env = cli.settings_env(settings)
        self.assertEqual(env["VIPPET_JOB_TIMEOUT_SECONDS"], "77")
        self.assertEqual(env["VIPPET_JOB_POLL_INTERVAL"], "0.5")


class TestDirectPytestConfigError(unittest.TestCase):
    def test_bad_config_prints_one_line_and_exits_2(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("PERF_")}
        env["PERF_CONFIG"] = "does-not-exist"
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(cli.PERF_DIR)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("invalid performance config", completed.stderr)
        self.assertIn("does-not-exist", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
