import itertools
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

from pipeline_runner import (
    PipelineRunner,
    PipelineRunResult,
    PipelineValidationResult,
)


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
        expected_result = PipelineRunResult(
            total_fps=100.0, per_stream_fps=100.0, num_streams=1
        )

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        # Avoid StopIteration by returning empty bytes forever after the real line
        process_mock.stdout.readline.side_effect = itertools.chain(
            [
                f"FpsCounter(average 10.0sec): total={expected_result.total_fps} fps, number-streams={expected_result.num_streams}, per-stream={expected_result.per_stream_fps} fps\n".encode(
                    "utf-8"
                )
            ],
            itertools.repeat(b""),
        )
        process_mock.pid = 1234
        # Ensure fileno returns an int to avoid TypeError in select and bad fd errors
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.wait.return_value = 0
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
        self.assertEqual(cmd[6], self.test_pipeline_command)

        # Verify FPS extraction with type narrowing
        assert isinstance(result, PipelineRunResult)  # Type narrowing
        self.assertEqual(result.total_fps, expected_result.total_fps)
        self.assertEqual(result.per_stream_fps, expected_result.per_stream_fps)
        self.assertEqual(result.num_streams, expected_result.num_streams)

    @patch("pipeline_runner.Popen")
    def test_stop_pipeline_normal_mode(self, mock_popen):
        """PipelineRunner in normal mode should handle cancellation correctly."""
        expected_result = PipelineRunResult(
            total_fps=0, per_stream_fps=0, num_streams=0
        )

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None]
        process_mock.wait.return_value = -1
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="normal", max_runtime=0)
        runner.cancel()
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        self.assertTrue(runner.is_cancelled())
        self.assertIsInstance(result, PipelineRunResult)
        # Type narrowing for accessing PipelineRunResult attributes
        assert isinstance(result, PipelineRunResult)
        self.assertEqual(result.total_fps, expected_result.total_fps)
        self.assertEqual(result.per_stream_fps, expected_result.per_stream_fps)
        self.assertEqual(result.num_streams, expected_result.num_streams)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    def test_pipeline_hang_raises_runtime_error(self, mock_select, mock_popen):
        """PipelineRunner in normal mode should raise RuntimeError on inactivity timeout."""
        runner = PipelineRunner(
            mode="normal",
            max_runtime=0,
            poll_interval=1,
            fps_file_path="/tmp/fps.txt",
            inactivity_timeout=0,
        )

        process_mock = MagicMock()
        # Process keeps running (poll() always returns None).
        process_mock.poll.return_value = None
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
    @patch("builtins.open", new_callable=mock_open)
    def test_run_pipeline_writes_zero_fps_on_completion(
        self, mock_open_file, mock_select, mock_ps, mock_popen
    ):
        """PipelineRunner should write 0.0 to FPS file after successful completion."""
        expected_result = PipelineRunResult(
            total_fps=100.0, per_stream_fps=100.0, num_streams=1
        )

        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        process_mock.stdout.readline.side_effect = itertools.chain(
            [
                f"FpsCounter(average 10.0sec): total={expected_result.total_fps} fps, number-streams={expected_result.num_streams}, per-stream={expected_result.per_stream_fps} fps\n".encode(
                    "utf-8"
                )
            ],
            itertools.repeat(b""),
        )
        process_mock.pid = 1234
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.wait.return_value = 0
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        if mock_ps is not None:
            mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner(
            mode="normal", max_runtime=0, fps_file_path="/tmp/test_fps.txt"
        )
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        # Verify result
        self.assertIsInstance(result, PipelineRunResult)
        assert isinstance(result, PipelineRunResult)
        self.assertEqual(result.total_fps, expected_result.total_fps)

        # Verify that current FPS (100.0) was written during execution
        # and 0.0 was written at the end (in finally block)
        write_calls = mock_open_file().write.call_args_list
        fps_writes = [call[0][0] for call in write_calls]

        # Should have written the current FPS during execution
        self.assertIn(
            "100.0\n", fps_writes, "Current FPS should be written during execution"
        )

        # Should have written 0.0 at the end
        self.assertIn("0.0\n", fps_writes, "0.0 should be written after completion")

        # Last write should be 0.0 (from finally block)
        self.assertEqual(fps_writes[-1], "0.0\n", "Last FPS write should be 0.0")

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    @patch("builtins.open", new_callable=mock_open)
    def test_run_pipeline_writes_zero_fps_on_error(
        self, mock_open_file, mock_select, mock_popen
    ):
        """PipelineRunner should write 0.0 to FPS file after pipeline failure."""
        process_mock = MagicMock()
        # First poll returns None (running), second poll returns 1 (exit code)
        process_mock.poll.side_effect = [None, 1]
        process_mock.stdout.readline.side_effect = itertools.repeat(b"")
        process_mock.stderr.readline.side_effect = itertools.repeat(b"")
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.wait.return_value = 1  # Non-zero exit code
        # Return empty lists for select to indicate no data available
        mock_select.return_value = ([], [], [])
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="normal", max_runtime=0, fps_file_path="/tmp/test_fps.txt"
        )

        with self.assertRaises(RuntimeError):
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        # Verify that 0.0 was written to FPS file (in finally block) even on error
        write_calls = [
            call
            for call in mock_open_file().write.call_args_list
            if call[0][0] == "0.0\n"
        ]
        self.assertEqual(
            len(write_calls),
            1,
            "0.0 should be written exactly once to FPS file after pipeline error",
        )

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.select.select")
    @patch("builtins.open", new_callable=mock_open)
    def test_pipeline_hang_writes_zero_fps_before_raising(
        self, mock_open_file, mock_select, mock_popen
    ):
        """PipelineRunner should write 0.0 to FPS file when raising inactivity timeout error."""
        runner = PipelineRunner(
            mode="normal",
            max_runtime=0,
            poll_interval=1,
            fps_file_path="/tmp/test_fps.txt",
            inactivity_timeout=0,
        )

        process_mock = MagicMock()
        process_mock.poll.return_value = None
        process_mock.stdout = MagicMock()
        process_mock.stderr = MagicMock()
        mock_select.return_value = ([], [], [])
        process_mock.wait.return_value = 0
        mock_popen.return_value = process_mock

        with self.assertRaises(RuntimeError) as ctx:
            runner.run(pipeline_command=self.test_pipeline_command, total_streams=1)

        self.assertIn("inactivity timeout", str(ctx.exception))

        # Verify that 0.0 was written to FPS file (in finally block)
        write_calls = [
            call
            for call in mock_open_file().write.call_args_list
            if call[0][0] == "0.0\n"
        ]
        self.assertEqual(
            len(write_calls),
            1,
            "0.0 should be written exactly once to FPS file after timeout error",
        )

    @patch("pipeline_runner.Popen")
    @patch("builtins.open", new_callable=mock_open)
    def test_stop_pipeline_writes_zero_fps(self, mock_open_file, mock_popen):
        """PipelineRunner should write 0.0 to FPS file when cancelled."""
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None]
        process_mock.wait.return_value = -1
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        mock_popen.return_value = process_mock

        runner = PipelineRunner(
            mode="normal", max_runtime=0, fps_file_path="/tmp/test_fps.txt"
        )
        runner.cancel()
        result = runner.run(
            pipeline_command=self.test_pipeline_command, total_streams=1
        )

        self.assertTrue(runner.is_cancelled())
        self.assertIsInstance(result, PipelineRunResult)

        # Verify that 0.0 was written to FPS file (in finally block) after cancellation
        write_calls = [
            call
            for call in mock_open_file().write.call_args_list
            if call[0][0] == "0.0\n"
        ]
        self.assertEqual(
            len(write_calls),
            1,
            "0.0 should be written exactly once to FPS file after cancellation",
        )


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
        """PipelineRunner in validation mode should return valid result on success."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = (
            "gst_runner - INFO - Pipeline parsed successfully.\n",
            "",  # No errors in stderr
        )
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineValidationResult)
        # Type narrowing for accessing PipelineValidationResult attributes
        assert isinstance(result, PipelineValidationResult)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    @patch("pipeline_runner.subprocess.Popen")
    def test_run_validation_failure(self, mock_popen):
        """PipelineRunner in validation mode should return invalid result with errors."""
        process_mock = MagicMock()
        process_mock.communicate.return_value = (
            "",
            "gst_runner - ERROR - no element foo\ngst_runner - ERROR - some other error\n",
        )
        process_mock.returncode = 1
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineValidationResult)
        # Type narrowing for accessing PipelineValidationResult attributes
        assert isinstance(result, PipelineValidationResult)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors, ["no element foo", "some other error"])

    @patch("pipeline_runner.subprocess.Popen")
    def test_run_validation_timeout(self, mock_popen):
        """PipelineRunner in validation mode should handle timeout gracefully."""
        process_mock = MagicMock()
        process_mock.communicate.side_effect = [
            __import__("subprocess").TimeoutExpired("gst_runner.py", 70)
        ]
        process_mock.communicate.side_effect = lambda timeout: (
            (_ for _ in ()).throw(
                __import__("subprocess").TimeoutExpired("gst_runner.py", timeout)
            )
            if timeout
            else ("", "")
        )

        # After kill, second communicate returns empty
        def communicate_with_timeout(timeout=None):
            if timeout:
                raise __import__("subprocess").TimeoutExpired("gst_runner.py", timeout)
            return ("", "")

        process_mock.communicate = communicate_with_timeout
        process_mock.returncode = -9
        mock_popen.return_value = process_mock

        runner = PipelineRunner(mode="validation", max_runtime=10)
        result = runner.run(self.test_pipeline_command)

        self.assertIsInstance(result, PipelineValidationResult)
        # Type narrowing for accessing PipelineValidationResult attributes
        assert isinstance(result, PipelineValidationResult)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("timed out" in err for err in result.errors))

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


if __name__ == "__main__":
    unittest.main()
