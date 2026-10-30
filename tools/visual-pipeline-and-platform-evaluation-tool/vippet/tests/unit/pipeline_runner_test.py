import itertools
import json
import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

import pipeline_runner
from pipeline_runner import (
    PipelineRunner,
    PipelineResult,
    LatencyTracerSample,
)


class _SyncExecutor:
    """Test double for the metrics-push ``ThreadPoolExecutor``.

    Production code submits every metrics push
    (``_post_metrics_async``) to a shared class-level
    ``ThreadPoolExecutor`` so the pipeline hot loop is never blocked
    by HTTP I/O. That makes assertions like
    ``mock_urlopen.assert_called_once()`` racy in unit tests — by
    the time the assertion runs, the worker may not have executed
    yet.

    Patching ``PipelineRunner._get_metrics_executor`` to return this
    stub makes every push synchronous and deterministic:
    ``submit(fn, *args, **kwargs)`` simply invokes ``fn`` in the
    calling thread. The worker's own try/except still swallows
    exceptions, so test behaviour mirrors production apart from
    timing.
    """

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        # Return a real-looking sentinel so callers that store the
        # future do not trip over ``None``. No test inspects it.
        return MagicMock(name="sync-future")


def _patch_sync_metrics_executor(target):
    """Decorator that swaps the shared metrics executor for a sync stub.

    Uses ``patch.object(..., new=...)`` so no extra mock argument is
    injected into the decorated methods — keeping test signatures
    unchanged when the decorator is applied at class level.

    The replacement is wrapped in ``classmethod`` so that the
    descriptor binding of the original ``_get_metrics_executor`` is
    preserved (otherwise the auto-passed ``cls`` would arrive as a
    spurious positional argument). A fresh ``_SyncExecutor`` is
    returned on every call; it is stateless so the cost is
    negligible.
    """
    return patch.object(
        PipelineRunner,
        "_get_metrics_executor",
        new=classmethod(lambda cls: _SyncExecutor()),
    )(target)


def _extract_pushed_fps_values(mock_urlopen: MagicMock) -> list[float]:
    """Extract the `value` field from every FPS-simple push.

    Filters urlopen calls to those targeting the
    ``/api/v1/metrics/simple`` endpoint (used by `_push_fps_metric`),
    so tests that also trigger latency batch pushes on the same mock
    still see a clean list of FPS values.
    """
    values: list[float] = []
    for call in mock_urlopen.call_args_list:
        req = call[0][0]
        if not req.full_url.endswith("/api/v1/metrics/simple"):
            continue
        payload = json.loads(req.data.decode())
        values.append(payload["value"])
    return values


def _extract_latency_payloads(mock_urlopen: MagicMock) -> list[dict]:
    """Extract every batch-endpoint payload sent to metrics-manager.

    Returns each JSON body as a dict, filtered to calls targeting the
    ``/api/v1/metrics`` batch endpoint used by `_push_latency_sample`
    and `_push_final_latency_metrics`.
    """
    payloads: list[dict] = []
    for call in mock_urlopen.call_args_list:
        req = call[0][0]
        # Batch endpoint path ends with `/api/v1/metrics` (no trailing `/simple`).
        if req.full_url.endswith("/api/v1/metrics/simple"):
            continue
        if not req.full_url.endswith("/api/v1/metrics"):
            continue
        payloads.append(json.loads(req.data.decode()))
    return payloads


def _make_metric_line(
    kind: str,
    fields: dict,
    element: str | None = None,
    prefix: str = "gst_runner - INFO - ",
) -> str:
    """Build a ``Pipeline metric: {json}`` stdout line as logged by ``gst_runner``.

    Mirrors ``gst_runner.log_pipeline_metric``: one ``dlstreamer/*`` bus
    message rendered as ``{"kind", "element", "fields"}`` after the
    marker, behind the Python log prefix of the subprocess.
    """
    payload = {"kind": kind, "element": element, "fields": fields}
    return f"{prefix}Pipeline metric: {json.dumps(payload)}"


def _latency_window_fields(
    source: str = "src_p0_s0_0_0",
    sink: str = "sink_p0_s0_0_0",
    count: int = 4,
    window_ms: float = 1000.0,
    sum_ms: float = 100.0,
    min_ms: float = 10.0,
    max_ms: float = 40.0,
    version: int = 1,
) -> dict:
    """Fields of a ``dlstreamer/latency-window`` message (raw tracer aggregates)."""
    return {
        "version": version,
        "source": source,
        "sink": sink,
        "count": count,
        "window_ms": window_ms,
        "sum_ms": sum_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
    }


def _make_record_line(
    source: str = "src_p0_s0_0_0",
    sink: str = "sink_p0_s0_0_0",
    interval: float = 1000.25,
    avg: float = 364.31,
    min_: float = 0.004,
    max_: float = 529.26,
    latency: float = 21.28,
    prefix: str = "gst_runner - INFO - ",
) -> str:
    """Build a ``latency_tracer_pipeline_interval`` record as promoted by ``gst_runner``.

    The latency fallback for a ``latency_tracer`` that predates
    ``post-metrics``.
    """
    return (
        f"{prefix}latency_tracer_pipeline_interval, "
        f"pipeline_name=(string)pipeline0, source_name=(string){source}, "
        f"sink_name=(string){sink}, interval=(double){interval}, "
        f"avg=(double){avg}, min=(double){min_}, max=(double){max_}, "
        f"latency=(double){latency}, fps=(double)46.99;"
    )


def _make_process_mock(stdout_lines: list[str], exit_code: int = 0) -> MagicMock:
    """Create a mocked Popen process that emits given stdout lines.

    The mock is configured so that each while-loop iteration in _run_normal
    reads exactly one line. poll() returns None for len(stdout_lines) + 1
    iterations (all real lines plus one empty-read cycle), then returns
    exit_code to end the loop.

    Args:
        stdout_lines: List of raw FpsCounter/gst_runner lines (without newline).
        exit_code: Process exit code to simulate.

    Returns:
        MagicMock configured to behave like a Popen process.
    """
    process_mock = MagicMock()
    encoded = [f"{line}\n".encode("utf-8") for line in stdout_lines]
    process_mock.stdout.readline.side_effect = itertools.chain(
        encoded, itertools.repeat(b"")
    )
    process_mock.pid = 1234
    process_mock.stdout.fileno.return_value = 10
    process_mock.stderr.fileno.return_value = 11
    # Allow enough loop iterations: one per line + one extra for the empty read
    # where zombie/exit is detected.
    n = len(stdout_lines)
    process_mock.poll.side_effect = [None] * (n + 1) + [exit_code]
    process_mock.wait.return_value = exit_code
    process_mock.returncode = exit_code
    process_mock.communicate.return_value = (b"", b"")
    return process_mock


@_patch_sync_metrics_executor
class TestPipelineRunnerNormalMode(unittest.TestCase):
    """Tests for PipelineRunner in normal mode (production pipeline execution).

    The shared metrics-push ``ThreadPoolExecutor`` is replaced with a
    synchronous stub at the class level so metrics pushes
    (``_post_metrics_async``) run inline in the calling thread. That
    keeps urlopen assertions deterministic without changing any
    production code path.
    """

    def setUp(self):
        self.test_pipeline_command = (
            "videotestsrc "
            " num-buffers=5 "
            " pattern=snow ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    def test_run_pipeline_normal_mode(self, mock_select, mock_ps, mock_popen):
        """PipelineRunner in normal mode should execute gst_runner.py and extract FPS metrics."""
        process_mock = _make_process_mock(
            [
                "FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps",
            ]
        )
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        if mock_ps is not None:
            mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", max_runtime=0)
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        # Verify command arguments
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1], "gst_runner.py")
        self.assertEqual(cmd[2], "--mode")
        self.assertEqual(cmd[3], "normal")
        self.assertEqual(cmd[4], "--max-runtime")
        self.assertEqual(cmd[5], "0")
        self.assertEqual(cmd[6], "--log-level")
        self.assertIn(cmd[7], ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"))
        self.assertEqual(cmd[8], self.test_pipeline_command)

        # Verify FPS extraction — should use Priority 1 (last average, exact match)
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.total_fps, 100.0)
        self.assertEqual(result.per_stream_fps, 100.0)
        self.assertEqual(result.num_streams, 1)
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.cancelled)
        assert result.details is not None
        self.assertIn("last average fps", result.details)
        self.assertIn("primary source", result.details)

    @patch("pipeline_runner.Popen")
    def test_stop_pipeline_normal_mode(self, mock_popen):
        """PipelineRunner in normal mode should handle cancellation correctly."""
        # Mock process
        process_mock = MagicMock()
        # First poll() returns None (main loop check: process running),
        # second poll() returns None (_graceful_terminate check: still running,
        # so it sends SIGINT and waits).
        process_mock.poll.side_effect = [None, None]
        process_mock.wait.return_value = 0
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b"", b"")
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="normal", max_runtime=0)
        runner.cancel()
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        self.assertTrue(runner.is_cancelled())
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.total_fps, 0.0)
        self.assertEqual(result.per_stream_fps, 0.0)
        self.assertEqual(result.num_streams, 0)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.details, "no fps metrics found in pipeline output")

        # Verify SIGINT was sent for graceful shutdown
        process_mock.send_signal.assert_called_once_with(signal.SIGINT)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    def test_pipeline_hang_raises_runtime_error(self, mock_select, mock_popen):
        """PipelineRunner in normal mode should raise RuntimeError on inactivity timeout."""
        runner = PipelineRunner(
            mode="normal",
            max_runtime=0,
            poll_interval=1,
            inactivity_timeout=0,
        )

        process_mock = MagicMock()
        # First poll() returns None (main loop: process running),
        # second poll() returns None (_graceful_terminate: still running).
        process_mock.poll.side_effect = [None, None]
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        # No data available on stdout/stderr, select returns no readable fds.
        mock_select.return_value = ([], [], [])
        process_mock.wait.return_value = 0
        mock_popen.return_value = process_mock

        # Act + Assert: with no activity, run() should hit inactivity timeout and raise.
        with self.assertRaises(RuntimeError) as ctx:
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        self.assertIn("inactivity timeout", str(ctx.exception))

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_pipeline_pushes_zero_fps_on_completion(
        self, mock_urlopen, mock_select, mock_ps, mock_popen
    ):
        """PipelineRunner should push 0.0 to metrics-manager after successful completion."""
        process_mock = _make_process_mock(
            [
                "FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps",
            ]
        )
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        if mock_ps is not None:
            mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", max_runtime=0)
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.total_fps, 100.0)

        # Verify that current FPS (100.0) was pushed during execution
        # and 0.0 was pushed at the end (in finally block).
        pushed = _extract_pushed_fps_values(mock_urlopen)

        self.assertIn(100.0, pushed, "Current FPS should be pushed during execution")
        self.assertIn(0.0, pushed, "0.0 should be pushed after completion")
        # Last push should be 0.0 (from finally block).
        self.assertEqual(pushed[-1], 0.0, "Last FPS push should be 0.0")

        # Every request targets the metrics-manager `/api/v1/metrics/simple` endpoint.
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            self.assertTrue(req.full_url.endswith("/api/v1/metrics/simple"))
            self.assertEqual(req.headers.get("Content-type"), "application/json")

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_pipeline_pushes_zero_fps_on_error(
        self, mock_urlopen, mock_select, mock_popen
    ):
        """PipelineRunner should push 0.0 to metrics-manager after pipeline failure."""
        process_mock = _make_process_mock([], exit_code=1)
        process_mock.stderr.readline.side_effect = itertools.repeat(b"")
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="normal", max_runtime=0)

        with self.assertRaises(RuntimeError):
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        # Verify that 0.0 was pushed exactly once (finally block) even on error.
        pushed = _extract_pushed_fps_values(mock_urlopen)
        self.assertEqual(
            pushed.count(0.0),
            1,
            "0.0 should be pushed exactly once to metrics-manager after pipeline error",
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_pipeline_hang_pushes_zero_fps_before_raising(
        self, mock_urlopen, mock_select, mock_popen
    ):
        """PipelineRunner should push 0.0 to metrics-manager when raising inactivity timeout error."""
        runner = PipelineRunner(
            mode="normal",
            max_runtime=0,
            poll_interval=1,
            inactivity_timeout=0,
        )

        process_mock = MagicMock()
        # First poll() returns None (main loop: process running),
        # second poll() returns None (_graceful_terminate: still running).
        process_mock.poll.side_effect = [None, None]
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        mock_select.return_value = ([], [], [])
        process_mock.wait.return_value = 0
        mock_popen.return_value = process_mock

        with self.assertRaises(RuntimeError) as ctx:
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        self.assertIn("inactivity timeout", str(ctx.exception))

        # Verify that 0.0 was pushed exactly once (finally block).
        pushed = _extract_pushed_fps_values(mock_urlopen)
        self.assertEqual(
            pushed.count(0.0),
            1,
            "0.0 should be pushed exactly once to metrics-manager after timeout error",
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_stop_pipeline_pushes_zero_fps(self, mock_urlopen, mock_popen):
        """PipelineRunner should push 0.0 to metrics-manager when cancelled."""
        process_mock = MagicMock()
        # First poll() returns None (main loop: process running),
        # second poll() returns None (_graceful_terminate: still running).
        process_mock.poll.side_effect = [None, None]
        process_mock.wait.return_value = 0
        process_mock.returncode = 0
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        # Mock communicate() for the post-loop stdout/stderr drain
        process_mock.communicate.return_value = (b"", b"")
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="normal", max_runtime=0)
        runner.cancel()
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        self.assertTrue(runner.is_cancelled())
        self.assertIsInstance(result, PipelineResult)

        # Verify that 0.0 was pushed exactly once (finally block) after cancellation.
        pushed = _extract_pushed_fps_values(mock_urlopen)
        self.assertEqual(
            pushed.count(0.0),
            1,
            "0.0 should be pushed exactly once to metrics-manager after cancellation",
        )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_fps_metric_uses_configured_url(self, mock_urlopen):
        """`_push_fps_metric` must POST JSON to `{METRICS_MANAGER_URL}/api/v1/metrics/simple`."""
        with patch.dict(
            "os.environ", {"METRICS_MANAGER_URL": "http://example:1234"}, clear=False
        ):
            runner = PipelineRunner(mode="normal", max_runtime=0)

        runner._push_fps_metric(42.5)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://example:1234/api/v1/metrics/simple")
        payload = json.loads(req.data.decode())
        self.assertEqual(payload, {"name": "fps", "value": 42.5})
        self.assertEqual(req.headers.get("Content-type"), "application/json")

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_fps_metric_swallows_network_errors(self, mock_urlopen):
        """Network errors while pushing FPS must be logged but not raised."""
        mock_urlopen.side_effect = OSError("boom")

        runner = PipelineRunner(mode="normal", max_runtime=0)

        # Must not raise — pipeline execution cannot be impacted by telemetry failures.
        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._push_fps_metric(1.0)

        self.assertTrue(
            any("Failed to push fps metric" in line for line in captured.output)
        )


@patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
@_patch_sync_metrics_executor
class TestFpsMetricSelection(unittest.TestCase):
    """Tests for the FPS metric selection fallback chain in _run_normal.

    gvafpscounter emits three metric types:
    - "last": FPS over the most recent N-second window (volatile, resets each print)
    - "average": cumulative mean FPS printed every ~1s (stable steady-state)
    - "overall": same as average but printed once at pipeline end (includes shutdown)

    The selection priority is:
    1. Last average for exact total_streams (best steady-state metric)
    2. Overall for exact total_streams (includes shutdown artifacts)
    3. Last average for closest total_streams (stream count mismatch)
    4. Last "last" line (volatile, last resort)
    """

    def setUp(self):
        self.pipeline_cmd = "videotestsrc ! gvafpscounter ! fakesink"

    def _run_with_lines(
        self, stdout_lines: list[str], total_streams: int = 5
    ) -> PipelineResult:
        """Helper: run PipelineRunner with mocked stdout lines and return result.

        The ps.Process mock returns "running" for each real line (so the inner
        loop continues to the next select iteration) and "zombie" on the first
        empty-read cycle (so the process terminates after all lines are consumed).
        """
        with (
            patch("pipeline_runner.Popen") as mock_popen,
            patch("pipeline_runner.ps") as mock_ps,
            patch("pipeline_runner.select.select") as mock_select,
        ):
            process_mock = _make_process_mock(stdout_lines)
            mock_select.return_value = ([process_mock.stdout], [], [])
            mock_popen.return_value = process_mock
            # Return "running" for each real line, then "zombie" to break out
            n = len(stdout_lines)
            mock_ps.Process.return_value.status.side_effect = ["running"] * n + [
                "zombie"
            ]

            runner = PipelineRunner(mode="normal", max_runtime=0)
            return runner.run(
                pipeline_command=self.pipeline_cmd,
                total_streams=total_streams,
            )

    def test_priority1_average_exact_match(self):
        """Priority 1: last average with exact total_streams should be selected."""
        result = self._run_with_lines(
            [
                # Multiple average lines — last one should win
                "FpsCounter(average 5.0sec): total=50.0 fps, number-streams=5, per-stream=10.0 fps",
                "FpsCounter(average 10.0sec): total=75.0 fps, number-streams=5, per-stream=15.0 fps",
                # Overall also present — should be ignored in favor of average
                "FpsCounter(overall 12.0sec): total=60.0 fps, number-streams=5, per-stream=12.0 fps",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 75.0)
        self.assertEqual(result.per_stream_fps, 15.0)
        self.assertEqual(result.num_streams, 5)
        assert result.details is not None
        self.assertIn("last average fps", result.details)
        self.assertIn("primary source", result.details)
        self.assertIn("5 stream(s)", result.details)

    def test_priority2_overall_exact_match(self):
        """Priority 2: overall with exact total_streams when no average is available."""
        result = self._run_with_lines(
            [
                # Only "last" and "overall" — no average lines
                "FpsCounter(last 1.0sec): total=120.0 fps, number-streams=5, per-stream=24.0 fps",
                "FpsCounter(overall 12.0sec): total=85.0 fps, number-streams=5, per-stream=17.0 fps",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 85.0)
        self.assertEqual(result.per_stream_fps, 17.0)
        self.assertEqual(result.num_streams, 5)
        assert result.details is not None
        self.assertIn("overall fps", result.details)
        self.assertIn("fallback 1", result.details)
        self.assertIn("5 stream(s)", result.details)

    def test_priority3_average_closest_stream_count(self):
        """Priority 3: last average for closest total_streams when exact match unavailable."""
        result = self._run_with_lines(
            [
                # Average for 3 streams only — requested is 5
                "FpsCounter(average 8.0sec): total=90.0 fps, number-streams=3, per-stream=30.0 fps",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 90.0)
        self.assertEqual(result.per_stream_fps, 30.0)
        self.assertEqual(result.num_streams, 3)
        assert result.details is not None
        self.assertIn("fallback 2", result.details)
        self.assertIn("3 stream(s)", result.details)
        self.assertIn("closest match to requested 5", result.details)

    def test_priority3_picks_closest_stream_count(self):
        """Priority 3 should pick the stream count closest to total_streams."""
        result = self._run_with_lines(
            [
                # Averages for 2 and 4 streams — requested is 5, so 4 is closest
                "FpsCounter(average 8.0sec): total=40.0 fps, number-streams=2, per-stream=20.0 fps",
                "FpsCounter(average 8.0sec): total=100.0 fps, number-streams=4, per-stream=25.0 fps",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 100.0)
        self.assertEqual(result.per_stream_fps, 25.0)
        self.assertEqual(result.num_streams, 4)
        assert result.details is not None
        self.assertIn("4 stream(s)", result.details)
        self.assertIn("fallback 2", result.details)

    def test_priority4_last_line_only(self):
        """Priority 4: last "last" line when no average or overall is available."""
        result = self._run_with_lines(
            [
                # Only "last" lines — no average, no overall
                "FpsCounter(last 1.0sec): total=100.0 fps, number-streams=5, per-stream=20.0 fps",
                "FpsCounter(last 1.0sec): total=130.0 fps, number-streams=5, per-stream=26.0 fps",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 130.0)
        self.assertEqual(result.per_stream_fps, 26.0)
        self.assertEqual(result.num_streams, 5)
        assert result.details is not None
        self.assertIn("last instantaneous fps", result.details)
        self.assertIn("fallback 3", result.details)

    def test_no_fps_metrics(self):
        """No FPS metrics at all should return zeros with appropriate details."""
        result = self._run_with_lines(
            [
                # Non-FpsCounter output only
                "gst_runner - INFO - Pipeline parsed successfully.",
            ],
            total_streams=5,
        )

        self.assertEqual(result.total_fps, 0.0)
        self.assertEqual(result.per_stream_fps, 0.0)
        self.assertEqual(result.num_streams, 0)
        self.assertEqual(result.details, "no fps metrics found in pipeline output")

    def test_average_preferred_over_overall_same_streams(self):
        """When both average and overall exist for exact total_streams, average must win."""
        result = self._run_with_lines(
            [
                "FpsCounter(average 10.0sec): total=610.0 fps, number-streams=16, per-stream=38.0 fps",
                # overall is lower due to shutdown flush — must NOT be selected
                "FpsCounter(overall 13.0sec): total=472.0 fps, number-streams=16, per-stream=29.5 fps",
            ],
            total_streams=16,
        )

        # Must use average (38.0), not overall (29.5)
        self.assertEqual(result.total_fps, 610.0)
        self.assertEqual(result.per_stream_fps, 38.0)
        self.assertEqual(result.num_streams, 16)
        assert result.details is not None
        self.assertIn("primary source", result.details)

    def test_full_realistic_output(self):
        """Realistic gvafpscounter output with all three metric types, interleaved."""
        result = self._run_with_lines(
            [
                "gst_runner - INFO - Pipeline parsed successfully.",
                "FpsCounter(last 1.02sec): total=135.09 fps, number-streams=5, per-stream=27.02 fps",
                "FpsCounter(average 1.91sec): total=16.19 fps, number-streams=5, per-stream=3.24 fps",
                "FpsCounter(last 1.11sec): total=102.27 fps, number-streams=5, per-stream=20.45 fps",
                "FpsCounter(average 3.03sec): total=47.87 fps, number-streams=5, per-stream=9.57 fps",
                "FpsCounter(last 1.02sec): total=124.95 fps, number-streams=5, per-stream=24.99 fps",
                "FpsCounter(average 4.05sec): total=67.24 fps, number-streams=5, per-stream=13.45 fps",
                "FpsCounter(average 10.75sec): total=76.49 fps, number-streams=5, per-stream=15.30 fps",
                "gst_runner - INFO - Stopping pipeline (reason: max_runtime).",
                "FpsCounter(average 11.99sec): total=75.51 fps, number-streams=5, per-stream=15.10 fps",
                # Shutdown flush spike — should be ignored
                "FpsCounter(last 0.47sec): total=330.93 fps, number-streams=5, per-stream=66.19 fps",
                # Overall is lower than last average due to shutdown — should also be ignored
                "FpsCounter(overall 12.45sec): total=85.06 fps, number-streams=5, per-stream=17.01 fps",
                "gst_runner - INFO - Pipeline run succeeded.",
            ],
            total_streams=5,
        )

        # Must pick last average (75.51 total, 15.10 per-stream), NOT overall (85.06, 17.01)
        self.assertEqual(result.total_fps, 75.51)
        self.assertEqual(result.per_stream_fps, 15.10)
        self.assertEqual(result.num_streams, 5)
        assert result.details is not None
        self.assertIn("primary source", result.details)


class TestPipelineRunnerValidationMode(unittest.TestCase):
    """Tests for PipelineRunner in validation mode (pipeline validation)."""

    def setUp(self):
        self.test_pipeline_command = "videotestsrc ! fakesink"

    def test_validation_mode_requires_positive_max_runtime(self):
        """PipelineRunner in validation mode should require max_runtime > 0."""
        with self.assertRaises(ValueError) as ctx:
            PipelineRunner(mode="validation", max_runtime=0)

        self.assertIn("max_runtime > 0", str(ctx.exception))

    def test_validation_mode_sets_default_hard_timeout(self):
        """PipelineRunner in validation mode should set default hard_timeout to max_runtime + 60."""
        runner = PipelineRunner(mode="validation", max_runtime=10)
        self.assertEqual(runner.hard_timeout, 70)

    def test_validation_mode_accepts_custom_hard_timeout(self):
        """PipelineRunner in validation mode should accept custom hard_timeout."""
        runner = PipelineRunner(mode="validation", max_runtime=10, hard_timeout=100)
        self.assertEqual(runner.hard_timeout, 100)

    @patch("pipeline_runner.subprocess.Popen")
    def test_run_validation_success(self, mock_popen):
        """PipelineRunner in validation mode should return PipelineResult with exit_code=0 and empty stderr on success."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = (
            "gst_runner - INFO - Pipeline parsed successfully.\n",
            "",  # No errors in stderr
        )
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stderr, [])
        self.assertFalse(result.cancelled)

    @patch("pipeline_runner.subprocess.Popen")
    def test_run_validation_failure(self, mock_popen):
        """PipelineRunner in validation mode should return PipelineResult with errors in stderr."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = (
            "",
            "gst_runner - ERROR - no element foo\ngst_runner - ERROR - some other error\n",
        )
        process_mock.returncode = 1
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, ["no element foo", "some other error"])
        self.assertFalse(result.cancelled)

    @patch("pipeline_runner.subprocess.Popen")
    def test_run_validation_timeout(self, mock_popen):
        """PipelineRunner in validation mode should handle timeout gracefully."""
        process_mock = MagicMock()

        def communicate_with_timeout(timeout=None):
            if timeout:
                raise __import__("subprocess").TimeoutExpired("gst_runner.py", timeout)
            return "", ""

        process_mock.communicate = communicate_with_timeout
        # _graceful_terminate checks poll(), sends SIGINT, then waits.
        process_mock.poll.return_value = None
        process_mock.wait.return_value = 0
        process_mock.returncode = -2
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineResult)
        self.assertNotEqual(result.exit_code, 0)
        self.assertTrue(any("timed out" in err for err in result.stderr))
        self.assertFalse(result.cancelled)

        # Verify SIGINT was sent for graceful shutdown
        process_mock.send_signal.assert_called_once_with(signal.SIGINT)

    def test_parse_validation_stderr(self):
        """_parse_validation_stderr should extract only gst_runner ERROR messages."""
        runner = PipelineRunner(mode="validation", max_runtime=10)

        raw_stderr = "\n".join(
            [
                "some-other-tool - INFO - hello",
                "gst_runner - ERROR - first error",
                "gst_runner - ERROR -   second error   ",
                "gst_runner - ERROR -    ",
                "completely unrelated line",
            ]
        )

        errors = runner._parse_validation_stderr(raw_stderr)
        self.assertEqual(errors, ["first error", "second error"])

    def test_parse_validation_stderr_empty_input(self):
        """_parse_validation_stderr should handle empty input."""
        runner = PipelineRunner(mode="validation", max_runtime=10)
        errors = runner._parse_validation_stderr("")
        self.assertEqual(errors, [])


class TestPipelineRunnerModeValidation(unittest.TestCase):
    """Tests for PipelineRunner mode validation."""

    def test_invalid_mode_raises_error(self):
        """PipelineRunner should reject invalid mode values."""
        with self.assertRaises(ValueError) as ctx:
            PipelineRunner(mode="invalid_mode")

        self.assertIn("Invalid mode", str(ctx.exception))


@patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
@_patch_sync_metrics_executor
class TestPipelineRunnerLatencyMetrics(unittest.TestCase):
    """Tests for the `enable_latency_metrics` subprocess-env configuration.

    These tests verify that when the flag is True the GStreamer subprocess
    is launched with the environment variables required to activate the
    DLStreamer `latency_tracer` in pipeline-only mode with a 1000 ms
    interval, and that when the flag is False neither GST_DEBUG nor
    GST_TRACERS is touched.
    """

    test_pipeline_command = "videotestsrc ! fakesink"

    def _assert_tracer_env_applied(self, env: dict[str, str]) -> None:
        """Shared assertions for an env dict built with the flag enabled.

        The tracer's text records are the fallback; ``gst_runner`` raises the
        GST_TRACER threshold for them at runtime, so ``GST_DEBUG`` never
        carries ``GST_TRACER``.
        """
        self.assertEqual(env["VIPPET_LATENCY_RECORD_FALLBACK"], "1")
        self.assertNotIn("GST_TRACER", env.get("GST_DEBUG", ""))
        self.assertEqual(
            env["GST_TRACERS"],
            "latency_tracer(flags=pipeline,interval=1000,post-metrics=true)",
        )

    # --- Pure _build_subprocess_env unit tests --------------------------------

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_disabled_leaves_tracer_vars_unset(self):
        """With the flag False the env must not contain GST_DEBUG/GST_TRACERS."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertNotIn("GST_DEBUG", env)
        self.assertNotIn("GST_TRACERS", env)
        self.assertNotIn("VIPPET_LATENCY_RECORD_FALLBACK", env)

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_enabled_sets_tracer_vars_without_gst_debug(self):
        """With the flag True and no pre-existing GST_DEBUG, GST_DEBUG stays unset."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        env = runner._build_subprocess_env()
        self.assertNotIn("GST_DEBUG", env)
        self._assert_tracer_env_applied(env)

    @patch.dict("os.environ", {"GST_DEBUG": "2,GST_ELEMENT_PADS:5"}, clear=True)
    def test_build_env_enabled_preserves_existing_gst_debug(self):
        """An existing GST_DEBUG is passed through unchanged by the latency flag."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "2,GST_ELEMENT_PADS:5")
        self._assert_tracer_env_applied(env)

    @patch.dict(
        "os.environ",
        {"GST_TRACERS": "some_other_tracer"},
        clear=True,
    )
    def test_build_env_enabled_overwrites_existing_gst_tracers(self):
        """GST_TRACERS is always set to the latency_tracer value when enabled."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        env = runner._build_subprocess_env()
        self._assert_tracer_env_applied(env)

    # --- Pure _build_subprocess_env unit tests: gvagenai branch ---------------

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_genai_only_sets_gvagenai_debug_no_tracers(self):
        """With only the genai flag on, GST_DEBUG=gvagenai:4 and GST_TRACERS untouched."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        runner._genai_metrics_enabled = True
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "gvagenai:4")
        self.assertNotIn("GST_TRACERS", env)

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_genai_and_latency_combine_debug_categories(self):
        """With both flags on, GST_DEBUG carries gvagenai:4 and GST_TRACERS is set."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        runner._genai_metrics_enabled = True
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "gvagenai:4")
        self._assert_tracer_env_applied(env)

    @patch.dict("os.environ", {"GST_DEBUG": "2,GST_ELEMENT_PADS:5"}, clear=True)
    def test_build_env_genai_only_appends_to_existing_gst_debug(self):
        """Existing GST_DEBUG must be preserved and gvagenai:4 appended."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        runner._genai_metrics_enabled = True
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "2,GST_ELEMENT_PADS:5,gvagenai:4")
        self.assertNotIn("GST_TRACERS", env)

    @patch.dict("os.environ", {"GST_DEBUG": "2,GST_ELEMENT_PADS:5"}, clear=True)
    def test_build_env_genai_and_latency_append_to_existing_gst_debug(self):
        """gvagenai:4 must be appended after any pre-existing GST_DEBUG value."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        runner._genai_metrics_enabled = True
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "2,GST_ELEMENT_PADS:5,gvagenai:4")
        self._assert_tracer_env_applied(env)

    # --- Pure _build_subprocess_env unit tests: bundled plugin path -----------

    @staticmethod
    def _bundled_plugins_dir() -> str:
        """The ``gst_plugins/`` directory as resolved by the production code."""
        return os.path.join(
            os.path.dirname(os.path.abspath(pipeline_runner.__file__)),
            "gst_plugins",
        )

    @patch("pipeline_runner.os.path.isdir", return_value=True)
    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_sets_plugin_path_when_unset(self, _mock_isdir):
        """With no GST_PLUGIN_PATH, the bundled plugin dir becomes the whole value."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_PLUGIN_PATH"], self._bundled_plugins_dir())
        self.assertEqual(env["GST_REGISTRY_FORK"], "no")

    @patch("pipeline_runner.os.path.isdir", return_value=True)
    @patch.dict(
        "os.environ",
        {"GST_PLUGIN_PATH": "/opt/vendor/plugins"},
        clear=True,
    )
    def test_build_env_prepends_plugin_path_to_existing_value(self, _mock_isdir):
        """An existing GST_PLUGIN_PATH must be preserved after the bundled dir."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertEqual(
            env["GST_PLUGIN_PATH"],
            f"{self._bundled_plugins_dir()}{os.pathsep}/opt/vendor/plugins",
        )
        self.assertEqual(env["GST_REGISTRY_FORK"], "no")

    @patch("pipeline_runner.os.path.isdir", return_value=True)
    @patch.dict("os.environ", {"GST_REGISTRY_FORK": "yes"}, clear=True)
    def test_build_env_preserves_existing_registry_fork(self, _mock_isdir):
        """An explicit GST_REGISTRY_FORK from the environment is not overridden."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_REGISTRY_FORK"], "yes")
        self.assertEqual(env["GST_PLUGIN_PATH"], self._bundled_plugins_dir())

    @patch("pipeline_runner.os.path.isdir", return_value=False)
    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_skips_plugin_vars_when_dir_missing(self, _mock_isdir):
        """Without the bundled directory neither plugin-related var is introduced."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertNotIn("GST_PLUGIN_PATH", env)
        self.assertNotIn("GST_REGISTRY_FORK", env)

    # --- Popen-level integration: normal mode ---------------------------------

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_normal_mode_disabled_does_not_modify_env(
        self, mock_select, mock_ps, mock_popen
    ):
        """Normal-mode Popen env must have neither GST_DEBUG nor GST_TRACERS when disabled."""
        process_mock = _make_process_mock([])
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        env = mock_popen.call_args.kwargs["env"]
        self.assertNotIn("GST_DEBUG", env)
        self.assertNotIn("GST_TRACERS", env)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_normal_mode_enabled_sets_tracer_env(
        self, mock_select, mock_ps, mock_popen
    ):
        """Normal-mode Popen env must contain the tracer vars when enabled."""
        process_mock = _make_process_mock([])
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        env = mock_popen.call_args.kwargs["env"]
        self._assert_tracer_env_applied(env)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_normal_mode_gvagenai_pipeline_adds_gvagenai_debug(
        self, mock_select, mock_ps, mock_popen
    ):
        """A `gvagenai` element in the pipeline command must add `gvagenai:4` to GST_DEBUG."""
        process_mock = _make_process_mock([])
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        runner.run(
            pipeline_command=(
                "videotestsrc ! gvagenai model=foo metrics=true ! fakesink"
            ),
            total_streams=1,
        )

        env = mock_popen.call_args.kwargs["env"]
        self.assertEqual(env["GST_DEBUG"], "gvagenai:4")
        self.assertNotIn("GST_TRACERS", env)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_normal_mode_gvagenai_pipeline_with_latency_combines_categories(
        self, mock_select, mock_ps, mock_popen
    ):
        """With a gvagenai pipeline and the latency flag, GST_DEBUG is gvagenai:4 and GST_TRACERS is set."""
        process_mock = _make_process_mock([])
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        runner.run(
            pipeline_command=(
                "videotestsrc ! gvagenai model=foo metrics=true ! fakesink"
            ),
            total_streams=1,
        )

        env = mock_popen.call_args.kwargs["env"]
        self.assertEqual(env["GST_DEBUG"], "gvagenai:4")
        self._assert_tracer_env_applied(env)

    # --- Popen-level integration: validation mode -----------------------------

    @patch("pipeline_runner.subprocess.Popen")
    @patch.dict("os.environ", {}, clear=True)
    def test_validation_mode_disabled_does_not_modify_env(self, mock_popen):
        """Validation-mode Popen env must not be modified when disabled."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = ("", "")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="validation", max_runtime=5, enable_latency_metrics=False
        )
        runner.run(self.test_pipeline_command)

        env = mock_popen.call_args.kwargs["env"]
        self.assertNotIn("GST_DEBUG", env)
        self.assertNotIn("GST_TRACERS", env)

    @patch("pipeline_runner.subprocess.Popen")
    @patch.dict("os.environ", {}, clear=True)
    def test_validation_mode_enabled_sets_tracer_env(self, mock_popen):
        """Validation-mode Popen env must contain the tracer vars when enabled."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = ("", "")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="validation", max_runtime=5, enable_latency_metrics=True
        )
        runner.run(self.test_pipeline_command)

        env = mock_popen.call_args.kwargs["env"]
        self._assert_tracer_env_applied(env)

    # --- PipelineResult.latency_tracer_metrics semantics in validation mode ---
    #
    # Validation mode never parses tracer samples. The map on the result
    # must still reflect whether the tracer was enabled, matching the
    # semantics documented on `PipelineResult.latency_tracer_metrics`:
    #   * `None`  → tracer disabled,
    #   * `{}`    → tracer enabled but no samples were collected.

    @patch("pipeline_runner.subprocess.Popen")
    @patch.dict("os.environ", {}, clear=True)
    def test_validation_mode_disabled_returns_none_metrics(self, mock_popen):
        """With the flag False, validation results carry `latency_tracer_metrics=None`."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = ("", "")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="validation", max_runtime=5, enable_latency_metrics=False
        )
        result = runner.run(self.test_pipeline_command)

        self.assertIsNone(result.latency_tracer_metrics)

    @patch("pipeline_runner.subprocess.Popen")
    @patch.dict("os.environ", {}, clear=True)
    def test_validation_mode_enabled_returns_empty_metrics(self, mock_popen):
        """With the flag True, validation results carry `latency_tracer_metrics={}`."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = ("", "")
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="validation", max_runtime=5, enable_latency_metrics=True
        )
        result = runner.run(self.test_pipeline_command)

        self.assertEqual(result.latency_tracer_metrics, {})

    @patch("pipeline_runner.subprocess.Popen")
    @patch.dict("os.environ", {}, clear=True)
    def test_validation_mode_timeout_preserves_metrics_semantics(self, mock_popen):
        """On hard-timeout, the returned PipelineResult keeps the same tracer-map semantics."""
        import subprocess as _subprocess

        process_mock = MagicMock()
        # First communicate() raises TimeoutExpired; second (after kill) returns empty.
        process_mock.communicate.side_effect = [
            _subprocess.TimeoutExpired(cmd="gst_runner.py", timeout=1),
            ("", ""),
        ]
        process_mock.returncode = -9
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="validation",
            max_runtime=1,
            hard_timeout=1,
            enable_latency_metrics=True,
        )
        with patch.object(runner, "_graceful_terminate"):
            result = runner.run(self.test_pipeline_command)

        self.assertEqual(result.latency_tracer_metrics, {})

    # --- latency-window metric line from gst_runner is forwarded and parsed ---

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_pipeline_metric_line_forwarded_from_gst_runner_stdout(
        self, mock_select, mock_ps, mock_popen
    ):
        """`gst_runner - INFO - Pipeline metric: {...}` stdout lines are logged and recorded.

        In production ``gst_runner`` forwards each ``dlstreamer/latency-window``
        bus message as one INFO ``Pipeline metric:`` line. The parent
        PipelineRunner logs it through ``_is_loggable_gst_runner_line`` and
        records the window in ``PipelineResult.latency_tracer_metrics``.
        """
        sample_line = _make_metric_line(
            "latency-window",
            _latency_window_fields(source="filesrc0", sink="default_output_sink_0_0"),
        )
        process_mock = _make_process_mock([sample_line])
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        with self.assertLogs("PipelineRunner", level="INFO") as captured:
            result = runner.run(
                pipeline_command=self.test_pipeline_command, total_streams=1
            )

        joined = "\n".join(captured.output)
        self.assertIn("Pipeline metric:", joined)
        self.assertEqual(
            set(result.latency_tracer_metrics or {}),
            {"filesrc0__default_output_sink_0_0"},
        )


@patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
@_patch_sync_metrics_executor
class TestLatencyWindowParser(unittest.TestCase):
    """Unit tests for the ``latency-window`` pipeline-metric parser.

    ``gst_runner`` forwards every ``dlstreamer/latency-window`` bus
    message posted by the DLStreamer ``latency_tracer``
    (``post-metrics=true``) as a ``Pipeline metric: {json}`` line.
    :meth:`PipelineRunner._parse_and_handle_pipeline_metric` decodes it
    and :meth:`PipelineRunner._record_latency_window` derives the
    :class:`LatencyTracerSample`. These tests exercise the parser
    directly (no subprocess) so we can assert the exact shape of the
    resulting map entries.
    """

    STREAM_ID = "src_p0_s0_0_0__sink_p0_s0_0_0"

    def _make_runner(self, enable: bool) -> PipelineRunner:
        """Return a PipelineRunner configured for parser testing.

        Args:
            enable: Value of ``enable_latency_metrics``. When False the
                runner keeps ``latency_tracer_metrics=None`` and the
                parser is expected to short-circuit.
        """
        return PipelineRunner(mode="normal", enable_latency_metrics=enable)

    def test_window_derives_sample_fields(self):
        """avg = sum/count and latency = window/count; interval/min/max pass through."""
        runner = self._make_runner(enable=True)
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "latency-window",
                _latency_window_fields(
                    count=4, window_ms=1000.0, sum_ms=100.0, min_ms=10.0, max_ms=40.0
                ),
            )
        )

        assert runner.latency_tracer_metrics is not None  # for the type-checker
        self.assertEqual(len(runner.latency_tracer_metrics), 1)
        self.assertEqual(
            runner.latency_tracer_metrics[self.STREAM_ID],
            LatencyTracerSample(
                interval_ms=1000.0,
                avg_ms=25.0,
                min_ms=10.0,
                max_ms=40.0,
                latency_ms=250.0,
            ),
        )

    def test_parser_accepts_any_log_prefix(self):
        """The JSON after the marker is parsed regardless of the log prefix before it."""
        for prefix in ("", "gst_runner - INFO - ", "12:00:00 gst_runner - INFO - "):
            with self.subTest(prefix=prefix):
                runner = self._make_runner(enable=True)
                runner._parse_and_handle_pipeline_metric(
                    _make_metric_line(
                        "latency-window", _latency_window_fields(), prefix=prefix
                    )
                )

                assert runner.latency_tracer_metrics is not None
                self.assertEqual(set(runner.latency_tracer_metrics), {self.STREAM_ID})

    def test_record_latency_window_accepts_integer_values(self):
        """Integral JSON numbers (e.g. ``1000``) are accepted and stored as floats."""
        runner = self._make_runner(enable=True)
        runner._record_latency_window(
            _latency_window_fields(count=2, window_ms=1000, sum_ms=50, min_ms=20)
        )

        assert runner.latency_tracer_metrics is not None
        sample = runner.latency_tracer_metrics[self.STREAM_ID]
        self.assertIsInstance(sample.interval_ms, float)
        self.assertEqual(sample.avg_ms, 25.0)
        self.assertEqual(sample.latency_ms, 500.0)

    def test_parser_ignores_malformed_lines(self):
        """Broken JSON, non-dict payloads and missing/non-dict ``fields`` are dropped."""
        runner = self._make_runner(enable=True)

        for line in (
            "gst_runner - INFO - Pipeline metric: not-json",
            "gst_runner - INFO - Pipeline metric:",
            "gst_runner - INFO - Pipeline metric: [1, 2]",
            'gst_runner - INFO - Pipeline metric: {"kind": "latency-window"',
            'gst_runner - INFO - Pipeline metric: {"kind": "latency-window"}',
            'gst_runner - INFO - Pipeline metric: {"kind": "latency-window", '
            '"fields": "count=4"}',
        ):
            with self.subTest(line=line):
                runner._parse_and_handle_pipeline_metric(line)

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_ignores_malformed_window_fields(self):
        """Missing or non-numeric window fields drop the sample silently."""
        runner = self._make_runner(enable=True)

        complete = _latency_window_fields()
        for missing in complete:
            fields = {k: v for k, v in complete.items() if k != missing}
            with self.subTest(missing=missing):
                runner._parse_and_handle_pipeline_metric(
                    _make_metric_line("latency-window", fields)
                )
        for key, value in (("count", "four"), ("sum_ms", None), ("max_ms", [1])):
            with self.subTest(key=key, value=value):
                runner._parse_and_handle_pipeline_metric(
                    _make_metric_line("latency-window", {**complete, key: value})
                )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_ignores_non_positive_count(self):
        """Windows with ``count <= 0`` carry no frames and must not divide by zero."""
        runner = self._make_runner(enable=True)

        for count in (0, -1):
            with self.subTest(count=count):
                runner._parse_and_handle_pipeline_metric(
                    _make_metric_line(
                        "latency-window", _latency_window_fields(count=count)
                    )
                )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_ignores_unknown_kind(self):
        """Unknown or missing ``kind`` values are dropped, even with valid window fields."""
        runner = self._make_runner(enable=True)

        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("frame-latency", _latency_window_fields())
        )
        runner._parse_and_handle_pipeline_metric(
            "gst_runner - INFO - Pipeline metric: "
            + json.dumps({"fields": _latency_window_fields()})
        )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_keeps_only_last_sample_per_stream(self):
        """Successive windows for the same stream_id overwrite the entry."""
        runner = self._make_runner(enable=True)

        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("latency-window", _latency_window_fields())
        )
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "latency-window",
                _latency_window_fields(count=5, window_ms=2000.0, sum_ms=500.0),
            )
        )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(len(runner.latency_tracer_metrics), 1)
        metrics = runner.latency_tracer_metrics[self.STREAM_ID]
        # Only the latest values are retained — no history.
        self.assertEqual(metrics.interval_ms, 2000.0)
        self.assertEqual(metrics.avg_ms, 100.0)
        self.assertEqual(metrics.latency_ms, 400.0)

    def test_parser_separates_streams_by_source_sink_pair(self):
        """Different source/sink pairs produce distinct map entries."""
        runner = self._make_runner(enable=True)

        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("latency-window", _latency_window_fields())
        )
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "latency-window",
                _latency_window_fields(source="src_p0_s1_0_1", sink="sink_p0_s1_0_1"),
            )
        )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(
            set(runner.latency_tracer_metrics.keys()),
            {
                "src_p0_s0_0_0__sink_p0_s0_0_0",
                "src_p0_s1_0_1__sink_p0_s1_0_1",
            },
        )

    def test_parser_short_circuits_when_latency_metrics_disabled(self):
        """When enable_latency_metrics=False, the map is None and no entry is recorded."""
        runner = self._make_runner(enable=False)

        self.assertIsNone(runner.latency_tracer_metrics)

        # Neither entry point may crash or allocate the map.
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("latency-window", _latency_window_fields())
        )
        runner._record_latency_window(_latency_window_fields())

        self.assertIsNone(runner.latency_tracer_metrics)

    def test_window_makes_messages_the_latency_source(self):
        """Filtered and malformed windows still prove the tracer posts messages."""
        runner = self._make_runner(enable=True)
        runner._allowed_stream_ids = {"some_other_src__some_other_sink"}
        self.assertIsNone(runner._latency_source)

        runner._record_latency_window(_latency_window_fields())
        runner._record_latency_window(_latency_window_fields(count=0))
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "latency-window", {"version": 1, "source": "src_p0_s0_0_0"}
            )
        )

        self.assertEqual(runner._latency_source, "messages")
        self.assertEqual(runner.latency_tracer_metrics, {})

        disabled = self._make_runner(enable=False)
        disabled._record_latency_window(_latency_window_fields())
        self.assertIsNone(disabled._latency_source)

    def test_non_window_metrics_do_not_set_latency_source(self):
        """Only ``latency-window`` lines decide the source; other kinds and broken lines do not."""
        runner = self._make_runner(enable=True)

        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("frame-latency", _latency_window_fields())
        )
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "genai-request",
                {
                    "version": 1,
                    "ttft_ms": 1.0,
                    "tpot_ms": 1.0,
                    "generate_duration_ms": 1.0,
                },
            )
        )
        runner._parse_and_handle_pipeline_metric("Pipeline metric: not-json")

        self.assertIsNone(runner._latency_source)

    def test_window_with_unknown_version_is_skipped_with_one_warning(self):
        """Windows of another schema version are dropped; the warning is logged once."""
        runner = self._make_runner(enable=True)

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._record_latency_window(_latency_window_fields(version=2))
            runner._record_latency_window(_latency_window_fields(version=2))
            fields = _latency_window_fields()
            del fields["version"]
            runner._record_latency_window(fields)

        self.assertEqual(runner.latency_tracer_metrics, {})
        self.assertIsNone(runner._latency_source)
        messages = [r.getMessage() for r in captured.records]
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("latency-window", messages[0])
        self.assertIn("version 2", messages[0])
        self.assertIn("version None", messages[1])

    def test_parser_drops_samples_outside_allowed_stream_ids(self):
        """
        Windows whose stream_id is not in ``_allowed_stream_ids`` are
        silently discarded. This models the production filter applied
        by ``PipelineRunner.run(allowed_stream_ids=...)`` that keeps
        only user-facing source/sink pairs (dropping internal bin
        sinks and intermediate ``splitmuxsink`` rows).
        """
        runner = self._make_runner(enable=True)
        # Only accept the "real" main source/sink pair for stream 0.
        runner._allowed_stream_ids = {self.STREAM_ID}

        # Allowed: appears verbatim in the allowlist.
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("latency-window", _latency_window_fields())
        )
        # Disallowed: an internal bin sink named just "sink", and the
        # recorder's splitmuxsink.
        for sink in ("sink", "splitmuxsink0"):
            runner._parse_and_handle_pipeline_metric(
                _make_metric_line("latency-window", _latency_window_fields(sink=sink))
            )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(set(runner.latency_tracer_metrics.keys()), {self.STREAM_ID})


@_patch_sync_metrics_executor
class TestLatencyMetricsPush(unittest.TestCase):
    """Tests for the live + final latency push to metrics-manager.

    Covers the following runner behavior:
    ``_push_latency_sample`` fires on every recorded ``latency-window``
    metric line, and ``_push_final_latency_metrics`` re-pushes the last
    sample per stream once the subprocess exits. The shared
    metrics-push ``ThreadPoolExecutor`` is replaced with a synchronous
    stub so every push runs inline in the calling thread, which keeps
    urlopen assertions deterministic.
    """

    SAMPLE_WINDOW_LINE = _make_metric_line("latency-window", _latency_window_fields())

    def _sample(self, seed: float = 1.0) -> LatencyTracerSample:
        """Build a deterministic sample where every field derives from a single seed."""
        return LatencyTracerSample(
            interval_ms=1000.0 * seed,
            avg_ms=10.0 * seed,
            min_ms=1.0 * seed,
            max_ms=100.0 * seed,
            latency_ms=5.0 * seed,
        )

    # ------------------------------------------------------------------
    # _push_latency_sample: payload shape, URL, tags
    # ------------------------------------------------------------------

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_latency_sample_uses_batch_endpoint(self, mock_urlopen):
        """Latency pushes target the batch `/api/v1/metrics` endpoint (NOT `/simple`)."""
        with patch.dict(
            "os.environ",
            {"METRICS_MANAGER_URL": "http://example:1234"},
            clear=False,
        ):
            runner = PipelineRunner(
                mode="normal", enable_latency_metrics=True, job_id="job-42"
            )

        runner._push_latency_sample("stream-a", self._sample())

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://example:1234/api/v1/metrics")
        self.assertEqual(req.headers.get("Content-type"), "application/json")

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_latency_sample_payload_shape(self, mock_urlopen):
        """Payload is a single-entry batch with the four timing fields and both tags."""
        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=True, job_id="job-42"
        )
        sample = self._sample(seed=2.0)

        runner._push_latency_sample("stream-a", sample)

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode())
        self.assertEqual(
            body,
            {
                "metrics": [
                    {
                        "name": "pipeline_latency",
                        "fields": {
                            "avg_ms": sample.avg_ms,
                            "min_ms": sample.min_ms,
                            "max_ms": sample.max_ms,
                            "latency_ms": sample.latency_ms,
                        },
                        "tags": {"job_id": "job-42", "stream_id": "stream-a"},
                    }
                ]
            },
        )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_latency_sample_omits_interval_and_fps(self, mock_urlopen):
        """`interval_ms` and `fps` must never leak into the payload fields."""
        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=True, job_id="job-42"
        )

        runner._push_latency_sample("stream-a", self._sample())

        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        fields = body["metrics"][0]["fields"]
        self.assertNotIn("interval_ms", fields)
        self.assertNotIn("fps", fields)

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_latency_sample_without_job_id_still_tags_stream_id(
        self, mock_urlopen
    ):
        """When `job_id=None`, `stream_id` is still present as a tag."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        runner._push_latency_sample("stream-a", self._sample())

        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["metrics"][0]["tags"], {"stream_id": "stream-a"})

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_latency_sample_swallows_network_errors(self, mock_urlopen):
        """Network errors while pushing latency must be logged at WARNING, never raised."""
        mock_urlopen.side_effect = OSError("boom")
        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=True, job_id="job-42"
        )

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._push_latency_sample("stream-a", self._sample())

        self.assertTrue(
            any("Failed to push latency metric" in line for line in captured.output)
        )

    # ------------------------------------------------------------------
    # Live push: every recorded window is forwarded
    # ------------------------------------------------------------------

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_parser_triggers_live_push_for_each_sample(self, mock_urlopen):
        """Each recorded latency-window line produces exactly one batch POST."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_WINDOW_LINE)
        runner._parse_and_handle_pipeline_metric(self.SAMPLE_WINDOW_LINE)

        self.assertEqual(mock_urlopen.call_count, 2)
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            self.assertTrue(req.full_url.endswith("/api/v1/metrics"))
            body = json.loads(req.data.decode())
            self.assertEqual(body["metrics"][0]["name"], "pipeline_latency")
            self.assertEqual(
                body["metrics"][0]["fields"],
                {"avg_ms": 25.0, "min_ms": 10.0, "max_ms": 40.0, "latency_ms": 250.0},
            )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_parser_live_push_uses_parsed_stream_id_as_tag(self, mock_urlopen):
        """The `stream_id` tag matches the composite `source__sink` key in the map."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_WINDOW_LINE)

        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(
            body["metrics"][0]["tags"]["stream_id"],
            "src_p0_s0_0_0__sink_p0_s0_0_0",
        )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_parser_does_not_push_when_latency_metrics_disabled(self, mock_urlopen):
        """When `enable_latency_metrics=False`, no HTTP request is ever made."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_WINDOW_LINE)

        mock_urlopen.assert_not_called()

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_parser_does_not_push_for_filtered_stream_id(self, mock_urlopen):
        """Samples dropped by `_allowed_stream_ids` must not produce a push."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        # Allow only a different stream_id than the one in the sample line.
        runner._allowed_stream_ids = {"some_other_stream"}

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_WINDOW_LINE)

        mock_urlopen.assert_not_called()

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_parser_does_not_push_for_malformed_or_unknown_lines(self, mock_urlopen):
        """Dropped metric lines (bad JSON, count <= 0, unknown kind) never push."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        runner._parse_and_handle_pipeline_metric("Pipeline metric: not-json")
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("latency-window", _latency_window_fields(count=0))
        )
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line("frame-latency", _latency_window_fields())
        )

        mock_urlopen.assert_not_called()

    # ------------------------------------------------------------------
    # Final push: every stream in the map is re-pushed on exit
    # ------------------------------------------------------------------

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_final_latency_metrics_emits_one_per_stream(self, mock_urlopen):
        """One batch POST per stream present in `latency_tracer_metrics`."""
        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=True, job_id="job-42"
        )
        runner.latency_tracer_metrics = {
            "stream-a": self._sample(seed=1.0),
            "stream-b": self._sample(seed=2.0),
        }

        runner._push_final_latency_metrics()

        self.assertEqual(mock_urlopen.call_count, 2)
        pushed_stream_ids = set()
        for call in mock_urlopen.call_args_list:
            body = json.loads(call[0][0].data.decode())
            pushed_stream_ids.add(body["metrics"][0]["tags"]["stream_id"])
        self.assertEqual(pushed_stream_ids, {"stream-a", "stream-b"})

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_final_latency_metrics_noop_when_disabled(self, mock_urlopen):
        """No-op when the tracer is disabled (map is `None`)."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)

        runner._push_final_latency_metrics()

        mock_urlopen.assert_not_called()

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_final_latency_metrics_noop_when_map_empty(self, mock_urlopen):
        """No-op when the tracer was enabled but produced no samples."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        # Map already starts empty when enabled; assert explicitly for clarity.
        self.assertEqual(runner.latency_tracer_metrics, {})

        runner._push_final_latency_metrics()

        mock_urlopen.assert_not_called()

    # ------------------------------------------------------------------
    # End-to-end: final push is invoked from `_run_normal`'s `finally`
    # ------------------------------------------------------------------

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_normal_triggers_final_latency_push_in_finally(
        self, mock_urlopen, mock_select, mock_ps, mock_popen
    ):
        """A full `_run_normal` emits both a live push and a final push per stream."""
        # One window line on stdout: the live push fires once, then the
        # `finally` block re-pushes the same stream → 2 batch POSTs total.
        process_mock = _make_process_mock([self.SAMPLE_WINDOW_LINE])
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=True, job_id="job-42"
        )
        runner.run(pipeline_command="videotestsrc ! fakesink", total_streams=1)

        batch_bodies = _extract_latency_payloads(mock_urlopen)
        self.assertEqual(
            len(batch_bodies),
            2,
            "Expected one live push + one final push for the single stream",
        )
        for body in batch_bodies:
            self.assertEqual(body["metrics"][0]["name"], "pipeline_latency")
            self.assertEqual(body["metrics"][0]["tags"]["job_id"], "job-42")
            self.assertEqual(
                body["metrics"][0]["tags"]["stream_id"],
                "src_p0_s0_0_0__sink_p0_s0_0_0",
            )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_normal_does_not_push_latency_when_disabled(
        self, mock_urlopen, mock_select, mock_ps, mock_popen
    ):
        """With `enable_latency_metrics=False`, no batch-endpoint call is ever made."""
        process_mock = _make_process_mock([self.SAMPLE_WINDOW_LINE])
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(
            mode="normal", enable_latency_metrics=False, job_id="job-42"
        )
        runner.run(pipeline_command="videotestsrc ! fakesink", total_streams=1)

        batch_bodies = _extract_latency_payloads(mock_urlopen)
        self.assertEqual(batch_bodies, [])

    # ------------------------------------------------------------------
    # `_run_normal` warns when the tracer was enabled but stayed silent
    #
    # The warning is logged only on the successful-return path, when no
    # `latency-window` line reached `_record_latency_window` during the
    # run (counted before stream filtering) and the run was not
    # cancelled.
    # ------------------------------------------------------------------

    NO_WINDOW_WARNING = "no latency_tracer window arrived"

    def _run_normal_with_lines(
        self,
        stdout_lines: list[str],
        enable_latency_metrics: bool = True,
        *,
        runner: PipelineRunner | None = None,
        allowed_stream_ids: set[str] | None = None,
        exit_code: int = 0,
        cancel_after_first_line: bool = False,
    ) -> tuple[PipelineRunner, PipelineResult]:
        """Run `_run_normal` against a mocked subprocess emitting `stdout_lines`.

        With ``cancel_after_first_line`` the runner is cancelled from
        inside the first ``readline()``, so the next loop iteration
        takes the cancellation path (``_graceful_terminate`` is mocked).
        """
        process_mock = _make_process_mock(stdout_lines, exit_code=exit_code)
        if runner is None:
            runner = PipelineRunner(
                mode="normal", enable_latency_metrics=enable_latency_metrics
            )
        if cancel_after_first_line:
            lines = process_mock.stdout.readline.side_effect

            def _readline_then_cancel():
                line = next(lines)
                runner.cancel()
                return line

            process_mock.stdout.readline.side_effect = _readline_then_cancel
        with (
            patch("pipeline_runner.Popen", return_value=process_mock),
            patch("pipeline_runner.ps") as mock_ps,
            patch(
                "pipeline_runner.select.select",
                return_value=([process_mock.stdout], [], []),
            ),
            patch("pipeline_runner.urllib.request.urlopen"),
            patch.object(runner, "_graceful_terminate"),
        ):
            mock_ps.Process.return_value.status.return_value = "zombie"
            result = runner.run(
                pipeline_command="videotestsrc ! fakesink",
                total_streams=1,
                allowed_stream_ids=allowed_stream_ids,
            )
        return runner, result

    def _assert_no_window_warning(self, output: list[str]) -> None:
        self.assertFalse(
            any(self.NO_WINDOW_WARNING in line for line in output),
            f"Unexpected no-window warning in: {output}",
        )

    def test_run_normal_warns_when_no_latency_window_arrived(self):
        """Enabled tracer + zero windows logs one WARNING."""
        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner, result = self._run_normal_with_lines(["some unrelated line"])

        self.assertEqual(runner.latency_tracer_metrics, {})
        self.assertEqual(result.latency_tracer_metrics, {})
        warnings = [
            r for r in captured.records if self.NO_WINDOW_WARNING in r.getMessage()
        ]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].levelname, "WARNING")

    def test_run_normal_does_not_warn_when_latency_window_arrived(self):
        """At least one recorded window suppresses the warning."""
        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            self._run_normal_with_lines([self.SAMPLE_WINDOW_LINE])

    def test_run_normal_does_not_warn_when_latency_disabled(self):
        """With the tracer disabled (map `None`) there is nothing to warn about."""
        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            self._run_normal_with_lines(
                ["some unrelated line"], enable_latency_metrics=False
            )

    def test_run_normal_does_not_warn_when_all_windows_are_filtered(self):
        """Windows dropped by `allowed_stream_ids` still prove the tracer posts messages."""
        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            _, result = self._run_normal_with_lines(
                [self.SAMPLE_WINDOW_LINE],
                allowed_stream_ids={"some_other_src__some_other_sink"},
            )

        # Nothing was recorded, yet the tracer was demonstrably active.
        self.assertEqual(result.latency_tracer_metrics, {})

    def test_run_normal_does_not_warn_when_cancelled(self):
        """A cancelled run may end before the first window; that is not worth a warning."""
        # Cancellation makes gst_runner exit non-zero (SIGINT), which logs at
        # ERROR, so filter on the warning text rather than on the level.
        with self.assertLogs("PipelineRunner", level="INFO") as captured:
            _, result = self._run_normal_with_lines(
                ["some unrelated line"], exit_code=-2, cancel_after_first_line=True
            )

        self.assertTrue(result.cancelled)
        self.assertEqual(result.latency_tracer_metrics, {})
        self._assert_no_window_warning(captured.output)

    def test_run_normal_does_not_warn_when_run_fails(self):
        """A failed run raises; the warning is only logged on the successful-return path."""
        with self.assertLogs("PipelineRunner", level="INFO") as captured:
            with self.assertRaises(RuntimeError):
                self._run_normal_with_lines(["some unrelated line"], exit_code=1)

        self._assert_no_window_warning(captured.output)

    def test_run_normal_resets_latency_source_per_run(self):
        """A window seen in an earlier run on the same runner must not hide the warning."""
        runner, _ = self._run_normal_with_lines([self.SAMPLE_WINDOW_LINE])
        self.assertEqual(runner._latency_source, "messages")

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            self._run_normal_with_lines(["some unrelated line"], runner=runner)

        self.assertIsNone(runner._latency_source)
        self.assertTrue(any(self.NO_WINDOW_WARNING in line for line in captured.output))

    # ------------------------------------------------------------------
    # End-to-end latency fallback and output drained after exit
    # ------------------------------------------------------------------

    FALLBACK_WARNING = "falling back to parsing its log records"

    def test_run_normal_records_single_held_record_at_end_of_run(self):
        """Without any window message, a run's only record is recorded with one warning."""
        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            _, result = self._run_normal_with_lines([_make_record_line(avg=12.5)])

        assert result.latency_tracer_metrics is not None
        self.assertEqual(
            result.latency_tracer_metrics["src_p0_s0_0_0__sink_p0_s0_0_0"].avg_ms, 12.5
        )
        warnings = [r.getMessage() for r in captured.records]
        self.assertEqual(
            [m for m in warnings if self.FALLBACK_WARNING in m], [warnings[0]]
        )
        self._assert_no_window_warning(warnings)

    def test_run_normal_prefers_window_messages_over_records(self):
        """A record logged before the first posted window is dropped, without a warning."""
        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            _, result = self._run_normal_with_lines(
                [_make_record_line(avg=99.0), self.SAMPLE_WINDOW_LINE]
            )

        assert result.latency_tracer_metrics is not None
        self.assertEqual(
            result.latency_tracer_metrics["src_p0_s0_0_0__sink_p0_s0_0_0"].avg_ms, 25.0
        )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_normal_parses_metrics_drained_after_exit(self, mock_urlopen):
        """Metric lines read by ``communicate()`` after the loop still count."""
        process_mock = _make_process_mock([])
        process_mock.communicate.return_value = (
            f"{self.SAMPLE_WINDOW_LINE}\nPipeline run succeeded.\n".encode(),
            b"",
        )
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        with (
            patch("pipeline_runner.Popen", return_value=process_mock),
            patch("pipeline_runner.ps") as mock_ps,
            patch("pipeline_runner.select.select", return_value=([], [], [])),
            self.assertNoLogs("PipelineRunner", level="WARNING"),
        ):
            mock_ps.Process.return_value.status.return_value = "zombie"
            result = runner.run(
                pipeline_command="videotestsrc ! fakesink", total_streams=1
            )

        assert result.latency_tracer_metrics is not None
        self.assertEqual(
            set(result.latency_tracer_metrics), {"src_p0_s0_0_0__sink_p0_s0_0_0"}
        )


class TestLatencyRecordFallback(unittest.TestCase):
    """``latency_tracer_pipeline_interval`` records as the latency fallback.

    A ``latency_tracer`` that predates ``post-metrics`` ignores the
    parameter and only logs its windows as text records, which
    ``gst_runner`` promotes until the tracer posts a window as a bus
    message. The runner holds a record per stream back until it knows
    which source the run has: a ``latency-window`` message (records are
    dropped) or a second record of the same stream (records are used).
    """

    STREAM_ID = "src_p0_s0_0_0__sink_p0_s0_0_0"
    FALLBACK_WARNING = "falling back to parsing its log records"

    def _runner(self) -> PipelineRunner:
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        self.push = MagicMock()
        runner._push_latency_sample = self.push  # type: ignore[method-assign]
        return runner

    def test_second_record_of_a_stream_selects_records(self):
        """Both records are recorded and pushed, in order; one warning is logged."""
        runner = self._runner()

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._handle_dl_streamer_metric_line(
                _make_record_line(avg=1.5), emit_events=True
            )
            self.assertIsNone(runner._latency_source)
            runner._handle_dl_streamer_metric_line(
                _make_record_line(avg=2.5), emit_events=True
            )
            runner._handle_dl_streamer_metric_line(
                _make_record_line(avg=3.5), emit_events=True
            )

        self.assertEqual(runner._latency_source, "records")
        self.assertEqual(len(captured.records), 1)
        self.assertIn(self.FALLBACK_WARNING, captured.records[0].getMessage())
        pushed = [c.args[1].avg_ms for c in self.push.call_args_list]
        self.assertEqual(pushed, [1.5, 2.5, 3.5])
        assert runner.latency_tracer_metrics is not None
        self.assertEqual(
            runner.latency_tracer_metrics[self.STREAM_ID],
            LatencyTracerSample(
                interval_ms=1000.25,
                avg_ms=3.5,
                min_ms=0.004,
                max_ms=529.26,
                latency_ms=21.28,
            ),
        )

    def test_records_of_different_streams_are_held(self):
        """One record per stream does not decide the source yet."""
        runner = self._runner()

        runner._parse_latency_record(_make_record_line())
        runner._parse_latency_record(
            _make_record_line(source="src_p0_s1_0_1", sink="sink_p0_s1_0_1")
        )

        self.assertIsNone(runner._latency_source)
        self.assertEqual(runner.latency_tracer_metrics, {})
        self.push.assert_not_called()

    def test_window_message_drops_held_records_and_later_records(self):
        """Once a window arrives, records are never recorded, and no warning is logged."""
        runner = self._runner()

        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            runner._parse_latency_record(_make_record_line(avg=99.0))
            runner._parse_latency_record(
                _make_record_line(source="src_p0_s1_0_1", sink="sink_p0_s1_0_1")
            )
            runner._handle_dl_streamer_metric_line(
                _make_metric_line("latency-window", _latency_window_fields()),
                emit_events=True,
            )
            runner._parse_latency_record(_make_record_line(avg=98.0))
            runner._parse_latency_record(_make_record_line(avg=97.0))
            runner._finish_latency_records()

        self.assertEqual(runner._latency_source, "messages")
        assert runner.latency_tracer_metrics is not None
        self.assertEqual(set(runner.latency_tracer_metrics), {self.STREAM_ID})
        self.assertEqual(runner.latency_tracer_metrics[self.STREAM_ID].avg_ms, 25.0)
        self.assertEqual(self.push.call_count, 1)

    def test_window_message_after_records_switches_to_messages(self):
        """Messages win even after records were selected."""
        runner = self._runner()
        runner._parse_latency_record(_make_record_line(avg=1.0))
        with self.assertLogs("PipelineRunner", level="WARNING"):
            runner._parse_latency_record(_make_record_line(avg=2.0))

        runner._record_latency_window(_latency_window_fields())
        runner._parse_latency_record(_make_record_line(avg=3.0))

        self.assertEqual(runner._latency_source, "messages")
        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics[self.STREAM_ID].avg_ms, 25.0)

    def test_finish_records_held_records_with_one_warning(self):
        """Held records are recorded when the run ends without a window message."""
        runner = self._runner()
        runner._parse_latency_record(_make_record_line())
        runner._parse_latency_record(
            _make_record_line(source="src_p0_s1_0_1", sink="sink_p0_s1_0_1")
        )

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._finish_latency_records()
            runner._finish_latency_records()

        self.assertEqual(len(captured.records), 1)
        self.assertEqual(runner._latency_source, "records")
        assert runner.latency_tracer_metrics is not None
        self.assertEqual(
            set(runner.latency_tracer_metrics),
            {self.STREAM_ID, "src_p0_s1_0_1__sink_p0_s1_0_1"},
        )

    def test_finish_without_records_keeps_source_undecided(self):
        runner = self._runner()

        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            runner._finish_latency_records()

        self.assertIsNone(runner._latency_source)

    def test_records_respect_allowed_stream_ids(self):
        """Records of internal sinks are used to decide the source but not stored."""
        runner = self._runner()
        runner._allowed_stream_ids = {self.STREAM_ID}

        with self.assertLogs("PipelineRunner", level="WARNING"):
            runner._parse_latency_record(_make_record_line(sink="sink"))
            runner._parse_latency_record(_make_record_line(sink="sink"))
        runner._parse_latency_record(_make_record_line())

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(set(runner.latency_tracer_metrics), {self.STREAM_ID})

    def test_malformed_records_are_ignored(self):
        runner = self._runner()

        for line in (
            "gst_runner - INFO - latency_tracer_pipeline_interval, garbage",
            _make_record_line().replace("avg=(double)364.31", "avg=(double)nan"),
        ):
            runner._parse_latency_record(line)
            runner._parse_latency_record(line)

        self.assertIsNone(runner._latency_source)
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_records_are_ignored_when_latency_disabled(self):
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)

        runner._handle_dl_streamer_metric_line(_make_record_line(), emit_events=True)
        runner._handle_dl_streamer_metric_line(_make_record_line(), emit_events=True)
        runner._finish_latency_records()

        self.assertIsNone(runner.latency_tracer_metrics)
        self.assertIsNone(runner._latency_source)

    def test_reset_clears_per_run_state(self):
        runner = self._runner()
        runner._parse_latency_record(_make_record_line())
        runner._finish_latency_records()
        runner._genai_fallback_warned = True
        runner._unknown_metric_versions.add(("genai-request", 2))

        runner._reset_dl_streamer_metrics_state()

        self.assertIsNone(runner._latency_source)
        self.assertEqual(runner._held_latency_records, {})
        self.assertFalse(runner._genai_fallback_warned)
        self.assertEqual(runner._unknown_metric_versions, set())


@_patch_sync_metrics_executor
class TestVlmMetricsPush(unittest.TestCase):
    """Tests for the ``gvagenai`` VLM-metrics parse + push path.

    ``gvagenai`` (with ``post-metrics=true``, set by ``gst_runner``) posts
    one ``dlstreamer/genai-request`` bus message per generation request.
    ``gst_runner`` forwards it as a ``Pipeline metric: {json}`` line
    whose ``fields`` carry that request's ``ttft_ms``, ``tpot_ms`` and
    ``generate_duration_ms``; the runner pushes them unchanged to
    metrics-manager as ``vlm_metrics``. The emitting ``gvagenai_*``
    element name (``element`` in the payload) is used as the
    ``stream_id`` tag so multi-stream jobs can be partitioned on the
    dashboard; when it is ``null`` the push omits the tag rather than
    failing.

    A ``gvagenai`` that predates ``post-metrics`` keeps the cumulative
    ``metrics`` block in its ``Added meta message:`` JSON line, which is
    then pushed as the fallback (``gst_runner`` drops the block for
    elements that do post messages).
    """

    # Pushed `vlm_metrics` fields, and the message fields they come from.
    REQUEST_FIELDS = {"ttft_ms": 12.5, "tpot_ms": 3.25, "generate_duration_ms": 250.0}
    MESSAGE_FIELDS = {"version": 1, **REQUEST_FIELDS}

    SAMPLE_REQUEST_LINE = _make_metric_line(
        "genai-request", MESSAGE_FIELDS, element="gvagenai_0_0"
    )
    SAMPLE_REQUEST_LINE_NO_ELEMENT = _make_metric_line("genai-request", MESSAGE_FIELDS)
    META_LINE_WITH_METRICS = (
        "gst_runner - INFO - <gvagenai_0_0> Added meta message: "
        '{"result": "Yes", "metrics": {"ttft_mean": 12.5, "tpot_mean": 3.25, '
        '"generate_duration_mean": 250.0, "load_time": 1.0}}'
    )
    FALLBACK_WARNING = "does not support post-metrics"

    def _get_vlm_payload(self, mock_urlopen: MagicMock) -> dict:
        """Return the single ``vlm_metrics`` batch payload sent to metrics-manager."""
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            if not req.full_url.endswith("/api/v1/metrics"):
                continue
            body = json.loads(req.data.decode())
            if body["metrics"][0]["name"] == "vlm_metrics":
                return body
        self.fail("No vlm_metrics batch push was made")

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_pushes_element_name_as_stream_id(self, mock_urlopen):
        """The payload ``element`` must be forwarded as the ``stream_id`` tag."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_REQUEST_LINE)

        body = self._get_vlm_payload(mock_urlopen)
        tags = body["metrics"][0]["tags"]
        self.assertEqual(tags["stream_id"], "gvagenai_0_0")
        self.assertEqual(tags["job_id"], "job-42")

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_forwards_metric_fields(self, mock_urlopen):
        """Exactly the three per-request fields are pushed; extra fields are ignored."""
        runner = PipelineRunner(mode="normal")

        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "genai-request",
                {**self.MESSAGE_FIELDS, "num_generated_tokens": 42},
                element="gvagenai_0_0",
            )
        )

        body = self._get_vlm_payload(mock_urlopen)
        self.assertEqual(body["metrics"][0]["fields"], self.REQUEST_FIELDS)

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_omits_stream_id_when_element_missing(self, mock_urlopen):
        """Without an ``element`` the push must still succeed, minus ``stream_id``."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_REQUEST_LINE_NO_ELEMENT)

        body = self._get_vlm_payload(mock_urlopen)
        tags = body["metrics"][0]["tags"]
        self.assertNotIn("stream_id", tags)
        self.assertEqual(tags["job_id"], "job-42")

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_ignores_non_string_element(self, mock_urlopen):
        """A non-string ``element`` is treated as missing, not stringified."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        runner._parse_and_handle_pipeline_metric(
            "gst_runner - INFO - Pipeline metric: "
            + json.dumps(
                {"kind": "genai-request", "element": 7, "fields": self.MESSAGE_FIELDS}
            )
        )

        body = self._get_vlm_payload(mock_urlopen)
        self.assertEqual(body["metrics"][0]["tags"], {"job_id": "job-42"})

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_without_job_id_still_tags_stream_id(self, mock_urlopen):
        """When only ``stream_id`` is known the payload must still carry a ``tags`` block."""
        runner = PipelineRunner(mode="normal", job_id=None)

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_REQUEST_LINE)

        body = self._get_vlm_payload(mock_urlopen)
        self.assertEqual(body["metrics"][0]["tags"], {"stream_id": "gvagenai_0_0"})

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_without_tags_omits_tags_field(self, mock_urlopen):
        """No job_id and no element must produce a payload without a ``tags`` field."""
        runner = PipelineRunner(mode="normal", job_id=None)

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_REQUEST_LINE_NO_ELEMENT)

        body = self._get_vlm_payload(mock_urlopen)
        self.assertNotIn("tags", body["metrics"][0])

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_requests_are_pushed_separately_per_element(self, mock_urlopen):
        """Two elements in the same run must produce two pushes with distinct ``stream_id`` tags."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        runner._parse_and_handle_pipeline_metric(self.SAMPLE_REQUEST_LINE)
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "genai-request", self.MESSAGE_FIELDS, element="gvagenai_0_1"
            )
        )

        stream_ids: list[str] = []
        for call in mock_urlopen.call_args_list:
            body = json.loads(call[0][0].data.decode())
            if body["metrics"][0]["name"] == "vlm_metrics":
                stream_ids.append(body["metrics"][0]["tags"]["stream_id"])
        self.assertEqual(stream_ids, ["gvagenai_0_0", "gvagenai_0_1"])

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_with_missing_or_non_numeric_field_is_dropped(
        self, mock_urlopen
    ):
        """All three fields are required and must be numeric; otherwise nothing is pushed."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        for missing in self.REQUEST_FIELDS:
            fields = {k: v for k, v in self.MESSAGE_FIELDS.items() if k != missing}
            runner._parse_and_handle_pipeline_metric(
                _make_metric_line("genai-request", fields, element="gvagenai_0_0")
            )
        runner._parse_and_handle_pipeline_metric(
            _make_metric_line(
                "genai-request",
                {**self.MESSAGE_FIELDS, "ttft_ms": "fast"},
                element="gvagenai_0_0",
            )
        )
        runner._parse_and_handle_pipeline_metric(
            "gst_runner - INFO - Pipeline metric: not-json"
        )

        mock_urlopen.assert_not_called()

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_genai_request_with_unknown_version_is_skipped(self, mock_urlopen):
        """Requests of another schema version are not pushed; one warning per version."""
        runner = PipelineRunner(mode="normal", job_id="job-42")

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            for _ in range(2):
                runner._parse_and_handle_pipeline_metric(
                    _make_metric_line(
                        "genai-request",
                        {**self.MESSAGE_FIELDS, "version": 2},
                        element="gvagenai_0_0",
                    )
                )
            runner._parse_and_handle_pipeline_metric(
                _make_metric_line(
                    "genai-request", self.REQUEST_FIELDS, element="gvagenai_0_0"
                )
            )

        mock_urlopen.assert_not_called()
        messages = [r.getMessage() for r in captured.records]
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("genai-request", messages[0])
        self.assertIn("version 2", messages[0])
        self.assertIn("version None", messages[1])

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_meta_message_metrics_block_is_pushed_as_fallback(self, mock_urlopen):
        """A ``metrics`` block (no ``post-metrics``) is pushed, warning once per run."""
        events = []
        runner = PipelineRunner(mode="normal", job_id="job-42", on_event=events.append)
        runner._genai_metrics_enabled = True

        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner._parse_genai_meta_line(self.META_LINE_WITH_METRICS)
            runner._parse_genai_meta_line(self.META_LINE_WITH_METRICS)

        bodies = _extract_latency_payloads(mock_urlopen)
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0]["metrics"][0]["name"], "vlm_metrics")
        self.assertEqual(bodies[0]["metrics"][0]["fields"], self.REQUEST_FIELDS)
        self.assertEqual(
            bodies[0]["metrics"][0]["tags"],
            {"job_id": "job-42", "stream_id": "gvagenai_0_0"},
        )
        self.assertEqual(len(captured.records), 1)
        self.assertIn(self.FALLBACK_WARNING, captured.records[0].getMessage())
        self.assertIn("gvagenai_0_0", captured.records[0].getMessage())
        self.assertEqual([e.text for e in events], ["Yes", "Yes"])

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_meta_message_without_means_is_not_pushed(self, mock_urlopen):
        """Blocks without the VLM means (e.g. openai-http token usage) are not pushed."""
        runner = PipelineRunner(mode="normal")
        runner._genai_metrics_enabled = True

        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            for metrics in (
                '{"prompt_tokens": 10, "completion_tokens": 5}',
                '{"ttft_mean": "fast", "tpot_mean": 1, "generate_duration_mean": 1}',
                '"not-a-dict"',
            ):
                runner._parse_genai_meta_line(
                    "gst_runner - INFO - <gvagenai_0_0> Added meta message: "
                    f'{{"result": "Yes", "metrics": {metrics}}}'
                )

        mock_urlopen.assert_not_called()

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_normal_pushes_genai_request(
        self, mock_urlopen, mock_select, mock_ps, mock_popen
    ):
        """End-to-end: with post-metrics the meta line has no block; the request is pushed."""
        process_mock = _make_process_mock(
            [
                self.SAMPLE_REQUEST_LINE,
                "gst_runner - INFO - <gvagenai_0_0> Added meta message: "
                '{"result": "Yes"}',
            ]
        )
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        events = []
        runner = PipelineRunner(mode="normal", job_id="job-42", on_event=events.append)
        with self.assertNoLogs("PipelineRunner", level="WARNING"):
            runner.run(
                pipeline_command="videotestsrc ! gvagenai metrics=true ! fakesink",
                total_streams=1,
            )

        vlm_fields = [
            body["metrics"][0]["fields"]
            for body in _extract_latency_payloads(mock_urlopen)
            if body["metrics"][0]["name"] == "vlm_metrics"
        ]
        self.assertEqual(vlm_fields, [self.REQUEST_FIELDS])
        self.assertEqual([(e.source, e.text) for e in events], [("vlm", "Yes")])

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_run_normal_falls_back_to_meta_metrics(
        self, mock_urlopen, mock_select, mock_ps, mock_popen
    ):
        """End-to-end: without post-metrics the meta block is pushed, also without on_event."""
        process_mock = _make_process_mock([self.META_LINE_WITH_METRICS])
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", job_id="job-42")
        with self.assertLogs("PipelineRunner", level="WARNING") as captured:
            runner.run(
                pipeline_command="videotestsrc ! gvagenai metrics=true ! fakesink",
                total_streams=1,
            )

        vlm_fields = [
            body["metrics"][0]["fields"]
            for body in _extract_latency_payloads(mock_urlopen)
            if body["metrics"][0]["name"] == "vlm_metrics"
        ]
        self.assertEqual(vlm_fields, [self.REQUEST_FIELDS])
        self.assertTrue(
            any(self.FALLBACK_WARNING in r.getMessage() for r in captured.records)
        )


class TestPipelineEvents(unittest.TestCase):
    """Live events forwarded to ``on_event``: VLM answers and ``vippet-event`` lines."""

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_vlm_result_is_emitted_as_event(self, _mock_urlopen):
        events = []
        runner = PipelineRunner(mode="normal", on_event=events.append)

        runner._parse_genai_meta_line(
            "gst_runner - INFO - <gvagenai_0_0> Added meta message: "
            '{"result": " Yes ", "timestamp_seconds": 9.97, "prompt": "Riding?"}'
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "vlm")
        self.assertEqual(events[0].text, "Yes")
        self.assertEqual(events[0].prompt, "Riding?")
        self.assertEqual(events[0].element, "gvagenai_0_0")
        self.assertEqual(events[0].pts_seconds, 9.97)

    def test_vlm_result_without_text_or_element_prefix(self):
        """Blank results are dropped; a missing ``<name>`` prefix yields ``element=None``."""
        events = []
        runner = PipelineRunner(mode="normal", on_event=events.append)

        runner._parse_genai_meta_line(
            'gst_runner - INFO - <gvagenai_0_0> Added meta message: {"result": "  "}'
        )
        runner._parse_genai_meta_line(
            "gst_runner - INFO - <gvagenai_0_0> Added meta message: not-json"
        )
        runner._parse_genai_meta_line(
            'gst_runner - INFO - Added meta message: {"result": "No"}'
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].text, "No")
        self.assertIsNone(events[0].element)
        self.assertIsNone(events[0].pts_seconds)
        self.assertIsNone(events[0].prompt)

    def test_pipeline_event_line_is_emitted(self):
        events = []
        runner = PipelineRunner(mode="normal", on_event=events.append)

        runner._parse_and_emit_pipeline_event(
            "gst_runner - INFO - Pipeline event: "
            '{"source": "proximity-trigger", "text": "person near bicycle", '
            '"pts-seconds": 1.5, "element": "gvaproximitytrigger_py0"}'
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "proximity-trigger")
        self.assertEqual(events[0].text, "person near bicycle")
        self.assertEqual(events[0].element, "gvaproximitytrigger_py0")
        self.assertEqual(events[0].pts_seconds, 1.5)

    def test_malformed_pipeline_event_is_dropped(self):
        events = []
        runner = PipelineRunner(mode="normal", on_event=events.append)

        runner._parse_and_emit_pipeline_event("Pipeline event: not-json")
        runner._parse_and_emit_pipeline_event('Pipeline event: {"source": "x"}')

        self.assertEqual(events, [])


class TestPipelineResultRepr(unittest.TestCase):
    """Coverage for the custom ``PipelineResult.__repr__``.

    The implementation formats ``latency_tracer_metrics`` by its
    cardinality so the repr stays compact when many streams are
    running; both branches (``None`` and non-empty dict) must be
    covered.
    """

    def test_repr_with_latency_metrics_none(self):
        """When tracer is disabled the repr uses the literal ``None`` marker."""
        result = PipelineResult(total_fps=10.0, per_stream_fps=5.0, num_streams=2)
        text = repr(result)
        self.assertIn("PipelineResult(", text)
        self.assertIn("latency_tracer_metrics=None", text)

    def test_repr_with_latency_metrics_streams(self):
        """When tracer produced samples the repr summarises their count."""
        sample = LatencyTracerSample(
            interval_ms=1000.0,
            avg_ms=10.0,
            min_ms=1.0,
            max_ms=100.0,
            latency_ms=5.0,
        )
        result = PipelineResult(
            total_fps=10.0,
            per_stream_fps=5.0,
            num_streams=2,
            latency_tracer_metrics={"a": sample, "b": sample},
        )
        text = repr(result)
        self.assertIn("latency_tracer_metrics=<2 stream(s)>", text)


class TestGetLogLevel(unittest.TestCase):
    """Coverage for the ``RUNNER_LOG_LEVEL`` env-var parsing."""

    @patch.dict("os.environ", {"RUNNER_LOG_LEVEL": "DEBUG"}, clear=False)
    def test_valid_level_is_returned_as_is(self):
        self.assertEqual(PipelineRunner._get_log_level(), "DEBUG")

    @patch.dict("os.environ", {"RUNNER_LOG_LEVEL": "not-a-level"}, clear=False)
    def test_invalid_level_falls_back_to_info(self):
        """Unknown values must map to the documented default ``INFO``."""
        self.assertEqual(PipelineRunner._get_log_level(), "INFO")


class TestGracefulTerminate(unittest.TestCase):
    """Coverage for ``PipelineRunner._graceful_terminate``.

    The method is a defensive helper used in three distinct
    scenarios, each represented here by one test:

    1. The subprocess has already exited — ``poll()`` returns an
       exit code and the method short-circuits with no signal.
    2. The subprocess ignores SIGINT and ``wait(timeout=...)`` raises
       ``TimeoutExpired`` — the method must escalate to SIGKILL.
    3. ``send_signal`` raises ``OSError`` (process reaped between the
       ``poll()`` check and the signal) — the exception is swallowed.
    """

    def test_returns_immediately_when_process_already_exited(self):
        proc = MagicMock()
        proc.poll.return_value = 0  # already exited

        PipelineRunner._graceful_terminate(proc)

        proc.send_signal.assert_not_called()
        proc.kill.assert_not_called()

    def test_escalates_to_sigkill_on_sigint_timeout(self):
        """SIGINT timing out triggers SIGKILL + a final ``wait``."""
        proc = MagicMock()
        proc.poll.return_value = None  # still running
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="gst_runner.py", timeout=0.1),
            0,  # second wait() after kill() succeeds
        ]

        PipelineRunner._graceful_terminate(proc, timeout=0.1)

        proc.send_signal.assert_called_once_with(signal.SIGINT)
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 2)

    def test_swallows_oserror_from_send_signal(self):
        """``OSError`` (e.g. ``ESRCH`` after reap) must not propagate."""
        proc = MagicMock()
        proc.poll.return_value = None
        proc.send_signal.side_effect = OSError("no such process")

        # Must not raise.
        PipelineRunner._graceful_terminate(proc)

        proc.send_signal.assert_called_once_with(signal.SIGINT)


@_patch_sync_metrics_executor
class TestRunNormalEdgeCases(unittest.TestCase):
    """End-to-end coverage for rarely exercised ``_run_normal`` paths.

    These paths are hard to reach through the main happy-path tests
    because they rely on specific ``select`` / ``psutil`` orderings,
    but they are the runner's safety net in production and deserve
    explicit assertions.
    """

    PIPELINE_CMD = "videotestsrc ! gvafpscounter ! fakesink"

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
    def test_stderr_lines_are_captured_and_returned(
        self, mock_select, mock_ps, mock_popen
    ):
        """An stderr line must land in ``PipelineResult.stderr``.

        The main test suite always wires ``select`` to return stdout
        only; this one returns stderr so the ``elif r == process.stderr``
        branch in the stdout reader loop is executed.
        """
        process_mock = MagicMock()
        process_mock.pid = 1234
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        # First iteration: stderr has one line. Subsequent iterations:
        # nothing; poll then returns 0 to end the main loop.
        process_mock.stderr.readline.side_effect = itertools.chain(
            [b"boom on stderr\n"], itertools.repeat(b"")
        )
        process_mock.stdout.readline.return_value = b""
        process_mock.poll.side_effect = itertools.chain([None], itertools.repeat(0))
        process_mock.wait.return_value = 0
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b"", b"")
        mock_popen.return_value = process_mock

        mock_select.side_effect = itertools.chain(
            [([process_mock.stderr], [], [])], itertools.repeat(([], [], []))
        )
        # ps.Process must stay "running" until the main loop exits.
        mock_ps.Process.return_value.status.return_value = "running"

        runner = PipelineRunner(mode="normal", max_runtime=0)
        result = runner.run(pipeline_command=self.PIPELINE_CMD, total_streams=1)

        self.assertIn("boom on stderr", "\n".join(result.stderr))

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
    def test_zombie_detection_ends_loop(self, mock_select, mock_ps, mock_popen):
        """When ``ps`` reports the child as a zombie the runner breaks out
        and calls ``wait()`` to reap it, regardless of ``poll()``.
        """
        process_mock = MagicMock()
        process_mock.pid = 1234
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.stdout.readline.side_effect = itertools.chain(
            [b"some stdout line\n"], itertools.repeat(b"")
        )
        process_mock.stderr.readline.return_value = b""
        # First poll: still running (enters the loop). After the zombie
        # branch calls wait(), subsequent polls return the exit code so
        # the outer ``while`` terminates.
        process_mock.poll.side_effect = itertools.chain([None], itertools.repeat(0))
        process_mock.wait.return_value = 0
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b"", b"")
        mock_popen.return_value = process_mock

        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", max_runtime=0)
        result = runner.run(pipeline_command=self.PIPELINE_CMD, total_streams=1)

        self.assertIsInstance(result, PipelineResult)
        # wait() must have been called to reap the zombie.
        process_mock.wait.assert_called()

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen", new=MagicMock())
    def test_no_such_process_ends_loop(self, mock_select, mock_ps, mock_popen):
        """When ``psutil.Process`` raises ``NoSuchProcess`` the runner
        treats it as end-of-life: breaks out and calls ``wait()``.
        """
        process_mock = MagicMock()
        process_mock.pid = 1234
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.stdout.readline.side_effect = itertools.chain(
            [b"some stdout line\n"], itertools.repeat(b"")
        )
        process_mock.stderr.readline.return_value = b""
        # Same trick as the zombie test: first poll lets the runner
        # enter the loop, subsequent polls exit it.
        process_mock.poll.side_effect = itertools.chain([None], itertools.repeat(0))
        process_mock.wait.return_value = 0
        process_mock.returncode = 0
        process_mock.communicate.return_value = (b"", b"")
        mock_popen.return_value = process_mock

        mock_select.return_value = ([process_mock.stdout], [], [])
        # psutil raises NoSuchProcess(pid) — the runner must handle it.
        import psutil

        mock_ps.NoSuchProcess = psutil.NoSuchProcess
        mock_ps.Process.return_value.status.side_effect = psutil.NoSuchProcess(
            process_mock.pid
        )

        runner = PipelineRunner(mode="normal", max_runtime=0)
        result = runner.run(pipeline_command=self.PIPELINE_CMD, total_streams=1)

        self.assertIsInstance(result, PipelineResult)
        process_mock.wait.assert_called()


if __name__ == "__main__":
    unittest.main()
