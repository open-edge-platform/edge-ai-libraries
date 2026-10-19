# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance suite's console output and error texts.

Covers the pure message builders and, end to end, the order of the console
sections of a real pytest run against an in-process fake ViPPET.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tests.performance.perf_helpers import job_outcome
from tests.performance.perf_helpers.matrix import (
    MatrixFilters,
    build_matrix,
    describe_no_cases,
    describe_unknown_filter_ids,
    find_unknown_filter_ids,
)
from tests.performance.perf_helpers.preflight import format_discovered_hardware
from tests.performance.perf_helpers.settings import PERF_DIR

_PIPELINES = [
    {"id": "od", "name": "Object Detection", "variants": [{"id": "1", "name": "CPU"}]},
    {"id": "lpr", "name": "LPR", "variants": [{"id": "2", "name": "CPU"}]},
]


class TestMatrixMessages(unittest.TestCase):
    def test_all_excluded_points_at_table_and_flags(self) -> None:
        matrix = build_matrix(
            _PIPELINES, [{"device_family": "GPU"}], {}, MatrixFilters()
        )
        message = describe_no_cases(matrix)
        self.assertIn("All 2 discovered pipeline/variant(s) were excluded", message)
        self.assertIn("'Excluded' table", message)
        self.assertIn("To fix:", message)
        self.assertIn("--variants", message)

    def test_empty_inventory(self) -> None:
        matrix = build_matrix([], [{"device_family": "CPU"}], {}, MatrixFilters())
        message = describe_no_cases(matrix)
        self.assertIn("no pipelines with variants", message)
        self.assertIn("To fix:", message)


class TestUnknownFilterIds(unittest.TestCase):
    def test_finds_every_kind_of_unknown_id(self) -> None:
        filters = MatrixFilters(
            pipelines=["od", "nope"],
            variants=("cpu", "fpga"),
            skip_pipelines=("LPR", "ghost"),
            skip_variants=("tpu",),
        )
        issues = find_unknown_filter_ids(filters, ["od", "lpr"])
        self.assertEqual(
            [(i.key, i.value) for i in issues],
            [
                ("benchmark.pipelines", "nope"),
                ("benchmark.filters.skip_pipelines", "ghost"),
                ("benchmark.filters.skip_variants", "tpu"),
                ("benchmark.variants", "fpga"),
            ],
        )

    def test_wildcard_and_known_ids_are_accepted(self) -> None:
        self.assertEqual(find_unknown_filter_ids(MatrixFilters(), ["od"]), [])

    def test_message_names_flag_valid_values_and_fix(self) -> None:
        issues = find_unknown_filter_ids(
            MatrixFilters(pipelines=["nope"], variants=("fpga",)), ["od", "lpr"]
        )
        message = describe_unknown_filter_ids(issues, "/cfg/default.yaml")
        self.assertTrue(message.startswith("2 benchmark filter id(s)"))
        self.assertIn(
            "'nope' in benchmark.pipelines (--pipelines) is not a known "
            "pipeline id; valid values: lpr, od",
            message,
        )
        self.assertIn("'fpga' in benchmark.variants (--variants)", message)
        self.assertIn("device family; valid values: CPU, GPU, NPU", message)
        self.assertIn(
            "To fix: correct or remove these ids in /cfg/default.yaml", message
        )
        self.assertIn("PERF_ON_UNKNOWN_ID=warn", message)


class TestHardwareLines(unittest.TestCase):
    def test_groups_devices_by_family(self) -> None:
        lines = format_discovered_hardware(
            [
                {"device_family": "GPU", "full_device_name": "Arc A770"},
                {"device_family": "cpu", "full_device_name": "Core Ultra 7"},
                {"device_family": "GPU", "full_device_name": "Arc A770"},
                {"device_family": "FPGA", "full_device_name": "ignored"},
            ],
            "2026.1.0",
        )
        self.assertEqual(
            lines,
            ["ViPPET version: 2026.1.0", "CPU: Core Ultra 7", "GPU: Arc A770"],
        )

    def test_no_devices_is_explained(self) -> None:
        lines = format_discovered_hardware([], "Unknown")
        self.assertEqual(lines[0], "ViPPET version: Unknown")
        self.assertIn("No CPU, GPU or NPU device was discovered", lines[1])
        self.assertIn("To fix:", lines[1])


class TestJobOutcomeMessages(unittest.TestCase):
    LABEL = "pipeline_id=od variant_id=1 streams=3"
    BASE = "http://h/api/v1"

    def test_timeout_suggests_job_duration_flags(self) -> None:
        message = job_outcome.describe_job_failure(
            self.LABEL,
            {"state": "TIMEOUT", "job_id": "j1", "error_message": "slow"},
            2,
            self.BASE,
        )
        self.assertIn(f"{self.LABEL} did not complete", message)
        self.assertIn(
            "attempt 2 of 2 ended in state TIMEOUT (job_id=j1): slow", message
        )
        self.assertIn("--max-job-duration", message)
        self.assertIn("--max-runtime", message)

    def test_conflict_explains_single_job_slot(self) -> None:
        message = job_outcome.describe_job_failure(
            self.LABEL, {"state": "CONFLICT"}, 1, self.BASE
        )
        self.assertIn("one job at a time", message)
        self.assertIn("ViPPET returned no error message", message)
        self.assertIn("To fix: wait", message)

    def test_failed_points_at_job_logs_and_status_url(self) -> None:
        message = job_outcome.describe_job_failure(
            self.LABEL,
            {"state": "FAILED", "job_id": "j9", "error_message": "no model"},
            1,
            self.BASE,
        )
        self.assertIn("pipeline itself failed", message)
        self.assertIn("ViPPET logs for job j9", message)
        self.assertIn(f"{self.BASE}/jobs/tests/performance/j9/status", message)

    def test_zero_fps(self) -> None:
        message = job_outcome.describe_zero_fps(
            self.LABEL,
            {"job_id": "j1", "total_fps": 0, "per_stream_fps": 0},
            self.BASE,
        )
        self.assertIn("processed no frames", message)
        self.assertIn("To fix:", message)

    def test_rejected_submission_client_and_server_errors(self) -> None:
        client = job_outcome.describe_rejected_submission(
            self.LABEL, 422, '{"detail":\n "bad variant"}'
        )
        self.assertIn('HTTP 422: {"detail": "bad variant"}', client)
        self.assertIn("--dry-run", client)
        server = job_outcome.describe_rejected_submission(self.LABEL, 500, "")
        self.assertIn("HTTP 500: (empty response)", server)
        self.assertIn("docker compose logs", server)
        long = job_outcome.describe_rejected_submission(self.LABEL, 400, "x" * 1000)
        self.assertNotIn("x" * 301, long)

    def test_connection_lost(self) -> None:
        message = job_outcome.describe_connection_lost(
            self.LABEL, self.BASE, ConnectionError("reset")
        )
        self.assertIn(f"Lost contact with ViPPET at {self.BASE}", message)
        self.assertIn("ConnectionError: reset", message)
        self.assertIn("To fix:", message)

    def test_missing_hw_samples(self) -> None:
        results = [
            {"status": "success", "hw_metrics": {"sample_count": 0}},
            {"status": "failed", "hw_metrics": {"sample_count": 4}},
            {"status": "skipped", "hw_metrics": {"sample_count": 0}},
        ]
        message = job_outcome.describe_missing_hw_samples(results, "http://m/metrics")
        assert message is not None
        self.assertIn("from http://m/metrics for 1 of 2 test(s)", message)
        self.assertIn("--metrics-url", message)
        self.assertIsNone(
            job_outcome.describe_missing_hw_samples(results[1:], "http://m")
        )


# --------------------------------------------------------------------------- #
# End to end: pytest run against a fake ViPPET
# --------------------------------------------------------------------------- #


class _FakeVippet(BaseHTTPRequestHandler):
    job_state = "COMPLETED"
    status_polls = 0  # the first job status poll answers RUNNING

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - quiet
        pass

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        job_path = "/api/v1/jobs/tests/performance/j1/status"
        if self.path == job_path:
            type(self).status_polls += 1
        state = "RUNNING" if type(self).status_polls <= 1 else self.job_state
        routes: dict[str, Any] = {
            "/api/v1/health": {"healthy": True},
            "/api/v1/status": {"ready": True, "status": "ready", "version": "9.9"},
            "/api/v1/devices": [
                {
                    "device_name": "CPU",
                    "device_family": "CPU",
                    "full_device_name": "Fake CPU",
                }
            ],
            "/api/v1/pipelines": _PIPELINES,
            "/api/v1/models": [
                {
                    "display_name": "LPR Net",
                    "install_status": "not_installed",
                    "used_by_pipelines": ["lpr"],
                }
            ],
            "/api/v1/capabilities": {},
            job_path: {
                "job_id": "j1",
                "state": state,
                "total_fps": 30.0,
                "per_stream_fps": 30.0,
                "error_message": "decoder crashed"
                if self.job_state == "FAILED"
                else None,
            },
        }
        if self.path in routes:
            self._send(200, routes[self.path])
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send(200, {"job_id": "j1"})


class TestConsoleOutputEndToEnd(unittest.TestCase):
    def _run(
        self,
        job_state: str,
        pipelines: str = '"*"',
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        handler = type("Handler", (_FakeVippet,), {"job_state": job_state})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}/api/v1"

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        config = tmp / "perf.yaml"
        config.write_text(
            "vippet:\n  poll_interval: 0.1\n  readiness_timeout_seconds: 10\n"
            f"benchmark:\n  pipelines: {pipelines}\n"
            "  variants: [cpu]\n  stream_counts: [1]\n"
            "  execution:\n    max_retries: 0\n"
            "metrics:\n  sample_interval_seconds: 0.1\n"
            f"results:\n  output_dir: {json.dumps(str(tmp / 'results'))}\n"
            "  formats: [json]\n",
            encoding="utf-8",
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PERF_", "VIPPET_"))
        }
        env.update(
            {
                "PERF_CONFIG_FILE": str(config),
                "VIPPET_BASE_URL": base,
                "VIPPET_CAPABILITIES_URL": f"{base}/capabilities",
                **(extra_env or {}),
            }
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "perf",
                "-p",
                "no:cacheprovider",
                str(PERF_DIR),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def _assert_in_order(self, text: str, *needles: str) -> None:
        positions = []
        for needle in needles:
            self.assertIn(needle, text)
            positions.append(text.index(needle))
        self.assertEqual(positions, sorted(positions), f"wrong order in:\n{text}")

    def test_normal_run_shows_every_section_in_order(self) -> None:
        completed = self._run("COMPLETED")
        out = completed.stdout
        self.assertEqual(completed.returncode, 0, out + completed.stderr)
        self._assert_in_order(
            out,
            "test session starts",
            "ViPPET readiness",
            "/status: READY",
            "Discovered hardware",
            "CPU: Fake CPU",
            "Benchmark matrix",
            "Matrix: 1 run(s)",
            "Skipped at run time: missing_models: 1 run(s)",
            "[object_detection_cpu_x1] PASSED",
            "[lpr_cpu_x1] SKIPPED",
            "Benchmark artefacts",
            "No hardware metrics were sampled",
            "HTML report",
        )
        self.assertNotIn("Traceback", out + completed.stderr)

    def test_failed_job_is_explained_without_traceback(self) -> None:
        completed = self._run("FAILED")
        out = completed.stdout
        self.assertEqual(completed.returncode, 1, out + completed.stderr)
        self.assertIn("ended in state FAILED (job_id=j1): decoder crashed", out)
        self.assertIn("To fix: check the ViPPET logs for job j1", out)
        self.assertNotIn("AssertionError", out)
        self.assertNotIn("Traceback", out)

    def test_unknown_filter_id_aborts_with_explanation(self) -> None:
        completed = self._run("COMPLETED", pipelines="[od, nope]")
        text = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 4, text)
        self.assertIn("error: 1 benchmark filter id(s)", text)
        self.assertIn("'nope' in benchmark.pipelines (--pipelines)", text)
        self.assertIn("valid values: lpr, od", text)
        self.assertIn("PERF_ON_UNKNOWN_ID=warn", text)
        self.assertIn("Invalid benchmark filter ids (see the error above)", text)
        self.assertNotIn("Traceback", text)
        # The error comes after the matrix, on its own line.
        self._assert_in_order(
            completed.stdout,
            "Benchmark matrix",
            "Matrix: 1 run(s)",
            "\nerror: 1 benchmark filter id(s)",
        )

    def test_unknown_filter_id_in_warn_mode_skips_it(self) -> None:
        completed = self._run(
            "COMPLETED",
            pipelines="[od, nope]",
            extra_env={"PERF_ON_UNKNOWN_ID": "warn"},
        )
        out = completed.stdout
        self.assertEqual(completed.returncode, 0, out + completed.stderr)
        self._assert_in_order(
            out,
            "Matrix: 1 run(s)",
            "\nwarning: 1 benchmark filter id(s)",
            "[object_detection_cpu_x1] PASSED",
            "[invalid_pipelines_nope_x1] SKIPPED",
        )
        self.assertIn("To fix: correct or remove it in", out)


if __name__ == "__main__":
    unittest.main()
