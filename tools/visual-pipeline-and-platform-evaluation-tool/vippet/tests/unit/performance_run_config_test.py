# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the result "config" block and replay comparison."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.performance.perf_helpers import run_config
from tests.performance.perf_helpers.matrix import Matrix, MatrixFilters, build_matrix
from tests.performance.perf_helpers.settings import ResolvedSettings, resolve_settings

_PIPELINES = [
    {"id": "od", "name": "Object Detection", "variants": [{"id": "1", "name": "CPU"}]},
    {"id": "lpr", "name": "LPR", "variants": [{"id": "2", "name": "CPU"}]},
]
_SELECTION = [
    {"pipeline_id": "od", "variant_id": "1", "streams": 1, "test_id": "t_od"},
    {"pipeline_id": "lpr", "variant_id": "2", "streams": 1, "test_id": "t_lpr"},
]
_REVISIONS = {"suite": "abc", "vippet": "9.9"}


def _matrix(
    settings: ResolvedSettings,
    pipelines: list[dict[str, Any]] = _PIPELINES,
    missing: dict[str, set[str]] | None = None,
) -> Matrix:
    return build_matrix(
        pipelines,
        [{"device_family": "CPU"}],
        missing or {},
        MatrixFilters.from_settings(settings),
    )


class TestCompareWithRecording(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        recorded = resolve_settings("default", env={})
        config = run_config.build_config_block(
            recorded,
            matrix=_matrix(recorded),
            selection=_SELECTION,
            revisions=_REVISIONS,
            pytest_args=[],
            filter_problem=None,
            replay=None,
        )
        self.path = self.tmp / "bench_1.json"
        self.path.write_text(
            json.dumps({"benchmark_id": "bench_1", "test_cases": [], "config": config}),
            encoding="utf-8",
        )

    def _compare(
        self, env: dict[str, str] | None = None, **matrix_args: Any
    ) -> dict[str, Any]:
        settings = resolve_settings(self.path, env=env or {})
        return run_config.compare_with_recording(
            settings, _matrix(settings, **matrix_args), _REVISIONS, _SELECTION
        )

    def test_identical_run_has_no_differences(self) -> None:
        replay = self._compare()
        self.assertEqual(replay["benchmark_id"], "bench_1")
        for key in ("setting_changes", "revision_changes", "matrix_drift", "notes"):
            self.assertEqual(replay[key], [], key)

    def test_only_changes_to_what_runs_are_drift(self) -> None:
        extra = {"id": "new", "name": "New", "variants": [{"id": "3", "name": "NPU"}]}
        replay = self._compare(
            pipelines=[*_PIPELINES, extra], missing={"lpr": {"LPR Net"}}
        )
        self.assertEqual(replay["matrix_drift"], ["added missing models: lpr: LPR Net"])
        self.assertIn("added exclusion: new/NPU (unsupported_family)", replay["notes"])
        self.assertIn("added pipeline id: new", replay["notes"])

        replay = self._compare(pipelines=_PIPELINES[:1])
        self.assertIn("removed case: lpr/2 (CPU)", replay["matrix_drift"])

    def test_selection_and_revision_changes(self) -> None:
        settings = resolve_settings(self.path, env={})
        replay = run_config.compare_with_recording(
            settings, _matrix(settings), {"suite": "def"}, _SELECTION[:1]
        )
        self.assertEqual(replay["matrix_drift"], ["removed test: lpr/2 x1"])
        self.assertEqual(replay["revision_changes"], ["suite: abc -> def"])

    def test_env_override_is_listed_and_stale_metrics_host_noted(self) -> None:
        replay = self._compare(env={"VIPPET_BASE_URL": "http://other:1/api/v1"})
        self.assertEqual(
            replay["setting_changes"],
            [
                "vippet.base_url: 'http://localhost/api/v1' -> 'http://other:1/api/v1' (env)"
            ],
        )
        self.assertIn("--metrics-url and --capabilities-url", replay["notes"][-1])
        self.assertEqual(replay["matrix_drift"], [])

    def test_format_lists_every_section(self) -> None:
        text = run_config.format_replay(self._compare(pipelines=_PIPELINES[:1]))
        self.assertIn("Replay of bench_1", text)
        self.assertIn("Setting changes: (none)", text)
        self.assertIn("Matrix drift: 1\n  removed case: lpr/2 (CPU)", text)


class TestSuiteRevision(unittest.TestCase):
    def test_unknown_without_git(self) -> None:
        for error in (OSError("no git"), subprocess.CalledProcessError(128, "git")):
            with self.subTest(error=error):
                with patch.object(run_config.subprocess, "run", side_effect=error):
                    self.assertEqual(run_config.suite_revision(), "unknown")

    def test_dirty_working_copy_is_marked(self) -> None:
        outputs = iter(["abc123\n", " M conftest.py\n"])
        with patch.object(
            run_config.subprocess,
            "run",
            side_effect=lambda *a, **k: subprocess.CompletedProcess(
                a, 0, next(outputs)
            ),
        ):
            self.assertEqual(run_config.suite_revision(), "abc123-dirty")


if __name__ == "__main__":
    unittest.main()
