"""
Unit tests for gst_runner.py (GStreamer Pipeline Runner).

These tests focus on the Python control flow and error handling, using
mocking to avoid depending on real GStreamer behavior where possible.
"""

import json
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

    def test_pipeline_runner_sigint_during_get_state_returns_early(self) -> None:
        """SIGINT (KeyboardInterrupt) during the initial get_state() call should
        skip the main loop entirely, clean up immediately, and report success.
        """
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus
        fake_bus.pop.return_value = None

        # Simulate SIGINT interrupting the blocking get_state() call.
        fake_pipeline.get_state.side_effect = KeyboardInterrupt

        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop

            runner = gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="normal"
            )
            ok, reason = runner.run()

        self.assertTrue(ok)
        self.assertIsNone(reason)
        # The main loop must never be entered.
        mock_loop.run.assert_not_called()
        # _cleanup() must still transition the pipeline to NULL.
        fake_pipeline.set_state.assert_any_call(gst_runner.Gst.State.NULL)
        self.assertTrue(runner._state.shutdown_in_progress)
        self.assertEqual(runner._state.reason, "sigint")

    def test_pipeline_runner_sigint_early_exit_still_detects_bus_error(self) -> None:
        """The early-exit path (SIGINT during get_state()) must still observe
        an ERROR posted on the bus while _cleanup() transitions the pipeline
        to NULL, instead of unconditionally reporting success.
        """
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()
        fake_pipeline.get_bus.return_value = fake_bus

        fake_error_message = mock.Mock()
        fake_error_message.type = gst_runner.Gst.MessageType.ERROR
        fake_error = mock.Mock()
        fake_error.message = "simulated-teardown-error"
        fake_error_message.parse_error.return_value = (fake_error, "debug-info")

        # One ERROR message is sitting on the bus when _finalize() drains it,
        # simulating an error posted while set_state(NULL) ran in _cleanup().
        fake_bus.pop.side_effect = [fake_error_message, None]

        fake_pipeline.get_state.side_effect = KeyboardInterrupt

        with mock.patch.object(gst_runner, "GLib") as mock_glib:
            mock_loop = mock.Mock()
            mock_glib.MainLoop.return_value = mock_loop

            runner = gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="normal"
            )
            ok, reason = runner.run()

        self.assertFalse(ok)
        self.assertEqual(reason, "error")
        mock_loop.run.assert_not_called()

    def test_finalize_reports_error_drained_from_bus(self) -> None:
        """_finalize should surface an ERROR message drained from the bus even
        if no error had previously been recorded on _RunState.
        """
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        fake_bus = mock.Mock()

        fake_error_message = mock.Mock()
        fake_error_message.type = gst_runner.Gst.MessageType.ERROR
        fake_error = mock.Mock()
        fake_error.message = "late-error"
        fake_error_message.parse_error.return_value = (fake_error, "debug-info")
        fake_bus.pop.side_effect = [fake_error_message, None]

        runner = gst_runner._PipelineRunner(
            fake_pipeline, max_run_time_sec=0.0, mode="normal"
        )

        ok, reason = runner._finalize(fake_bus)

        self.assertFalse(ok)
        self.assertEqual(reason, "error")


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


class TestGstLogBridge(unittest.TestCase):
    """Tests for the `gst_log_bridge` level mapping and ``<name>`` prefixing.

    The DLStreamer `latency_tracer` posts its windows as
    ``dlstreamer/latency-window`` bus messages (``post-metrics=true``). A
    tracer that predates ``post-metrics`` only logs them as
    ``latency_tracer_pipeline_interval`` TRACE records, so the bridge
    promotes those records to INFO until the first window is posted.
    """

    def setUp(self) -> None:
        state = mock.patch.object(
            gst_runner, "_latency_record_state", gst_runner._LatencyRecordState()
        )
        state.start()
        self.addCleanup(state.stop)

    def _invoke_bridge(self, text: str, level: int) -> None:
        """Call gst_log_bridge with a fake GLib message carrying `text`."""
        fake_message = mock.MagicMock()
        fake_message.get.return_value = text
        gst_runner.gst_log_bridge(
            category=None,
            level=level,
            file=None,
            function=None,
            line=0,
            obj=None,
            message=fake_message,
            user_data=None,
        )

    def _invoke_bridge_with_obj(
        self, text: str, level: int, obj_name: str | None
    ) -> None:
        """Call gst_log_bridge with a named GstObject-like `obj`.

        When ``obj_name`` is ``None``, ``obj`` is passed as ``None`` to
        mirror the tracer path. Otherwise ``obj`` is a mock exposing
        ``get_name()`` returning ``obj_name``, mirroring the way
        GStreamer forwards a ``GstObject`` reference to the log
        function for element-scoped records.
        """
        fake_message = mock.MagicMock()
        fake_message.get.return_value = text
        fake_obj = None
        if obj_name is not None:
            fake_obj = mock.MagicMock()
            fake_obj.get_name.return_value = obj_name
        gst_runner.gst_log_bridge(
            category=None,
            level=level,
            file=None,
            function=None,
            line=0,
            obj=fake_obj,
            message=fake_message,
            user_data=None,
        )

    INTERVAL_SAMPLE = (
        "latency_tracer_pipeline_interval, pipeline_name=(string)pipeline0, "
        "source_name=(string)filesrc0, sink_name=(string)sink0, "
        "interval=(double)1000.0, avg=(double)5.0, min=(double)1.0, "
        "max=(double)9.0, latency=(double)3.0, fps=(double)60.0"
    )

    def test_pipeline_interval_sample_is_promoted_to_info(self) -> None:
        """Without a posted window, interval TRACE records are promoted to INFO."""
        with self.assertLogs("gst_runner", level="DEBUG") as captured:
            self._invoke_bridge(self.INTERVAL_SAMPLE, RealGst.DebugLevel.TRACE)

        self.assertEqual([r.levelname for r in captured.records], ["INFO"])
        self.assertEqual(captured.records[0].getMessage(), self.INTERVAL_SAMPLE)

    def test_pipeline_interval_sample_is_dropped_after_window_posted(self) -> None:
        """Once the tracer posts windows, its interval records are not logged at all."""
        gst_runner._latency_record_state.window_posted = True

        with self.assertNoLogs("gst_runner", level="DEBUG"):
            self._invoke_bridge(self.INTERVAL_SAMPLE, RealGst.DebugLevel.TRACE)

    def test_unrelated_trace_message_stays_at_debug(self) -> None:
        """Non-tracer TRACE messages must still land at DEBUG (default suppressed at INFO)."""
        # If promoted, assertLogs at INFO would succeed; we expect it to fail.
        with self.assertRaises(AssertionError):
            with self.assertLogs("gst_runner", level="INFO"):
                self._invoke_bridge(
                    "some unrelated trace line", RealGst.DebugLevel.TRACE
                )

    def test_per_frame_pipeline_sample_stays_at_debug(self) -> None:
        """Per-frame `latency_tracer_pipeline` samples must NOT be promoted."""
        per_frame = (
            "latency_tracer_pipeline, pipeline_name=(string)pipeline0, "
            "source_name=(string)filesrc0, sink_name=(string)sink0, "
            "frame_latency=(double)1.0, avg=(double)1.0, min=(double)1.0, "
            "max=(double)1.0, latency=(double)1.0, fps=(double)1.0, frame_num=(uint)1"
        )
        with self.assertRaises(AssertionError):
            with self.assertLogs("gst_runner", level="INFO"):
                self._invoke_bridge(per_frame, RealGst.DebugLevel.TRACE)

    def test_element_name_prefixed_when_obj_is_named(self) -> None:
        """`Added meta message:` INFO records from a named ``GstObject`` must be prefixed with ``<name>``.

        Downstream parsers (currently the VLM-metrics parser in
        ``pipeline_runner``) rely on this prefix to attribute a sample
        to a specific stream in multi-stream runs, since after
        ``unify_all_element_names`` the element name is unique per
        stream (e.g. ``gvagenai_0_0``).
        """
        with self.assertLogs("gst_runner", level="INFO") as captured:
            self._invoke_bridge_with_obj(
                "Added meta message: {}",
                RealGst.DebugLevel.INFO,
                obj_name="gvagenai_0_0",
            )

        joined = "\n".join(captured.output)
        self.assertIn("<gvagenai_0_0> Added meta message: {}", joined)

    def test_non_marker_message_is_not_prefixed_even_with_named_obj(self) -> None:
        """Only ``Added meta message:`` lines get the ``<name>`` prefix.

        The prefixing behavior is scoped to the VLM-metrics marker so
        that unrelated logs (errors, warnings, other INFOs) stay
        byte-identical to the pre-change output — every existing
        downstream parser sees exactly what it saw before.
        """
        with self.assertLogs("gst_runner", level="INFO") as captured:
            self._invoke_bridge_with_obj(
                "some unrelated info message",
                RealGst.DebugLevel.INFO,
                obj_name="gvagenai_0_0",
            )

        joined = "\n".join(captured.output)
        self.assertNotIn("<gvagenai_0_0>", joined)
        self.assertIn("some unrelated info message", joined)

    def test_no_prefix_when_obj_is_none(self) -> None:
        """A marker record without a source object must reach the logger unmodified."""
        with self.assertLogs("gst_runner", level="INFO") as captured:
            self._invoke_bridge_with_obj(
                "Added meta message: {}",
                RealGst.DebugLevel.INFO,
                obj_name=None,
            )

        joined = "\n".join(captured.output)
        self.assertNotIn("<", joined)
        self.assertIn("Added meta message: {}", joined)

    def test_no_prefix_when_named_obj_has_empty_name(self) -> None:
        """An empty ``get_name()`` result must not produce a ``<>`` prefix."""
        with self.assertLogs("gst_runner", level="INFO") as captured:
            self._invoke_bridge_with_obj(
                "Added meta message: {}",
                RealGst.DebugLevel.INFO,
                obj_name="",
            )

        joined = "\n".join(captured.output)
        self.assertNotIn("<>", joined)
        self.assertIn("Added meta message: {}", joined)

    def test_tracer_line_is_not_prefixed_even_if_obj_is_named(self) -> None:
        """Tracer records are not ``Added meta message:`` lines, so they get no ``<name>`` prefix."""
        with self.assertLogs("gst_runner", level="DEBUG") as captured:
            self._invoke_bridge_with_obj(
                self.INTERVAL_SAMPLE, RealGst.DebugLevel.TRACE, obj_name="some_tracer"
            )

        self.assertEqual([r.levelname for r in captured.records], ["INFO"])
        self.assertEqual(captured.records[0].getMessage(), self.INTERVAL_SAMPLE)

    def test_meta_message_metrics_dropped_for_post_metrics_element(self) -> None:
        """An element with ``post-metrics=true`` gets its cumulative block removed."""
        obj = mock.MagicMock()
        obj.get_name.return_value = "gvagenai_0_0"
        obj.get_property.side_effect = {"post-metrics": True, "prompt": ""}.__getitem__

        with self.assertLogs("gst_runner", level="INFO") as captured:
            gst_runner.gst_log_bridge(
                None,
                RealGst.DebugLevel.INFO,
                None,
                None,
                0,
                obj,
                mock.MagicMock(
                    get=mock.MagicMock(
                        return_value='Added meta message: {"result": "No", '
                        '"metrics": {"ttft_mean": 1.0}}'
                    )
                ),
                None,
            )

        self.assertEqual(
            captured.records[0].getMessage(),
            '<gvagenai_0_0> Added meta message: {"result": "No"}',
        )


class TestAddPromptToMetaMessage(unittest.TestCase):
    """``gvagenai`` meta JSON is enriched with the element's ``prompt``."""

    def test_prompt_is_added_to_json(self) -> None:
        obj = mock.MagicMock()
        obj.get_property.return_value = "Are people riding? "
        text = gst_runner._add_prompt_to_meta_message(
            'Added meta message: {"result": "No"}', obj
        )
        self.assertTrue(text.startswith("Added meta message: "))
        payload = json.loads(text[len("Added meta message: ") :])
        self.assertEqual(payload, {"result": "No", "prompt": "Are people riding?"})

    def test_text_unchanged_without_prompt_property(self) -> None:
        obj = mock.MagicMock()
        obj.get_property.side_effect = TypeError("no property")
        text = 'Added meta message: {"result": "No"}'
        self.assertEqual(gst_runner._add_prompt_to_meta_message(text, obj), text)

    def test_text_unchanged_for_invalid_json(self) -> None:
        obj = mock.MagicMock()
        obj.get_property.return_value = "prompt"
        text = "Added meta message: {not-json"
        self.assertEqual(gst_runner._add_prompt_to_meta_message(text, obj), text)


class TestDropMetricsFromMetaMessage(unittest.TestCase):
    """The cumulative ``metrics`` block is dropped only for ``post-metrics=true`` elements."""

    TEXT = 'Added meta message: {"result": "No", "metrics": {"ttft_mean": 1.0}}'

    @staticmethod
    def _obj(post_metrics: Any) -> mock.MagicMock:
        obj = mock.MagicMock()
        obj.get_property.side_effect = {"post-metrics": post_metrics}.__getitem__
        return obj

    def test_block_is_dropped_with_post_metrics(self) -> None:
        text = gst_runner._drop_metrics_from_meta_message(self.TEXT, self._obj(True))
        self.assertEqual(text, 'Added meta message: {"result": "No"}')

    def test_block_is_kept_without_post_metrics(self) -> None:
        for obj in (self._obj(False), None):
            with self.subTest(obj=obj):
                self.assertEqual(
                    gst_runner._drop_metrics_from_meta_message(self.TEXT, obj),
                    self.TEXT,
                )

    def test_block_is_kept_when_element_has_no_post_metrics_property(self) -> None:
        obj = mock.MagicMock()
        obj.get_property.side_effect = TypeError("no property 'post-metrics'")
        self.assertEqual(
            gst_runner._drop_metrics_from_meta_message(self.TEXT, obj), self.TEXT
        )

    def test_text_unchanged_without_block_or_valid_json(self) -> None:
        for text in (
            'Added meta message: {"result": "No"}',
            "Added meta message: {not-json",
            "Added meta message: no json",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    gst_runner._drop_metrics_from_meta_message(text, self._obj(True)),
                    text,
                )


class TestNoteLatencyWindowPosted(unittest.TestCase):
    """The first posted latency window stops the record fallback once."""

    def setUp(self) -> None:
        state = mock.patch.object(
            gst_runner, "_latency_record_state", gst_runner._LatencyRecordState()
        )
        state.start()
        self.addCleanup(state.stop)

    @staticmethod
    def _tracer_threshold() -> Any:
        return next(
            c.get_threshold()
            for c in RealGst.debug_get_all_categories()
            if c.get_name() == "GST_TRACER"
        )

    def _keep_tracer_threshold(self) -> None:
        RealGst.init(None)
        before = self._tracer_threshold()
        self.addCleanup(RealGst.debug_set_threshold_for_name, "GST_TRACER", before)

    def test_fallback_raises_then_restores_the_user_threshold(self) -> None:
        """The level from GST_DEBUG (here WARNING) is back after the first window."""
        self._keep_tracer_threshold()
        RealGst.debug_set_threshold_for_name("GST_TRACER", RealGst.DebugLevel.WARNING)

        gst_runner.enable_latency_record_fallback()
        self.assertEqual(self._tracer_threshold(), RealGst.DebugLevel.TRACE)
        self.assertEqual(
            gst_runner._latency_record_state.prior_threshold,
            RealGst.DebugLevel.WARNING,
        )

        gst_runner.note_latency_window_posted()
        self.assertTrue(gst_runner._latency_record_state.window_posted)
        self.assertEqual(self._tracer_threshold(), RealGst.DebugLevel.WARNING)

    def test_first_window_restores_the_threshold_once(self) -> None:
        gst_runner._latency_record_state.prior_threshold = RealGst.DebugLevel.ERROR
        with mock.patch.object(gst_runner, "Gst") as mock_gst:
            gst_runner.note_latency_window_posted()
            gst_runner.note_latency_window_posted()

        mock_gst.debug_set_threshold_for_name.assert_called_once_with(
            "GST_TRACER", RealGst.DebugLevel.ERROR
        )

    def test_threshold_untouched_without_the_fallback(self) -> None:
        """Without a raised threshold (no latency metrics) nothing is restored."""
        with mock.patch.object(gst_runner, "Gst") as mock_gst:
            gst_runner.note_latency_window_posted()

        self.assertTrue(gst_runner._latency_record_state.window_posted)
        mock_gst.debug_set_threshold_for_name.assert_not_called()
        mock_gst.debug_unset_threshold_for_name.assert_not_called()

    def test_initialization_enables_the_fallback_only_when_requested(self) -> None:
        for env, expected in (({"VIPPET_LATENCY_RECORD_FALLBACK": "1"}, 1), ({}, 0)):
            with self.subTest(env=env):
                with (
                    mock.patch.dict("os.environ", env, clear=True),
                    mock.patch.object(gst_runner, "Gst"),
                    mock.patch.object(
                        gst_runner, "enable_latency_record_fallback"
                    ) as mock_enable,
                ):
                    gst_runner.initialize_gstreamer_logging()
                self.assertEqual(mock_enable.call_count, expected)

    def test_sync_handler_notes_only_latency_windows(self) -> None:
        for name, expected in (
            ("dlstreamer/latency-window", 1),
            ("dlstreamer/genai-request", 0),
            ("vippet-event", 0),
            (None, 0),
        ):
            with self.subTest(name=name):
                message = mock.Mock()
                if name is None:
                    message.get_structure.return_value = None
                else:
                    message.get_structure.return_value.get_name.return_value = name
                with mock.patch.object(
                    gst_runner, "note_latency_window_posted"
                ) as mock_note:
                    gst_runner._PipelineRunner._on_sync_element_message(
                        mock.Mock(), message
                    )
                self.assertEqual(mock_note.call_count, expected)


class TestEnableGenaiPostMetrics(unittest.TestCase):
    """``post-metrics=true`` is set only where it is wanted and supported."""

    @staticmethod
    def _element(name: str, metrics: bool, has_post_metrics: bool) -> mock.Mock:
        element = mock.Mock()
        element.get_name.return_value = name
        element.get_property.side_effect = {"metrics": metrics}.__getitem__
        element.find_property.return_value = (
            mock.Mock(name="GParamSpec") if has_post_metrics else None
        )
        return element

    def test_sets_post_metrics_on_supported_elements_with_metrics(self) -> None:
        supported = self._element("gvagenai_0_0", True, True)
        old = self._element("gvagenai_0_1", True, False)
        no_metrics = self._element("gvagenai_0_2", False, True)
        pipeline = mock.create_autospec(gst_runner.Gst.Pipeline, instance=True)
        pipeline.iterate_all_by_element_factory_name.return_value = [
            supported,
            old,
            no_metrics,
        ]

        gst_runner.enable_genai_post_metrics(pipeline, gst_runner.get_logger())

        pipeline.iterate_all_by_element_factory_name.assert_called_once_with("gvagenai")
        supported.set_property.assert_called_once_with("post-metrics", True)
        old.set_property.assert_not_called()
        no_metrics.set_property.assert_not_called()

    def test_non_bin_is_ignored(self) -> None:
        gst_runner.enable_genai_post_metrics(object(), gst_runner.get_logger())  # type: ignore[arg-type]

    def test_real_pipeline_without_gvagenai_is_unchanged(self) -> None:
        RealGst.init(None)
        pipeline = RealGst.parse_launch("fakesrc num-buffers=1 ! fakesink")

        gst_runner.enable_genai_post_metrics(pipeline, gst_runner.get_logger())

    def test_run_pipeline_enables_post_metrics_after_parsing(self) -> None:
        fake_pipeline = object()
        with (
            mock.patch.object(
                gst_runner, "parse_pipeline", return_value=(fake_pipeline, True)
            ),
            mock.patch.object(gst_runner, "enable_genai_post_metrics") as mock_enable,
            mock.patch.object(
                gst_runner, "run_pipeline_for_duration", return_value=(True, None)
            ),
        ):
            self.assertTrue(gst_runner.run_pipeline("x", 1.0, "normal"))

        mock_enable.assert_called_once_with(fake_pipeline, gst_runner.get_logger())


class TestLogPipelineEvent(unittest.TestCase):
    """``vippet-event`` element messages are logged as one JSON line."""

    def test_logs_structure_fields_and_element_name(self) -> None:
        RealGst.init(None)
        structure = RealGst.Structure.new_empty(gst_runner.PIPELINE_EVENT_STRUCTURE)
        structure.set_value("source", "proximity-trigger")
        structure.set_value("text", "person near bicycle")
        structure.set_value("pts-seconds", 1.5)
        src = mock.MagicMock()
        src.get_name.return_value = "gvaproximitytrigger_py0"

        with self.assertLogs("gst_runner", level="INFO") as captured:
            gst_runner.log_pipeline_event(gst_runner.get_logger(), src, structure)

        line = captured.records[0].getMessage()
        self.assertTrue(line.startswith(gst_runner.PIPELINE_EVENT_MARKER))
        payload = json.loads(line[len(gst_runner.PIPELINE_EVENT_MARKER) :])
        self.assertEqual(
            payload,
            {
                "source": "proximity-trigger",
                "text": "person near bicycle",
                "pts-seconds": 1.5,
                "element": "gvaproximitytrigger_py0",
            },
        )


class TestLogPipelineMetric(unittest.TestCase):
    """``dlstreamer/*`` element messages are logged as one ``Pipeline metric:`` JSON line."""

    @staticmethod
    def _parse_line(captured: Any) -> dict:
        line = captured.records[0].getMessage()
        assert line.startswith(gst_runner.PIPELINE_METRIC_MARKER)
        return json.loads(line[len(gst_runner.PIPELINE_METRIC_MARKER) :])

    def test_logs_kind_element_and_scalar_fields(self) -> None:
        RealGst.init(None)
        structure = RealGst.Structure.new_empty("dlstreamer/latency-window")
        structure.set_value("source", "src_p0_s0_0_0")
        structure.set_value("sink", "sink_p0_s0_0_0")
        structure.set_value("count", 4)
        structure.set_value("window_ms", 1000.5)
        structure.set_value("partial", True)
        src = mock.MagicMock()
        src.get_name.return_value = "pipeline0"

        with self.assertLogs("gst_runner", level="INFO") as captured:
            gst_runner.log_pipeline_metric(gst_runner.get_logger(), src, structure)

        self.assertEqual(captured.records[0].levelname, "INFO")
        self.assertEqual(
            self._parse_line(captured),
            {
                "kind": "latency-window",
                "element": "pipeline0",
                "fields": {
                    "source": "src_p0_s0_0_0",
                    "sink": "sink_p0_s0_0_0",
                    "count": 4,
                    "window_ms": 1000.5,
                    "partial": True,
                },
            },
        )

    def test_element_is_none_without_src(self) -> None:
        RealGst.init(None)
        structure = RealGst.Structure.new_empty("dlstreamer/genai-request")
        structure.set_value("ttft_ms", 12.5)

        with self.assertLogs("gst_runner", level="INFO") as captured:
            gst_runner.log_pipeline_metric(gst_runner.get_logger(), None, structure)

        self.assertEqual(
            self._parse_line(captured),
            {"kind": "genai-request", "element": None, "fields": {"ttft_ms": 12.5}},
        )

    def test_non_scalar_fields_are_dropped(self) -> None:
        values: dict[str, Any] = {
            "ttft_ms": 12.5,
            "caps": mock.MagicMock(name="Gst.Caps"),
            "tokens": [1, 2, 3],
            "nested": {"a": 1},
            "missing": None,
        }
        structure = mock.MagicMock()
        structure.get_name.return_value = "dlstreamer/genai-request"
        structure.n_fields.return_value = len(values)
        structure.nth_field_name.side_effect = list(values).__getitem__
        structure.get_value.side_effect = values.__getitem__
        src = mock.MagicMock()
        src.get_name.return_value = "gvagenai_0_0"

        with self.assertLogs("gst_runner", level="INFO") as captured:
            gst_runner.log_pipeline_metric(gst_runner.get_logger(), src, structure)

        self.assertEqual(
            self._parse_line(captured),
            {
                "kind": "genai-request",
                "element": "gvagenai_0_0",
                "fields": {"ttft_ms": 12.5},
            },
        )


class TestElementMessageDispatch(unittest.TestCase):
    """``_PipelineRunner._on_bus_message`` routes ELEMENT messages by structure name."""

    def _make_runner(self) -> Any:
        fake_pipeline = mock.create_autospec(gst_runner.Gst.Pipeline)
        with mock.patch.object(gst_runner, "GLib"):
            return gst_runner._PipelineRunner(
                fake_pipeline, max_run_time_sec=0.1, mode="normal"
            )

    @staticmethod
    def _make_element_message(structure_name: str | None) -> mock.Mock:
        message = mock.Mock()
        message.type = gst_runner.Gst.MessageType.ELEMENT
        if structure_name is None:
            message.get_structure.return_value = None
        else:
            message.get_structure.return_value.get_name.return_value = structure_name
        return message

    def _dispatch(self, structure_name: str | None) -> Tuple[Any, Any, Any, Any]:
        runner = self._make_runner()
        message = self._make_element_message(structure_name)
        loop = mock.Mock()
        with (
            mock.patch.object(gst_runner, "log_pipeline_metric") as mock_metric,
            mock.patch.object(gst_runner, "log_pipeline_event") as mock_event,
        ):
            result = runner._on_bus_message(mock.Mock(), message, loop)
        self.assertTrue(result)
        loop.quit.assert_not_called()
        return runner, message, mock_metric, mock_event

    def test_dlstreamer_messages_are_logged_as_metrics(self) -> None:
        for name in ("dlstreamer/latency-window", "dlstreamer/genai-request"):
            with self.subTest(name=name):
                runner, message, mock_metric, mock_event = self._dispatch(name)

                mock_metric.assert_called_once_with(
                    runner._logger, message.src, message.get_structure.return_value
                )
                mock_event.assert_not_called()

    def test_vippet_event_is_logged_as_event(self) -> None:
        runner, message, mock_metric, mock_event = self._dispatch(
            gst_runner.PIPELINE_EVENT_STRUCTURE
        )

        mock_event.assert_called_once_with(
            runner._logger, message.src, message.get_structure.return_value
        )
        mock_metric.assert_not_called()

    def test_other_element_messages_are_ignored(self) -> None:
        for name in (None, "GstMultiQueueOverrun", "dlstreamer", "latency-window"):
            with self.subTest(name=name):
                _, _, mock_metric, mock_event = self._dispatch(name)

                mock_metric.assert_not_called()
                mock_event.assert_not_called()


class TestDrainBusMessagesMetrics(unittest.TestCase):
    """``drain_bus_messages`` forwards ``dlstreamer/*`` element messages left on the bus.

    A last latency window or GenAI request can be posted during shutdown,
    after the main loop stopped dispatching bus messages. Draining must
    still log it as a ``Pipeline metric:`` line; every other ELEMENT
    message stays on the DEBUG ``Pipeline bus message:`` branch.
    """

    @staticmethod
    def _make_bus(*messages: Any) -> mock.Mock:
        bus = mock.Mock()
        bus.pop.side_effect = [*messages, None]
        return bus

    @staticmethod
    def _make_element_message(structure: Any, src_name: str | None) -> mock.Mock:
        message = mock.Mock()
        message.type = gst_runner.Gst.MessageType.ELEMENT
        message.get_structure.return_value = structure
        if src_name is None:
            message.src = None
        else:
            message.src.get_name.return_value = src_name
        return message

    def test_dlstreamer_element_message_is_logged_as_metric(self) -> None:
        RealGst.init(None)
        structure = RealGst.Structure.new_empty("dlstreamer/latency-window")
        structure.set_value("source", "src_p0_s0_0_0")
        structure.set_value("sink", "sink_p0_s0_0_0")
        structure.set_value("count", 3)
        structure.set_value("window_ms", 450.0)
        bus = self._make_bus(self._make_element_message(structure, "pipeline0"))

        with self.assertLogs("gst_runner", level="INFO") as captured:
            saw_error = gst_runner.drain_bus_messages(bus, gst_runner.get_logger())

        self.assertFalse(saw_error)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(record.levelname, "INFO")
        line = record.getMessage()
        self.assertTrue(line.startswith(gst_runner.PIPELINE_METRIC_MARKER))
        self.assertEqual(
            json.loads(line[len(gst_runner.PIPELINE_METRIC_MARKER) :]),
            {
                "kind": "latency-window",
                "element": "pipeline0",
                "fields": {
                    "source": "src_p0_s0_0_0",
                    "sink": "sink_p0_s0_0_0",
                    "count": 3,
                    "window_ms": 450.0,
                },
            },
        )

    def test_other_element_messages_are_not_logged_as_metrics(self) -> None:
        for name in ("GstMultiQueueOverrun", gst_runner.PIPELINE_EVENT_STRUCTURE, None):
            with self.subTest(name=name):
                structure = None
                if name is not None:
                    structure = mock.Mock()
                    structure.get_name.return_value = name
                bus = self._make_bus(self._make_element_message(structure, "elem0"))

                with mock.patch.object(
                    gst_runner, "log_pipeline_metric"
                ) as mock_metric:
                    with self.assertNoLogs("gst_runner", level="INFO"):
                        with self.assertLogs("gst_runner", level="DEBUG") as captured:
                            saw_error = gst_runner.drain_bus_messages(
                                bus, gst_runner.get_logger()
                            )

                self.assertFalse(saw_error)
                mock_metric.assert_not_called()
                messages = [r.getMessage() for r in captured.records]
                self.assertEqual(len(messages), 1)
                self.assertTrue(messages[0].startswith("Pipeline bus message:"))

    def test_metric_and_error_are_both_drained(self) -> None:
        RealGst.init(None)
        structure = RealGst.Structure.new_empty("dlstreamer/genai-request")
        structure.set_value("ttft_ms", 12.5)
        error_message = mock.Mock()
        error_message.type = gst_runner.Gst.MessageType.ERROR
        fake_error = mock.Mock()
        fake_error.message = "late-error"
        error_message.parse_error.return_value = (fake_error, "debug-info")
        bus = self._make_bus(self._make_element_message(structure, None), error_message)

        with self.assertLogs("gst_runner", level="INFO") as captured:
            saw_error = gst_runner.drain_bus_messages(bus, gst_runner.get_logger())

        self.assertTrue(saw_error)
        self.assertEqual([r.levelname for r in captured.records], ["INFO", "ERROR"])
        line = captured.records[0].getMessage()
        self.assertEqual(
            json.loads(line[len(gst_runner.PIPELINE_METRIC_MARKER) :]),
            {"kind": "genai-request", "element": None, "fields": {"ttft_ms": 12.5}},
        )


if __name__ == "__main__":
    unittest.main()
