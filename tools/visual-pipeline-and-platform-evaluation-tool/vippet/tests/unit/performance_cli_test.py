# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-benchmark CLI."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx

from tests.performance.perf_helpers import cli
from tests.performance.perf_helpers import reporters
from tests.performance.perf_helpers.matrix import MatrixFilters, build_matrix
from tests.performance.perf_helpers.model_install import (
    ENV_MODEL_INSTALL,
    ModelOutcome,
    Outcome,
    decode_outcomes,
)
from tests.performance.perf_helpers.preflight import PreflightError
from tests.performance.perf_helpers.reporters import generate_html_report
from tests.performance.perf_helpers.settings import (
    ENV_CONFIG_FILE,
    SPECS,
    read_cli_layer,
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

_MODELS = [
    {
        "name": "lprnet",
        "display_name": "LPR Net",
        "source": "omz",
        "install_status": "not_installed",
        "used_by_pipelines": ["lpr"],
    }
]


class _Api:
    """Fake ViPPET model endpoints; records every request."""

    def __init__(
        self, models: list[dict[str, Any]] | None = None, models_status: int = 200
    ) -> None:
        self.models = _MODELS if models is None else models
        self.models_status = models_status
        self.requests: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        if path.endswith("/models"):
            return httpx.Response(self.models_status, json=self.models)
        if request.method == "POST" and path.endswith("/models/download"):
            names = json.loads(request.content)["names"]
            return httpx.Response(
                202,
                json={
                    "jobs": {
                        n: {
                            "name": n,
                            "job_id": "j1",
                            "status_code": 202,
                            "message": "",
                        }
                        for n in names
                    }
                },
            )
        if path.endswith("/jobs/models/j1/status"):
            return httpx.Response(200, json={"state": "COMPLETED", "details": []})
        return httpx.Response(404, json={"message": "not found"})

    def factory(self) -> Callable[[], httpx.Client]:
        return lambda: httpx.Client(transport=httpx.MockTransport(self))

    @property
    def posts(self) -> list[str]:
        return [path for method, path in self.requests if method == "POST"]


def _api_client(**kwargs: Any) -> Callable[[], httpx.Client]:
    return _Api(**kwargs).factory()


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
            "--no-save-log",
        )
        self.assertEqual(
            cli.cli_overrides(ns),
            {
                "vippet.base_url": "http://h:1/api/v1",
                "benchmark.stream_counts": [1, 5],
                "benchmark.pipelines": ["a", "b"],
                "benchmark.filters.skip_missing_models": False,
                "results.save_log": False,
            },
        )

    def test_options_are_registered_alphabetically(self) -> None:
        flags = [
            action.option_strings[0]
            for action in cli.build_parser()._actions
            if action.option_strings and action.option_strings[0] != "-h"
        ]
        self.assertEqual(flags, sorted(flags))

    def test_help_lists_options_alphabetically(self) -> None:
        parser = cli.build_parser()
        flags = sorted(
            action.option_strings[0]
            for action in parser._actions
            if action.option_strings and action.option_strings[0] != "-h"
        )
        help_text = parser.format_help()
        # First occurrence after the usage block: "  --flag" starts a help entry.
        positions = [help_text.index(f"\n  {flag}") for flag in flags]
        self.assertEqual(positions, sorted(positions))

    def test_unset_flags_do_not_override(self) -> None:
        self.assertEqual(cli.cli_overrides(_parse()), {})

    def test_model_install_flags(self) -> None:
        ns = _parse("--install-missing-models", "yes", "--model-install-timeout", "90")
        self.assertEqual(
            cli.cli_overrides(ns),
            {
                "benchmark.models.install": "yes",
                "benchmark.models.install_timeout_seconds": 90,
            },
        )
        for argv in (
            ["--install-missing-models", "maybe"],
            ["--model-install-timeout", "0"],
            ["--model-install-timeout", "1.5"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit):
                    with patch("sys.stderr", io.StringIO()):
                        _parse(*argv)

    def test_invalid_values_rejected(self) -> None:
        for argv in (
            ["--streams", "0"],
            ["--base-url", "file:///etc/passwd"],
            ["--output-mode", "stdout"],
            ["--metrics-trim-fraction", "0.5"],
            ["--metrics-trim-fraction", "1"],
            ["--metrics-trim-fraction", "-0.1"],
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
            client_factory=_api_client(),
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

    def test_dry_run_counts_missing_model_runs_when_not_skipped(self) -> None:
        settings = resolve_settings(
            "default",
            env={},
            cli_overrides={
                "benchmark.filters.skip_pipelines": ["sp"],
                "benchmark.filters.skip_missing_models": False,
            },
        )
        out = io.StringIO()
        rc = cli.run_dry_run(
            settings,
            discover=self._discover,
            preflight=Mock(),
            client_factory=_api_client(),
            stdout=out,
            stderr=io.StringIO(),
        )
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("Matrix: 4 run(s)", text)
        self.assertIn("Missing models, will run anyway: 2 run(s)", text)
        self.assertNotIn("Skipped at run time", text)

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
            client_factory=_api_client(),
            stdout=io.StringIO(),
            stderr=err,
        )
        self.assertEqual(rc, 2)
        self.assertIn("down", err.getvalue())

    def test_discovery_failure_exits_2(self) -> None:
        err = io.StringIO()
        rc = cli.run_dry_run(
            self.settings,
            discover=Mock(side_effect=RuntimeError("boom")),
            preflight=Mock(),
            client_factory=_api_client(),
            stdout=io.StringIO(),
            stderr=err,
        )
        self.assertEqual(rc, 2)
        self.assertIn(
            "ViPPET reported ready, but reading its inventory", err.getvalue()
        )
        self.assertIn("RuntimeError: boom", err.getvalue())
        self.assertIn("To fix:", err.getvalue())

    def test_all_excluded_explains_what_to_change(self) -> None:
        out = io.StringIO()
        rc = cli.run_dry_run(
            self.settings,
            discover=lambda settings: build_matrix(
                _PIPELINES,
                [{"device_family": "GPU"}],
                {},
                MatrixFilters.from_settings(settings),
            ),
            preflight=Mock(),
            client_factory=_api_client(),
            stdout=out,
            stderr=io.StringIO(),
        )
        self.assertEqual(rc, 0)
        self.assertIn("note: All 4 discovered pipeline/variant(s)", out.getvalue())
        self.assertIn("To fix: widen --pipelines / --variants", out.getvalue())

    def test_matrix_renderer_is_shared_with_pytest(self) -> None:
        from tests.performance.perf_helpers import matrix

        self.assertIs(cli.format_matrix, matrix.format_matrix)


class TestDryRunInstallPlan(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = resolve_settings("default", env={})

    def _discover(self, settings: Any) -> Any:
        return build_matrix(
            _PIPELINES,
            [{"device_family": "CPU"}],
            {"lpr": {"LPR Net"}},
            MatrixFilters.from_settings(settings),
        )

    def _dry_run(self, api: _Api, settings: Any = None, tty: bool = False) -> Any:
        out, err = io.StringIO(), io.StringIO()
        rc = cli.run_dry_run(
            settings or self.settings,
            discover=self._discover,
            preflight=Mock(),
            client_factory=api.factory(),
            stdin_is_tty=lambda: tty,
            stdout=out,
            stderr=err,
        )
        return rc, out.getvalue(), err.getvalue()

    def test_prints_plan_and_never_installs(self) -> None:
        api = _Api()
        rc, out, _ = self._dry_run(api)
        self.assertEqual(rc, 0)
        matrix_part, plan_part = out.split("\nModel installation\n")
        self.assertIn("Matrix:", matrix_part)
        self.assertIn("LPR Net  omz", plan_part)
        self.assertIn("By installing you accept the license terms", plan_part)
        self.assertIn("stdin is not a terminal", plan_part)
        self.assertEqual(api.posts, [])

    def test_mode_effect_follows_the_setting(self) -> None:
        yes = resolve_settings(
            "default", env={}, cli_overrides={"benchmark.models.install": "yes"}
        )
        _, out, _ = self._dry_run(_Api(), settings=yes)
        self.assertIn("installs these models without asking", out)
        _, out, _ = self._dry_run(_Api(), tty=True)
        self.assertIn("asks before installing", out)

    def test_empty_plan_is_one_line(self) -> None:
        installed = [dict(_MODELS[0], install_status="installed")]
        rc, out, _ = self._dry_run(_Api(models=installed))
        self.assertEqual(rc, 0)
        self.assertIn("Every model the selected runs need is installed.", out)
        self.assertNotIn("--install-missing-models", out)

    def test_models_failure_exits_2(self) -> None:
        rc, _, err = self._dry_run(_Api(models_status=500))
        self.assertEqual(rc, 2)
        self.assertIn("reading its inventory", err)


class TestModelInstallStep(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = resolve_settings(
            "default", env={}, cli_overrides={"benchmark.stream_counts": [1]}
        )

    def _discover(self, settings: Any) -> Any:
        return build_matrix(
            _PIPELINES,
            [{"device_family": "CPU"}],
            {"lpr": {"LPR Net"}},
            MatrixFilters.from_settings(settings),
        )

    def _step(
        self,
        *,
        ask: bool,
        answer: str | None = None,
        settings: Any = None,
        api: _Api | None = None,
        preflight: Any = None,
        discover: Any = None,
    ) -> tuple[int, Any, str, str, _Api, list[str]]:
        api = api or _Api()
        prompts: list[str] = []

        def input_fn(text: str) -> str:
            prompts.append(text)
            if answer is None:
                raise AssertionError("must not prompt")
            return answer

        out, err = io.StringIO(), io.StringIO()
        rc, outcomes = cli.run_model_install(
            settings or self.settings,
            ask=ask,
            discover=discover or self._discover,
            preflight=preflight or Mock(),
            client_factory=api.factory(),
            input_fn=input_fn,
            installer_options={"sleep": lambda _: None},
            stdout=out,
            stderr=err,
        )
        return rc, outcomes, out.getvalue(), err.getvalue(), api, prompts

    def test_accepting_installs_and_returns_outcomes(self) -> None:
        rc, outcomes, out, _, api, prompts = self._step(ask=True, answer="y")
        self.assertEqual(rc, 0)
        self.assertEqual(prompts, ["Install 1 model(s) now? [y/N] "])
        self.assertEqual(api.posts, ["/api/v1/models/download"])
        self.assertEqual(
            outcomes, [ModelOutcome("lprnet", "LPR Net", Outcome.INSTALLED)]
        )
        self.assertIn("Model installation", out)
        self.assertIn("[model-install] LPR Net: installed", out)

    def test_declining_installs_nothing(self) -> None:
        rc, outcomes, out, _, api, _ = self._step(ask=True, answer="")
        self.assertEqual(rc, 0)
        self.assertEqual(api.posts, [])
        self.assertEqual([o.outcome for o in outcomes], [Outcome.DECLINED])
        self.assertIn("Not installing", out)

    def test_yes_never_prompts(self) -> None:
        rc, outcomes, _, _, api, prompts = self._step(ask=False)
        self.assertEqual(rc, 0)
        self.assertEqual(prompts, [])
        self.assertEqual(api.posts, ["/api/v1/models/download"])
        self.assertEqual([o.outcome for o in outcomes], [Outcome.INSTALLED])

    def test_readiness_check_is_quiet_unless_waiting_or_failing(self) -> None:
        def preflight(*_: Any, report: Callable[[str], None]) -> None:
            report("[pre-flight] GET http://x/health: OK (HTTP 200)")
            report("[pre-flight] GET http://x/status: WAITING (starting)")
            report("[pre-flight] GET http://x/status: READY (HTTP 200)")

        _, _, out, err, _, _ = self._step(ask=False, preflight=preflight)
        self.assertEqual(
            err.strip(), "[pre-flight] GET http://x/status: WAITING (starting)"
        )
        self.assertNotIn("pre-flight", out)

    def test_preflight_failure_exits_2(self) -> None:
        rc, outcomes, _, err, api, _ = self._step(
            ask=False, preflight=Mock(side_effect=PreflightError("down"))
        )
        self.assertEqual((rc, outcomes), (2, None))
        self.assertIn("error: down", err)
        self.assertEqual(api.requests, [])

    def test_discovery_failure_exits_2(self) -> None:
        rc, outcomes, _, err, _, _ = self._step(
            ask=False, discover=Mock(side_effect=RuntimeError("boom"))
        )
        self.assertEqual((rc, outcomes), (2, None))
        self.assertIn("reading its inventory", err)

    def test_unknown_filter_ids_skip_the_step(self) -> None:
        settings = resolve_settings(
            "default", env={}, cli_overrides={"benchmark.pipelines": ["nope"]}
        )
        rc, outcomes, out, _, api, _ = self._step(ask=False, settings=settings)
        self.assertEqual((rc, outcomes), (0, None))
        self.assertEqual(api.requests, [])
        self.assertEqual(out, "")

    def test_unknown_filter_ids_with_warn_still_offer(self) -> None:
        settings = resolve_settings(
            "default",
            env={},
            cli_overrides={
                "benchmark.pipelines": ["lpr", "nope"],
                "benchmark.filters.on_unknown_id": "warn",
            },
        )
        rc, outcomes, _, _, _, _ = self._step(ask=False, settings=settings)
        self.assertEqual(rc, 0)
        self.assertEqual([o.name for o in outcomes], ["lprnet"])


class TestMainInstallStep(unittest.TestCase):
    def _main(
        self, mode: str, *, tty: bool, step: Any = None
    ) -> tuple[int, Mock, Mock]:
        step = step or Mock(return_value=(0, []))
        runner = Mock(return_value=0)
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(cli, "run_model_install", step),
            patch.object(cli, "run_pytest", runner),
            patch.object(cli, "_stdin_is_tty", return_value=tty),
            patch("sys.stderr", io.StringIO()),
        ):
            os.environ.pop("PERF_INSTALL_MISSING_MODELS", None)
            rc = cli.main(["--config", "quick", "--install-missing-models", mode])
        return rc, step, runner

    def test_no_never_runs_the_step(self) -> None:
        rc, step, runner = self._main("no", tty=True)
        self.assertEqual(rc, 0)
        step.assert_not_called()
        self.assertEqual(runner.call_args.kwargs["extra_env"], {})

    def test_ask_without_terminal_behaves_like_no(self) -> None:
        _, step, runner = self._main("ask", tty=False)
        step.assert_not_called()
        runner.assert_called_once()

    def test_ask_with_terminal_prompts(self) -> None:
        _, step, _ = self._main("ask", tty=True)
        self.assertIs(step.call_args.kwargs["ask"], True)

    def test_yes_installs_without_terminal(self) -> None:
        _, step, _ = self._main("yes", tty=False)
        self.assertIs(step.call_args.kwargs["ask"], False)

    def test_outcome_is_passed_to_pytest(self) -> None:
        outcome = ModelOutcome("m", "M", Outcome.FAILED, "no token")
        _, _, runner = self._main(
            "yes", tty=False, step=Mock(return_value=(0, [outcome]))
        )
        extra_env = runner.call_args.kwargs["extra_env"]
        self.assertEqual(decode_outcomes(extra_env[ENV_MODEL_INSTALL]), [outcome])

    def test_skipped_step_passes_no_outcome(self) -> None:
        _, _, runner = self._main("yes", tty=False, step=Mock(return_value=(0, None)))
        self.assertEqual(runner.call_args.kwargs["extra_env"], {})

    def test_step_failure_stops_the_run(self) -> None:
        rc, _, runner = self._main("yes", tty=False, step=Mock(return_value=(2, None)))
        self.assertEqual(rc, 2)
        runner.assert_not_called()

    def test_ctrl_c_at_the_prompt_aborts(self) -> None:
        rc, _, runner = self._main(
            "ask", tty=True, step=Mock(side_effect=KeyboardInterrupt)
        )
        self.assertEqual(rc, 130)
        runner.assert_not_called()

    def test_env_exported_by_discovery_does_not_reach_pytest(self) -> None:
        def step(*_: Any, **__: Any) -> tuple[int, list[Any]]:
            os.environ["VIPPET_BASE_URL"] = "http://exported/api/v1"
            return 0, []

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VIPPET_BASE_URL", None)
            _, _, runner = self._main("yes", tty=False, step=step)
        self.assertNotIn("VIPPET_BASE_URL", runner.call_args.kwargs["base_env"])


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
    def test_passes_cli_layer_to_pytest(self) -> None:
        overrides = {
            "vippet.base_url": "http://cli:9/api/v1",
            "benchmark.stream_counts": [7],
        }
        settings = resolve_settings("quick", env={}, cli_overrides=overrides)
        cli_layer = {"config": "quick", "overrides": overrides}
        seen: dict[str, Any] = {}

        def runner(cmd: list[str], env: dict[str, str], check: bool) -> Any:
            seen["cmd"] = cmd
            seen["env"] = env
            seen["reloaded"] = resolve_settings(env=env, **read_cli_layer(env))
            return subprocess.CompletedProcess(cmd, 5)

        rc = cli.run_pytest(cli_layer, ["-k", "x"], base_env={}, runner=runner)

        self.assertEqual(rc, 5)
        self.assertEqual(seen["cmd"][1:5], ["-m", "pytest", "-m", "perf"])
        self.assertEqual(seen["cmd"][-2:], ["-k", "x"])
        self.assertIn(str(cli.PERF_DIR), seen["cmd"])
        self.assertNotIn(ENV_CONFIG_FILE, seen["env"])
        # Resolved values are not exported, or they would show up as "env".
        self.assertNotIn("VIPPET_BASE_URL", seen["env"])
        self.assertEqual(seen["reloaded"]["benchmark.stream_counts"], [7])
        self.assertEqual(dict(seen["reloaded"].values), dict(settings.values))
        # Same sources as the CLI's own resolution, so the artefact is accurate.
        self.assertEqual(dict(seen["reloaded"].sources), dict(settings.sources))
        self.assertEqual(seen["reloaded"].sources["vippet.base_url"], "cli")

    def test_model_outcome_env_comes_only_from_the_cli(self) -> None:
        seen: list[dict[str, str]] = []

        def runner(cmd: list[str], env: dict[str, str], check: bool) -> Any:
            seen.append(env)
            return subprocess.CompletedProcess(cmd, 0)

        layer = {"config": None, "overrides": {}}
        stale = {ENV_MODEL_INSTALL: "[stale]"}
        cli.run_pytest(layer, [], base_env=stale, runner=runner)
        cli.run_pytest(
            layer,
            [],
            base_env=stale,
            extra_env={ENV_MODEL_INSTALL: "[]"},
            runner=runner,
        )
        self.assertNotIn(ENV_MODEL_INSTALL, seen[0])
        self.assertEqual(seen[1][ENV_MODEL_INSTALL], "[]")

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
