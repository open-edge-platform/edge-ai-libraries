#!/usr/bin/env python3
"""
GStreamer Pipeline Runner

This module provides a command-line tool and library API for running
GStreamer pipeline descriptions.

The runner supports two modes:

- normal: Run pipelines for production use.
- validation: Run pipelines for a limited time to verify correctness.

The runner:

1. Initializes GStreamer and hooks its debug logging into Python's logging.
2. Parses a textual pipeline description via Gst.parse_launch().
3. Treats the parse as FAILED if:
   - Gst.parse_launch() raises an exception, OR
   - any GStreamer ERROR-level log is emitted during parsing.
4. If parsing succeeds without ERRORs:
   - starts the pipeline (PLAYING),
   - runs it under a GLib.MainLoop for a configurable duration (max-runtime),
   - watches the bus for GStreamer ERROR and EOS messages.
5. Stops the pipeline when:
   - an ERROR is observed on the bus (run FAIL), OR
   - EOS is observed on the bus, OR
   - the max-runtime elapses (if configured).

Running semantics:

- Failure (exit code 1):
  * pipeline cannot be parsed (exception in parse_launch), OR
  * any GStreamer ERROR is logged during parsing (even if parse_launch
    returns a pipeline object), OR
  * a GStreamer ERROR is observed on the bus at ANY time during the run
    or shutdown, OR
  * invalid combination of mode and max-runtime arguments.
- Success (exit code 0):
  * the pipeline is parsed successfully AND
  * no GStreamer ERROR appears during parsing, run, or shutdown.

The script is designed to:

- Be callable as a subprocess by another application.
- Provide clear logging for diagnosing pipeline issues.
- Be testable via dependency injection.
"""

import argparse
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import gi  # pyright: ignore[reportMissingImports]

gi.require_version("Gst", "1.0")
gi.require_version("GObject", "2.0")
from gi.repository import Gst, GLib  # noqa: E402 # pyright: ignore[reportMissingImports]


###############################################################################
# Logging and GStreamer initialization
###############################################################################


def configure_root_logging(level: int) -> None:
    """Configure root logging for the whole process.

    This function sets a basic logging configuration with a uniform format
    and the given log level. It is intended to be called once early in main().

    The configuration is split into two handlers:

    * stdout_handler – handles all log records with level < ERROR,
      writing them to stdout.
    * stderr_handler – handles ERROR and CRITICAL records (including those
      produced by logger.exception()), writing them to stderr.

    This ensures that only error-level messages end up on stderr while
    all informational and debug logs go to stdout.
    """
    # Remove any existing handlers that might have been configured by
    # previous calls or by other libraries, to avoid duplicate logs.
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(level)

    # Simple "logger - LEVEL - message" format, without brackets or categories.
    log_format = "%(name)s - %(levelname)s - %(message)s"

    # Handler for non-error messages -> stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_handler.setFormatter(logging.Formatter(log_format))

    # Handler for error and critical messages -> stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(logging.Formatter(log_format))

    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)


def get_logger() -> logging.Logger:
    """Get the module-level logger for this script."""
    return logging.getLogger("gst_runner")


def gst_log_bridge(
    category,
    level,
    file,
    function,
    line,
    obj,
    message,
    user_data,
) -> None:
    """Bridge GStreamer logging to Python's logging system.

    This function is registered with Gst.debug_add_log_function() so that
    GStreamer log messages are forwarded to the Python logger.

    It does NOT track any validation state by itself; it only mirrors
    GStreamer logging to Python's logging subsystem.

    Mapping:
    - ERROR and above -> logger.error()
    - WARNING         -> logger.warning()
    - INFO            -> logger.info()
    - Below INFO      -> logger.debug()

    Args:
        category: GStreamer debug category (unused).
        level: GStreamer debug level.
        file: Source file name (unused).
        function: Function name (unused).
        line: Line number (unused).
        obj: GObject instance (unused).
        message: GLib.LogMessage, from which we extract the human-readable text.
        user_data: Custom user data (unused).

    All messages are logged without the GStreamer category – only the
    human-readable message text is propagated. Any newline or carriage
    return characters in the original message are replaced with spaces
    so that each log record is emitted as a single line.
    """
    logger = get_logger()
    text = message.get()

    # Normalize message to a single line: replace newlines and carriage
    # returns with spaces. This keeps stderr parsing in the caller simple.
    text = text.replace("\r", " ").replace("\n", " ")

    # Log only the message body, without any extra category/prefix.
    if level >= Gst.DebugLevel.ERROR:
        logger.error("%s", text)
    elif level >= Gst.DebugLevel.WARNING:
        logger.warning("%s", text)
    elif level >= Gst.DebugLevel.INFO:
        logger.info("%s", text)
    else:
        logger.debug("%s", text)


def initialize_gstreamer_logging() -> None:
    """Initialize GStreamer and hook its logging into Python's logging.

    This should be called exactly once at the startup of the program.

    It:
    - calls Gst.init(),
    - logs the GStreamer version,
    - replaces default GStreamer log handlers with gst_log_bridge().

    Note:
        Additional temporary log handlers may be installed by individual
        functions (e.g. parse_pipeline) for more fine-grained error
        detection, but this global bridge remains active for the lifetime
        of the process.
    """
    logger = get_logger()

    Gst.init(None)
    version = Gst.version()
    logger.info(
        "GStreamer initialized successfully — version: %d.%d.%d",
        version.major,
        version.minor,
        version.micro,
    )

    # Remove any default log functions and add our bridge for general logging.
    Gst.debug_remove_log_function(None)
    Gst.debug_add_log_function(gst_log_bridge, None)


###############################################################################
# Bus processing utilities
###############################################################################


def drain_bus_messages(
    bus: Gst.Bus,
    logger: logging.Logger,
) -> bool:
    """Drain all pending messages from the given GStreamer bus.

    This helper function consumes all currently available messages from
    the bus and logs them appropriately.

    It is safe to call this function multiple times; if no messages are
    available, it simply returns.

    Typical usage:
      - during or after shutdown, to surface any late ERROR/WARNING/EOS
        messages that might have been posted while the pipeline was
        transitioning to NULL.

    Returns:
        True if at least one ERROR message was seen while draining,
        False otherwise.
    """
    saw_error = False
    message = bus.pop()
    while message is not None:
        mtype = message.type

        if mtype == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            debug = debug.replace("\r", " ").replace("\n", " ")
            logger.error("Pipeline error: %s (debug: %s)", error.message, debug)
            saw_error = True
        elif mtype == Gst.MessageType.WARNING:
            warning, debug = message.parse_warning()
            debug = debug.replace("\r", " ").replace("\n", " ")
            logger.warning("Pipeline warning: %s (debug: %s)", warning.message, debug)
        elif mtype == Gst.MessageType.STATE_CHANGED:
            old, new, pending = message.parse_state_changed()
            logger.debug(
                "Pipeline state changed: %s -> %s (pending: %s)", old, new, pending
            )
        elif mtype == Gst.MessageType.EOS:
            logger.info("Pipeline reached EOS (end-of-stream).")
        else:
            logger.debug("Pipeline bus message: %s", message)

        message = bus.pop()

    return saw_error


###############################################################################
# Parsing with a local GStreamer ERROR collector
###############################################################################


@dataclass
class _ParseLogState:
    """State used to collect GStreamer ERROR logs during parsing."""

    error_seen: bool = False


def _parse_log_collector(
    category,
    level,
    file,
    function,
    line,
    obj,
    message,
    state: _ParseLogState,
) -> None:
    """Temporary log function used only during parsing.

    This handler's sole responsibility is to record whether an ERROR-level
    GStreamer log was observed while :func:`Gst.parse_launch` is running.

    It deliberately does *not* emit any Python log messages itself to avoid
    double-logging, because the global :func:`gst_log_bridge` is already
    registered and forwards all GStreamer messages to the Python logging
    system.

    Args:
        category: GStreamer debug category (unused).
        level: GStreamer debug level.
        file: Source file name (unused).
        function: Function name (unused).
        line: Line number (unused).
        obj: GObject instance (unused).
        message: GLib.LogMessage, from which we extract the human-readable text (unused).
        state: A _ParseLogState instance used to record whether an ERROR
               was observed.
    """
    if level >= Gst.DebugLevel.ERROR:
        state.error_seen = True


def parse_pipeline(pipeline_description: str) -> Tuple[Optional[Gst.Pipeline], bool]:
    """Parse a textual GStreamer pipeline description with error awareness.

    This function wraps Gst.parse_launch() and considers two failure modes:

    - A Python exception thrown by parse_launch() -> parse failure.
    - No exception, but GStreamer logs ERRORs during parse_launch() ->
      also treated as parse failure, even if a pipeline object is returned.

    To detect the latter, we install a temporary GStreamer log handler that
    tracks ERROR-level logs only for the duration of parse_launch().

    This approach is conservative but practical: in many real-world cases
    GStreamer logs a parse-time ERROR (e.g. missing elements, resources,
    or caps negotiation issues) without raising an exception. From the
    runner's perspective such pipelines should be rejected before any
    runtime validation is attempted.

    Args:
        pipeline_description: Pipeline string to be parsed.

    Returns:
        (pipeline, True)  if parsing succeeded and no parse-time ERROR was seen.
        (None, False)     if parsing failed with an exception or if parse-time
                          ERRORs were logged by GStreamer.
    """
    logger = get_logger()
    logger.debug("Parsing pipeline: %s", pipeline_description)

    # Local collector for parse-time GStreamer ERRORs.
    parse_state = _ParseLogState()

    # Install temporary log collector in addition to the global bridge.
    # We do not remove the bridge; we add an extra handler that sees only
    # parse-time logs and updates parse_state.
    Gst.debug_add_log_function(_parse_log_collector, parse_state)

    try:
        try:
            pipeline = Gst.parse_launch(pipeline_description)
        except Exception as exc:  # noqa: BLE001
            # This will be logged once via gst_log_bridge (from GStreamer)
            # and once here as the high-level Python error message.
            logger.error("Failed to parse pipeline (exception): %r", exc)
            return None, False
    finally:
        # Remove the temporary parse-time handler, leaving the global bridge.
        Gst.debug_remove_log_function(_parse_log_collector)

    if parse_state.error_seen:
        # GStreamer reported ERRORs while parsing. Even if we got a pipeline
        # object, we must treat this as a parse failure and not start it.
        logger.error(
            "Pipeline description is invalid: GStreamer reported ERRORs "
            "during parsing. Aborting validation.",
        )
        # Ensure the partially constructed pipeline is torn down cleanly.
        try:
            pipeline.set_state(Gst.State.NULL)
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.warning(
                "Error while cleaning up invalid pipeline after parse: %r",
                cleanup_exc,
            )
        return None, False

    logger.info("Pipeline parsed successfully.")
    return pipeline, True


###############################################################################
# Pipeline execution using a GLib.MainLoop
###############################################################################


@dataclass
class _RunState:
    """Internal state tracked during a single pipeline run."""

    error_seen: bool = False
    eos_seen: bool = False
    max_runtime_triggered: bool = False
    shutdown_in_progress: bool = False
    reason: Optional[str] = None


class _PipelineRunner:
    """Internal helper that runs a pipeline under a GLib.MainLoop.

    This class encapsulates:

    - A GLib.MainLoop driving the pipeline, similar to gst-launch.
    - A mechanism that stops the pipeline after max-runtime elapses (if configured).
    - A bus message handler that records ERROR/EOS and terminates the loop.

    Max-runtime semantics:

    - If max-runtime > 0: pipeline will be stopped after this duration if it
      hasn't finished or errored.
    - If max-runtime == 0: pipeline runs until natural completion (EOS or error).

    Mode semantics:

    - validation mode: used for testing pipeline validity.
    - normal mode: used for production pipeline execution.

    Note on looping:
    - This runner does not implement pipeline looping. If you need a pipeline
      to loop (play repeatedly), use GStreamer elements that support looping
      natively, such as `multifilesrc loop=true`.
    - With normal mode and max-runtime == 0, such a pipeline will run indefinitely.
    - With normal mode and max-runtime > 0, the pipeline will loop until
      max-runtime is reached.
    """

    def __init__(
        self,
        pipeline: Gst.Pipeline,
        max_run_time_sec: float,
        mode: str,
    ):
        if not isinstance(pipeline, Gst.Pipeline):
            raise TypeError("pipeline must be a Gst.Pipeline instance")

        self._pipeline = pipeline
        self._max_run_time_sec = max_run_time_sec
        self._mode = mode
        self._state = _RunState()
        self._logger = get_logger()

    def _on_bus_message(self, bus: Gst.Bus, message: Gst.Message, loop: GLib.MainLoop):
        """Handle GStreamer bus messages.

        We stop the main loop on EOS or ERROR, just like gst-launch does.

        This callback is connected via bus.connect("message", ...) and is used
        to record runtime errors and EOS, updating the shared _RunState.
        """
        msg_type = message.type

        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            debug = debug.replace("\r", " ").replace("\n", " ")

            # Ignore errors that occur during graceful shutdown after max-runtime.
            # Elements like rtspclientsink may report errors when the pipeline
            # is being stopped, which is expected behavior.
            if self._state.shutdown_in_progress:
                self._logger.debug(
                    "Ignoring error during shutdown: %s (debug: %s)",
                    err.message,
                    debug,
                )
                return True

            self._logger.error(
                "Pipeline runtime error: %s (debug: %s)",
                err.message,
                debug,
            )
            self._state.error_seen = True
            self._state.reason = self._state.reason or "error"
            loop.quit()

        elif msg_type == Gst.MessageType.EOS:
            self._logger.info("Pipeline reached EOS.")
            self._state.eos_seen = True
            self._state.reason = self._state.reason or None
            loop.quit()

        return True

    def _max_runtime_enforcement_thread(self, loop: GLib.MainLoop):
        """Thread that enforces the maximum pipeline runtime.

        After `max_run_time_sec` seconds, this thread initiates a graceful
        shutdown by:

        1. Pausing the pipeline to stop source elements from producing
           new data.
        2. Flushing the entire pipeline (FLUSH_START + FLUSH_STOP) to
           discard all internally buffered data in every element — not
           just queue elements, but also decoders, inference elements,
           and trackers.
        3. Resuming the pipeline (PLAYING) and sending an EOS event.
           Since all internal buffers have been flushed, the EOS
           propagates through the pipeline almost instantly.

        This ensures that elements like gvafpscounter still receive
        the EOS event and can emit their final summary, while avoiding
        the delay caused by processing hundreds of buffered frames.

        If the pipeline does not reach EOS within the grace period,
        it is forcefully stopped.
        """
        eos_grace_period_sec = 2.0

        time.sleep(self._max_run_time_sec)

        # If an ERROR or EOS already terminated the run, do nothing.
        if self._state.error_seen or self._state.eos_seen:
            return

        self._logger.info(
            "Max runtime (%.1f s) elapsed; initiating graceful shutdown.",
            self._max_run_time_sec,
        )
        self._state.max_runtime_triggered = True
        self._state.shutdown_in_progress = True
        self._state.reason = self._state.reason or "max_runtime"

        # Step 1: Pause the pipeline to stop sources from producing
        # new buffers.
        self._logger.debug("Pausing pipeline to stop data production.")
        self._pipeline.set_state(Gst.State.PAUSED)
        self._pipeline.get_state(2 * Gst.SECOND)

        # Step 2: Flush the entire pipeline. FLUSH_START discards all
        # data buffered internally in every element (decoders, inference
        # elements, queues, trackers, etc.). FLUSH_STOP resets the
        # pipeline's streaming state so it can accept the subsequent
        # EOS event normally.
        self._logger.debug("Flushing pipeline to discard all internally buffered data.")
        self._pipeline.send_event(Gst.Event.new_flush_start())
        self._pipeline.send_event(Gst.Event.new_flush_stop(True))

        # Step 3: Resume the pipeline and send EOS. The pipeline is now
        # empty — no queued frames to process — so EOS will propagate
        # through to the sink almost immediately, triggering summary
        # output from elements like gvafpscounter along the way.
        self._logger.debug("Resuming pipeline and sending EOS.")
        self._pipeline.set_state(Gst.State.PLAYING)

        eos_sent = self._pipeline.send_event(Gst.Event.new_eos())
        if not eos_sent:
            self._logger.warning(
                "Failed to send EOS event to pipeline; forcing shutdown."
            )
            try:
                self._pipeline.set_state(Gst.State.NULL)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Error while force-stopping pipeline: %r", exc)
            loop.quit()
            return

        # Step 4: Wait briefly for EOS to arrive on the bus. With a
        # fully flushed pipeline this should take well under a second.
        time.sleep(eos_grace_period_sec)

        if not self._state.eos_seen and not self._state.error_seen:
            self._logger.warning(
                "Pipeline did not reach EOS within %.1f s grace period; "
                "forcing shutdown.",
                eos_grace_period_sec,
            )
            try:
                self._pipeline.set_state(Gst.State.NULL)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Error while force-stopping pipeline after grace period: %r",
                    exc,
                )
            loop.quit()

    def run(self) -> Tuple[bool, Optional[str]]:
        """Run the pipeline and return (ok, reason).

        The sequence is:

        1. Obtain the pipeline's bus and create a GLib.MainLoop.
        2. Attach a bus watch and connect _on_bus_message for ERROR/EOS.
        3. Request PLAYING state on the pipeline.
        4. Call get_state() with a configured wait time (for diagnostics only)
           to log the initial state-change outcome.
        5. If max-runtime > 0, start a background thread that will trigger when
           max_run_time_sec elapses.
        6. Run the GLib.MainLoop until:
             - ERROR on the bus, OR
             - EOS on the bus, OR
             - the max-runtime enforcement thread calls loop.quit().
        7. After the loop exits, stop the pipeline, remove the bus watch,
           drain any remaining bus messages for logging, and derive the
           final result from _RunState.

        Returns:
            (True, None)
                if the pipeline ran successfully (EOS or clean run before
                max-runtime, and no errors on the bus).
            (True, "max_runtime")
                if the pipeline was stopped at max-runtime with no errors
                observed during run or shutdown.
            (False, "error")
                if any GStreamer ERROR was observed.
        """
        bus = self._pipeline.get_bus()
        loop = GLib.MainLoop()

        # Attach bus watch and connect handler.
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message, loop)

        # Request PLAYING state.
        ret = self._pipeline.set_state(Gst.State.PLAYING)
        self._logger.debug("Requested pipeline state PLAYING, result: %s", ret)

        # Wait for initial state change (for logging only).
        # This does not control the run outcome directly; runtime errors
        # are still detected via bus messages and the max-runtime enforcement thread.
        state_change_ret, current_state, pending = self._pipeline.get_state(
            5 * Gst.SECOND,
        )

        self._logger.debug(
            "Initial state change result: %s, current: %s, pending: %s",
            state_change_ret,
            current_state,
            pending,
        )

        # Start max-runtime enforcement thread only if max-runtime > 0.
        if self._max_run_time_sec > 0:
            max_runtime_thread = threading.Thread(
                target=self._max_runtime_enforcement_thread,
                args=(loop,),
                daemon=True,
            )
            max_runtime_thread.start()

        # Run main loop until:
        #   - ERROR (bus handler quits loop),
        #   - EOS (bus handler quits loop),
        #   - max-runtime enforcement thread quits loop (if configured).
        try:
            loop.run()
        finally:
            # Ensure we always stop the pipeline and clean up the bus watch.
            try:
                self._pipeline.set_state(Gst.State.NULL)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Error while stopping pipeline after run: %r", exc)
            bus.remove_signal_watch()

        # Drain any remaining messages for logging purposes.
        if drain_bus_messages(bus, self._logger):
            # If we see an ERROR here and no reason was recorded yet,
            # treat it as an error.
            if not self._state.error_seen:
                self._state.error_seen = True
                self._state.reason = self._state.reason or "error"

        # Determine final outcome.
        if self._state.error_seen:
            return False, "error"
        if self._state.max_runtime_triggered and not self._state.error_seen:
            return True, "max_runtime"
        # EOS or normal stop without errors.
        return True, None


def run_pipeline_for_duration(
    pipeline: Gst.Pipeline,
    max_run_time_sec: float,
    mode: str,
) -> Tuple[bool, Optional[str]]:
    """Run the pipeline for up to max_run_time_sec seconds.

    This is a thin wrapper around _PipelineRunner to keep the public
    interface simple and testable.

    Args:
        pipeline: A GStreamer pipeline created by parse_launch().
        max_run_time_sec: Maximum time in seconds for which the pipeline
                          will run. Behavior depends on the value:
                          - > 0: pipeline stops after this duration if not
                            finished earlier
                          - == 0: pipeline runs until natural completion (EOS)
        mode: Execution mode ("normal" or "validation").

    Returns:
        (True, None)          if the pipeline ran successfully (EOS or clean
                              run before max-runtime and clean shutdown).
        (False, "error")      if a GStreamer ERROR was observed.
        (True, "max_runtime") if the pipeline was stopped at max-runtime with
                              NO error.
    """
    runner = _PipelineRunner(pipeline, max_run_time_sec, mode)
    return runner.run()


###############################################################################
# High-level pipeline running and CLI
###############################################################################


def run_pipeline(
    pipeline_description: str,
    max_run_time_sec: float,
    mode: str,
) -> bool:
    """High-level pipeline running helper.

    This function combines parsing and running of the pipeline into a single
    high-level operation suitable for use in main() and in unit tests.

    Running rules:

    - If parsing fails (exception OR parse-time GStreamer ERRORs) ->
      run FAILS.
    - If parsing succeeds but the pipeline emits a GStreamer ERROR at any
      moment during the run or shutdown -> run FAILS.
    - If the pipeline runs and:
        * reaches EOS within the max-runtime, OR
        * runs until max-runtime is reached and shuts down cleanly without
          errors,
      -> run SUCCEEDS.

    Args:
        pipeline_description: Textual GStreamer pipeline description.
        max_run_time_sec: Maximum runtime in seconds (behavior depends on value).
        mode: Execution mode ("normal" or "validation").

    Returns:
        True  if the pipeline ran successfully.
        False otherwise.
    """
    logger = get_logger()

    pipeline, parsed_ok = parse_pipeline(pipeline_description)
    if not parsed_ok or pipeline is None:
        logger.error("Pipeline run failed: pipeline parsing error.")
        return False

    run_ok: bool = False
    failure_reason: Optional[str] = None

    try:
        run_ok, failure_reason = run_pipeline_for_duration(
            pipeline=pipeline,
            max_run_time_sec=max_run_time_sec,
            mode=mode,
        )
    finally:
        # Ensure the pipeline is always set to NULL, even if something goes
        # wrong in the runner.
        try:
            logger.debug("Final pipeline cleanup (ensuring NULL state).")
            pipeline.set_state(Gst.State.NULL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error while cleaning up pipeline: %r", exc)

    if not run_ok:
        logger.error(
            "Pipeline run failed: pipeline runtime error (reason: %s).",
            failure_reason or "unknown",
        )
        return False

    if failure_reason == "max_runtime":
        logger.info(
            "Pipeline run succeeded: pipeline ran for the configured max-runtime "
            "and shut down without GStreamer errors."
        )
    else:
        logger.info("Pipeline run succeeded: pipeline completed successfully.")

    return True


def validate_arguments(mode: str, max_runtime: float) -> Optional[str]:
    """Validate the combination of mode and max-runtime arguments.

    Args:
        mode: Execution mode ("normal" or "validation").
        max_runtime: Maximum runtime in seconds.

    Returns:
        None if arguments are valid, otherwise an error message string.
    """
    # Validate mode value.
    if mode not in ("normal", "validation"):
        return f"Invalid mode '{mode}'. Must be either 'normal' or 'validation'."

    # Negative max-runtime is not allowed.
    if max_runtime < 0:
        return (
            f"Invalid max-runtime value {max_runtime}. "
            "Negative values are not allowed. "
            "If you need a pipeline to loop indefinitely, use pipeline elements "
            "that support looping (e.g., 'multifilesrc loop=true') with "
            "mode='normal' and max-runtime=0."
        )

    # Validate mode and max-runtime combinations.
    if mode == "validation":
        if max_runtime == 0:
            return (
                "Invalid argument combination: validation mode requires "
                "max-runtime > 0. Validation mode is designed to run pipelines "
                "for a limited time to verify correctness."
            )

    return None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional list of arguments to parse. If None, sys.argv is used.
              This parameter makes the function easier to test.

    Returns:
        Parsed arguments as an argparse.Namespace instance.
    """
    parser = argparse.ArgumentParser(
        prog="GStreamer Pipeline Runner",
        description=(
            "Run a GStreamer pipeline by starting it and running it for a "
            "configurable duration. The runner monitors for GStreamer errors "
            "during execution."
        ),
    )

    parser.add_argument(
        "--mode",
        type=str,
        default="normal",
        choices=["normal", "validation"],
        help=(
            "Execution mode. 'normal' runs the pipeline for production use. "
            "'validation' runs the pipeline for a limited time to verify correctness. "
            "Default: %(default)s."
        ),
    )

    parser.add_argument(
        "--max-runtime",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help=(
            "Maximum time (in seconds) to run the pipeline. Behavior depends "
            "on the value: "
            "> 0: pipeline stops after this duration if not finished earlier; "
            "== 0: pipeline runs until natural completion (EOS). "
            "Note: To make a pipeline loop indefinitely, use pipeline elements "
            "that support looping (e.g., 'multifilesrc loop=true') with "
            "max-runtime=0. To loop for a limited time, use looping elements "
            "with max-runtime > 0. "
            "Default: %(default).1f seconds."
        ),
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help=(
            "Minimum log level to use for both the runner and the "
            "GStreamer-to-logging bridge (default: %(default)s)."
        ),
    )

    parser.add_argument(
        "pipeline",
        nargs="+",
        help=(
            "GStreamer pipeline description to be run. "
            "All positional arguments are joined with spaces into a single "
            "string before being passed to Gst.parse_launch()."
        ),
    )

    return parser.parse_args(argv)


def run_application(
    argv: Optional[List[str]],
    initialize_gst_fn: Callable[[], None],
    run_fn: Callable[[str, float, str], bool],
) -> int:
    """Core implementation of the CLI entry point with dependency injection.

    This function contains the actual main() logic, but accepts the GStreamer
    initialization function and the pipeline running function as arguments.

    Benefits:

    - In production, we call it with real implementations:
          initialize_gst_fn = initialize_gstreamer_logging
          run_fn           = run_pipeline
    - In tests, we can call it with fake/mocked implementations.

    Args:
        argv: Optional list of CLI arguments (like sys.argv[1:]).
        initialize_gst_fn: Function used to initialize GStreamer and logging.
        run_fn: Function used to run the pipeline string. The callable
                MUST accept (pipeline_description: str,
                max_run_time_sec: float, mode: str) in this order.

    Returns:
        0 on successful run,
        1 on run failure or unexpected internal error.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Parse arguments.
    args = parse_args(argv)

    # Map string log level to the logging module's numeric value.
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    configure_root_logging(log_level)
    logger = get_logger()

    logger.debug("Parsed arguments: %s", args)

    # Validate argument combinations.
    validation_error = validate_arguments(args.mode, args.max_runtime)
    if validation_error:
        logger.error("%s", validation_error)
        return 1

    # Initialize GStreamer and its logging bridge.
    try:
        initialize_gst_fn()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize GStreamer: %r", exc)
        return 1

    # Join the pipeline pieces into a single string.
    pipeline_description = " ".join(args.pipeline)
    logger.info(
        "Running pipeline in %s mode (max-runtime: %.1f s): %s",
        args.mode,
        args.max_runtime,
        pipeline_description,
    )

    try:
        success = run_fn(
            pipeline_description,
            args.max_runtime,
            args.mode,
        )
    except Exception as exc:  # noqa: BLE001
        # Any unexpected internal error is treated as a run failure,
        # but we still exit "cleanly" with a non-zero code.
        logger.exception("Unexpected internal error during pipeline run: %r", exc)
        return 1

    if not success:
        return 1

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Public CLI entry point.

    This is the function actually called when running the script as:

        python3 gst_runner.py ...

    For production execution, it simply forwards to run_application()
    with the real GStreamer initialization and running implementations.
    """
    return run_application(
        argv=argv,
        initialize_gst_fn=initialize_gstreamer_logging,
        run_fn=run_pipeline,
    )


if __name__ == "__main__":
    # Run main() and exit with the returned code.
    sys.exit(main())
