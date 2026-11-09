# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import httpx

import dlsps2_runner
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

    Each item of ``polls`` answers one polling round, a
    ``GET /pipelines/{id}/status`` per instance: a list with one status dict
    per instance in POST order (an instance beyond the list gets 404), an
    ``httpx.Response`` for every request of the round, or a callable producing
    either. A round starts when an instance is asked for a second time. The
    last item repeats. Once an instance was sent ``DELETE``, its status comes
    from ``instance_states`` if given there. Stopped instances are
    reported as ``ABORTED``. Each item of ``validations`` answers one
    ``GET /validate/status/{id}`` the same way; the default is ``VALID``.
    A status with frames and no ``frame_interval`` gets a new one on every
    poll, so it reads as a new window; pass ``frame_interval`` to repeat one.
    """

    def __init__(
        self,
        polls: list,
        post_responses: list[httpx.Response | None] | None = None,
        delete_codes: dict[str, list[int]] | None = None,
        instance_states: dict[str, list[str]] | None = None,
        validations: list | None = None,
        metrics: list[dict] | httpx.Response | None = None,
        gvagenai: str | httpx.Response | None = None,
    ):
        self.polls = list(polls)
        # GET /elements/gvagenai: gst-inspect output, or a fixed response (404 if None).
        self.gvagenai = gvagenai
        # metrics-manager GET /api/v1/metrics: stored metrics, or a fixed response.
        self.metrics = metrics if metrics is not None else []
        self.post_responses = list(post_responses or [])
        self.delete_codes = delete_codes or {}
        self.instance_states = instance_states or {}
        self.validations: list = list(validations or [{"state": "VALID"}])
        self.requests: list[httpx.Request] = []
        self.posted = 0
        self.validated = 0
        self.status_polls = 0
        self.stopped: set[str] = set()
        self.deleted: set[str] = set()
        self._round: object = None
        self._round_served: set[str] = set()

    @staticmethod
    def _next(items: list):
        return items.pop(0) if len(items) > 1 else items[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/v1/metrics":
            if isinstance(self.metrics, httpx.Response):
                return self.metrics
            name = request.url.params.get("name")
            found = [m for m in self.metrics if m["name"] == name]
            return httpx.Response(200, json={"metrics": found, "count": len(found)})
        if path == "/elements/gvagenai":
            if isinstance(self.gvagenai, httpx.Response):
                return self.gvagenai
            if self.gvagenai is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(
                200,
                json={
                    "name": "gvagenai",
                    "plugin": "genai",
                    "description": "GenAI",
                    "details": self.gvagenai,
                },
            )
        if path == "/validate":
            self.validated += 1
            return httpx.Response(200, json={"validation_id": f"val-{self.validated}"})
        if path.startswith("/validate/status/"):
            item = self._next(self.validations)
            if callable(item):
                item = item()
            if isinstance(item, httpx.Response):
                return item
            assert isinstance(item, dict)
            return httpx.Response(200, json={"validation_id": path[17:], **item})
        if request.method == "POST":
            response = self.post_responses.pop(0) if self.post_responses else None
            if response is not None:
                return response
            self.posted += 1
            return httpx.Response(200, json={"instance_id": f"inst-{self.posted}"})
        if request.method == "DELETE":
            instance_id = path.rsplit("/", 1)[-1]
            self.deleted.add(instance_id)
            codes = self.delete_codes.get(instance_id)
            code = self._next(codes) if codes else 200
            if code == 200:
                self.stopped.add(instance_id)
            return httpx.Response(code)
        instance_id = path.split("/")[2]
        if instance_id in self.instance_states and instance_id in self.deleted:
            states = self.instance_states[instance_id]
            return httpx.Response(
                200, json={"id": instance_id, "state": self._next(states)}
            )
        return self._polled_status(instance_id)

    def _polled_status(self, instance_id: str) -> httpx.Response:
        if self._round is None or instance_id in self._round_served:
            item = self._next(self.polls)
            if callable(item):
                item = item()
            self._round = item
            self._round_served = set()
            if isinstance(item, list):
                self.status_polls += 1
        self._round_served.add(instance_id)
        item = self._round
        if isinstance(item, httpx.Response):
            return item
        assert isinstance(item, list)
        index = int(instance_id.rsplit("-", 1)[-1]) - 1
        if index >= len(item):
            return httpx.Response(404, json={"detail": "not found"})
        status = {"id": instance_id, **item[index]}
        if status.get("frame_fps") and "frame_interval" not in status:
            # Dyadic, so fps-weighted sums of whole fps stay exact.
            status["frame_interval"] = 1.0 + self.status_polls / 1024
        if instance_id in self.stopped:
            status["state"] = "ABORTED"
        return httpx.Response(200, json=status)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    @property
    def pipeline_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.startswith("/pipelines")]

    def metrics_reads(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/api/v1/metrics"]

    def calls(self, method: str) -> list[httpx.Request]:
        """Requests to ``/pipelines`` only; ``/validate`` ones are left out."""
        return [r for r in self.pipeline_requests if r.method == method]

    def validate_posts(self) -> list[dict]:
        return [
            json.loads(r.content)
            for r in self.requests
            if r.method == "POST" and r.url.path == "/validate"
        ]


def _running(fps: float, **extra) -> dict:
    # A stream reporting frames has had its first frame.
    first = {"first_frame_time": 1000.0} if fps > 0 else {}
    return {"state": "RUNNING", "frame_fps": fps, **first, **extra}


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
        with (
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            return runner.run(
                PIPELINE,
                total_streams=total_streams,
                stream_commands=stream_commands,
            )


class TestDlsps2RunnerInit(unittest.TestCase):
    def test_latency_metrics_start_with_an_empty_map(self):
        self.assertEqual(
            Dlsps2PipelineRunner(enable_latency_metrics=True).latency_tracer_metrics,
            {},
        )
        self.assertIsNone(Dlsps2PipelineRunner().latency_tracer_metrics)

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
        self.assertEqual(
            json.loads(post.content),
            {"pipeline": PIPELINE, "validate_pipeline": True},
        )
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
            fake.validate_posts(),
            [
                {"pipeline": "pipeline a", "timeout": 120},
                {"pipeline": "pipeline b", "timeout": 120},
            ],
        )
        self.assertEqual(
            [json.loads(p.content) for p in posts],
            [
                {"pipeline": "pipeline a", "validate_pipeline": False},
                {"pipeline": "pipeline b", "validate_pipeline": False},
            ],
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

    def test_window_starts_at_first_frame_before_any_fps_report(self):
        fake = _FakeStreamSet(
            [
                [_running(30.0), _running(0.0, first_frame_time=1000.5)],
                [_running(30.0), _running(20.0)],
            ]
        )

        result = self._run_streams(self._runner(max_runtime=10), fake)

        self.assertEqual(self.clock.now, 10.0)
        self.assertEqual(result.stream_fps, {"a": 30.0, "b": 20.0})

    def test_fps_is_weighted_by_frame_interval_and_each_window_counts_once(self):
        fake = _FakeStreamSet(
            [
                [_running(10.0, frame_interval=1.0)],
                [_running(10.0, frame_interval=1.0)],
                [_running(10.0, frame_interval=1.0)],
                [_running(30.0, frame_interval=0.5)],
                [_running(30.0, frame_interval=0.5)],
                [_running(10.0, frame_interval=1.5)],
            ]
        )

        # Warm-up is max_runtime / 2 = 3 s: windows from t=3 count, t=4 repeats t=3.
        result = self._run(self._runner(max_runtime=6), fake)

        self.assertEqual(result.stream_fps, {"stream": 15.0})

    def test_unchanged_window_counts_as_no_frames(self):
        fake = _FakeStreamSet(
            [
                [_running(30.0), _running(20.0)],
                [_running(30.0), _running(20.0, frame_interval=1.0)],
            ]
        )

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(inactivity_timeout=3), fake)

        self.assertIn("No frames from stream(s) b", str(ctx.exception))
        self.assertEqual(len(fake.calls("DELETE")), 2)

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

    def test_cancel_during_validation_starts_no_instance(self):
        runner = self._runner()

        def cancel_while_queued() -> dict:
            runner.cancel()
            return {"state": "QUEUED"}

        fake = _FakeStreamSet([[_running(30.0)]], validations=[cancel_while_queued])

        result = self._run_streams(runner, fake)

        self.assertTrue(result.cancelled)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake.pipeline_requests, [])
        self.assertEqual(self._pushed_values(), [])

    def test_cancel_while_starting_starts_no_further_instance(self):
        runner = self._runner()
        fake = _FakeStreamSet([[_running(30.0), _running(30.0)]])
        start = runner._start

        def start_then_cancel(*args, **kwargs) -> str:
            instance_id = start(*args, **kwargs)
            runner.cancel()
            return instance_id

        with patch.object(runner, "_start", side_effect=start_then_cancel):
            result = self._run_streams(runner, fake)

        self.assertTrue(result.cancelled)
        self.assertEqual(result.num_streams, 1)
        self.assertEqual(len(fake.calls("POST")), 1)
        self.assertEqual(
            [r.url.path for r in fake.calls("DELETE")], ["/pipelines/inst-1"]
        )

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

        self.assertEqual(len(fake.pipeline_requests), 1)
        self.assertEqual(self._pushed_values(), [])

    def test_each_launch_string_is_validated_once_per_runner(self):
        runner = self._runner()
        done = {"state": "COMPLETED", "avg_fps": 10.0}
        first = _FakeStreamSet([[done, done]])
        second = _FakeStreamSet([[done, done, done]])

        self._run_streams(runner, first)
        self._run(
            runner,
            second,
            total_streams=3,
            stream_commands={**self.STREAMS, "c": "pipeline b"},
        )

        self.assertEqual(len(first.validate_posts()), 2)
        self.assertEqual(second.validate_posts(), [])
        self.assertEqual(len(second.calls("POST")), 3)

    def test_pre_check_can_be_turned_off(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED", "avg_fps": 10.0}]])

        result = self._run(self._runner(validate_pipelines=False), fake)

        self.assertEqual(fake.validate_posts(), [])
        self.assertEqual(
            [json.loads(p.content) for p in fake.calls("POST")],
            [{"pipeline": PIPELINE, "validate_pipeline": False}],
        )
        self.assertEqual(result.total_fps, 10.0)

    def test_invalid_launch_string_raises_before_any_instance_starts(self):
        fake = _FakeStreamSet(
            [[_running(30.0)]],
            validations=[
                {"state": "VALID"},
                {"state": "INVALID", "message": "no element foo"},
            ],
        )

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(), fake)

        self.assertIn(
            "validation failed on DLSPS 2.0: no element foo", str(ctx.exception)
        )
        self.assertEqual(fake.pipeline_requests, [])

    def test_no_validation_verdict_within_inactivity_timeout_raises(self):
        fake = _FakeStreamSet([[_running(30.0)]], validations=[{"state": "QUEUED"}])

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(inactivity_timeout=3), fake)

        self.assertIn("no verdict for 2 launch string(s)", str(ctx.exception))
        self.assertEqual(fake.pipeline_requests, [])

    def test_validation_request_error_reports_server_detail(self):
        fake = _FakeStreamSet(
            [[_running(30.0)]],
            validations=[httpx.Response(404, json={"detail": "not found"})],
        )

        with self.assertRaises(RuntimeError) as ctx:
            self._run_streams(self._runner(), fake)

        self.assertIn("HTTP 404: not found", str(ctx.exception))
        self.assertEqual(fake.pipeline_requests, [])

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

        def cancel() -> list[dict]:
            runner.cancel()
            return [{"state": "QUEUED"}]

        fake = _FakeStreamSet(
            [cancel],
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


def _mm_point(name: str, pipeline_id: str, ts: int, value: float, **tags) -> dict:
    """A metric as metrics-manager stores a DLSPS OTLP data point."""
    histogram = name.startswith("genai_")
    if histogram:
        tags.setdefault("temporality", "delta")
    return {
        "name": name,
        "fields": (
            {"count": 2, "sum": 2 * value, "avg": value, "min": value, "max": value}
            if histogram
            else {"value": value}
        ),
        "tags": {"service.name": "dlsps2", "pipeline_id": pipeline_id, **tags},
        "timestamp": ts,
    }


def _latency_export(pipeline_id, ts, source, sink, avg, mn, mx, frames, window):
    branch = {"source": source, "sink": sink}
    return [
        _mm_point("pipeline_latency_avg", pipeline_id, ts, avg, **branch),
        _mm_point("pipeline_latency_min", pipeline_id, ts, mn, **branch),
        _mm_point("pipeline_latency_max", pipeline_id, ts, mx, **branch),
        _mm_point("pipeline_latency_frames", pipeline_id, ts, frames, **branch),
        _mm_point("pipeline_latency_window", pipeline_id, ts, window, **branch),
    ]


def _genai_export(pipeline_id, ts, ttft, tpot, duration, element="gvagenai_a"):
    return [
        _mm_point(name, pipeline_id, ts, value, element=element)
        for name, value in (
            ("genai_ttft", ttft),
            ("genai_tpot", tpot),
            ("genai_generate_duration", duration),
        )
    ]


GVAGENAI_WITH_POST_METRICS = """Element Properties:

  metrics             : Include performance metrics in the JSON output
                        flags: readable, writable
                        Boolean. Default: false
  post-metrics        : Post a "dlstreamer/genai-request" element message
                        flags: readable, writable
                        Boolean. Default: false
"""
GVAGENAI_WITHOUT_POST_METRICS = """Element Properties:

  metrics             : Include performance metrics in the JSON output
                        flags: readable, writable
                        Boolean. Default: false
"""


def _finished(*pipeline_ids: str, ts: int = 500) -> list[dict]:
    return [_mm_point("pipeline_running", iid, ts, 0.0) for iid in pipeline_ids]


class TestDlsps2RunnerMetricsManager(Dlsps2RunnerTestBase):
    """Latency and VLM samples come from DLSPS's OTel export via metrics-manager."""

    STREAMS = {"src_a__sink_a": "pipeline a", "src_b__sink_b": "pipeline b"}
    POLLS = [[_running(30.0), _running(30.0)]]

    def _runner(self, **kwargs) -> Dlsps2PipelineRunner:
        runner = Dlsps2PipelineRunner(
            mode="normal",
            base_url="http://dlsps:8080",
            job_id="job-1",
            max_runtime=4,
            **kwargs,
        )
        patch.object(runner, "_push_fps_metric").start()
        self.batches: list[tuple[list[dict], str]] = []
        patch.object(
            runner,
            "_post_batch",
            side_effect=lambda metrics, description: self.batches.append(
                (metrics, description)
            ),
        ).start()
        self.addCleanup(patch.stopall)
        return runner

    def _run_with(self, runner, fake, streams=None):
        with (
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            return runner.run(
                PIPELINE,
                total_streams=2,
                allowed_stream_ids=set(self.STREAMS),
                stream_commands=streams or self.STREAMS,
            )

    def _pushed(self, description: str) -> list[dict]:
        return [m for metrics, d in self.batches if d == description for m in metrics]

    def test_latency_is_republished_per_stream_with_job_tags(self):
        metrics = (
            _latency_export(
                "inst-1", 100, "src_a", "sink_a", 10.0, 5.0, 20.0, 30, 1000.0
            )
            + _latency_export(
                "inst-1", 200, "src_a", "sink_a", 12.0, 6.0, 30.0, 25, 1000.0
            )
            + _latency_export(
                "inst-2", 100, "src_b", "sink_b", 50.0, 40.0, 60.0, 10, 2000.0
            )
            # Another job's instance, an internal bin sink, an incomplete export.
            + _latency_export("other", 100, "src_a", "sink_a", 1.0, 1.0, 1.0, 1, 1.0)
            + _latency_export("inst-1", 100, "src_a", "sink", 1.0, 1.0, 1.0, 1, 1.0)
            + [
                _mm_point(
                    "pipeline_latency_avg",
                    "inst-2",
                    300,
                    99.0,
                    source="src_b",
                    sink="sink_b",
                )
            ]
            + _finished("inst-1", "inst-2")
        )
        fake = _FakeStreamSet(self.POLLS, metrics=metrics)

        result = self._run_with(self._runner(enable_latency_metrics=True), fake)

        latency = result.latency_tracer_metrics
        assert latency is not None
        self.assertEqual(set(latency), set(self.STREAMS))
        self.assertEqual(latency["src_a__sink_a"].avg_ms, 12.0)
        self.assertEqual(latency["src_a__sink_a"].max_ms, 30.0)
        self.assertEqual(latency["src_a__sink_a"].latency_ms, 1000.0 / 25)
        self.assertEqual(latency["src_b__sink_b"].interval_ms, 2000.0)
        self.assertEqual(latency["src_b__sink_b"].latency_ms, 200.0)

        pushed = self._pushed("latency")
        # Every export period exactly once, though metrics-manager was read repeatedly.
        self.assertEqual(len(pushed), 3)
        self.assertGreater(len(fake.metrics_reads()), 5)
        self.assertEqual(
            pushed[0],
            {
                "name": "pipeline_latency",
                "fields": {
                    "avg_ms": 10.0,
                    "min_ms": 5.0,
                    "max_ms": 20.0,
                    "latency_ms": 1000.0 / 30,
                },
                "tags": {"job_id": "job-1", "stream_id": "src_a__sink_a"},
            },
        )

    def test_only_dlsps_series_names_are_read(self):
        """ViPPET's own republished series are never read back as DLSPS data."""
        fake = _FakeStreamSet(
            self.POLLS,
            metrics=[
                {
                    "name": "pipeline_latency",
                    "fields": {"avg_ms": 1.0, "min_ms": 1.0, "max_ms": 1.0},
                    "tags": {"job_id": "job-1", "stream_id": "src_a__sink_a"},
                    "timestamp": 100,
                }
            ]
            + _finished("inst-1", "inst-2"),
        )

        with self.assertLogs("dlsps2_runner", level="WARNING"):
            result = self._run_with(self._runner(enable_latency_metrics=True), fake)

        self.assertEqual(result.latency_tracer_metrics, {})
        names = {r.url.params.get("name") for r in fake.metrics_reads()}
        self.assertEqual(
            names,
            {
                "pipeline_running",
                "pipeline_latency_avg",
                "pipeline_latency_min",
                "pipeline_latency_max",
                "pipeline_latency_frames",
                "pipeline_latency_window",
            },
        )

    def test_export_split_over_two_seconds_is_joined(self):
        export = _latency_export(
            "inst-1", 100, "src_a", "sink_a", 10.0, 5.0, 20.0, 30, 1000.0
        )
        for point in export[3:]:
            point["timestamp"] = 101
        fake = _FakeStreamSet(
            self.POLLS, metrics=export + _finished("inst-1", "inst-2")
        )

        result = self._run_with(self._runner(enable_latency_metrics=True), fake)

        assert result.latency_tracer_metrics is not None
        self.assertEqual(result.latency_tracer_metrics["src_a__sink_a"].avg_ms, 10.0)
        self.assertEqual(len(self._pushed("latency")), 1)

    def test_two_exports_within_one_second_are_both_republished(self):
        fake = _FakeStreamSet(self.POLLS)
        fake.metrics = _finished("inst-1", "inst-2")
        first = _latency_export(
            "inst-1", 100, "src_a", "sink_a", 10.0, 5.0, 20.0, 30, 1000.0
        )
        second = _latency_export(
            "inst-1", 100, "src_a", "sink_a", 11.0, 5.0, 20.0, 3, 100.0
        )
        runner = self._runner(enable_latency_metrics=True)
        instances = {"src_a__sink_a": "inst-1"}

        with fake.client() as client:
            fake.metrics = first
            runner._poll_metrics_manager(client, instances, None, False)
            fake.metrics = first + second
            runner._poll_metrics_manager(client, instances, None, False)
            runner._poll_metrics_manager(client, instances, None, False)

        self.assertEqual(
            [p["fields"]["avg_ms"] for p in self._pushed("latency")], [10.0, 11.0]
        )

    def test_vlm_requests_are_republished_with_the_element_as_stream(self):
        streams = {"src_a__sink_a": "a ! gvagenai name=gvagenai_a metrics=true ! b"}
        cumulative = _genai_export("inst-1", 150, 1.0, 1.0, 1.0)
        for point in cumulative:
            point["tags"]["temporality"] = "cumulative"
        idle = _mm_point("genai_ttft", "inst-1", 160, 0.0, element="gvagenai_a")
        idle["fields"] = {"count": 0}
        metrics = (
            _genai_export("inst-1", 100, 900.0, 40.0, 1300.0)
            + cumulative
            + [idle]
            + _finished("inst-1")
        )
        fake = _FakeStreamSet(
            [[_running(1.0)]], metrics=metrics, gvagenai=GVAGENAI_WITH_POST_METRICS
        )

        result = self._run_with(self._runner(), fake, streams)

        self.assertIsNone(result.latency_tracer_metrics)
        self.assertEqual(
            self._pushed("vlm"),
            [
                {
                    "name": "vlm_metrics",
                    "fields": {
                        "ttft_ms": 900.0,
                        "tpot_ms": 40.0,
                        "generate_duration_ms": 1300.0,
                    },
                    "tags": {"job_id": "job-1", "stream_id": "gvagenai_a"},
                }
            ],
        )

    def test_genai_points_without_histogram_fields_are_skipped(self):
        """A metrics-manager without histogram support stores them as value 0."""
        streams = {"src_a__sink_a": "a ! gvagenai name=gvagenai_a metrics=true ! b"}
        flattened = _genai_export("inst-1", 100, 900.0, 40.0, 1300.0)
        for point in flattened:
            point["fields"] = {"value": 0}
            del point["tags"]["temporality"]
        fake = _FakeStreamSet(
            [[_running(1.0)]],
            metrics=flattened + _finished("inst-1"),
            gvagenai=GVAGENAI_WITH_POST_METRICS,
        )
        runner = self._runner()

        with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
            self._run_with(runner, fake, streams)

        self.assertEqual(self._pushed("vlm"), [])
        self.assertTrue(any("histogram support" in m for m in logs.output))
        # Answers read from event files now provide VLM metrics.
        self.assertTrue(runner._vlm_from_answers)

    def test_metrics_manager_is_not_read_without_latency_or_vlm(self):
        fake = _FakeStreamSet(self.POLLS)

        self._run_with(self._runner(), fake)

        self.assertEqual(fake.metrics_reads(), [])

    def test_missing_samples_are_warned_about(self):
        fake = _FakeStreamSet(self.POLLS, metrics=_finished("inst-1", "inst-2"))

        with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
            result = self._run_with(self._runner(enable_latency_metrics=True), fake)

        self.assertEqual(result.latency_tracer_metrics, {})
        self.assertIn("no DLSPS latency samples", logs.output[-1])
        self.assertIn("post-metrics=true", logs.output[-1])

    def test_no_missing_samples_warning_when_cancelled(self):
        runner = self._runner(enable_latency_metrics=True)

        def _cancel():
            runner.cancel()
            return [_running(30.0), _running(30.0)]

        fake = _FakeStreamSet([_cancel], metrics=_finished("inst-1", "inst-2"))

        with self.assertNoLogs("dlsps2_runner", level="WARNING"):
            result = self._run_with(runner, fake)

        self.assertTrue(result.cancelled)
        self.assertEqual(result.latency_tracer_metrics, {})

    def test_unreachable_metrics_manager_does_not_fail_the_run(self):
        fake = _FakeStreamSet(self.POLLS, metrics=httpx.Response(503))

        with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
            result = self._run_with(self._runner(enable_latency_metrics=True), fake)

        self.assertEqual(result.total_fps, 60.0)
        failures = [line for line in logs.output if "Failed to read DLSPS" in line]
        self.assertEqual(len(failures), 1)

    def test_metrics_manager_uses_its_own_short_timeout_client(self):
        runner = Dlsps2PipelineRunner()

        with runner._metrics_client() as client:
            self.assertEqual(
                client.timeout.read, dlsps2_runner.DLSPS2_METRICS_HTTP_TIMEOUT_S
            )
        self.assertLess(
            dlsps2_runner.DLSPS2_METRICS_HTTP_TIMEOUT_S,
            dlsps2_runner.DLSPS2_HTTP_TIMEOUT_S,
        )

    def test_metrics_reads_go_through_the_metrics_client(self):
        fake = _FakeStreamSet(self.POLLS, metrics=_finished("inst-1", "inst-2"))
        dlsps_only = _FakeStreamSet(self.POLLS)
        runner = self._runner(enable_latency_metrics=True)

        with (
            patch.object(runner, "_client", side_effect=dlsps_only.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
            self.assertLogs("dlsps2_runner", level="WARNING"),
        ):
            runner.run(PIPELINE, total_streams=2, stream_commands=self.STREAMS)

        self.assertEqual(dlsps_only.metrics_reads(), [])
        self.assertTrue(fake.metrics_reads())

    def test_state_of_an_earlier_run_is_dropped(self):
        runner = self._runner(enable_latency_metrics=True)
        first = _FakeStreamSet(
            self.POLLS,
            metrics=_latency_export(
                "inst-1", 100, "src_a", "sink_a", 10.0, 5.0, 20.0, 30, 1000.0
            )
            + _finished("inst-1", "inst-2"),
        )
        self._run_with(runner, first)
        self.assertEqual(set(runner.latency_tracer_metrics or {}), {"src_a__sink_a"})

        second = _FakeStreamSet(self.POLLS, metrics=_finished("inst-1", "inst-2"))
        with self.assertLogs("dlsps2_runner", level="WARNING"):
            result = self._run_with(runner, second)

        self.assertEqual(result.latency_tracer_metrics, {})


class TestDlsps2RunnerFinalExport(Dlsps2RunnerTestBase):
    """After stopping, metrics-manager is read until each instance's final export arrives."""

    STREAMS = {"src_a__sink_a": "pipeline a"}

    def _runner(self, max_runtime: float = 4) -> Dlsps2PipelineRunner:
        runner = Dlsps2PipelineRunner(
            mode="normal",
            base_url="http://dlsps:8080",
            max_runtime=max_runtime,
            enable_latency_metrics=True,
        )
        patch.object(runner, "_push_fps_metric").start()
        patch.object(runner, "_post_batch").start()
        self.addCleanup(patch.stopall)
        return runner

    def _run_with(self, runner, fake):
        self.stopped_at: float | None = None
        original = runner._stop_all

        def _stop_all(client, ids):
            self.stopped_at = self.clock.now
            original(client, ids)

        with (
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
            patch.object(runner, "_stop_all", side_effect=_stop_all),
        ):
            return runner.run(PIPELINE, total_streams=1, stream_commands=self.STREAMS)

    def _final_reads(self, fake) -> int:
        return sum(
            1
            for r in fake.metrics_reads()
            if r.url.params.get("name") == "pipeline_running"
        )

    def test_final_export_arriving_late_is_still_read(self):
        """The flush lands after DELETE returned; the runner waits for it."""
        running = [_mm_point("pipeline_running", "inst-1", 100, 1.0)]
        fake = _FakeStreamSet([[_running(30.0)]], metrics=running)
        late = _latency_export(
            "inst-1", 200, "src_a", "sink_a", 10.0, 5.0, 20.0, 30, 1000.0
        ) + _finished("inst-1", ts=200)
        reads_after_stop = 0
        handler = fake.handler

        def _handler(request):
            nonlocal reads_after_stop
            if (
                self.stopped_at is not None
                and request.url.params.get("name") == "pipeline_running"
            ):
                reads_after_stop += 1
                if reads_after_stop == 3:
                    fake.metrics = running + late
            return handler(request)

        fake.handler = _handler  # type: ignore[method-assign]

        result = self._run_with(self._runner(), fake)

        assert result.latency_tracer_metrics is not None
        self.assertEqual(result.latency_tracer_metrics["src_a__sink_a"].avg_ms, 10.0)
        self.assertEqual(reads_after_stop, 3)

    def test_wait_is_bounded_by_the_export_interval(self):
        running = [_mm_point("pipeline_running", "inst-1", 100, 1.0)]
        fake = _FakeStreamSet([[_running(30.0)]], metrics=running)

        with self.assertLogs("dlsps2_runner", level="WARNING"):
            self._run_with(self._runner(), fake)

        assert self.stopped_at is not None
        waited = self.clock.now - self.stopped_at
        limit = dlsps2_runner.DLSPS2_OTEL_INTERVAL_MS / 1000 + 2.0
        self.assertLessEqual(waited, limit + 1.0)
        self.assertGreaterEqual(waited, limit - 1.0)

    def test_no_wait_once_the_final_export_is_there(self):
        fake = _FakeStreamSet([[_running(30.0)]], metrics=_finished("inst-1"))

        with self.assertLogs("dlsps2_runner", level="WARNING"):
            self._run_with(self._runner(), fake)

        assert self.stopped_at is not None
        self.assertLess(self.clock.now - self.stopped_at, 1.0)

    def test_no_wait_without_any_export_in_a_long_run(self):
        """A run longer than the wait that saw no export: telemetry is off."""
        fake = _FakeStreamSet([[_running(30.0)]])

        with self.assertLogs("dlsps2_runner", level="WARNING"):
            self._run_with(self._runner(max_runtime=30), fake)

        assert self.stopped_at is not None
        self.assertLess(self.clock.now - self.stopped_at, 1.0)

    def test_no_wait_when_cancelled(self):
        runner = self._runner()

        def _cancel():
            runner.cancel()
            return [_running(30.0)]

        fake = _FakeStreamSet([_cancel])

        self._run_with(runner, fake)

        assert self.stopped_at is not None
        self.assertLess(self.clock.now - self.stopped_at, 1.0)
        self.assertEqual(self._final_reads(fake), 1)


class TestDlsps2LatencyConfigured(unittest.TestCase):
    TRACERS = "latency_tracer(flags=pipeline,interval=1000,post-metrics=true)"

    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(dlsps2_runner.dlsps2_latency_configured())

    def test_on_with_complete_setup(self):
        env = {"DLSPS2_OTEL": "true", "DLSPS2_GST_TRACERS": self.TRACERS}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(dlsps2_runner.dlsps2_latency_configured())

    def test_incomplete_setup_is_off(self):
        for env in (
            {"DLSPS2_GST_TRACERS": self.TRACERS},
            {"DLSPS2_OTEL": "false", "DLSPS2_GST_TRACERS": self.TRACERS},
            {"DLSPS2_OTEL": "true"},
            {
                "DLSPS2_OTEL": "true",
                "DLSPS2_GST_TRACERS": "latency_tracer(flags=pipeline)",
            },
        ):
            with self.subTest(env=env):
                with patch.dict(os.environ, env, clear=True):
                    self.assertFalse(dlsps2_runner.dlsps2_latency_configured())


class TestWithGenaiPostMetrics(unittest.TestCase):
    def test_adds_post_metrics_to_gvagenai_with_metrics(self):
        command = (
            'filesrc ! gvagenai prompt="Hi! Is it?" metrics=true ! '
            "gvagenai metrics=false ! gvagenai ! fakesink"
        )
        self.assertTrue(dlsps2_runner.wants_genai_post_metrics(command))
        self.assertEqual(
            dlsps2_runner.with_genai_post_metrics(command),
            'filesrc ! gvagenai prompt="Hi! Is it?" metrics=true post-metrics=true ! '
            "gvagenai metrics=false ! gvagenai ! fakesink",
        )

    def test_keeps_an_explicit_post_metrics(self):
        command = "a ! gvagenai metrics=true post-metrics=false ! b"
        self.assertFalse(dlsps2_runner.wants_genai_post_metrics(command))
        self.assertEqual(dlsps2_runner.with_genai_post_metrics(command), command)

    def test_nothing_wanted_without_metrics(self):
        for command in (PIPELINE, "a ! gvagenai ! b", "a ! gvagenai metrics=false ! b"):
            with self.subTest(command=command):
                self.assertFalse(dlsps2_runner.wants_genai_post_metrics(command))


class TestDlsps2RunnerGenaiPostMetrics(unittest.TestCase):
    """``post-metrics=true`` is added only if the server's gvagenai has it."""

    STREAMS = {"s": "a ! gvagenai metrics=true ! b"}

    def _run(self, fake: _FakeStreamSet, streams=None) -> Dlsps2PipelineRunner:
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            runner.run(PIPELINE, stream_commands=streams or self.STREAMS)
        return runner

    @staticmethod
    def _fake(**kwargs) -> _FakeStreamSet:
        return _FakeStreamSet(
            [[{"state": "COMPLETED"}]], metrics=_finished("inst-1"), **kwargs
        )

    @staticmethod
    def _sent(fake: _FakeStreamSet) -> list[str]:
        return [json.loads(r.content)["pipeline"] for r in fake.calls("POST")]

    def test_added_when_the_server_gvagenai_has_the_property(self):
        fake = self._fake(gvagenai=GVAGENAI_WITH_POST_METRICS)

        self._run(fake)

        self.assertEqual(
            self._sent(fake), ["a ! gvagenai metrics=true post-metrics=true ! b"]
        )
        self.assertEqual(
            fake.validate_posts()[0]["pipeline"],
            "a ! gvagenai metrics=true post-metrics=true ! b",
        )
        self.assertTrue(fake.metrics_reads())

    def test_not_added_when_the_server_cannot_tell(self):
        """An older server image, a missing element, or an error: run unchanged, warn."""
        for gvagenai in (
            GVAGENAI_WITHOUT_POST_METRICS,
            None,
            httpx.Response(500),
            httpx.Response(200, json=["not", "a", "dict"]),
        ):
            with self.subTest(gvagenai=gvagenai):
                fake = self._fake(gvagenai=gvagenai)

                with self.assertLogs("dlsps2_runner", level="WARNING") as logs:
                    self._run(fake)

                self.assertEqual(self._sent(fake), ["a ! gvagenai metrics=true ! b"])
                self.assertIn("VLM metrics are not collected", logs.output[0])
                # Without posting elements there is nothing to read.
                self.assertEqual(fake.metrics_reads(), [])

    def test_server_is_asked_once_per_runner(self):
        fake = self._fake(gvagenai=GVAGENAI_WITH_POST_METRICS)
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            for _ in range(2):
                fake.posted = 0
                fake.stopped.clear()
                runner.run(PIPELINE, stream_commands=self.STREAMS)

        asked = [r for r in fake.requests if r.url.path == "/elements/gvagenai"]
        self.assertEqual(len(asked), 1)

    def test_server_not_asked_without_gvagenai_metrics(self):
        fake = self._fake(gvagenai=GVAGENAI_WITH_POST_METRICS)

        self._run(fake, {"s": PIPELINE})

        self.assertFalse(
            [r for r in fake.requests if r.url.path.startswith("/elements")]
        )


if __name__ == "__main__":
    unittest.main()


class TestDlsps2RunnerEvents(unittest.TestCase):
    """With ``on_event`` the run collects events from the files it adds."""

    STREAMS = {
        "s0": 'a ! gvaproximitytrigger_py name=t0 ! gvagenai name=g0 prompt="q" '
        "metrics=true ! b"
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch("pipeline_events.EVENTS_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, fake: _FakeStreamSet, on_event, gvagenai_metrics=None):
        runner = Dlsps2PipelineRunner(
            mode="normal",
            base_url="http://dlsps:8080",
            max_runtime=0,
            job_id="job-1",
            on_event=on_event,
        )
        pushes: list[dict] = []
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(
                runner, "_post_batch", side_effect=lambda m, _d: pushes.extend(m)
            ),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            runner.run(PIPELINE, stream_commands=self.STREAMS)
        return pushes

    def _files(self, fake: _FakeStreamSet) -> tuple[str, str]:
        sent = json.loads(fake.calls("POST")[0].content)["pipeline"]
        trigger = sent.split("events-file=")[1].split()[0]
        genai = sent.split("gvametapublish file-format=json-lines file-path=")[1]
        return trigger, genai.split()[0]

    def test_events_and_vlm_fallback_metrics_reach_the_job(self):
        events: list = []
        fake = _FakeStreamSet([[{"state": "COMPLETED"}]], metrics=_finished("inst-1"))

        written: list[bool] = []

        def _completed_after_writing() -> list[dict]:
            if written:
                return [{"state": "COMPLETED"}]
            written.append(True)
            trigger, genai = self._files(fake)
            with open(trigger, "a", encoding="utf-8") as f:
                f.write(json.dumps({"source": "proximity-trigger", "text": "hit"}))
                f.write("\n")
            with open(genai, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "result": "No.",
                            "timestamp_seconds": 2.0,
                            "metrics": {
                                "ttft_mean": 1,
                                "tpot_mean": 2,
                                "generate_duration_mean": 3,
                            },
                        }
                    )
                    + "\n"
                )
            return [{"state": "COMPLETED"}]

        fake.polls = [_completed_after_writing]

        with self.assertLogs("dlsps2_runner", level="WARNING"):
            pushes = self._run(fake, events.append)

        self.assertEqual(
            [(e.source, e.text, e.element, e.prompt) for e in events],
            [("proximity-trigger", "hit", "t0", None), ("vlm", "No.", "g0", "q")],
        )
        self.assertEqual(
            pushes,
            [
                {
                    "name": "vlm_metrics",
                    "fields": {
                        "ttft_ms": 1.0,
                        "tpot_ms": 2.0,
                        "generate_duration_ms": 3.0,
                    },
                    "tags": {"job_id": "job-1", "stream_id": "g0"},
                }
            ],
        )
        # Only the started launch string writes event files; the validated
        # one has neither the events-file nor the injected publisher.
        validated = fake.validate_posts()[0]["pipeline"]
        self.assertNotIn("events-file", validated)
        self.assertNotIn("gvametapublish", validated)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_no_files_without_on_event(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED"}]], metrics=_finished("inst-1"))
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            runner.run(PIPELINE, stream_commands=self.STREAMS)

        sent = json.loads(fake.calls("POST")[0].content)["pipeline"]
        self.assertEqual(sent, self.STREAMS["s0"])
        self.assertEqual(os.listdir(self.tmp.name), [])


class TestWithFpsChainLast(unittest.TestCase):
    SID = "src_p0_s0__sink_p0_s0"
    MAIN = (
        "filesrc location=/v.ts ! tsdemux ! decodebin3 ! tee name=t ! queue ! "
        "fakesink name=sink_p0_s0"
    )
    SIDE = 't. ! queue ! gvagenai prompt="Is it! safe?" ! fakesink name=vlm'

    def test_main_chain_moves_after_the_side_branch(self):
        self.assertEqual(
            dlsps2_runner.with_fps_chain_last(f"{self.MAIN} {self.SIDE}", self.SID),
            f"{self.SIDE} {self.MAIN}",
        )

    def test_main_branch_of_a_tee_moves_last(self):
        command = (
            "videotestsrc ! tee name=t t. ! queue ! fakesink name=sink_p0_s0 "
            "t. ! queue ! fakesink name=side"
        )
        self.assertEqual(
            dlsps2_runner.with_fps_chain_last(command, self.SID),
            "videotestsrc ! tee name=t t. ! queue ! fakesink name=side "
            "t. ! queue ! fakesink name=sink_p0_s0",
        )

    def test_caps_with_parentheses_are_not_bins(self):
        # Caps features and typed fields, as in GPU/NPU pipelines after
        # decodebin3 is replaced (graph.apply_decodebin3_replacement).
        for caps in (
            "video/x-raw(memory:VAMemory)",
            r"video/x-raw\(memory:VAMemory\)",
            "video/x-raw(memory:VAMemory),format=NV12,width=320",
            "video/x-raw,format=(string)NV12,width=(int)320,framerate=(fraction)30/1",
        ):
            main = (
                f"filesrc location=/v.ts ! parsebin ! vah264dec ! {caps} ! "
                "gvadetect device=GPU ! tee name=t ! queue ! "
                "fakesink name=sink_p0_s0"
            )
            with self.subTest(caps=caps):
                self.assertEqual(
                    dlsps2_runner.with_fps_chain_last(f"{main} {self.SIDE}", self.SID),
                    f"{self.SIDE} {main}",
                )

    def test_unchanged_cases(self):
        for command, stream_id in (
            (f"{self.SIDE} {self.MAIN}", self.SID),  # already last
            (f"{self.MAIN} {self.SIDE}", "stream"),  # no sink in the id
            (f"{self.MAIN} {self.SIDE}", "src__other_sink"),  # sink not found
            ("a ! ( b ! fakesink name=sink_p0_s0 ) c ! fakesink", self.SID),  # bin
            ("a ! (b ! fakesink name=sink_p0_s0) c ! fakesink", self.SID),  # bin
            ("a ! fakesink name=sink_p0_s0 c !fakesink", self.SID),  # odd link
        ):
            with self.subTest(command=command, stream_id=stream_id):
                self.assertEqual(
                    dlsps2_runner.with_fps_chain_last(command, stream_id), command
                )

    def test_counted_side_branch_moves_last(self):
        # video-captioning-vlm / alerting-vlm: gvafpscounter on the VLM branch.
        side = (
            "t. ! queue leaky=downstream max-size-buffers=1 ! gvagenai "
            'prompt="Is it! safe?" ! gvafpscounter starting-frame=10 ! '
            "fakesink sync=false async=false"
        )
        self.assertEqual(
            dlsps2_runner.with_fps_chain_last(f"{self.MAIN} {side}", self.SID),
            f"{self.MAIN} {side}",
        )
        self.assertEqual(
            dlsps2_runner.with_fps_chain_last(f"{side} {self.MAIN}", self.SID),
            f"{self.MAIN} {side}",
        )

    def test_counted_main_chain_moves_last(self):
        # cv-triggered-vlm: gvafpscounter before a second tee on the main chain.
        main = (
            "filesrc location=/v.ts ! decodebin3 ! tee name=t ! queue ! "
            "gvafpscounter ! tee name=t2 ! queue ! fakesink name=sink_p0_s0"
        )
        record = "t2. ! queue ! filesink location=/out.mp4"
        self.assertEqual(
            dlsps2_runner.with_fps_chain_last(f"{main} {record} {self.SIDE}", self.SID),
            f"{record} {self.SIDE} {main}",
        )

    def test_main_sink_when_gvafpscounter_does_not_pick_one_chain(self):
        counted = "t. ! queue ! gvafpscounter ! fakesink name=a"
        for side in (
            f"{counted} t. ! queue ! gvafpscounter ! fakesink name=b",  # two
            "t. ! queue ! gvafpscounter ! tee name=t2 t2. ! fakesink",  # no sink
        ):
            with self.subTest(side=side):
                self.assertEqual(
                    dlsps2_runner.with_fps_chain_last(f"{self.MAIN} {side}", self.SID),
                    f"{side} {self.MAIN}",
                )

    def test_runs_start_with_the_main_sink_last(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED"}]])
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            runner.run(PIPELINE, stream_commands={self.SID: f"{self.MAIN} {self.SIDE}"})

        sent = json.loads(fake.calls("POST")[0].content)["pipeline"]
        self.assertEqual(sent, f"{self.SIDE} {self.MAIN}")


class TestValidationLaunchString(unittest.TestCase):
    def test_writing_sinks_become_fakesinks(self):
        command = (
            "filesrc location=/v.ts ! decodebin3 ! tee name=t ! queue ! "
            "vah264enc ! h264parse ! mp4mux ! filesink location=/out/a.mp4 "
            "name=sink_p0_s0 sync=false t. ! queue ! jpegenc ! "
            "multifilesink location=/img/f_%05d.jpeg async=false "
            "t. ! queue ! splitmuxsink location=/rec/%03d.mp4 max-size-time=1"
        )

        self.assertEqual(
            dlsps2_runner.validation_launch_string(command),
            "filesrc location=/v.ts ! decodebin3 ! tee name=t ! queue ! "
            "vah264enc ! h264parse ! mp4mux ! fakesink name=sink_p0_s0 "
            "async=false sync=false t. ! queue ! jpegenc ! fakesink async=false "
            "t. ! queue ! fakesink async=false",
        )

    def test_live_stream_and_metadata_writers(self):
        command = (
            'a ! gvagenai prompt="Hit? Reply ! briefly" ! '
            "gvametapublish file-format=json-lines file-path=/metadata/x.jsonl ! "
            "vah264enc ! rtspclientsink location=rtsp://mediamtx:8554/s name=out"
        )

        self.assertEqual(
            dlsps2_runner.validation_launch_string(command),
            'a ! gvagenai prompt="Hit? Reply ! briefly" ! identity ! '
            "vah264enc ! fakesink name=out async=false",
        )

    def test_unchanged_cases(self):
        for command in (
            "videotestsrc ! gvadetect ! fakesink name=default_output_sink",
            # The sink's pads are referenced by name, so it must stay.
            "a ! splitmuxsink name=mux location=/r.mp4 b ! queue ! mux.video",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    dlsps2_runner.validation_launch_string(command), command
                )


class TestDlsps2RunnerValidationStreams(unittest.TestCase):
    STREAMS = {
        "s0": "a ! vah264enc ! filesink location=/out/s0.mp4 name=s0",
        "s1": "a ! fakesink name=s1",
    }

    def _run(self, fake, **kwargs):
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            return runner.run(PIPELINE, stream_commands=self.STREAMS, **kwargs)

    def test_validates_only_the_given_streams_without_writers(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED"}, {"state": "COMPLETED"}]])

        self._run(fake, validation_stream_ids={"s0"})

        self.assertEqual(
            [body["pipeline"] for body in fake.validate_posts()],
            ["a ! vah264enc ! fakesink name=s0 async=false"],
        )
        started = sorted(json.loads(r.content)["pipeline"] for r in fake.calls("POST"))
        self.assertEqual(started, sorted(self.STREAMS.values()))
        self.assertTrue(
            all(
                json.loads(r.content)["validate_pipeline"] is False
                for r in fake.calls("POST")
            )
        )

    def test_without_ids_every_stream_is_validated(self):
        fake = _FakeStreamSet([[{"state": "COMPLETED"}, {"state": "COMPLETED"}]])

        self._run(fake)

        self.assertEqual(len(fake.validate_posts()), 2)


class TestDlsps2RunnerLostInstance(unittest.TestCase):
    STREAMS = {"s0": "a ! fakesink name=s0", "s1": "a ! fakesink name=s1"}

    def _run(self, fake):
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            return runner.run(PIPELINE, stream_commands=self.STREAMS)

    def test_lost_instance_fails_the_run_at_once(self):
        fake = _FakeStreamSet([[]])

        with self.assertRaisesRegex(RuntimeError, "no longer reports stream"):
            self._run(fake)
        # The first poll fails the run; the second is the final read after the
        # instances are stopped.
        self.assertEqual(fake.status_polls, 2)
        self.assertEqual(len(fake.calls("DELETE")), 2)


class TestDlsps2RunnerPerInstancePolling(unittest.TestCase):
    def test_polls_each_instance_not_the_whole_registry(self):
        streams = {"s0": "a ! fakesink name=s0", "s1": "a ! fakesink name=s1"}
        fake = _FakeStreamSet(
            [[_running(30.0), _running(20.0)], [{"state": "COMPLETED"}] * 2]
        )
        runner = Dlsps2PipelineRunner(
            mode="normal", base_url="http://dlsps:8080", max_runtime=0
        )
        with (
            patch.object(runner, "_push_fps_metric"),
            patch.object(runner, "_client", side_effect=fake.client),
            patch.object(runner, "_metrics_client", side_effect=fake.client),
        ):
            runner.run(PIPELINE, stream_commands=streams)

        polled = [r.url.path for r in fake.calls("GET")]
        self.assertNotIn("/pipelines/status", polled)
        self.assertIn("/pipelines/inst-1/status", polled)
        self.assertIn("/pipelines/inst-2/status", polled)


class TestStopLeftoverInstances(unittest.TestCase):
    def _client(self, handler):
        real_client = httpx.Client
        return patch(
            "dlsps2_runner.httpx.Client",
            side_effect=lambda **_: real_client(transport=httpx.MockTransport(handler)),
        )

    def test_stops_only_active_instances(self):
        deleted = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "DELETE":
                deleted.append(request.url.path.rsplit("/", 1)[-1])
                return httpx.Response(200)
            return httpx.Response(
                200,
                json=[
                    {"id": "run", "state": "RUNNING"},
                    {"id": "queued", "state": "QUEUED"},
                    {"id": "done", "state": "COMPLETED"},
                    {"id": "gone", "state": "ABORTED"},
                ],
            )

        with self._client(handler), self.assertLogs("dlsps2_runner", "WARNING"):
            stopped = dlsps2_runner.stop_leftover_instances(base_url="http://d:8080")

        self.assertEqual(stopped, 2)
        self.assertEqual(sorted(deleted), ["queued", "run"])

    def test_unreachable_server_is_logged(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with self._client(handler), self.assertLogs("dlsps2_runner", "WARNING") as logs:
            self.assertEqual(
                dlsps2_runner.stop_leftover_instances(base_url="http://d:8080"), 0
            )
        self.assertTrue(any("leftover" in m for m in logs.output))
