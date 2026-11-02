#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
GStreamer Pipeline Validator for DLSPS 2.0

Starts a pipeline description and waits for it to reach PLAYING, checking
that it does so without emitting any GStreamer ERROR.

Why this exists
----------------
:mod:`core.gst_worker` can host multiple concurrent pipelines inside one
long-lived process (so pipelines sharing a ``model-instance-id`` can
actually benefit from that sharing). But that also means a single bad
pipeline description could, in principle, destabilize a worker process
that is also hosting other, unrelated pipelines.

This validator runs a candidate pipeline description FIRST, on its own, in
a short-lived, fully isolated subprocess. Only if that validation passes
does ``pipeline_manager.py`` then hand the (unchanged) pipeline description
off to the single, shared, long-lived :mod:`core.gst_worker` process for
real execution.

Validation semantics
---------------------
FAIL if:
  * ``Gst.parse_launch()`` raises, OR
  * GStreamer logs an ERROR during parsing, OR
  * a GStreamer ERROR is observed on the bus at any point.

PASS if:
  * the pipeline parses, and
  * it reaches PLAYING (or EOS, for very short test clips) without any
    ERROR.

Because GStreamer prerolls before completing the PAUSED -> PLAYING
transition, reaching PLAYING already implies that at least one buffer has
flowed all the way through every element in the pipeline — including
through any inference elements — so it is a meaningful validation signal
on its own. Validation therefore returns as soon as PLAYING is reached
instead of keeping the pipeline running for a fixed extra duration
afterwards.

This module has no internal timeout: a pipeline that never reaches
PLAYING (e.g. because of an unreachable source) will hang here
indefinitely. Guarding against that is the caller's responsibility —
``pipeline_manager.py`` runs this validator as a subprocess bounded by an
external ``subprocess.run(..., timeout=...)``, which kills the subprocess
(and thus this hang) if it takes too long.

CLI usage
---------
    python3 gst_validator.py [--log-level LEVEL] <pipeline...>

Exit code 0 means the pipeline is valid; 1 means it is not (or an
unexpected internal error occurred).
"""

import argparse
import gc
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

# When launched directly as a subprocess, sys.path[0] is the "core"
# directory rather than "src". Add the parent "src" directory so that the
# "core.publishers" package can be imported.
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

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

    * stdout_handler - handles all log records with level < ERROR,
      writing them to stdout.
    * stderr_handler - handles ERROR and CRITICAL records (including those
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
    return logging.getLogger("gst_validator")


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

    All messages are logged without the GStreamer category - only the
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
    # Note: GStreamer debug levels use lower values for higher severity:
    # ERROR=1, WARNING=2, FIXME=3, INFO=4, DEBUG=5, LOG=6, TRACE=7
    if level <= Gst.DebugLevel.ERROR:
        logger.error("%s", text)
    elif level <= Gst.DebugLevel.WARNING:
        logger.warning("%s", text)
    elif level <= Gst.DebugLevel.INFO:
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

    # Register Python GStreamer publisher sink elements.  This must happen
    # after Gst.init() because Gst.Plugin.register_static() is called at
    # module import time inside each publisher module.
    try:
        from core.publishers import register_all  # noqa: PLC0415

        register_all()
    except Exception as _pub_exc:  # pylint: disable=broad-except
        logger.warning("Publisher element registration failed: %s", _pub_exc)

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
    if level <= Gst.DebugLevel.ERROR:
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
# Bounded pipeline execution
###############################################################################


@dataclass
class _ValidationState:
    """Internal state tracked during a single validation run."""

    error_seen: bool = False
    eos_seen: bool = False
    reason: Optional[str] = None


class _PipelineValidator:
    """Runs an already-parsed pipeline until it reaches PLAYING (or fails),
    watching for GStreamer ERRORs on the bus.

    There is no internal timeout here: validation returns as soon as the
    pipeline reaches PLAYING, hits EOS, or errors. A pipeline that never
    reaches PLAYING (e.g. an unreachable source) will hang in :meth:`run`
    indefinitely -- guarding against that is the caller's responsibility
    (``pipeline_manager.py`` bounds the whole validator subprocess with an
    external ``subprocess.run(..., timeout=...)``).
    """

    def __init__(self, pipeline: Gst.Pipeline):
        self._pipeline = pipeline
        self._state = _ValidationState()
        self._logger = get_logger()

    def _on_bus_message(self, _bus: Gst.Bus, message: Gst.Message, loop: GLib.MainLoop) -> bool:
        mtype = message.type

        if mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            debug = debug.replace("\r", " ").replace("\n", " ")
            self._logger.error(
                "Validation: pipeline error: %s (debug: %s)", err.message, debug
            )
            self._state.error_seen = True
            self._state.reason = self._state.reason or "error"
            loop.quit()
        elif mtype == Gst.MessageType.EOS:
            self._logger.info("Validation: pipeline reached EOS before reaching PLAYING.")
            self._state.eos_seen = True
            self._state.reason = self._state.reason or "eos"
            loop.quit()
        elif mtype == Gst.MessageType.STATE_CHANGED and message.src == self._pipeline:
            _old, new, _pending = message.parse_state_changed()
            if new == Gst.State.PLAYING:
                self._logger.info("Validation: pipeline reached PLAYING.")
                self._state.reason = self._state.reason or "playing"
                loop.quit()

        return True

    def run(self) -> Tuple[bool, Optional[str]]:
        """Wait for the pipeline to reach PLAYING (or fail) and return (ok, reason).

        Validation ends as soon as one of these happens, whichever is first:
        the pipeline reaches PLAYING, a GStreamer ERROR is observed, or EOS
        is reached. There is no internal timeout.

        Returns:
            (True, "playing" | "eos")
                if the pipeline reached PLAYING (or EOS, for very short
                test clips) with no ERROR observed.
            (False, "error")
                if a GStreamer ERROR was observed on the bus at any point.
        """
        bus = self._pipeline.get_bus()
        loop = GLib.MainLoop()

        bus.add_signal_watch()
        handler_id = bus.connect("message", self._on_bus_message, loop)

        ret = self._pipeline.set_state(Gst.State.PLAYING)
        self._logger.debug("Validation: requested pipeline state PLAYING, result: %s", ret)

        try:
            loop.run()
        finally:
            try:
                bus.disconnect(handler_id)
            except Exception:  # noqa: BLE001
                pass
            bus.remove_signal_watch()
            try:
                self._pipeline.set_state(Gst.State.NULL)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Validation: error while stopping pipeline: %r", exc)

        if drain_bus_messages(bus, self._logger):
            if not self._state.error_seen:
                self._state.error_seen = True
                self._state.reason = self._state.reason or "error"

        if self._state.error_seen:
            return False, self._state.reason or "error"
        return True, self._state.reason


###############################################################################
# High-level validation and CLI
###############################################################################


def validate_pipeline(pipeline_description: str) -> Tuple[bool, Optional[str]]:
    """High-level pipeline validation helper.

    Combines parsing (via :func:`parse_pipeline`) and waiting for PLAYING
    into a single call. There is no internal timeout; see the module
    docstring for why (the caller is expected to bound this externally).

    Args:
        pipeline_description: Textual GStreamer pipeline description.

    Returns:
        (True, reason)  if the pipeline is considered valid.
        (False, reason) if the pipeline failed to parse or errored while running.
    """
    logger = get_logger()

    pipeline, parsed_ok = parse_pipeline(pipeline_description)
    if not parsed_ok or pipeline is None:
        logger.error("Pipeline validation failed: pipeline parsing error.")
        return False, "parse_error"

    try:
        ok, reason = _PipelineValidator(pipeline).run()
    finally:
        # Ensure the pipeline is always set to NULL, even if something goes
        # wrong in the validator, then force GObject finalization so any
        # element cleanup happens promptly.
        try:
            pipeline.set_state(Gst.State.NULL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Validation: error during final cleanup: %r", exc)
        del pipeline
        gc.collect()

    return ok, reason


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="GStreamer Pipeline Validator",
        description=(
            "Parse a GStreamer pipeline description and wait for it to "
            "reach PLAYING to check that it does not error out, without "
            "running it for production."
        ),
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Minimum log level to use (default: %(default)s).",
    )

    parser.add_argument(
        "pipeline",
        nargs="+",
        help=(
            "GStreamer pipeline description to validate. All positional "
            "arguments are joined with spaces into a single string before "
            "being passed to Gst.parse_launch()."
        ),
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Public CLI entry point.

    Exit code 0 means the pipeline is valid; 1 means it is not (or an
    unexpected internal error occurred).
    """
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    configure_root_logging(log_level)
    logger = get_logger()

    logger.debug("Parsed arguments: %s", args)

    try:
        initialize_gstreamer_logging()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize GStreamer: %r", exc)
        return 1

    pipeline_description = " ".join(args.pipeline)
    logger.debug("Validating pipeline: %s", pipeline_description)

    try:
        ok, reason = validate_pipeline(pipeline_description)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected internal error during pipeline validation: %r", exc)
        return 1

    if not ok:
        logger.error("Pipeline validation FAILED (reason: %s).", reason or "unknown")
        return 1

    logger.info("Pipeline validation PASSED (reason: %s).", reason or "unknown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
