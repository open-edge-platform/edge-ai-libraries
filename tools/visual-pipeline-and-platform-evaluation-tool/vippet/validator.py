#!/usr/bin/env python3
"""
GStreamer Pipeline Validator

This module provides a small command-line tool and library API for
*validating* GStreamer pipeline descriptions.

The validation logic is intentionally conservative and focuses on
detecting obvious early failures rather than running pipelines to
completion. More concretely, the validator:

1. Initializes GStreamer and hooks its debug logging into Python's logging.
2. Parses a textual pipeline description via Gst.parse_launch().
3. Treats the parse as FAILED if:
   - Gst.parse_launch() raises an exception, OR
   - any GStreamer ERROR-level log is emitted during parsing.
4. If parsing succeeds without ERRORs:
   - starts the pipeline (PLAYING),
   - runs it under a GLib.MainLoop for a short, configurable window
     (max-runtime),
   - watches the bus for GStreamer ERROR and EOS messages.
5. Stops the pipeline when:
   - an ERROR is observed on the bus (validation FAIL), OR
   - EOS is observed on the bus (validation SUCCESS), OR
   - the max-runtime timeout elapses; in this case the pipeline is
     stopped and, if no ERRORs were observed at any point, the run is
     considered SUCCESS by timeout.

The validator does NOT aim to verify that the pipeline produces correct
application-level output or runs to natural EOS. It is a "smoke test"
for:

- pipeline description validity,
- early element/linking failures,
- failures that surface during a short initial run or on shutdown.

Validation semantics:

- Failure (exit code 1):
  * pipeline cannot be parsed (exception in parse_launch), OR
  * any GStreamer ERROR is logged during parsing (even if parse_launch
    returns a pipeline object), OR
  * a GStreamer ERROR is observed on the bus at ANY time during the run
    or shutdown.
- Success (exit code 0):
  * the pipeline is parsed successfully AND
  * no GStreamer ERROR appears during parsing, run, or shutdown.
  * reaching the max-runtime and stopping the pipeline due to timeout is
    considered SUCCESS, provided no ERRORs were seen.

The script is designed to:

- Be robust and production ready (clear logging, careful cleanup).
- Be suitable to be called as a subprocess by another application.
- Be unit-test-friendly: the core logic is factored into functions that can be
  tested without requiring a real GStreamer environment (via dependency injection).
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
    return logging.getLogger("validator")


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
    validator's perspective such pipelines should be rejected before any
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
# Short-run validation using a GLib.MainLoop
###############################################################################


@dataclass
class _RunState:
    """Internal state tracked during a single validation run."""

    error_seen: bool = False
    eos_seen: bool = False
    timeout_triggered: bool = False
    reason: Optional[str] = None


class _ValidationRunner:
    """Internal helper that runs a pipeline under a short validation window.

    This class encapsulates:

    - A GLib.MainLoop driving the pipeline, similar to gst-launch.
    - A timeout that stops the pipeline after a short period.
    - A bus message handler that records ERROR/EOS and terminates the loop.

    The goal is to detect early failures (ERRORs) while allowing the pipeline
    to start and run briefly without requiring it to reach EOS.

    Timeout semantics:

    - If an ERROR or EOS is observed before the timeout, the loop is stopped
      immediately and the outcome is derived from the observed messages.
    - If the timeout elapses first, the pipeline is stopped (set to NULL) and
      the loop is quit. Provided no ERRORs were observed, this is considered
      a successful validation by timeout.
    """

    def __init__(self, pipeline: Gst.Pipeline, max_run_time_sec: float):
        if not isinstance(pipeline, Gst.Pipeline):
            raise TypeError("pipeline must be a Gst.Pipeline instance")

        self._pipeline = pipeline
        self._max_run_time_sec = max_run_time_sec
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
            self._logger.error(
                "Pipeline runtime error during validation: %s (debug: %s)",
                err.message,
                debug,
            )
            self._state.error_seen = True
            self._state.reason = self._state.reason or "error"
            loop.quit()

        elif msg_type == Gst.MessageType.EOS:
            self._logger.info("Pipeline produced EOS during validation run.")
            self._state.eos_seen = True
            self._state.reason = self._state.reason or None
            loop.quit()

        return True

    def _hard_timeout_thread(self, loop: GLib.MainLoop):
        """Thread that enforces the maximum validation runtime.

        After `max_run_time_sec` seconds, this thread stops the pipeline and
        quits the main loop, regardless of whether EOS was reached.

        Note:
            If an ERROR or EOS has already terminated the run, this thread
            does nothing. Otherwise, it performs a controlled stop of the
            pipeline and ends the validation window, which is treated as a
            success by timeout (provided no ERRORs are found on the bus).
        """
        time.sleep(self._max_run_time_sec)

        # If an ERROR or EOS already terminated the run, do nothing.
        if self._state.error_seen or self._state.eos_seen:
            return

        self._logger.info(
            "Validation timeout (%.1f s) elapsed; stopping pipeline.",
            self._max_run_time_sec,
        )
        self._state.timeout_triggered = True
        self._state.reason = self._state.reason or "timeout"

        try:
            self._pipeline.set_state(Gst.State.NULL)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Error while stopping pipeline on timeout: %r", exc)

        # Quit the loop so that run() can proceed to final evaluation.
        loop.quit()

    def run(self) -> Tuple[bool, Optional[str]]:
        """Run the pipeline under validation and return (ok, reason).

        The sequence is:

        1. Obtain the pipeline's bus and create a GLib.MainLoop.
        2. Attach a bus watch and connect _on_bus_message for ERROR/EOS.
        3. Request PLAYING state on the pipeline.
        4. Call get_state() with a short timeout (for diagnostics only) to
           log the initial state-change outcome.
        5. Start a background thread that will trigger a hard timeout after
           max_run_time_sec.
        6. Run the GLib.MainLoop until:
             - ERROR on the bus, OR
             - EOS on the bus, OR
             - the timeout thread calls loop.quit().
        7. After the loop exits, stop the pipeline, remove the bus watch,
           drain any remaining bus messages for logging, and derive the
           final validation result from _RunState.

        Returns:
            (True, None)
                if the pipeline is considered valid (EOS or clean run
                before timeout, and no errors on the bus).
            (True, "timeout")
                if the pipeline was stopped by timeout with no errors
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
        # This does not control validation outcome directly; runtime errors
        # are still detected via bus messages and the timeout thread.
        state_change_ret, current_state, pending = self._pipeline.get_state(
            5 * Gst.SECOND,
        )
        self._logger.debug(
            "Initial state change result: %s, current: %s, pending: %s",
            state_change_ret,
            current_state,
            pending,
        )

        # Start hard-timeout thread.
        timeout_thread = threading.Thread(
            target=self._hard_timeout_thread,
            args=(loop,),
            daemon=True,
        )
        timeout_thread.start()

        # Run main loop until:
        #   - ERROR (bus handler quits loop),
        #   - EOS   (bus handler quits loop),
        #   - hard timeout thread quits loop.
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
        if self._state.timeout_triggered and not self._state.error_seen:
            return True, "timeout"
        # EOS or normal stop without errors.
        return True, None


def run_pipeline_for_short_validation(
    pipeline: Gst.Pipeline,
    max_run_time_sec: float,
) -> Tuple[bool, Optional[str]]:
    """Run the pipeline briefly to validate that it starts without errors.

    This is a thin wrapper around _ValidationRunner to keep the public
    interface simple and testable.

    Args:
        pipeline: A GStreamer pipeline created by parse_launch().
        max_run_time_sec: Maximum time in seconds for which we observe the
                          pipeline. Passing this timeout is NOT an error unless
                          shutdown then produces GStreamer errors.

    Returns:
        (True, None)       if the pipeline is considered valid (EOS or clean
                           run before timeout and clean shutdown).
        (False, "error")  if a GStreamer ERROR was observed.
        (True, "timeout") if we stopped due to timeout with NO error. Timeout
                           is considered SUCCESS.
    """
    runner = _ValidationRunner(pipeline, max_run_time_sec)
    return runner.run()


###############################################################################
# High-level validation and CLI
###############################################################################


def validate_pipeline(
    pipeline_description: str,
    max_run_time_sec: float,
) -> bool:
    """High-level pipeline validation helper.

    This function combines parsing and a short run of the pipeline into a
    single high-level operation suitable for use in main() and in unit tests.

    Validation rules:

    - If parsing fails (exception OR parse-time GStreamer ERRORs) ->
      validation FAILS.
    - If parsing succeeds but the pipeline emits a GStreamer ERROR at any
      moment during the run or shutdown -> validation FAILS.
    - If the pipeline runs and:
        * reaches EOS within the time window, OR
        * stays alive without errors until the timeout is reached and shuts
          down cleanly without errors,
      -> validation SUCCEEDS.

    Args:
        pipeline_description: Textual GStreamer pipeline description.
        max_run_time_sec: Maximum allowed observation time in seconds.

    Returns:
        True  if the pipeline is considered valid.
        False otherwise.
    """
    logger = get_logger()

    pipeline, parsed_ok = parse_pipeline(pipeline_description)
    if not parsed_ok or pipeline is None:
        logger.error("Validation failed: pipeline parsing error.")
        return False

    run_ok: bool = False
    failure_reason: Optional[str] = None

    try:
        run_ok, failure_reason = run_pipeline_for_short_validation(
            pipeline=pipeline,
            max_run_time_sec=max_run_time_sec,
        )
    finally:
        # Ensure the pipeline is always set to NULL, even if something goes
        # wrong in the validation runner.
        try:
            logger.debug("Final pipeline cleanup (ensuring NULL state).")
            pipeline.set_state(Gst.State.NULL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error while cleaning up pipeline: %r", exc)

    if not run_ok:
        logger.error(
            "Validation failed: pipeline runtime error (reason: %s).",
            failure_reason or "unknown",
        )
        return False

    if failure_reason == "timeout":
        logger.info(
            "Validation succeeded by timeout: pipeline ran for the whole "
            "max-runtime and shut down without GStreamer errors."
        )
    else:
        logger.info("Validation succeeded: pipeline is considered healthy.")

    return True


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional list of arguments to parse. If None, sys.argv is used.
              This parameter makes the function easier to test.

    Returns:
        Parsed arguments as an argparse.Namespace instance.
    """
    parser = argparse.ArgumentParser(
        prog="GStreamer Pipeline Validator",
        description=(
            "Validate a GStreamer pipeline by starting it and observing it "
            "for a short time window. The validator only checks for early "
            "GStreamer errors and does NOT require the pipeline to run "
            "until EOS."
        ),
    )

    parser.add_argument(
        "--max-runtime",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help=(
            "Maximum time (in seconds) to observe the pipeline after starting "
            "it. If the pipeline does not reach EOS or error within this time, "
            "it is considered VALID (timeout is NOT a failure as long as "
            "no errors are observed). Default: %(default).1f seconds."
        ),
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help=(
            "Minimum log level to use for both the validator and the "
            "GStreamer-to-logging bridge (default: %(default)s)."
        ),
    )

    parser.add_argument(
        "pipeline",
        nargs="+",
        help=(
            "GStreamer pipeline description to be validated. "
            "All positional arguments are joined with spaces into a single "
            "string before being passed to Gst.parse_launch()."
        ),
    )

    return parser.parse_args(argv)


def run_application(
    argv: Optional[List[str]],
    initialize_gst_fn: Callable[[], None],
    validate_fn: Callable[[str, float], bool],
) -> int:
    """Core implementation of the CLI entry point with dependency injection.

    This function contains the actual main() logic, but accepts the GStreamer
    initialization function and the pipeline validation function as arguments.

    Benefits:

    - In production, we call it with real implementations:
          initialize_gst_fn = initialize_gstreamer_logging
          validate_fn      = validate_pipeline
    - In unit tests, we can call it with fake/mocked implementations,
      without relying on monkeypatching module-level symbols.

    Args:
        argv: Optional list of CLI arguments (like sys.argv[1:]).
        initialize_gst_fn: Function used to initialize GStreamer and logging.
        validate_fn: Function used to validate the pipeline string. The callable
                     MUST accept (pipeline_description: str,
                     max_run_time_sec: float) in this order.

    Returns:
        0 on successful validation,
        1 on validation failure or unexpected internal error.
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

    # Initialize GStreamer and its logging bridge.
    try:
        initialize_gst_fn()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize GStreamer: %r", exc)
        return 1

    # Join the pipeline pieces into a single string.
    pipeline_description = " ".join(args.pipeline)
    logger.info("Validating pipeline: %s", pipeline_description)

    try:
        valid = validate_fn(
            pipeline_description,
            args.max_runtime,
        )
    except Exception as exc:  # noqa: BLE001
        # Any unexpected internal error is treated as a validation failure,
        # but we still exit "cleanly" with a non-zero code.
        logger.exception("Unexpected internal error during validation: %r", exc)
        return 1

    if not valid:
        return 1

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Public CLI entry point.

    This is the function actually called when running the script as:

        python3 validator.py ...

    For production execution, it simply forwards to run_application()
    with the real GStreamer initialization and validation implementations.
    """
    return run_application(
        argv=argv,
        initialize_gst_fn=initialize_gstreamer_logging,
        validate_fn=validate_pipeline,
    )


if __name__ == "__main__":
    # Run main() and exit with the returned code.
    sys.exit(main())
