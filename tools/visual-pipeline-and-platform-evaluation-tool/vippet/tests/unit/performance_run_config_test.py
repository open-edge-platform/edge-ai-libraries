# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the result ``config`` block and loading it as ``--config``."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.performance.perf_helpers import settings as s
from tests.performance.perf_helpers.matrix import MatrixFilters, build_matrix
from tests.performance.perf_helpers.reporters import (
    ReportInputError,
    generate_html_report,
    load_result,
)
from tests.performance.perf_helpers.run_config import build_config_block

_PIPELINES = [
    {
        "id": "p1",
        "name": "P1",
        "variants": [{"id": "v1", "name": "CPU"}, {"id": "v2", "name": "NPU"}],
    }
]
_DEVICES = [{"device_family": "CPU"}]


def _result(config: dict[str, Any] | None, benchmark_id: str = "bench_1") -> dict:
    result: dict[str, Any] = {
        "benchmark_id": benchmark_id,
        "timestamp": "2026-11-02T10:00:00",
        "duration_seconds": 1.0,
        "test_cases": [],
        "summary": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
        "hardware": {},
        "system_info": {},
    }
    if config is not None:
        result["config"] = config
    return result


class TestBuildConfigBlock(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = s.resolve_settings(
            "quick",
            env={"VIPPET_JOB_POLL_INTERVAL": "0.5"},
            cli_overrides={"benchmark.stream_counts": [7]},
        )
        matrix = build_matrix(
            _PIPELINES, _DEVICES, {}, MatrixFilters.from_settings(self.settings)
        )
        self.block = build_config_block(
            self.settings, matrix=matrix, vippet_version="1.2.3"
        )

    def test_records_selector_values_and_sources(self) -> None:
        self.assertEqual(self.block["selector"]["value"], "quick")
        self.assertEqual(self.block["values"], dict(self.settings.values))
        self.assertEqual(self.block["sources"]["benchmark.stream_counts"], "cli")
        self.assertEqual(self.block["sources"]["vippet.poll_interval"], "env")
        self.assertEqual(set(self.block["sources"]), set(self.block["values"]))

    def test_records_applied_filters_and_exclusions(self) -> None:
        filters = self.block["filters"]
        self.assertEqual(filters["applied"]["stream_counts"], [7])
        self.assertEqual(
            [
                (e["pipeline_id"], e["variant"], e["reason"])
                for e in filters["excluded"]
            ],
            [("p1", "NPU", "variant_filter")],
        )

    def test_records_revisions_and_is_json_serialisable(self) -> None:
        self.assertEqual(self.block["revisions"]["vippet"], "1.2.3")
        self.assertIn("suite", self.block["revisions"])
        json.dumps(self.block)


class TestConfigFromResult(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run_dir = Path(tmp.name) / "bench_1"
        self.run_dir.mkdir()
        self.settings = s.resolve_settings(
            "quick", env={}, cli_overrides={"benchmark.stream_counts": [7]}
        )
        block = build_config_block(self.settings, matrix=None, vippet_version="x")
        self.path = self.run_dir / "bench_1.json"
        self.path.write_text(json.dumps(_result(block)), encoding="utf-8")

    def test_json_and_run_dir_reproduce_values(self) -> None:
        for target in (self.path, self.run_dir):
            with self.subTest(target=str(target)):
                reloaded = s.resolve_settings(str(target), env={})
                self.assertEqual(dict(reloaded.values), dict(self.settings.values))
                self.assertEqual(reloaded.sources["benchmark.stream_counts"], "yaml")

    def test_env_and_cli_override_recorded_values(self) -> None:
        reloaded = s.resolve_settings(
            str(self.path),
            env={"VIPPET_JOB_POLL_INTERVAL": "9"},
            cli_overrides={"benchmark.stream_counts": [2]},
        )
        self.assertEqual(reloaded["benchmark.stream_counts"], [2])
        self.assertEqual(reloaded["vippet.poll_interval"], 9.0)

    def test_result_without_config_is_rejected(self) -> None:
        self.path.write_text(json.dumps(_result(None)), encoding="utf-8")
        with self.assertRaisesRegex(s.SettingsError, "no config.values"):
            s.resolve_settings(str(self.path), env={})

    def test_result_with_other_setting_keys_is_rejected(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["config"]["values"]["bogus.key"] = 1
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(s.SettingsError, "different suite version"):
            s.resolve_settings(str(self.path), env={})

    def test_cli_layer_round_trip(self) -> None:
        layer = {"config": "quick", "overrides": {"benchmark.stream_counts": [7]}}
        kwargs = s.read_cli_layer({s.ENV_CLI_LAYER: json.dumps(layer)})
        resolved = s.resolve_settings(env={}, **kwargs)
        self.assertEqual(resolved["benchmark.stream_counts"], [7])
        self.assertEqual(resolved.sources["benchmark.stream_counts"], "cli")
        self.assertEqual(resolved.config_selector, "quick")

    def test_invalid_cli_layer_is_rejected(self) -> None:
        for raw in ("not json", json.dumps({"config": 1, "overrides": {}})):
            with self.subTest(raw=raw), self.assertRaises(s.SettingsError):
                s.read_cli_layer({s.ENV_CLI_LAYER: raw})


class TestReportConfig(unittest.TestCase):
    def test_result_without_config_still_loads_and_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench_1.json"
            path.write_text(json.dumps(_result(None)), encoding="utf-8")
            data = load_result(path)
        html = generate_html_report([data])
        self.assertNotIn('id="configuration"', html)

    def test_config_is_rendered_with_sources_and_filters(self) -> None:
        settings = s.resolve_settings(
            "quick", env={}, cli_overrides={"benchmark.stream_counts": [7]}
        )
        block = build_config_block(settings, matrix=None, vippet_version="1.2.3")
        html = generate_html_report([_result(block)])
        self.assertIn('id="configuration"', html)
        self.assertIn("benchmark.stream_counts", html)
        self.assertIn(">cli<", html)
        self.assertIn("Revision: vippet", html)

    def test_malformed_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench_1.json"
            path.write_text(json.dumps(_result({"selector": {}})), encoding="utf-8")
            with self.assertRaisesRegex(ReportInputError, "config.selector"):
                load_result(path)


if __name__ == "__main__":
    unittest.main()
