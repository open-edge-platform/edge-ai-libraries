# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import unittest
from collections.abc import Callable
from unittest.mock import patch

import httpx

from dlsps2_runner import Dlsps2PipelineRunner

PIPELINE = "filesrc location=/tmp/a.mp4 ! decodebin3 ! fakesink"
INSTANCE_ID = "inst-1"

StatusItem = dict | httpx.Response | Callable[[], dict | httpx.Response]


class _FakeDlsps2:
    """In-process stand-in for the DLSPS 2.0 REST API.

    Status responses are served in order; the last one repeats for any
    further polls. An item may be a JSON dict, a ready ``httpx.Response``,
    or a callable producing either (to trigger side effects mid-run).
    """

    def __init__(
        self,
        statuses: list[StatusItem],
        post_response: httpx.Response | None = None,
        delete_status: int = 200,
    ):
        self.statuses = list(statuses)
        self.post_response = post_response
        self.delete_status = delete_status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            return self.post_response or httpx.Response(
                200, json={"instance_id": INSTANCE_ID}
            )
        if request.method == "DELETE":
            return httpx.Response(self.delete_status)

        item = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if callable(item):
            item = item()
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def calls(self, method: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method]


class _FakeClock:
    """``time.monotonic``/``time.sleep`` pair where sleeping advances the clock."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _ImmediateThread:
    """Runs the target synchronously so metric pushes are deterministic."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self) -> None:
        self._target()


class Dlsps2RunnerTestBase(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        time_patcher = patch("dlsps2_runner.time")
        mock_time = time_patcher.start()
        mock_time.monotonic.side_effect = self.clock.monotonic
        mock_time.sleep.side_effect = self.clock.sleep
        self.addCleanup(time_patcher.stop)

    def _run(self, runner: Dlsps2PipelineRunner, fake: "_FakeDlsps2"):
        with patch.object(runner, "_client", side_effect=fake.client):
            return runner.run(PIPELINE)


class TestDlsps2RunnerInit(unittest.TestCase):
    def test_latency_metrics_not_supported(self):
        with self.assertRaises(NotImplementedError):
            Dlsps2PipelineRunner(enable_latency_metrics=True)

    def test_hard_timeout_defaults_to_max_runtime_plus_60(self):
        runner = Dlsps2PipelineRunner(max_runtime=10)
        self.assertEqual(runner.hard_timeout, 70)

    def test_explicit_hard_timeout_is_kept(self):
        runner = Dlsps2PipelineRunner(max_runtime=10, hard_timeout=15)
        self.assertEqual(runner.hard_timeout, 15)

    def test_base_url_trailing_slash_is_stripped(self):
        runner = Dlsps2PipelineRunner(base_url="http://dlsps:8080/")
        self.assertEqual(runner.base_url, "http://dlsps:8080")

    def test_cancel_sets_cancelled_flag(self):
        runner = Dlsps2PipelineRunner()
        self.assertFalse(runner.is_cancelled())
        runner.cancel()
        self.assertTrue(runner.is_cancelled())


class TestDlsps2RunnerValidation(Dlsps2RunnerTestBase):
    def _runner(self, **kwargs) -> Dlsps2PipelineRunner:
        kwargs.setdefault("max_runtime", 0)
        return Dlsps2PipelineRunner(
            mode="validation", base_url="http://dlsps:8080", **kwargs
        )

    def test_completed_is_valid_and_instance_is_stopped(self):
        fake = _FakeDlsps2([{"state": "COMPLETED"}])

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stderr, [])
        post = fake.calls("POST")[0]
        self.assertEqual(str(post.url), "http://dlsps:8080/pipelines")
        self.assertEqual(json.loads(post.content), {"pipeline": PIPELINE})
        delete = fake.calls("DELETE")
        self.assertEqual(len(delete), 1)
        self.assertEqual(delete[0].url.path, f"/pipelines/{INSTANCE_ID}")

    def test_running_for_max_runtime_is_valid(self):
        fake = _FakeDlsps2([{"state": "RUNNING"}])

        result = self._run(self._runner(max_runtime=0), fake)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_error_state_is_invalid_with_server_message(self):
        fake = _FakeDlsps2([{"state": "ERROR", "message": "no element foo"}])

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, ["no element foo"])
        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_aborted_without_message_reports_state(self):
        fake = _FakeDlsps2([{"state": "ABORTED"}])

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("state=ABORTED", result.stderr[0])

    def test_no_verdict_within_hard_timeout_is_invalid(self):
        fake = _FakeDlsps2([{"state": "QUEUED"}])

        result = self._run(self._runner(hard_timeout=0), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("timed out", result.stderr[0])
        self.assertIn("last state=QUEUED", result.stderr[0])
        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_submit_error_reports_server_detail_and_skips_stop(self):
        fake = _FakeDlsps2(
            [{"state": "COMPLETED"}],
            post_response=httpx.Response(400, json={"detail": "bad pipeline"}),
        )

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("HTTP 400: bad pipeline", result.stderr[0])
        self.assertEqual(fake.calls("DELETE"), [])

    def test_submit_error_without_json_body_still_reported(self):
        fake = _FakeDlsps2(
            [{"state": "COMPLETED"}],
            post_response=httpx.Response(502, text="Bad Gateway"),
        )

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to submit pipeline to DLSPS 2.0", result.stderr[0])
        self.assertIn("502", result.stderr[0])

    def test_status_poll_error_is_invalid_and_instance_is_stopped(self):
        fake = _FakeDlsps2([httpx.Response(500)])

        result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 1)
        self.assertIn(
            f"Failed to poll DLSPS 2.0 instance {INSTANCE_ID}", result.stderr[0]
        )
        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_delete_conflict_is_not_logged(self):
        fake = _FakeDlsps2([{"state": "COMPLETED"}], delete_status=409)

        with self.assertNoLogs("dlsps2_runner", level="WARNING"):
            result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 0)

    def test_delete_failure_is_logged_not_raised(self):
        fake = _FakeDlsps2([{"state": "COMPLETED"}], delete_status=500)

        with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
            result = self._run(self._runner(), fake)

        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            f"Failed to stop DLSPS 2.0 instance {INSTANCE_ID}", logs.output[0]
        )


class TestDlsps2RunnerFpsPush(unittest.TestCase):
    @patch("dlsps2_runner.threading.Thread", _ImmediateThread)
    @patch("dlsps2_runner.urllib.request.urlopen")
    def test_push_uses_metrics_manager_url_and_job_tag(self, mock_urlopen):
        with patch.dict(os.environ, {"METRICS_MANAGER_URL": "http://mm:9090/"}):
            runner = Dlsps2PipelineRunner(job_id="job-7")

        runner._push_fps_metric(42.0)

        req = mock_urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "http://mm:9090/api/v1/metrics/simple")
        self.assertEqual(
            json.loads(req.data),
            {"name": "fps", "value": 42.0, "tags": {"job_id": "job-7"}},
        )

    @patch("dlsps2_runner.threading.Thread", _ImmediateThread)
    @patch("dlsps2_runner.urllib.request.urlopen")
    def test_push_without_job_id_has_no_tags(self, mock_urlopen):
        Dlsps2PipelineRunner()._push_fps_metric(1.0)

        payload = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertNotIn("tags", payload)

    @patch("dlsps2_runner.threading.Thread", _ImmediateThread)
    @patch("dlsps2_runner.urllib.request.urlopen", side_effect=OSError("down"))
    def test_push_failure_is_logged_not_raised(self, _mock_urlopen):
        with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
            Dlsps2PipelineRunner()._push_fps_metric(1.0)

        self.assertIn("Failed to push fps metric", logs.output[0])


if __name__ == "__main__":
    unittest.main()
