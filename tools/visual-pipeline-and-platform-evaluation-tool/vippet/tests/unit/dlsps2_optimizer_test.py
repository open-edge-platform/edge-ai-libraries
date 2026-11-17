# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import unittest
from typing import Any, Callable
from unittest.mock import patch

import httpx

import dlsps2_optimizer
from dlsps2_optimizer import (
    Dlsps2Optimizer,
    Dlsps2OptimizerCancelled,
    Dlsps2OptimizerError,
    cancel_leftover_optimizations,
)

BASE_URL = "http://d:8080"


class _FakeOptimizeApi:
    """In-memory DLSPS 2.0 /optimize API for one job."""

    def __init__(
        self,
        states: list[str],
        result: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        # State returned by each status poll; the last one repeats.
        self.states = list(states)
        self.result = result or {
            "best": {"pipeline": "best ! sink", "fps": 120.5},
            "baseline": {"pipeline": "orig ! sink", "fps": 60.0},
        }
        self.message = message
        self.submitted: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.post_response: httpx.Response | None = None
        self.status_response: httpx.Response | None = None
        # POST /optimize requests answered with 409 before the job starts.
        self.busy_posts = 0
        # Status polls answered with 503 before the real status.
        self.status_errors = 0
        # Status polls that still report RUNNING after the job was cancelled.
        self.running_after_cancel = 0
        self.polls_after_cancel = 0

    def _state(self) -> str:
        if self.deleted:
            self.polls_after_cancel += 1
            if self.running_after_cancel:
                self.running_after_cancel -= 1
                return "RUNNING"
            return "CANCELLED"
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/optimize":
            self.submitted.append(json.loads(request.content))
            if self.busy_posts:
                self.busy_posts -= 1
                return httpx.Response(409, json={"detail": "job old is still running"})
            return self.post_response or httpx.Response(200, json={"job_id": "j1"})
        if request.method == "GET" and path == "/optimize/status/j1":
            if self.status_response is not None:
                return self.status_response
            if self.status_errors:
                self.status_errors -= 1
                return httpx.Response(503, json={"detail": "starting"})
            state = self._state()
            return httpx.Response(
                200,
                json={
                    "job_id": "j1",
                    "state": state,
                    "final": state != "RUNNING",
                    "message": self.message,
                },
            )
        if request.method == "GET" and path == "/optimize/result/j1":
            return httpx.Response(200, json={"job_id": "j1", **self.result})
        if request.method == "DELETE" and path == "/optimize/j1":
            self.deleted.append("j1")
            return httpx.Response(200, json={"job_id": "j1"})
        return httpx.Response(404, json={"detail": "Not Found"})


def _patched_client(handler: Callable[[httpx.Request], httpx.Response]):
    real_client = httpx.Client
    return patch(
        "dlsps2_optimizer.httpx.Client",
        side_effect=lambda **_: real_client(transport=httpx.MockTransport(handler)),
    )


class TestDlsps2Optimizer(unittest.TestCase):
    def _optimize(self, api: _FakeOptimizeApi, optimizer=None, **kwargs):
        optimizer = optimizer or Dlsps2Optimizer(base_url=BASE_URL, poll_interval=0.01)
        with _patched_client(api.handler):
            return optimizer.optimize(
                "orig ! sink",
                search_duration=kwargs.get("search_duration", 60),
                sample_duration=kwargs.get("sample_duration", 5),
                allowed_devices=kwargs.get("allowed_devices"),
            )

    def test_completed_job_returns_best_pipeline_and_fps(self):
        api = _FakeOptimizeApi(["RUNNING", "RUNNING", "COMPLETED"])

        result = self._optimize(api, allowed_devices=["GPU"])

        self.assertEqual(result.pipeline, "best ! sink")
        self.assertEqual(result.fps, 120.5)
        self.assertEqual(
            api.submitted,
            [
                {
                    "pipeline": "orig ! sink",
                    "mode": "fps",
                    "search_duration": 60,
                    "sample_duration": 5,
                    "allowed_devices": ["GPU"],
                }
            ],
        )
        self.assertEqual(api.deleted, [])

    def test_allowed_devices_omitted_when_none(self):
        api = _FakeOptimizeApi(["COMPLETED"])

        self._optimize(api)

        self.assertNotIn("allowed_devices", api.submitted[0])

    def test_completed_without_best_falls_back_to_baseline(self):
        api = _FakeOptimizeApi(
            ["COMPLETED"],
            result={"best": None, "baseline": {"pipeline": "orig ! sink", "fps": 60.0}},
        )

        result = self._optimize(api)

        self.assertEqual((result.pipeline, result.fps), ("orig ! sink", 60.0))

    def test_completed_without_any_pipeline_raises(self):
        api = _FakeOptimizeApi(["COMPLETED"], result={"best": None, "baseline": None})

        with self.assertRaisesRegex(Dlsps2OptimizerError, "without a pipeline"):
            self._optimize(api)

    def test_server_without_optimize_endpoint_raises_clear_error(self):
        api = _FakeOptimizeApi(["COMPLETED"])
        api.post_response = httpx.Response(404, json={"detail": "Not Found"})

        with self.assertRaisesRegex(Dlsps2OptimizerError, "no optimizer endpoint"):
            self._optimize(api)

    def test_busy_server_raises_with_detail(self):
        api = _FakeOptimizeApi(["COMPLETED"])
        api.post_response = httpx.Response(
            409, json={"detail": "optimizer job abc is still running"}
        )

        with patch.object(dlsps2_optimizer, "DLSPS2_OPTIMIZE_BUSY_WAIT_S", 0.0):
            with self.assertRaisesRegex(
                Dlsps2OptimizerError, "already running.*abc is still running"
            ):
                self._optimize(api)

    def test_busy_server_is_retried_until_free(self):
        """A job still ending on the server delays the start instead of failing it."""
        api = _FakeOptimizeApi(["COMPLETED"])
        api.busy_posts = 2

        result = self._optimize(api)

        self.assertEqual(result.pipeline, "best ! sink")
        self.assertEqual(len(api.submitted), 3)

    def test_cancel_while_server_busy_raises_cancelled(self):
        api = _FakeOptimizeApi(["COMPLETED"])
        api.busy_posts = 1000
        optimizer = Dlsps2Optimizer(base_url=BASE_URL, poll_interval=0.01)
        timer = threading.Timer(0.05, optimizer.cancel)
        timer.start()

        with self.assertRaises(Dlsps2OptimizerCancelled):
            self._optimize(api, optimizer=optimizer)

        timer.join()
        self.assertEqual(api.deleted, [])

    def test_invalid_request_raises_with_detail(self):
        api = _FakeOptimizeApi(["COMPLETED"])
        api.post_response = httpx.Response(
            400, json={"detail": "pipeline must not be empty"}
        )

        with self.assertRaisesRegex(
            Dlsps2OptimizerError, "HTTP 400: pipeline must not be empty"
        ):
            self._optimize(api)

    def test_failed_job_raises_with_server_message(self):
        api = _FakeOptimizeApi(["RUNNING", "ERROR"], message="no element gvadetect")

        with self.assertRaisesRegex(Dlsps2OptimizerError, "no element gvadetect"):
            self._optimize(api)

    def test_job_cancelled_on_server_raises(self):
        api = _FakeOptimizeApi(["CANCELLED"])

        with self.assertRaisesRegex(Dlsps2OptimizerError, "cancelled on DLSPS"):
            self._optimize(api)

    def test_job_lost_after_server_restart_raises(self):
        api = _FakeOptimizeApi(["RUNNING"])
        api.status_response = httpx.Response(404, json={"detail": "not found"})

        with self.assertRaisesRegex(Dlsps2OptimizerError, "no longer knows"):
            self._optimize(api)

    def test_cancel_deletes_job_and_raises_cancelled(self):
        api = _FakeOptimizeApi(["RUNNING"])
        optimizer = Dlsps2Optimizer(base_url=BASE_URL, poll_interval=0.01)
        timer = threading.Timer(0.05, optimizer.cancel)
        timer.start()

        with self.assertRaises(Dlsps2OptimizerCancelled):
            self._optimize(api, optimizer=optimizer)

        timer.join()
        self.assertEqual(api.deleted, ["j1"])
        self.assertTrue(optimizer.is_cancelled())

    def test_job_running_past_deadline_is_cancelled(self):
        api = _FakeOptimizeApi(["RUNNING"])

        with patch.object(dlsps2_optimizer, "DLSPS2_OPTIMIZE_SLACK_S", 0.0):
            with self.assertRaisesRegex(Dlsps2OptimizerError, "did not finish in time"):
                self._optimize(api, search_duration=0.02, sample_duration=0)

        self.assertEqual(api.deleted, ["j1"])

    def test_failure_waits_until_server_job_ends(self):
        """After a failure the job is cancelled and awaited, so the server slot is free."""
        api = _FakeOptimizeApi(["RUNNING"])
        api.running_after_cancel = 2

        with patch.object(dlsps2_optimizer, "DLSPS2_OPTIMIZE_SLACK_S", 0.0):
            with self.assertRaisesRegex(Dlsps2OptimizerError, "did not finish in time"):
                self._optimize(api, search_duration=0.02, sample_duration=0)

        self.assertEqual(api.deleted, ["j1"])
        self.assertEqual(api.polls_after_cancel, 3)

    def test_server_error_while_polling_is_tolerated(self):
        api = _FakeOptimizeApi(["RUNNING", "COMPLETED"])
        api.status_errors = 2

        result = self._optimize(api)

        self.assertEqual(result.pipeline, "best ! sink")
        self.assertEqual(api.deleted, [])

    def test_persistent_server_error_while_polling_raises_after_grace(self):
        api = _FakeOptimizeApi(["RUNNING"])
        api.status_response = httpx.Response(502, json={"detail": "bad gateway"})

        with patch.object(dlsps2_optimizer, "DLSPS2_OPTIMIZE_UNREACHABLE_S", 0.02):
            with self.assertRaisesRegex(Dlsps2OptimizerError, "HTTP 502: bad gateway"):
                self._optimize(api)
        self.assertEqual(api.deleted, ["j1"])

    def test_unexpected_error_after_submit_cancels_job(self):
        api = _FakeOptimizeApi(["RUNNING"])

        with patch.object(Dlsps2Optimizer, "_wait", side_effect=RuntimeError("bug")):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                self._optimize(api)
        self.assertEqual(api.deleted, ["j1"])

    def test_unreachable_server_while_polling_raises_after_grace(self):
        class _UnreachableStatus(_FakeOptimizeApi):
            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.method == "GET":
                    raise httpx.ConnectError("refused")
                return super().handler(request)

        api = _UnreachableStatus(["RUNNING"])

        with patch.object(dlsps2_optimizer, "DLSPS2_OPTIMIZE_UNREACHABLE_S", 0.02):
            with self.assertRaisesRegex(Dlsps2OptimizerError, "unreachable"):
                self._optimize(api)
        self.assertEqual(api.deleted, ["j1"])


class TestCancelLeftoverOptimizations(unittest.TestCase):
    def test_cancels_only_running_jobs(self):
        deleted: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "DELETE":
                deleted.append(request.url.path.rsplit("/", 1)[-1])
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                json=[
                    {"job_id": "run", "state": "RUNNING"},
                    {"job_id": "done", "state": "COMPLETED"},
                    {"job_id": "err", "state": "ERROR"},
                ],
            )

        with _patched_client(handler), self.assertLogs("dlsps2_optimizer", "WARNING"):
            self.assertEqual(cancel_leftover_optimizations(base_url=BASE_URL), 1)
        self.assertEqual(deleted, ["run"])

    def test_server_without_optimize_endpoint_returns_zero(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Not Found"})

        with _patched_client(handler), self.assertLogs("dlsps2_optimizer", "WARNING"):
            self.assertEqual(cancel_leftover_optimizations(base_url=BASE_URL), 0)

    def test_unreachable_server_is_logged(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with (
            _patched_client(handler),
            self.assertLogs("dlsps2_optimizer", "WARNING") as logs,
        ):
            self.assertEqual(cancel_leftover_optimizations(base_url=BASE_URL), 0)
        self.assertTrue(any("leftover" in m for m in logs.output))


if __name__ == "__main__":
    unittest.main()
