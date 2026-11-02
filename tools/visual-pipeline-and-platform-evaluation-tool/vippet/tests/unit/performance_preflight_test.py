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
            with self.assertRaises(preflight.PreflightError) as context:
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1",
                    60,
                    2,
                    10,
                    client=client,
                    report=reports.append,
                )

        self.assertIn("/health: FAILED", reports[-1])
        message = str(context.exception)
        self.assertIn("Cannot reach ViPPET at http://localhost/api/v1/health", message)
        self.assertIn("connection refused", message)
        self.assertIn("not running, or the base URL points at the wrong", message)
        self.assertIn("To fix:", message)
        self.assertIn("--base-url / VIPPET_BASE_URL", message)
        self.assertIn("(currently http://localhost/api/v1)", message)

    def _health_failure(self, response: httpx.Response) -> str:
        with _client(lambda _request: response) as client:
            with self.assertRaises(preflight.PreflightError) as context:
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1",
                    60,
                    2,
                    10,
                    client=client,
                    report=lambda _message: None,
                )
        return str(context.exception)

    def test_health_404_points_at_base_url_path(self) -> None:
        message = self._health_failure(httpx.Response(404, json={"detail": "x"}))
        self.assertIn("answered, but not like the ViPPET API (HTTP 404)", message)
        self.assertIn("To fix:", message)
        self.assertIn("ends in /api/v1", message)

    def test_health_non_json_points_at_wrong_service(self) -> None:
        message = self._health_failure(httpx.Response(200, text="<html>hi</html>"))
        self.assertIn("not like the ViPPET API (JSONDecodeError", message)
        self.assertIn("different service or path", message)

    def test_health_server_error_points_at_backend_logs(self) -> None:
        message = self._health_failure(httpx.Response(502, text="Bad Gateway"))
        self.assertIn("answered with HTTP 502", message)
        self.assertIn("backend is down, restarting or crashed", message)
        self.assertIn("To fix: check 'docker compose ps'", message)

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
        self.assertIn("is reachable but did not report ready within 5s", message)
        self.assertIn("/status", message)
        self.assertIn("status='initializing'", message)
        self.assertIn("message='Loading models'", message)
        self.assertIn("still starting up", message)
        self.assertIn("To fix:", message)
        self.assertIn("--readiness-timeout (currently 5s)", message)

    def test_status_errors_until_deadline_are_reported_as_not_ready(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json={"healthy": True})
            return httpx.Response(503, json={"detail": "starting"})

        clock = _FakeClock()
        with _client(handler) as client:
            with self.assertRaises(preflight.PreflightError) as context:
                preflight.wait_for_vippet_ready(
                    "http://localhost/api/v1",
                    3,
                    2,
                    10,
                    client=client,
                    monotonic=clock.monotonic,
                    sleep=clock.sleep,
                    report=lambda _message: None,
                )

        message = str(context.exception)
        self.assertIn("did not report ready within 3s", message)
        self.assertIn("HTTPStatusError", message)

    @patch.object(preflight.pytest, "exit")
    @patch.object(
        preflight,
        "wait_for_vippet_ready",
        side_effect=preflight.PreflightError("service unavailable"),
    )
    def test_fatal_preflight_uses_dedicated_exit_code(
        self, _mock_wait: Mock, mock_exit: Mock
    ) -> None:
        errors: list[str] = []
        preflight.run_preflight_or_exit(
            "http://localhost/api/v1",
            60,
            2,
            10,
            client=Mock(spec=httpx.Client),
            report_error=errors.append,
        )

        # The full explanation is reported; pytest's banner gets a pointer.
        self.assertEqual(errors, ["service unavailable"])
        mock_exit.assert_called_once_with(
            preflight.FATAL_PREFLIGHT_EXIT_REASON,
            returncode=preflight.FATAL_PREFLIGHT_EXIT_CODE,
        )
        self.assertIn("see the error above", preflight.FATAL_PREFLIGHT_EXIT_REASON)
        self.assertEqual(preflight.FATAL_PREFLIGHT_EXIT_CODE, 2)

    @patch.object(preflight, "wait_for_vippet_ready")
    def test_preflight_report_is_forwarded(self, mock_wait: Mock) -> None:
        reports: list[str] = []
        preflight.run_preflight_or_exit(
            "http://localhost/api/v1",
            60,
            2,
            10,
            client=Mock(spec=httpx.Client),
            report=reports.append,
        )
        self.assertEqual(mock_wait.call_args.kwargs["report"], reports.append)

    def test_discovery_error_is_actionable(self) -> None:
        message = preflight.describe_discovery_error(
            RuntimeError("boom"), "http://h/api/v1"
        )
        self.assertIn("ViPPET reported ready, but reading its inventory", message)
        self.assertIn("from http://h/api/v1 failed: RuntimeError: boom", message)
        self.assertIn("To fix:", message)


class TestFetchDiscoveredDevices(unittest.TestCase):
    """Unit tests for the /devices snapshot captured at pre-flight time."""

    def test_returns_payload_on_success(self) -> None:
        requested_paths: list[str] = []
        devices = [
            {"device_name": "CPU", "full_device_name": "Intel(R) Core(TM) Ultra 7"},
            {"device_name": "GPU.0", "full_device_name": "Intel(R) Arc(TM) Graphics"},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            return httpx.Response(200, json=devices)

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_discovered_devices(
                "http://localhost/api/v1/",
                10,
                client=client,
                report=reports.append,
            )

        self.assertEqual(requested_paths, ["/api/v1/devices"])
        self.assertEqual(result, devices)
        self.assertIn(
            "GET http://localhost/api/v1/devices: OK (2 device(s))", reports[0]
        )

    def test_returns_empty_list_on_unreachable_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_discovered_devices(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, [])
        self.assertIn("/devices: FAILED", reports[-1])
        self.assertIn("ConnectError", reports[-1])
        self.assertIn("The report will have no hardware section", reports[-1])
        self.assertIn("To fix:", reports[-1])

    def test_returns_empty_list_on_non_list_payload(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"not": "a list"})

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_discovered_devices(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, [])
        self.assertIn("/devices: FAILED", reports[-1])
        self.assertIn("expected a list, got dict", reports[-1])

    def test_returns_empty_list_on_http_error_status(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_discovered_devices(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, [])
        self.assertIn("/devices: FAILED", reports[-1])

    def test_does_not_close_caller_owned_client(self) -> None:
        """The fetcher must never close a client it did not open."""
        devices = [{"device_name": "CPU", "full_device_name": "Some CPU"}]

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=devices)

        with _client(handler) as client:
            result = preflight.fetch_discovered_devices(
                "http://localhost/api/v1", 10, client=client
            )
            self.assertEqual(result, devices)
            self.assertFalse(client.is_closed)


class TestFetchCapabilities(unittest.TestCase):
    """Unit tests for the /api/v1/capabilities snapshot captured at pre-flight time."""

    def test_returns_payload_on_success(self) -> None:
        payload = {"platform": {"os": "Linux", "kernel": "6.6.0"}}

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_capabilities(
                "http://localhost:9090/api/v1/capabilities",
                10,
                client=client,
                report=reports.append,
            )

        self.assertEqual(result, payload)
        self.assertIn(": OK", reports[0])

    def test_returns_empty_dict_on_unreachable_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_capabilities(
                "http://localhost:9090/api/v1/capabilities",
                10,
                client=client,
                report=reports.append,
            )

        self.assertEqual(result, {})
        self.assertIn(": FAILED", reports[-1])
        self.assertIn("ConnectError", reports[-1])
        self.assertIn("'Unknown'", reports[-1])
        self.assertIn("--capabilities-url / VIPPET_CAPABILITIES_URL", reports[-1])

    def test_returns_empty_dict_on_non_object_payload(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["not", "an", "object"])

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_capabilities(
                "http://localhost:9090/api/v1/capabilities",
                10,
                client=client,
                report=reports.append,
            )

        self.assertEqual(result, {})
        self.assertIn("expected an object, got list", reports[-1])

    def test_returns_empty_dict_on_http_error_status(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        with _client(handler) as client:
            result = preflight.fetch_capabilities(
                "http://localhost:9090/api/v1/capabilities", 10, client=client
            )

        self.assertEqual(result, {})


class TestFetchVippetVersion(unittest.TestCase):
    """Unit tests for the ViPPET version captured from GET /status at pre-flight time."""

    def test_returns_version_on_success(self) -> None:
        requested_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            return httpx.Response(200, json={"version": "2026.2.0-rc2"})

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(requested_paths, ["/api/v1/status"])
        self.assertEqual(result, "2026.2.0-rc2")
        self.assertIn(": OK", reports[0])

    def test_appends_revision_when_present(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"version": "2026.3.0-dev", "revision": "e47cc195-dirty"}
            )

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        # Revision is shown as-is, with no trimming of the "-dirty" suffix.
        self.assertEqual(result, "2026.3.0-dev (e47cc195-dirty)")
        self.assertIn(": OK", reports[0])

    def test_omits_revision_when_absent(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"version": "2026.3.0-dev", "revision": None}
            )

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, "2026.3.0-dev")

    def test_omits_revision_when_literal_unknown(self) -> None:
        """GET /status reports "unknown" (not null) when VIPPET_REVISION is unset."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"version": "2026.3.0-dev", "revision": "unknown"}
            )

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, "2026.3.0-dev")

    def test_returns_bare_version_when_version_is_literal_unknown(self) -> None:
        """GET /status reports "unknown" (not null/missing) when VIPPET_VERSION is
        unset -- unlike revision, an unknown version is still shown as-is, not
        collapsed to the generic pre-flight-failure "Unknown"."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"version": "unknown", "revision": "unknown"}
            )

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, "unknown")
        self.assertIn(": OK", reports[0])

    def test_returns_unknown_on_unreachable_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, "Unknown")
        self.assertIn(": FAILED", reports[-1])
        self.assertIn("ViPPET version as 'Unknown'", reports[-1])
        self.assertIn("To fix:", reports[-1])

    def test_returns_unknown_when_version_field_missing(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ready"})

        reports: list[str] = []
        with _client(handler) as client:
            result = preflight.fetch_vippet_version(
                "http://localhost/api/v1", 10, client=client, report=reports.append
            )

        self.assertEqual(result, "Unknown")
        self.assertIn("missing 'version' field", reports[-1])


if __name__ == "__main__":
    unittest.main()
