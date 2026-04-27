import itertools
import json
import signal
import sys
import unittest
from unittest.mock import MagicMock, patch

from pipeline_runner import (
    PipelineRunner,
    PipelineResult,
)


def _extract_pushed_fps_values(mock_urlopen: MagicMock) -> list[float]:
    """Extract the `value` field from every JSON payload sent via urlopen.

    Used by tests that verify FPS metrics are pushed to metrics-service
    through `PipelineRunner._push_fps_metric` (which calls
    `urllib.request.urlopen` with a JSON body of the form
    `{"name": "fps", "value": <float>}`).
    """
    values: list[float] = []
    for call in mock_urlopen.call_args_list:
        req = call[0][0]
        payload = json.loads(req.data.decode())
        values.append(payload["value"])
    return values


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


class TestPipelineRunnerNormalMode(unittest.TestCase):
    """Tests for PipelineRunner in normal mode (production pipeline execution)."""

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
        """PipelineRunner should push 0.0 to metrics-service after successful completion."""
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

        # Every request targets the metrics-service `/api/v1/metrics/simple` endpoint.
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
        """PipelineRunner should push 0.0 to metrics-service after pipeline failure."""
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
            "0.0 should be pushed exactly once to metrics-service after pipeline error",
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_pipeline_hang_pushes_zero_fps_before_raising(
        self, mock_urlopen, mock_select, mock_popen
    ):
        """PipelineRunner should push 0.0 to metrics-service when raising inactivity timeout error."""
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
            "0.0 should be pushed exactly once to metrics-service after timeout error",
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.urllib.request.urlopen")
    def test_stop_pipeline_pushes_zero_fps(self, mock_urlopen, mock_popen):
        """PipelineRunner should push 0.0 to metrics-service when cancelled."""
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
            "0.0 should be pushed exactly once to metrics-service after cancellation",
        )

    @patch("pipeline_runner.urllib.request.urlopen")
    def test_push_fps_metric_uses_configured_url(self, mock_urlopen):
        """`_push_fps_metric` must POST JSON to `{METRICS_SERVICE_URL}/api/v1/metrics/simple`."""
        with patch.dict(
            "os.environ", {"METRICS_SERVICE_URL": "http://example:1234"}, clear=False
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
            any("Failed to push FPS metric" in line for line in captured.output)
        )


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
        """Shared assertions for an env dict built with the flag enabled."""
        self.assertIn("GST_DEBUG", env)
        self.assertIn("GST_TRACER:7", env["GST_DEBUG"])
        self.assertEqual(
            env["GST_TRACERS"],
            "latency_tracer(flags=pipeline,interval=1000)",
        )

    # --- Pure _build_subprocess_env unit tests --------------------------------

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_disabled_leaves_tracer_vars_unset(self):
        """With the flag False the env must not contain GST_DEBUG/GST_TRACERS."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=False)
        env = runner._build_subprocess_env()
        self.assertNotIn("GST_DEBUG", env)
        self.assertNotIn("GST_TRACERS", env)

    @patch.dict("os.environ", {}, clear=True)
    def test_build_env_enabled_sets_tracer_vars_when_gst_debug_unset(self):
        """With the flag True and no pre-existing GST_DEBUG, both vars are set."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "GST_TRACER:7")
        self._assert_tracer_env_applied(env)

    @patch.dict("os.environ", {"GST_DEBUG": "2,GST_ELEMENT_PADS:5"}, clear=True)
    def test_build_env_enabled_appends_to_existing_gst_debug(self):
        """Existing GST_DEBUG must be extended with `,GST_TRACER:7`, not overwritten."""
        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)
        env = runner._build_subprocess_env()
        self.assertEqual(env["GST_DEBUG"], "2,GST_ELEMENT_PADS:5,GST_TRACER:7")
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

    # --- latency_tracer sample line from gst_runner is forwarded to INFO ---

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    @patch.dict("os.environ", {}, clear=True)
    def test_latency_tracer_interval_line_forwarded_from_gst_runner_stdout(
        self, mock_select, mock_ps, mock_popen
    ):
        """`gst_runner - INFO - latency_tracer_pipeline_interval,...` stdout lines must be forwarded to INFO log.

        In production the subprocess's ``gst_log_bridge`` promotes tracer
        samples to INFO level, which Python logging prints to stdout as
        ``gst_runner - INFO - latency_tracer_pipeline_interval, ...``.
        The parent PipelineRunner then picks them up through
        ``_is_loggable_gst_runner_line`` and logs them as INFO.
        """
        sample_line = (
            "gst_runner - INFO - latency_tracer_pipeline_interval, "
            "pipeline_name=(string)pipeline0, source_name=(string)filesrc0, "
            "sink_name=(string)default_output_sink_0_0, interval=(double)1000.0, "
            "avg=(double)5.0, min=(double)1.0, max=(double)9.0, "
            "latency=(double)3.0, fps=(double)60.0"
        )
        process_mock = _make_process_mock([sample_line])
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(mode="normal", enable_latency_metrics=True)

        with self.assertLogs("PipelineRunner", level="INFO") as captured:
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        joined = "\n".join(captured.output)
        self.assertIn("latency_tracer_pipeline_interval", joined)


class TestLatencyTracerIntervalParser(unittest.TestCase):
    """Unit tests for the `latency_tracer_pipeline_interval` line parser.

    The parser lives on :class:`PipelineRunner` as
    ``_parse_and_record_latency_sample`` and is driven by the
    class-level compiled regex ``_LATENCY_TRACER_INTERVAL_PATTERN``.
    These tests exercise the parser directly (no subprocess) so we can
    assert the exact shape of the resulting
    :class:`InternalLatencyMetrics` entries.

    Sample lines follow the format documented in
    ``/docs/user-guide/dev_guide/latency_tracer.md`` in the DLStreamer
    repository.
    """

    # Sample line taken from the DLStreamer `latency_tracer` documentation.
    SAMPLE_INTERVAL_LINE = (
        "latency_tracer_pipeline_interval, "
        "pipeline_name=(string)pipeline0, "
        "source_name=(string)src_p0_s0_0_0, "
        "sink_name=(string)sink_p0_s0_0_0, "
        "interval=(double)1000.25, "
        "avg=(double)364.31, "
        "min=(double)0.004, "
        "max=(double)529.26, "
        "latency=(double)21.28, "
        "fps=(double)46.99;"
    )

    # Same payload as seen on our subprocess stdout — prefixed with the
    # Python log format emitted by `gst_runner`.
    SAMPLE_INTERVAL_LINE_WITH_PREFIX = "gst_runner - INFO - " + SAMPLE_INTERVAL_LINE

    def _make_runner(self, enable: bool) -> PipelineRunner:
        """Return a PipelineRunner configured for parser testing.

        Args:
            enable: Value of ``enable_latency_metrics``. When False the
                runner keeps ``latency_tracer_metrics=None`` and the
                parser is expected to short-circuit.
        """
        return PipelineRunner(mode="normal", enable_latency_metrics=enable)

    def test_parser_extracts_all_five_fields(self):
        """All five timing fields are extracted as floats from a sample line."""
        runner = self._make_runner(enable=True)
        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE)

        self.assertIsNotNone(runner.latency_tracer_metrics)
        assert runner.latency_tracer_metrics is not None  # for the type-checker
        self.assertEqual(len(runner.latency_tracer_metrics), 1)

        stream_id = "src_p0_s0_0_0__sink_p0_s0_0_0"
        self.assertIn(stream_id, runner.latency_tracer_metrics)
        metrics = runner.latency_tracer_metrics[stream_id]

        # Exact values, rounded to the tracer's emitted precision.
        self.assertAlmostEqual(metrics.interval_ms, 1000.25)
        self.assertAlmostEqual(metrics.avg_ms, 364.31)
        self.assertAlmostEqual(metrics.min_ms, 0.004)
        self.assertAlmostEqual(metrics.max_ms, 529.26)
        self.assertAlmostEqual(metrics.latency_ms, 21.28)

    def test_parser_accepts_gst_runner_prefix(self):
        """Any log prefix before the marker is ignored by the parser."""
        runner = self._make_runner(enable=True)
        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE_WITH_PREFIX)

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(len(runner.latency_tracer_metrics), 1)

    def test_parser_ignores_non_interval_lines(self):
        """Lines that don't contain the interval marker produce no update."""
        runner = self._make_runner(enable=True)

        runner._parse_and_record_latency_sample(
            "FpsCounter(average 5.0sec): total=120.0 fps, "
            "number-streams=2, per-stream=60.0 fps"
        )
        runner._parse_and_record_latency_sample(
            "latency_tracer_pipeline, frame_latency=(double)704.90, "
            "avg=(double)238.75, min=(double)0.013, max=(double)704.90, "
            "latency=(double)32.28, fps=(double)30.98, frame_num=(uint)27;"
        )
        runner._parse_and_record_latency_sample("some unrelated stderr line")

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_ignores_malformed_interval_lines(self):
        """Lines with the marker but a broken field layout are dropped silently."""
        runner = self._make_runner(enable=True)

        # Truncated after `source_name`: `sink_name` and the rest missing.
        runner._parse_and_record_latency_sample(
            "latency_tracer_pipeline_interval, source_name=(string)src_p0_s0"
        )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(runner.latency_tracer_metrics, {})

    def test_parser_keeps_only_last_sample_per_stream(self):
        """Successive samples for the same stream_id overwrite the entry."""
        runner = self._make_runner(enable=True)

        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE)

        second_line = (
            "latency_tracer_pipeline_interval, "
            "source_name=(string)src_p0_s0_0_0, "
            "sink_name=(string)sink_p0_s0_0_0, "
            "interval=(double)2000.50, avg=(double)400.00, "
            "min=(double)0.010, max=(double)600.00, "
            "latency=(double)25.00, fps=(double)48.00"
        )
        runner._parse_and_record_latency_sample(second_line)

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(len(runner.latency_tracer_metrics), 1)
        metrics = runner.latency_tracer_metrics["src_p0_s0_0_0__sink_p0_s0_0_0"]
        # Only the latest values are retained — no history.
        self.assertAlmostEqual(metrics.interval_ms, 2000.50)
        self.assertAlmostEqual(metrics.avg_ms, 400.00)

    def test_parser_separates_streams_by_source_sink_pair(self):
        """Different source/sink pairs produce distinct map entries."""
        runner = self._make_runner(enable=True)

        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE)
        runner._parse_and_record_latency_sample(
            "latency_tracer_pipeline_interval, "
            "source_name=(string)src_p0_s1_0_1, "
            "sink_name=(string)sink_p0_s1_0_1, "
            "interval=(double)1000.00, avg=(double)100.0, "
            "min=(double)1.0, max=(double)200.0, "
            "latency=(double)10.0, fps=(double)30.0"
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

        # Calling the parser must not crash and must not allocate the map.
        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE)

        self.assertIsNone(runner.latency_tracer_metrics)

    def test_parser_drops_samples_outside_allowed_stream_ids(self):
        """
        Samples whose stream_id is not in ``_allowed_stream_ids`` are
        silently discarded. This models the production filter applied
        by ``PipelineRunner.run(allowed_stream_ids=...)`` that keeps
        only user-facing source/sink pairs (dropping internal bin
        sinks and intermediate ``splitmuxsink`` rows).
        """
        runner = self._make_runner(enable=True)
        # Only accept the "real" main source/sink pair for stream 0.
        runner._allowed_stream_ids = {"src_p0_s0_0_0__sink_p0_s0_0_0"}

        # Allowed: appears verbatim in the allowlist.
        runner._parse_and_record_latency_sample(self.SAMPLE_INTERVAL_LINE)

        # Disallowed: an internal bin sink named just "sink".
        runner._parse_and_record_latency_sample(
            "latency_tracer_pipeline_interval, "
            "source_name=(string)src_p0_s0_0_0, "
            "sink_name=(string)sink, "
            "interval=(double)1000.0, avg=(double)1.0, "
            "min=(double)1.0, max=(double)1.0, "
            "latency=(double)1.0, fps=(double)30.0"
        )
        # Disallowed: the recorder's splitmuxsink.
        runner._parse_and_record_latency_sample(
            "latency_tracer_pipeline_interval, "
            "source_name=(string)src_p0_s0_0_0, "
            "sink_name=(string)splitmuxsink0, "
            "interval=(double)1000.0, avg=(double)1.0, "
            "min=(double)1.0, max=(double)1.0, "
            "latency=(double)1.0, fps=(double)30.0"
        )

        assert runner.latency_tracer_metrics is not None
        self.assertEqual(
            set(runner.latency_tracer_metrics.keys()),
            {"src_p0_s0_0_0__sink_p0_s0_0_0"},
        )


if __name__ == "__main__":
    unittest.main()
