# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-test ViPPET pre-flight."""

import unittest
from collections.abc import Callable
from unittest.mock import Mock, patch

import httpx

from tests.performance.perf_helpers import preflight


class _FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += seconds


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestPerformancePreflight(unittest.TestCase):
    def test_ready_service_reports_health_and_status(self) -> None:
        requested_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json={"healthy": True})
            return httpx.Response(
                200, json={"status": "ready", "ready": True, "message": None}
            )

        reports: list[str] = []
        with _client(handler) as client:
            preflight.wait_for_vippet_ready(
                "http://localhost/api/v1/",
                60,
                2,
                10,
                client=client,
                report=reports.append,
            )

        self.assertEqual(requested_paths, ["/api/v1/health", "/api/v1/status"])
        self.assertIn("GET http://localhost/api/v1/health: OK", reports[0])
        self.assertIn("GET http://localhost/api/v1/status: READY", reports[1])

    def test_initializing_service_is_polled_until_ready(self) -> None:
        status_responses = iter(
            [
                {"status": "initializing", "ready": False, "message": "Loading"},
                {"status": "ready", "ready": True, "message": None},
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json={"healthy": True})
            return httpx.Response(200, json=next(status_responses))

        clock = _FakeClock()
        reports: list[str] = []
        with _client(handler) as client:
            preflight.wait_for_vippet_ready(
                "http://localhost/api/v1",
                60,
                2,
                10,
                client=client,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
                report=reports.append,
            )

        self.assertEqual(clock.current, 2)
        self.assertTrue(any("status='initializing'" in line for line in reports))
        self.assertIn("READY", reports[-1])

    def test_unreachable_health_endpoint_is_actionable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        reports: list[str] = []
        with _client(handler) as client:
            with self.assertRaisesRegex(
                preflight.PreflightError, r"/health.*connection refused.*Remedy"
            ):
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1",
                    60,
                    2,
                    10,
                    client=client,
                    report=reports.append,
                )

        self.assertIn("/health: FAILED", reports[-1])

    def test_malformed_health_payload_is_fatal(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"healthy": True}])

        with _client(handler) as client:
            with self.assertRaisesRegex(
                preflight.PreflightError, "expected an object, got list"
            ):
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1", 60, 2, 10, client=client
                )

    def test_status_timeout_reports_last_observed_state(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json={"healthy": True})
            return httpx.Response(
                200,
                json={
                    "status": "initializing",
                    "ready": False,
                    "message": "Loading models",
                },
            )

        clock = _FakeClock()
        with _client(handler) as client:
            with self.assertRaises(preflight.PreflightError) as context:
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1",
                    5,
                    2,
                    10,
                    client=client,
                    monotonic=clock.monotonic,
                    sleep=clock.sleep,
                    report=lambda _message: None,
                )

        message = str(context.exception)
        self.assertIn("timed out after 5s", message)
        self.assertIn("/status", message)
        self.assertIn("status='initializing'", message)
        self.assertIn("message='Loading models'", message)
        self.assertIn("Remedy:", message)

    @patch.object(preflight.pytest, "exit")
    @patch.object(
        preflight,
        "wait_for_vippet_ready",
        side_effect=preflight.PreflightError("service unavailable"),
    )
    def test_fatal_preflight_uses_dedicated_exit_code(
        self, _mock_wait: Mock, mock_exit: Mock
    ) -> None:
        preflight.run_preflight_or_exit("http://localhost/api/v1", 60, 2, 10)

        mock_exit.assert_called_once_with(
            "service unavailable", returncode=preflight.FATAL_PREFLIGHT_EXIT_CODE
        )
        self.assertEqual(preflight.FATAL_PREFLIGHT_EXIT_CODE, 2)


if __name__ == "__main__":
    unittest.main()
