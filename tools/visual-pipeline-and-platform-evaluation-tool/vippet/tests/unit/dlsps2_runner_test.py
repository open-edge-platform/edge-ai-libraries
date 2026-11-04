# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock, patch

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


class _FakeStreamSet:
    """In-process DLSPS 2.0 for normal mode: one instance per POST.

    Each item of ``polls`` answers one ``GET /pipelines/status``: a list with
    one status dict per instance in POST order, an ``httpx.Response``, or a
    callable producing either. The last item repeats. Stopped instances are
    reported as ``ABORTED``.
    """

    def __init__(
        self,
        polls: list,
        post_responses: list[httpx.Response | None] | None = None,
        delete_codes: dict[str, list[int]] | None = None,
        instance_states: dict[str, list[str]] | None = None,
    ):
        self.polls = list(polls)
        self.post_responses = list(post_responses or [])
        self.delete_codes = delete_codes or {}
        self.instance_states = instance_states or {}
        self.requests: list[httpx.Request] = []
        self.posted = 0
        self.stopped: set[str] = set()

    @staticmethod
    def _next(items: list):
        return items.pop(0) if len(items) > 1 else items[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            response = self.post_responses.pop(0) if self.post_responses else None
            if response is not None:
                return response
            self.posted += 1
            return httpx.Response(200, json={"instance_id": f"inst-{self.posted}"})
        if request.method == "DELETE":
            instance_id = path.rsplit("/", 1)[-1]
            codes = self.delete_codes.get(instance_id)
            code = self._next(codes) if codes else 200
            if code == 200:
                self.stopped.add(instance_id)
            return httpx.Response(code)
        if path == "/pipelines/status":
            item = self._next(self.polls)
            if callable(item):
                item = item()
            if isinstance(item, httpx.Response):
                return item
            assert isinstance(item, list)
            body = [{"id": f"inst-{i + 1}", **s} for i, s in enumerate(item)]
            for status in body:
                if status["id"] in self.stopped:
                    status["state"] = "ABORTED"
            return httpx.Response(200, json=body)
        instance_id = path.split("/")[2]
        states = self.instance_states.get(instance_id, ["RUNNING"])
        return httpx.Response(
            200, json={"id": instance_id, "state": self._next(states)}
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def calls(self, method: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method]


def _running(fps: float, **extra) -> dict:
    return {"state": "RUNNING", "frame_fps": fps, **extra}


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

    def _run(
        self,
        runner: Dlsps2PipelineRunner,
        fake: "_FakeDlsps2 | _FakeStreamSet",
        total_streams: int = 1,
        stream_commands: dict[str, str] | None = None,
    ):
        with patch.object(runner, "_client", side_effect=fake.client):
            return runner.run(
                PIPELINE,
                total_streams=total_streams,
                stream_commands=stream_commands,
            )


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


class TestDlsps2RunnerNormal(Dlsps2RunnerTestBase):
    STREAMS = {"a": "pipeline a", "b": "pipeline b"}

    def _runner(self, **kwargs) -> Dlsps2PipelineRunner:
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", job_id="job-1", **kwargs
        )
        self.pushed_fps = MagicMock()
        patcher = patch.object(runner, "_push_fps_metric", self.pushed_fps)
        patcher.start()
        self.addCleanup(patcher.stop)
        return runner

    def _pushed_values(self) -> list[float]:
        return [c.args[0] for c in self.pushed_fps.call_args_list]

    def _run_streams(self, runner, fake):
        return self._run(runner, fake, total_streams=2, stream_commands=self.STREAMS)

    def test_combined_command_for_several_streams_is_not_supported(self):
        fake = _FakeStreamSet([[_running(30.0)]])

        with self.assertRaises(NotImplementedError):
            self._run(self._runner(), fake, total_streams=2)

        self.assertEqual(fake.requests, [])

    def test_each_stream_is_measured_over_the_common_window(self):
        queued = {"state": "QUEUED", "frame_fps": 0.0}
        fake = _FakeStreamSet(
            [
                [queued, queued],
                [_running(30.0), _running(0.0)],
                [_running(30.0), _running(20.0)],
            ]
        )

        result = self._run_streams(self._runner(max_runtime=10), fake)

        posts = fake.calls("POST")
        self.assertEqual(
            [json.loads(p.content) for p in posts],
            [{"pipeline": "pipeline a"}, {"pipeline": "pipeline b"}],
        )
        # All streams play from t=2; samples count after the 5 s warm-up.
        self.assertEqual(result.stream_fps, {"a": 30.0, "b": 20.0})
        self.assertEqual(result.min_stream_fps, 20.0)
        self.assertEqual(result.total_fps, 50.0)
        self.assertEqual(result.per_stream_fps, 25.0)
        self.assertEqual(result.num_streams, 2)
        self.assertFalse(result.cancelled)
        self.assertIsNone(result.latency_tracer_metrics)
        self.assertNotIn("avg_fps", result.details or "")
        self.assertEqual(self.clock.now, 12.0)
        self.assertEqual(
            sorted(r.url.path for r in fake.calls("DELETE")),
            ["/pipelines/inst-1", "/pipelines/inst-2"],
        )
        pushed = self._pushed_values()
        self.assertEqual(pushed[:3], [0.0, 15.0, 25.0])
        self.assertEqual(pushed[-1], 0.0)

    def test_run_shorter_than_warm_up_falls_back_to_final_avg_fps(self):
        fake = _FakeStreamSet(
            [
                [_running(30.0, avg_fps=29.0)],
                [{"state": "COMPLETED", "frame_fps": 0.0, "avg_fps": 29.5}],
            ]
        )

        result = self._run(self._runner(), fake)

        self.assertEqual(result.stream_fps, {"stream": 29.5})
        self.assertEqual(result.total_fps, 29.5)
        self.assertIn("final avg_fps used for 1 stream(s)", result.details or "")

    def test_server_message_is_returned_in_stderr(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED", "message": "EOS"}]])

        result = self._run(self._runner(), fake)

        self.assertEqual(result.stderr, ["stream: EOS"])

    def test_error_state_raises_and_stops_every_instance(self):
        fake = _FakeStreamSet(
            [[_running(30.0), {"state": "ERROR", "message": "device lost"}]]
        )

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(), fake)

        self.assertIn("Stream b failed on DLSPS 2.0: device lost", str(ctx.exception))
        self.assertEqual(len(fake.calls("DELETE")), 2)
        self.assertEqual(self._pushed_values(), [0.0])

    def test_cancel_stops_without_raising(self):
        runner = self._runner()

        def cancel_then_running() -> list[dict]:
            runner.cancel()
            return [_running(20.0, avg_fps=19.0), _running(20.0, avg_fps=18.0)]

        fake = _FakeStreamSet([[_running(20.0), _running(20.0)], cancel_then_running])

        result = self._run_streams(runner, fake)

        self.assertTrue(result.cancelled)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stream_fps, {"a": 19.0, "b": 18.0})
        self.assertEqual(len(fake.calls("DELETE")), 2)

    def test_submit_error_stops_streams_already_started(self):
        fake = _FakeStreamSet(
            [[_running(30.0)]],
            post_responses=[None, httpx.Response(503, json={"detail": "worker busy"})],
        )

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(), fake)

        self.assertIn("Failed to submit stream b", str(ctx.exception))
        self.assertIn("HTTP 503: worker busy", str(ctx.exception))
        self.assertEqual(
            [r.url.path for r in fake.calls("DELETE")], ["/pipelines/inst-1"]
        )

    def test_submit_error_on_first_stream_sends_no_other_request(self):
        fake = _FakeStreamSet(
            [[_running(30.0)]],
            post_responses=[httpx.Response(400, json={"detail": "bad pipeline"})],
        )

        with self.assertRaises(RuntimeError):
            self._run_streams(self._runner(), fake)

        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(self._pushed_values(), [])

    def test_stream_without_frames_beyond_inactivity_timeout_raises(self):
        fake = _FakeStreamSet([[_running(30.0), _running(0.0)]])

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(inactivity_timeout=3), fake)

        self.assertIn("No frames from stream(s) b", str(ctx.exception))
        self.assertEqual(len(fake.calls("DELETE")), 2)

    def test_transient_poll_error_is_retried(self):
        fake = _FakeStreamSet(
            [
                httpx.Response(500),
                [{"state": "COMPLETED", "frame_fps": 0.0, "avg_fps": 15.0}],
            ]
        )

        result = self._run(self._runner(), fake)

        self.assertEqual(result.total_fps, 15.0)

    def test_lost_contact_beyond_inactivity_timeout_raises(self):
        fake = _FakeStreamSet([httpx.Response(500)])

        with self.assertRaises(RuntimeError) as ctx:
            self._run(self._runner(inactivity_timeout=2), fake)

        self.assertIn("Lost contact", str(ctx.exception))
        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_queued_instance_is_stopped_once_it_leaves_queued(self):
        runner = self._runner()

        def cancel() -> list[dict]:
            runner.cancel()
            return [{"state": "QUEUED"}]

        fake = _FakeStreamSet(
            [cancel],
            delete_codes={"inst-1": [409, 200]},
            instance_states={"inst-1": ["QUEUED"]},
        )
        runner.cancel()

        result = self._run(runner, fake)

        self.assertTrue(result.cancelled)
        self.assertEqual(len(fake.calls("DELETE")), 2)

    def test_finished_instance_conflict_is_not_retried(self):
        fake = _FakeStreamSet(
            [[{"state": "COMPLETED", "avg_fps": 10.0}]],
            delete_codes={"inst-1": [409]},
            instance_states={"inst-1": ["COMPLETED"]},
        )

        with self.assertNoLogs("dlsps2_runner", level="WARNING"):
            self._run(self._runner(), fake)

        self.assertEqual(len(fake.calls("DELETE")), 1)

    def test_instance_still_queued_after_stop_timeout_is_logged(self):
        runner = self._runner()
        runner.cancel()
        fake = _FakeStreamSet(
            [[{"state": "QUEUED"}]],
            delete_codes={"inst-1": [409]},
            instance_states={"inst-1": ["QUEUED"]},
        )

        with patch("dlsps2_runner.DLSPS2_STOP_TIMEOUT_S", 3):
            with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
                self._run(runner, fake)

        self.assertIn("still queued", logs.output[0])
        self.assertEqual(len(fake.calls("DELETE")), 4)


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
