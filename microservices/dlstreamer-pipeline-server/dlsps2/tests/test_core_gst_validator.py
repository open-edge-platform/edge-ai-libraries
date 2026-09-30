# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.gst_validator module (pipeline validation)."""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock GStreamer before importing
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()

from core.gst_validator import (
    configure_root_logging,
    drain_bus_messages,
    parse_pipeline,
    validate_pipeline,
    _PipelineValidator,
)
from gi.repository import Gst, GLib


def _make_message(mtype, **attrs):
    """Build a mock Gst.Message of the given type with the given attributes
    (e.g. parse_error/parse_warning/parse_state_changed return values, src)."""
    msg = MagicMock()
    msg.type = mtype
    for key, value in attrs.items():
        setattr(msg, key, value)
    return msg


class TestConfigureRootLogging:
    """Test configure_root_logging(): installs split stdout/stderr handlers."""

    def test_sets_root_logger_level(self):
        """The requested level is applied to the root logger."""
        configure_root_logging(logging.DEBUG)
        assert logging.getLogger().level == logging.DEBUG

    def test_replaces_existing_handlers(self):
        """Any handlers from a previous call (or another library) are removed first."""
        root = logging.getLogger()
        stale_handler = logging.NullHandler()
        root.addHandler(stale_handler)

        configure_root_logging(logging.INFO)

        assert stale_handler not in root.handlers

    def test_installs_exactly_two_handlers(self):
        """Exactly one stdout handler and one stderr handler are installed."""
        configure_root_logging(logging.WARNING)
        assert len(logging.getLogger().handlers) == 2

    def test_stdout_handler_filters_out_error_and_above(self):
        """The stdout handler passes sub-ERROR records but filters out ERROR+."""
        configure_root_logging(logging.DEBUG)
        stdout_handler = next(
            h for h in logging.getLogger().handlers if h.stream is sys.stdout
        )
        error_record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", None, None)
        info_record = logging.LogRecord("x", logging.INFO, __file__, 1, "info", None, None)

        assert stdout_handler.filter(error_record) is False
        assert stdout_handler.filter(info_record) is True

    def test_stderr_handler_only_handles_error_and_above(self):
        """The stderr handler's own level is set to ERROR."""
        configure_root_logging(logging.DEBUG)
        stderr_handler = next(
            h for h in logging.getLogger().handlers if h.stream is sys.stderr
        )
        assert stderr_handler.level == logging.ERROR


class TestParsePipeline:
    """Test parse_pipeline(): wraps Gst.parse_launch() with GStreamer-ERROR awareness."""

    def test_successful_parse_returns_pipeline_and_true(self):
        """A pipeline that parses cleanly is returned with ok=True."""
        mock_pipeline = MagicMock()

        with patch("core.gst_validator.Gst.parse_launch", return_value=mock_pipeline):
            pipeline, ok = parse_pipeline("videotestsrc ! fakesink")

        assert ok is True
        assert pipeline is mock_pipeline

    def test_parse_launch_exception_returns_none_and_false(self):
        """A Gst.parse_launch() exception (e.g. bad syntax) is a parse failure."""
        with patch(
            "core.gst_validator.Gst.parse_launch",
            side_effect=RuntimeError("could not parse pipeline"),
        ):
            pipeline, ok = parse_pipeline("videotestsrc ! (unclosed")

        assert ok is False
        assert pipeline is None

    def test_gstreamer_error_without_exception_is_still_a_failure(self):
        """Gst.parse_launch() can return a pipeline object even when GStreamer
        logged a parse-time ERROR (e.g. missing element); that must still be
        treated as a parse failure, and the partial pipeline torn down."""
        mock_pipeline = MagicMock()

        def fake_add_log_function(fn, state):
            # Simulate GStreamer emitting a parse-time ERROR log.
            fn(None, Gst.DebugLevel.ERROR, None, None, None, None, None, state)

        # Gst.DebugLevel.ERROR needs to be a real, comparable int here since
        # _parse_log_collector does `level <= Gst.DebugLevel.ERROR`.
        with patch.object(Gst.DebugLevel, "ERROR", 1), \
             patch("core.gst_validator.Gst.parse_launch", return_value=mock_pipeline), \
             patch(
                 "core.gst_validator.Gst.debug_add_log_function",
                 side_effect=fake_add_log_function,
             ):
            pipeline, ok = parse_pipeline("videotestsrc ! missingelement")

        assert ok is False
        assert pipeline is None
        mock_pipeline.set_state.assert_called_once_with(Gst.State.NULL)


class TestDrainBusMessages:
    """Test drain_bus_messages(): consumes all pending bus messages, reporting
    whether any ERROR message was seen."""

    @staticmethod
    def _make_bus(messages):
        bus = MagicMock()
        bus.pop.side_effect = list(messages) + [None]
        return bus

    def test_no_messages_returns_false(self):
        bus = self._make_bus([])
        assert drain_bus_messages(bus, logging.getLogger("test")) is False

    def test_error_message_returns_true(self):
        err = _make_message(Gst.MessageType.ERROR)
        err.parse_error.return_value = (MagicMock(message="boom"), "debug info")
        bus = self._make_bus([err])

        assert drain_bus_messages(bus, logging.getLogger("test")) is True

    def test_warning_message_returns_false(self):
        warn = _make_message(Gst.MessageType.WARNING)
        warn.parse_warning.return_value = (MagicMock(message="careful"), "debug info")
        bus = self._make_bus([warn])

        assert drain_bus_messages(bus, logging.getLogger("test")) is False

    def test_eos_message_returns_false(self):
        eos = _make_message(Gst.MessageType.EOS)
        bus = self._make_bus([eos])

        assert drain_bus_messages(bus, logging.getLogger("test")) is False

    def test_error_among_multiple_messages_returns_true(self):
        eos = _make_message(Gst.MessageType.EOS)
        err = _make_message(Gst.MessageType.ERROR)
        err.parse_error.return_value = (MagicMock(message="boom"), "debug info")
        bus = self._make_bus([eos, err])

        assert drain_bus_messages(bus, logging.getLogger("test")) is True


class TestPipelineValidatorRun:
    """Test _PipelineValidator.run(): waits for the pipeline to reach PLAYING,
    EOS, or ERROR via bus messages, then always tears it down to NULL."""

    @staticmethod
    def _make_pipeline():
        pipeline = MagicMock()
        bus = MagicMock()
        pipeline.get_bus.return_value = bus
        return pipeline, bus

    @staticmethod
    def _fire_bus_message(bus, message):
        """Invoke the callback that .run() registered via bus.connect(...)
        with the given fake message, as GStreamer would when it fires."""
        _signal, callback, loop = bus.connect.call_args[0]
        callback(bus, message, loop)

    def test_reaching_playing_is_success(self):
        """A STATE_CHANGED message to PLAYING for the pipeline itself ends
        validation successfully with reason 'playing'."""
        pipeline, bus = self._make_pipeline()
        validator = _PipelineValidator(pipeline)
        msg = _make_message(
            Gst.MessageType.STATE_CHANGED,
            src=pipeline,
            parse_state_changed=MagicMock(
                return_value=(Gst.State.PAUSED, Gst.State.PLAYING, Gst.State.VOID_PENDING)
            ),
        )

        with patch("core.gst_validator.GLib.MainLoop") as mock_loop_cls, \
             patch("core.gst_validator.drain_bus_messages", return_value=False):
            mock_loop_cls.return_value.run.side_effect = lambda: self._fire_bus_message(bus, msg)
            ok, reason = validator.run()

        assert (ok, reason) == (True, "playing")
        pipeline.set_state.assert_any_call(Gst.State.PLAYING)
        pipeline.set_state.assert_any_call(Gst.State.NULL)

    def test_state_changed_for_other_element_is_ignored(self):
        """A STATE_CHANGED message whose src is not the pipeline itself must
        not be mistaken for the pipeline reaching PLAYING."""
        pipeline, bus = self._make_pipeline()
        validator = _PipelineValidator(pipeline)
        other_element = MagicMock()
        msg = _make_message(
            Gst.MessageType.STATE_CHANGED,
            src=other_element,
            parse_state_changed=MagicMock(
                return_value=(Gst.State.PAUSED, Gst.State.PLAYING, Gst.State.VOID_PENDING)
            ),
        )

        def fake_run():
            self._fire_bus_message(bus, msg)
            # Loop wasn't quit by the irrelevant message; validator's state
            # is left with no reason recorded.

        with patch("core.gst_validator.GLib.MainLoop") as mock_loop_cls, \
             patch("core.gst_validator.drain_bus_messages", return_value=False):
            mock_loop_cls.return_value.run.side_effect = fake_run
            ok, reason = validator.run()

        assert (ok, reason) == (True, None)

    def test_error_message_is_failure(self):
        """A GStreamer ERROR message ends validation with ok=False, reason='error'."""
        pipeline, bus = self._make_pipeline()
        validator = _PipelineValidator(pipeline)
        msg = _make_message(Gst.MessageType.ERROR)
        msg.parse_error.return_value = (MagicMock(message="boom"), "debug info")

        with patch("core.gst_validator.GLib.MainLoop") as mock_loop_cls, \
             patch("core.gst_validator.drain_bus_messages", return_value=False):
            mock_loop_cls.return_value.run.side_effect = lambda: self._fire_bus_message(bus, msg)
            ok, reason = validator.run()

        assert (ok, reason) == (False, "error")
        pipeline.set_state.assert_any_call(Gst.State.NULL)

    def test_eos_before_playing_is_success(self):
        """EOS (e.g. from a very short test clip) is treated as a valid endpoint."""
        pipeline, bus = self._make_pipeline()
        validator = _PipelineValidator(pipeline)
        msg = _make_message(Gst.MessageType.EOS)

        with patch("core.gst_validator.GLib.MainLoop") as mock_loop_cls, \
             patch("core.gst_validator.drain_bus_messages", return_value=False):
            mock_loop_cls.return_value.run.side_effect = lambda: self._fire_bus_message(bus, msg)
            ok, reason = validator.run()

        assert (ok, reason) == (True, "eos")

    def test_error_seen_only_during_final_drain_still_fails(self):
        """Even if PLAYING was reached, an ERROR message discovered only
        while draining the bus one last time must still fail validation
        (the earlier 'playing' reason is kept -- only the ok flag flips)."""
        pipeline, bus = self._make_pipeline()
        validator = _PipelineValidator(pipeline)
        msg = _make_message(
            Gst.MessageType.STATE_CHANGED,
            src=pipeline,
            parse_state_changed=MagicMock(
                return_value=(Gst.State.PAUSED, Gst.State.PLAYING, Gst.State.VOID_PENDING)
            ),
        )

        with patch("core.gst_validator.GLib.MainLoop") as mock_loop_cls, \
             patch("core.gst_validator.drain_bus_messages", return_value=True):
            mock_loop_cls.return_value.run.side_effect = lambda: self._fire_bus_message(bus, msg)
            ok, reason = validator.run()

        assert ok is False
        assert reason == "playing"


class TestValidatePipeline:
    """Test validate_pipeline(): combines parse_pipeline() + _PipelineValidator.run()."""

    def test_parse_failure_short_circuits_without_running(self):
        """A parse failure returns immediately with reason 'parse_error',
        never attempting to run the (nonexistent) pipeline."""
        with patch("core.gst_validator.parse_pipeline", return_value=(None, False)):
            ok, reason = validate_pipeline("videotestsrc ! (unclosed")

        assert (ok, reason) == (False, "parse_error")

    def test_delegates_to_pipeline_validator_and_cleans_up(self):
        """On a successful parse, runs the pipeline via _PipelineValidator and
        always sets it back to NULL afterwards."""
        mock_pipeline = MagicMock()

        with patch(
            "core.gst_validator.parse_pipeline", return_value=(mock_pipeline, True)
        ), patch("core.gst_validator._PipelineValidator") as mock_validator_cls:
            mock_validator_cls.return_value.run.return_value = (True, "playing")
            ok, reason = validate_pipeline("videotestsrc ! fakesink")

        assert (ok, reason) == (True, "playing")
        mock_validator_cls.assert_called_once_with(mock_pipeline)
        mock_pipeline.set_state.assert_called_once_with(Gst.State.NULL)

    def test_cleans_up_even_when_validator_run_raises(self):
        """The pipeline is still torn down to NULL if _PipelineValidator.run() raises."""
        mock_pipeline = MagicMock()

        with patch(
            "core.gst_validator.parse_pipeline", return_value=(mock_pipeline, True)
        ), patch("core.gst_validator._PipelineValidator") as mock_validator_cls:
            mock_validator_cls.return_value.run.side_effect = RuntimeError("boom")

            with pytest.raises(RuntimeError):
                validate_pipeline("videotestsrc ! fakesink")

        mock_pipeline.set_state.assert_called_once_with(Gst.State.NULL)

