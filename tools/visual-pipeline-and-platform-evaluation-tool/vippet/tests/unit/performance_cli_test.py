# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-benchmark CLI."""

import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from tests.performance.perf_helpers import cli
from tests.performance.perf_helpers.matrix import MatrixFilters, build_matrix
from tests.performance.perf_helpers.preflight import PreflightError
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
            "--no-require-models",
        )
        self.assertEqual(
            cli.cli_overrides(ns),
            {
                "vippet.base_url": "http://h:1/api/v1",
                "benchmark.stream_counts": [1, 5],
                "benchmark.pipelines": ["a", "b"],
                "benchmark.filters.require_models": False,
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


class TestReportOnly(unittest.TestCase):
    def test_placeholder_exits_non_zero(self) -> None:
        settings = resolve_settings("default", env={})
        err = io.StringIO()
        self.assertNotEqual(cli.run_report_only(settings, stderr=err), 0)
        self.assertIn("not yet implemented", err.getvalue())


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

    def test_explicit_perf_selection_suppresses_default_dir(self) -> None:
        test_file = cli.PERF_DIR / "test_pipeline_performance.py"
        for arg in (
            str(test_file),
            f"{test_file}::test_pipeline_performance",
            str(cli.PERF_DIR),
        ):
            with self.subTest(arg=arg):
                cmd = cli.build_pytest_command([arg])
                self.assertEqual(cmd[-1], arg)
                self.assertEqual(
                    cmd.count(str(cli.PERF_DIR)), int(arg == str(cli.PERF_DIR))
                )

    def test_option_values_do_not_suppress_default_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "perf.xml"
            existing.write_text("", encoding="utf-8")
            outside_py = Path(tmp) / "conftest.py"
            outside_py.write_text("", encoding="utf-8")
            # Existing files that are not perf test selections: an option
            # value, a non-.py file inside PERF_DIR, and a .py outside it.
            for args in (
                ["--junitxml", str(existing)],
                ["-k", str(existing)],
                [str(cli.PERF_DIR / "README.md")],
                [str(outside_py)],
            ):
                with self.subTest(args=args):
                    cmd = cli.build_pytest_command(args)
                    self.assertIn(str(cli.PERF_DIR), cmd)
                    self.assertEqual(cmd[-len(args) :], args)


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
