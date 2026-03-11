"""
Unit tests for gst_runner.py (GStreamer Pipeline Runner).

These tests focus on the Python control flow and error handling, using
mocking to avoid depending on real GStreamer behavior where possible.
"""

import unittest
from typing import Any, Tuple
from unittest import mock

import gst_runner
from gi.repository import Gst as RealGst  # type: ignore[import]


class TestParseArgs(unittest.TestCase):
    """Tests for the parse_args helper."""

    def test_parse_args_basic(self) -> None:
        """parse_args should correctly parse mode, max-runtime, log-level and pipeline."""
        args = gst_runner.parse_args(
            [
                "--mode",
                "validation",
                "--max-runtime",
                "5",
                "--log-level",
                "DEBUG",
                "videotestsrc",
                "!",
                "fakesink",
            ]
        )

        self.assertEqual(args.mode, "validation")
        self.assertEqual(args.max_runtime, 5.0)
        self.assertEqual(args.log_level, "DEBUG")
        self.assertEqual(args.pipeline, ["videotestsrc", "!", "fakesink"])

    def test_parse_args_defaults(self) -> None:
        """parse_args should use correct default values when arguments are not provided."""
        args = gst_runner.parse_args(["videotestsrc", "!", "fakesink"])

        self.assertEqual(args.mode, "normal")
        self.assertEqual(args.max_runtime, 0.0)
        self.assertEqual(args.log_level, "INFO")


class TestValidateArguments(unittest.TestCase):
    """Tests for the validate_arguments helper."""

    def test_validate_arguments_normal_mode_positive_max_runtime(self) -> None:
        """validate_arguments should accept positive max-runtime in normal mode."""
        self.assertIsNone(gst_runner.validate_arguments("normal", 10.0))

    def test_validate_arguments_normal_mode_zero_max_runtime(self) -> None:
        """validate_arguments should accept zero max-runtime in normal mode."""
        self.assertIsNone(gst_runner.validate_arguments("normal", 0.0))

    def test_validate_arguments_normal_mode_negative_max_runtime(self) -> None:
        """validate_arguments should reject negative max-runtime in normal mode."""
        error = gst_runner.validate_arguments("normal", -1.0)
        self.assertIsNotNone(error)
        assert error is not None  # Type narrowing for assertIn
        self.assertIn("Negative values are not allowed", error)
        self.assertIn("multifilesrc loop=true", error)

    def test_validate_arguments_validation_mode_positive_max_runtime(self) -> None:
        """validate_arguments should accept positive max-runtime in validation mode."""
        self.assertIsNone(gst_runner.validate_arguments("validation", 10.0))

    def test_validate_arguments_validation_mode_zero_max_runtime(self) -> None:
        """validate_arguments should reject zero max-runtime in validation mode."""
        error = gst_runner.validate_arguments("validation", 0.0)
        self.assertIsNotNone(error)
        assert error is not None  # Type narrowing for assertIn
        self.assertIn("validation mode requires max-runtime > 0", error)

    def test_validate_arguments_validation_mode_negative_max_runtime(self) -> None:
        """validate_arguments should reject negative max-runtime in validation mode."""
        error = gst_runner.validate_arguments("validation", -1.0)
        self.assertIsNotNone(error)
        assert error is not None  # Type narrowing for assertIn
        self.assertIn("Negative values are not allowed", error)

    def test_validate_arguments_invalid_mode(self) -> None:
        """validate_arguments should reject invalid mode values."""
        error = gst_runner.validate_arguments("invalid_mode", 10.0)
        self.assertIsNotNone(error)
        assert error is not None  # Type narrowing for assertIn
        self.assertIn("Invalid mode 'invalid_mode'", error)


class TestParsePipeline(unittest.TestCase):
    """Tests for the parse_pipeline helper."""

    @mock.patch.object(gst_runner, "Gst")
    def test_parse_pipeline_failure(self, mock_gst: Any) -> None:
        """parse_pipeline should return (None, False) when Gst.parse_launch raises."""
        mock_gst.parse_launch.side_effect = RuntimeError("parse error")

        pipeline, ok = gst_runner.parse_pipeline("invalid pipeline ! element")

        self.assertIsNone(pipeline)
        self.assertFalse(ok)

    @mock.patch.object(gst_runner, "Gst")
    def test_parse_pipeline_success(self, mock_gst: Any) -> None:
        """parse_pipeline should return (pipeline, True) on success when no ERROR is logged."""
        fake_pipeline = object()
        mock_gst.parse_launch.return_value = fake_pipeline

        # Simulate add/remove of the temporary log handler used during parsing.
        mock_gst.debug_add_log_function.return_value = 123

        pipeline, ok = gst_runner.parse_pipeline("videotestsrc ! fakesink")

        self.assertIs(pipeline, fake_pipeline)
        self.assertTrue(ok)
        mock_gst.debug_add_log_function.assert_called_once()
        # The temporary parsing handler must be removed again afterward.
        mock_gst.debug_remove_log_function.assert_called_with(
            gst_runner._parse_log_collector
        )

    def test_parse_pipeline_failure_on_logged_error(self) -> None:
        """_parse_log_collector should mark error_seen when an ERROR log is observed."""
        state = gst_runner._ParseLogState()
        message = mock.Mock()
        message.get.return_value = "simulated parse error"

        gst_runner._parse_log_collector(
            category=mock.Mock(get_name=lambda: "SIMULATED"),
            level=RealGst.DebugLevel.ERROR,
            file=None,
            function=None,
            line=0,
            obj=None,
            message=message,
            state=state,
        )

        self.assertTrue(
            state.error_seen,
            "Parse log collector should mark error_seen when ERROR is logged.",
        )


class TestRunPipeline(unittest.TestCase):
    """Tests for the run_pipeline high-level helper."""

    def test_run_pipeline_failure_on_parse(self) -> None:
        """run_pipeline should return False if parsing fails."""

        def fake_parse_pipeline(_desc: str) -> Tuple[None, bool]:
            return None, False

        with mock.patch.object(gst_runner, "parse_pipeline", fake_parse_pipeline):
            self.assertFalse(
                gst_runner.run_pipeline(
                    "invalid pipeline", max_run_time_sec=1.0, mode="normal"
                )
            )

    def test_run_pipeline_success_on_eos(self) -> None:
        """run_pipeline should return True if parse and run both succeed (e.g. via EOS)."""
        fake_pipeline = object()

        def fake_parse_pipeline(_desc: str):
            return fake_pipeline, True

        def fake_run_pipeline_for_duration(pipeline, max_run_time_sec, mode):
            self.assertIs(pipeline, fake_pipeline)
            self.assertEqual(max_run_time_sec, 2.0)
            self.assertEqual(mode, "validation")
            # True, None -> success via EOS or clean completion before max-runtime.
            return True, None

        with (
            mock.patch.object(gst_runner, "parse_pipeline", fake_parse_pipeline),
            mock.patch.object(
                gst_runner,
                "run_pipeline_for_duration",
                fake_run_pipeline_for_duration,
            ),
        ):
            self.assertTrue(
                gst_runner.run_pipeline(
                    "videotestsrc ! fakesink", max_run_time_sec=2.0, mode="validation"
                )
            )

    def test_run_pipeline_success_on_max_runtime(self) -> None:
        """Max-runtime should be treated as SUCCESS by run_pipeline when no errors occur."""
        fake_pipeline = object()

        def fake_parse_pipeline(_desc: str):
            return fake_pipeline, True

        def fake_run_pipeline_for_duration(pipeline, max_run_time_sec, mode):
            self.assertIs(pipeline, fake_pipeline)
            self.assertEqual(mode, "normal")
            # True, "max_runtime" -> success via max-runtime (no error observed).
            return True, "max_runtime"

        with (
            mock.patch.object(gst_runner, "parse_pipeline", fake_parse_pipeline),
            mock.patch.object(
                gst_runner,
                "run_pipeline_for_duration",
                fake_run_pipeline_for_duration,
            ),
        ):
            self.assertTrue(
                gst_runner.run_pipeline(
                    "videotestsrc ! fakesink", max_run_time_sec=1.0, mode="normal"
                )
            )

    def test_run_pipeline_failure_on_run_error(self) -> None:
        """run_pipeline should return False if run_pipeline_for_duration fails."""
        fake_pipeline = object()

        def fake_parse_pipeline(_desc: str):
            return fake_pipeline, True

        def fake_run_pipeline_for_duration(pipeline, max_run_time_sec, mode):
            self.assertIs(pipeline, fake_pipeline)
            # False, "error" -> runtime error was observed.
            return False, "error"

        with (
            mock.patch.object(gst_runner, "parse_pipeline", fake_parse_pipeline),
            mock.patch.object(
                gst_runner,
                "run_pipeline_for_duration",
                fake_run_pipeline_for_duration,
            ),
        ):
            self.assertFalse(
                gst_runner.run_pipeline(
                    "videotestsrc ! fakesink", max_run_time_sec=1.0, mode="normal"
                )
            )


class TestRunState(unittest.TestCase):
    """Tests for the _RunState dataclass."""

    def test_run_state_defaults(self) -> None:
        """_RunState should have correct default values."""
        state = gst_runner._RunState()
        self.assertFalse(state.error_seen)
        self.assertFalse(state.eos_seen)
        self.assertFalse(state.max_runtime_triggered)
        self.assertFalse(state.shutdown_in_progress)
        self.assertIsNone(state.reason)

    def test_run_state_shutdown_in_progress(self) -> None:
        """_RunState should track shutdown_in_progress flag."""
        state = gst_runner._RunState()
        state.shutdown_in_progress = True
        self.assertTrue(state.shutdown_in_progress)


class TestPipelineRunner(unittest.TestCase):
    """Tests for the internal _PipelineRunner helper."""

    def test_pipeline_runner_handles_bus_error(self) -> None:
        """_PipelineRunner.run should fail when an ERROR message is seen on the bus."""
        # Create a fake pipeline that passes isinstance(..., Gst.Pipeline).
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus

        # Prepare a fake ERROR message for drain_bus_messages after the loop.
        fake_error_message = mock.Mock()
        fake_error_message.type = gst_runner.Gst.MessageType.ERROR

        # parse_error() must return a (error, debug) tuple like real GStreamer.
        fake_error = mock.Mock()
        fake_error.message = "simulated-runtime-error"
        fake_error_message.parse_error.return_value = (fake_error, "debug-info")

        # pop() returns one ERROR, then None.
        fake_bus.pop.side_effect = [fake_error_message, None]

        # get_state should eventually succeed; the exact values are not important here.
        fake_pipeline.get_state.return_value = (
            gst_runner.Gst.StateChangeReturn.SUCCESS,
            gst_runner.Gst.State.PLAYING,
            gst_runner.Gst.State.VOID_PENDING,
        )

        # We do not actually want to run a real GLib.MainLoop in tests; instead,
        # we patch it so that loop.run() returns immediately.
        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop

            mock_loop.run.side_effect = lambda: None

            runner = gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="validation"
            )
            ok, reason = runner.run()

        self.assertFalse(ok)
        self.assertEqual(reason, "error")

    def test_pipeline_runner_ignores_errors_during_shutdown(self) -> None:
        """_PipelineRunner should ignore errors when shutdown_in_progress is True."""
        # Create a fake pipeline that passes isinstance(..., Gst.Pipeline).
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus

        # No messages on the bus initially
        fake_bus.pop.return_value = None

        # get_state should eventually succeed
        fake_pipeline.get_state.return_value = (
            gst_runner.Gst.StateChangeReturn.SUCCESS,
            gst_runner.Gst.State.PLAYING,
            gst_runner.Gst.State.VOID_PENDING,
        )

        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop
            mock_loop.run.side_effect = lambda: None

            runner = gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="validation"
            )

            # Manually set shutdown_in_progress to True
            runner._state.shutdown_in_progress = True

            # Create a fake ERROR message
            fake_error_message = mock.Mock()
            fake_error_message.type = gst_runner.Gst.MessageType.ERROR
            fake_error = mock.Mock()
            fake_error.message = "simulated-shutdown-error"
            fake_error_message.parse_error.return_value = (fake_error, "debug-info")

            # Call the bus message handler directly
            result = runner._on_bus_message(fake_bus, fake_error_message, mock_loop)

            # Should return True (continue processing) and NOT mark error_seen
            self.assertTrue(result)
            self.assertFalse(runner._state.error_seen)

    def test_pipeline_runner_records_error_when_not_shutting_down(self) -> None:
        """_PipelineRunner should record errors when shutdown_in_progress is False."""
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus
        fake_bus.pop.return_value = None

        fake_pipeline.get_state.return_value = (
            gst_runner.Gst.StateChangeReturn.SUCCESS,
            gst_runner.Gst.State.PLAYING,
            gst_runner.Gst.State.VOID_PENDING,
        )

        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop
            mock_loop.run.side_effect = lambda: None

            runner = gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="validation"
            )

            # shutdown_in_progress is False by default
            self.assertFalse(runner._state.shutdown_in_progress)

            # Create a fake ERROR message
            fake_error_message = mock.Mock()
            fake_error_message.type = gst_runner.Gst.MessageType.ERROR
            fake_error = mock.Mock()
            fake_error.message = "simulated-runtime-error"
            fake_error_message.parse_error.return_value = (fake_error, "debug-info")

            # Call the bus message handler directly
            runner._on_bus_message(fake_bus, fake_error_message, mock_loop)

            # Should mark error_seen and quit the loop
            self.assertTrue(runner._state.error_seen)
            self.assertEqual(runner._state.reason, "error")
            mock_loop.quit.assert_called_once()

    def test_max_runtime_sets_shutdown_in_progress(self) -> None:
        """_max_runtime_enforcement_thread should set shutdown_in_progress before stopping."""
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus

        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop

            # Mock Gst.Event methods to avoid GStreamer initialization requirement
            with mock.patch.object(gst_runner.Gst, "Event") as mock_event:
                mock_event.new_flush_start.return_value = mock.Mock()
                mock_event.new_flush_stop.return_value = mock.Mock()
                mock_event.new_eos.return_value = mock.Mock()

                runner = gst_runner._PipelineRunner(
                    fake_pipeline, max_run_time_sec=0.001, mode="normal"
                )

                # Mock time.sleep to avoid actual waiting
                with mock.patch.object(gst_runner.time, "sleep"):
                    runner._max_runtime_enforcement_thread(mock_loop)

            # Verify shutdown_in_progress was set
            self.assertTrue(runner._state.shutdown_in_progress)
            self.assertTrue(runner._state.max_runtime_triggered)
            self.assertEqual(runner._state.reason, "max_runtime")


class TestMain(unittest.TestCase):
    """Tests for the main CLI entry point using dependency injection.

    We test run_application(), which lets us inject fake
    initialize_gst_fn and run_fn implementations. This way we can
    fully exercise main's control flow without requiring a real GStreamer
    installation in the unit test environment.
    """

    def test_main_success(self) -> None:
        """run_application should return 0 when pipeline run succeeds."""

        def fake_initialize_gst() -> None:
            # No-op: pretend GStreamer initialized successfully.
            return None

        def fake_run(
            pipeline_description: str, max_run_time_sec: float, mode: str
        ) -> bool:
            # We can assert that arguments are passed correctly if we want.
            self.assertIn("videotestsrc", pipeline_description)
            self.assertEqual(max_run_time_sec, 3.0)
            self.assertEqual(mode, "normal")
            return True

        exit_code = gst_runner.run_application(
            argv=[
                "--max-runtime",
                "3",
                "--log-level",
                "INFO",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 0)

    def test_main_success_with_validation_mode(self) -> None:
        """run_application should pass mode argument correctly to run function."""

        def fake_initialize_gst() -> None:
            return None

        def fake_run(
            pipeline_description: str, max_run_time_sec: float, mode: str
        ) -> bool:
            self.assertEqual(mode, "validation")
            self.assertEqual(max_run_time_sec, 5.0)
            return True

        exit_code = gst_runner.run_application(
            argv=[
                "--mode",
                "validation",
                "--max-runtime",
                "5",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 0)

    def test_main_failure(self) -> None:
        """run_application should return 1 when pipeline run fails."""

        def fake_initialize_gst() -> None:
            return None

        def fake_run(_desc: str, _max_run_time_sec: float, _mode: str) -> bool:
            return False

        exit_code = gst_runner.run_application(
            argv=[
                "--max-runtime",
                "3",
                "--log-level",
                "INFO",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 1)

    def test_main_failure_on_invalid_mode_combination(self) -> None:
        """run_application should return 1 when mode and max-runtime combination is invalid."""

        def fake_initialize_gst() -> None:
            return None

        def fake_run(_desc: str, _max_run_time_sec: float, _mode: str) -> bool:
            # Should not be called due to validation error.
            self.fail("run_fn should not be called with invalid arguments")
            return False

        # validation mode with max-runtime == 0 is invalid.
        exit_code = gst_runner.run_application(
            argv=[
                "--mode",
                "validation",
                "--max-runtime",
                "0",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 1)

    def test_main_failure_on_negative_max_runtime(self) -> None:
        """run_application should return 1 when max-runtime is negative."""

        def fake_initialize_gst() -> None:
            return None

        def fake_run(_desc: str, _max_run_time_sec: float, _mode: str) -> bool:
            # Should not be called due to validation error.
            self.fail("run_fn should not be called with invalid arguments")
            return False

        # Negative max-runtime is invalid.
        exit_code = gst_runner.run_application(
            argv=[
                "--mode",
                "normal",
                "--max-runtime",
                "-1",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 1)

    def test_main_internal_error(self) -> None:
        """run_application should return 1 when run_fn raises."""

        def fake_initialize_gst() -> None:
            return None

        def fake_run(_desc: str, _max_run_time_sec: float, _mode: str) -> bool:
            raise RuntimeError("unexpected")

        exit_code = gst_runner.run_application(
            argv=[
                "--max-runtime",
                "3",
                "--log-level",
                "INFO",
                "videotestsrc",
                "!",
                "fakesink",
            ],
            initialize_gst_fn=fake_initialize_gst,
            run_fn=fake_run,
        )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
