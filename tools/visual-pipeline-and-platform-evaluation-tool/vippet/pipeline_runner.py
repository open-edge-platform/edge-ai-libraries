"""pipeline_runner.py

This module provides the PipelineRunner class for executing GStreamer pipelines
and extracting performance metrics (FPS).

The runner uses gst_runner.py to execute pipelines in either normal or validation
mode, providing unified interface for both production pipeline execution and
pipeline validation.
"""

import json
import logging
import os
import re
import select
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from subprocess import PIPE, Popen

import psutil as ps


@dataclass
class LatencyTracerSample:
    """
    Last observed DLStreamer ``latency_tracer`` sample for a single stream.

    This is a deliberately runner-local dataclass: it MIRRORS
    :class:`internal_types.InternalLatencyMetrics` one-to-one in terms
    of fields and semantics, but lives next to the subprocess parser
    so ``pipeline_runner`` does not need to import from
    ``internal_types`` (that would create a circular import:
    ``pipeline_runner`` → ``internal_types`` → ``graph`` →
    ``videos`` → ``pipeline_runner``).

    Callers of :meth:`PipelineRunner.run` are expected to map this
    type onto ``InternalLatencyMetrics`` when copying the result into
    an internal job-status object — see
    ``TestsManager._execute_performance_test`` for the canonical
    conversion site.

    All timing fields are in milliseconds (as reported by the tracer).
    ``fps`` is intentionally NOT stored because FPS is already exposed
    via ``gvafpscounter`` on :class:`PipelineResult`, so re-reporting it
    here would just duplicate state.

    Attributes:
        interval_ms: Length of the measurement window (``interval``).
        avg_ms: Average frame latency over the window (``avg``).
        min_ms: Minimum frame latency observed in the window (``min``).
        max_ms: Maximum frame latency observed in the window (``max``).
        latency_ms: Current end-to-end latency reported by the tracer
            (``latency``).
    """

    interval_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    latency_ms: float


@dataclass
class PipelineResult:
    """Unified result of a pipeline run.

    Used for both normal and validation modes. In normal mode, FPS fields
    contain extracted metrics. In validation mode, FPS fields default to 0.0
    and exit_code + stderr are used to determine validity.

    Attributes:
        total_fps: Total FPS across all streams (normal mode).
        per_stream_fps: Average FPS per stream (normal mode).
        num_streams: Number of streams detected in metrics (normal mode).
        exit_code: Process exit code (0 = success).
        cancelled: Whether the run was cancelled by the user.
        stdout: Captured stdout lines from gst_runner.py.
        stderr: Captured stderr lines from gst_runner.py.
        details: Human-readable description of which FPS metric source was
            selected and for how many streams, or None if not applicable.
        latency_tracer_metrics: Last observed DLStreamer `latency_tracer`
            sample per stream, keyed by ``stream_id``
            (``"{source_name}__{sink_name}"``).

            * ``None`` when the runner was started with
              ``enable_latency_metrics=False`` — the tracer was not
              activated at all, so no samples could ever be produced.
            * Empty ``dict`` when the tracer was active but produced no
              samples (e.g. the pipeline exited before the first 1000 ms
              interval closed, or the tracer output was not forwarded).
            * Non-empty ``dict`` otherwise. Only the latest sample per
              stream is kept; earlier samples for the same stream are
              overwritten as new interval lines arrive.
    """

    total_fps: float = 0.0
    per_stream_fps: float = 0.0
    num_streams: int = 0
    exit_code: int = 0
    cancelled: bool = False
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    details: str | None = None
    latency_tracer_metrics: "dict[str, LatencyTracerSample] | None" = None

    def __repr__(self):
        # `latency_tracer_metrics` is reported by its cardinality only so
        # the repr stays compact even when many streams are running.
        if self.latency_tracer_metrics is None:
            latency_repr = "latency_tracer_metrics=None"
        else:
            latency_repr = (
                f"latency_tracer_metrics=<{len(self.latency_tracer_metrics)} stream(s)>"
            )
        return (
            f"PipelineResult("
            f"total_fps={self.total_fps}, "
            f"per_stream_fps={self.per_stream_fps}, "
            f"num_streams={self.num_streams}, "
            f"exit_code={self.exit_code}, "
            f"cancelled={self.cancelled}, "
            f"details={self.details!r}, "
            f"{latency_repr}"
            f")"
        )


class PipelineRunner:
    """
    A class for running GStreamer pipelines in normal or validation mode.

    This class handles the execution of GStreamer pipeline commands using
    gst_runner.py and provides two operational modes:

    - normal mode: Runs pipelines for production use, extracting FPS metrics.
    - validation mode: Runs pipelines for a limited time to verify correctness.

    The runner manages the full lifecycle of gst_runner.py subprocess execution,
    including timeout enforcement, output parsing, and error handling.
    """

    # Default metrics-service URL for pushing FPS metrics
    DEFAULT_METRICS_SERVICE_URL = "http://metrics-service:9090"

    # ------------------------------------------------------------------
    # latency_tracer configuration
    #
    # When `enable_latency_metrics=True`, the GStreamer subprocess is
    # launched with the DLStreamer `latency_tracer` active in
    # pipeline-only mode with a 1000 ms aggregation interval. Tracer
    # samples are emitted by GStreamer at TRACE level and routed through
    # `gst_runner.py`'s log bridge, which promotes
    # `latency_tracer_pipeline_interval` messages to INFO so they appear
    # on the subprocess stdout as `gst_runner - INFO - ...` lines and
    # are forwarded to our logger by `_is_loggable_gst_runner_line`.
    # Those lines are then parsed by `_parse_and_record_latency_sample`
    # to populate `self.latency_tracer_metrics`.
    # ------------------------------------------------------------------
    LATENCY_TRACER_GST_DEBUG = "GST_TRACER:7"
    LATENCY_TRACER_GST_TRACERS = "latency_tracer(flags=pipeline,interval=1000)"

    # ------------------------------------------------------------------
    # latency_tracer output parser
    #
    # Every 1000 ms the tracer emits ONE line per running stream, for
    # example (single line, reformatted here for readability)::
    #
    #   latency_tracer_pipeline_interval,
    #   source_name=(string)src_p0_s0_0_0,
    #   sink_name=(string)sink_p0_s0_0_0,
    #   interval=(double)1000.25, avg=(double)364.31,
    #   min=(double)0.004, max=(double)529.26,
    #   latency=(double)21.28, fps=(double)46.99;
    #
    # In our stack these lines reach us on the subprocess stdout with the
    # `gst_runner - INFO - ` prefix (see gst_runner._log_gst_message for
    # the promotion from GST_TRACER:7 to python INFO).
    #
    # The regex below is intentionally ONE compiled `re.Pattern`
    # instance (built at module-import time) because the parser runs in
    # the hot stdout-reading loop — one subprocess line per stream per
    # second. Using named groups + `re.search` with a single pattern
    # keeps per-line parsing at a single regex operation; there is no
    # backtracking cost because every field appears at most once.
    #
    # Notes on the pattern:
    #   * We anchor on the literal marker `latency_tracer_pipeline_interval,`
    #     and match everywhere in the line (no `^` anchor) so any log
    #     prefix — `gst_runner - INFO - `, a timestamp, etc. — is
    #     simply ignored.
    #   * Between the marker and each captured field we allow any
    #     characters (``.*?``, non-greedy). The tracer optionally emits
    #     extra leading fields such as ``pipeline_name=(string)pipelineN``
    #     that we neither need nor want; tolerating arbitrary text keeps
    #     the parser forward-compatible with future tracer additions.
    #     Non-greedy quantifiers together with fixed literal field
    #     anchors (``source_name=(string)``, ``sink_name=(string)``, ...)
    #     keep the effective match linear in line length.
    #   * The DLStreamer tracer emits double values as plain decimals
    #     (`364.31`, `0.004`); no scientific notation, no sign. A strict
    #     `\d+\.\d+` is enough and cheaper than `[\d.eE+\-]+`.
    #   * Fields are matched in the exact order emitted by the tracer,
    #     which avoids the quadratic cost of independent lookups.
    #   * `fps` is captured but intentionally discarded at the Python
    #     level — FPS is already reported by `gvafpscounter` on the
    #     `PipelineResult`, so re-exposing it here would only duplicate
    #     state. Keeping the group in the regex still documents the
    #     full tracer layout and lets us drop it without re-parsing
    #     should the need arise.
    # ------------------------------------------------------------------
    _LATENCY_TRACER_INTERVAL_MARKER = "latency_tracer_pipeline_interval,"
    _LATENCY_TRACER_INTERVAL_PATTERN = re.compile(
        r"latency_tracer_pipeline_interval,"
        r".*?source_name=\(string\)(?P<source>[^,]+),"
        r".*?sink_name=\(string\)(?P<sink>[^,]+),"
        r".*?interval=\(double\)(?P<interval>\d+\.\d+),"
        r".*?avg=\(double\)(?P<avg>\d+\.\d+),"
        r".*?min=\(double\)(?P<min>\d+\.\d+),"
        r".*?max=\(double\)(?P<max>\d+\.\d+),"
        r".*?latency=\(double\)(?P<latency>\d+\.\d+),"
        r".*?fps=\(double\)(?P<fps>\d+\.\d+)"
    )

    def __init__(
        self,
        mode: str = "normal",
        max_runtime: float = 0.0,
        poll_interval: int = 1,
        inactivity_timeout: int = 120,
        hard_timeout: int | None = None,
        enable_latency_metrics: bool = False,
    ):
        """
        Initialize the PipelineRunner.

        Args:
            mode: Execution mode - either "normal" or "validation".
                - normal: Run pipeline for production use (default).
                - validation: Run pipeline for limited time to verify correctness.
            max_runtime: Maximum time in seconds for pipeline execution.
                - For normal mode: 0 means run until EOS, >0 means stop after duration.
                - For validation mode: must be >0.
            poll_interval: Interval in seconds to poll the process for metrics
                (only used in normal mode).
            inactivity_timeout: Max seconds to wait without new stdout/stderr logs
                before treating the pipeline as hung and terminating it
                (only used in normal mode).
            hard_timeout: Absolute maximum time in seconds before forcibly killing
                the subprocess regardless of state (only used in validation mode).
                If None in validation mode, defaults to max_runtime + 60.
            enable_latency_metrics: When True, activates the DLStreamer
                `latency_tracer` in pipeline-only mode with a 1000 ms interval
                by augmenting the GStreamer subprocess environment with
                `GST_DEBUG=GST_TRACER:7` (appended to any existing value) and
                `GST_TRACERS=latency_tracer(flags=pipeline,interval=1000)`.
                When False (default), neither variable is modified.
        """
        self.mode = mode
        self.max_runtime = max_runtime
        self.poll_interval = poll_interval
        self.inactivity_timeout = inactivity_timeout
        self.hard_timeout = hard_timeout
        # Resolve the metrics-service base URL once and pre-compute the
        # full endpoint used by `_push_fps_metric`. Trailing slashes on
        # the configured base are stripped so concatenation with the
        # fixed path cannot produce `//api/v1/...`, which some proxies
        # and routers treat as a distinct (and unmapped) path.
        self.metrics_service_url = os.environ.get(
            "METRICS_SERVICE_URL", self.DEFAULT_METRICS_SERVICE_URL
        ).rstrip("/")
        self._metrics_service_fps_url = (
            f"{self.metrics_service_url}/api/v1/metrics/simple"
        )
        self.enable_latency_metrics = enable_latency_metrics
        self.logger = logging.getLogger("PipelineRunner")
        self.logger_level = self._get_log_level()
        self.logger.setLevel(self.logger_level)
        self.cancelled = False

        # Map of stream_id -> last observed latency_tracer sample.
        #
        # `None` when `enable_latency_metrics=False`: the tracer is not
        # started, so no mapping can exist. When enabled, the map is
        # allocated as an empty dict at the start of each run (in
        # `_run_normal`) and overwritten per stream as new interval
        # lines arrive. Only the latest sample per stream is retained;
        # no history is kept.
        self.latency_tracer_metrics: "dict[str, LatencyTracerSample] | None" = (
            None if not enable_latency_metrics else {}
        )

        # Set of stream_ids the latency_tracer parser is allowed to
        # record. Populated per-run from `PipelineRunner.run()`. `None`
        # means "no filtering — keep every parsed sample".
        self._allowed_stream_ids: set[str] | None = None

        # Validate mode
        if self.mode not in ("normal", "validation"):
            raise ValueError(
                f"Invalid mode '{self.mode}'. Must be 'normal' or 'validation'."
            )

        # Validate max_runtime for validation mode
        if self.mode == "validation":
            if self.max_runtime <= 0:
                raise ValueError(
                    "Validation mode requires max_runtime > 0. "
                    "Received max_runtime={}.".format(self.max_runtime)
                )
            # Set default hard_timeout for validation if not provided
            if self.hard_timeout is None:
                self.hard_timeout = int(self.max_runtime + 60)

    def run(
        self,
        pipeline_command: str,
        total_streams: int = 1,
        allowed_stream_ids: set[str] | None = None,
    ) -> PipelineResult:
        """
        Run a GStreamer pipeline and return results.

        The pipeline is executed using gst_runner.py with the configured mode
        and max-runtime parameters.

        Args:
            pipeline_command: The complete GStreamer pipeline command string.
            total_streams: Total number of streams to expect in metrics
                (only used in normal mode for FPS extraction).
            allowed_stream_ids: Optional set of ``stream_id`` values
                (``"{source_name}__{sink_name}"``) that identify the
                user-facing source/sink pairs of the running streams.
                When provided, the latency_tracer parser only keeps
                samples whose ``stream_id`` is in this set — every
                other row (e.g. internal bin sinks named ``sink``, the
                intermediate ``splitmuxsink`` of a recorder pipeline,
                etc.) is dropped. When ``None`` (default), all parsed
                samples are kept; this is intended for ad-hoc tests
                where the caller does not know the set of stream ids
                up front. Has no effect when
                ``enable_latency_metrics=False``.

        Returns:
            PipelineResult with FPS metrics, exit code, and captured output.

        Raises:
            RuntimeError: If pipeline execution fails in normal mode.
        """
        # Normalize and store on the instance so the stdout hot loop
        # can cheaply consult it via `_parse_and_record_latency_sample`.
        # An empty set is treated as "no streams allowed" and will drop
        # every sample; that is only correct if the caller actually
        # passed an empty set, which is a programmer error we do not
        # try to hide.
        self._allowed_stream_ids: set[str] | None = allowed_stream_ids

        if self.mode == "validation":
            return self._run_validation(pipeline_command)
        else:
            return self._run_normal(pipeline_command, total_streams)

    def _run_validation(self, pipeline_command: str) -> PipelineResult:
        """
        Run pipeline in validation mode.

        This method executes gst_runner.py with --mode validation and enforces
        the configured hard_timeout.

        Args:
            pipeline_command: GStreamer pipeline description string.

        Returns:
            PipelineResult with exit_code and stderr for determining validity.
        """
        cmd = [
            sys.executable,
            "gst_runner.py",
            "--mode",
            "validation",
            "--max-runtime",
            str(self.max_runtime),
            "--log-level",
            self.logger_level,
            pipeline_command,
        ]

        self.logger.debug(
            "Starting validation subprocess with cmd=%s, pipeline=%s",
            cmd,
            pipeline_command,
        )

        # Start subprocess with pipes for stdout/stderr
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._build_subprocess_env(),
            text=True,
        )

        try:
            # Wait for completion up to the hard timeout
            stdout, stderr = proc.communicate(timeout=self.hard_timeout)
        except subprocess.TimeoutExpired:
            # If process exceeds hard timeout, kill it
            self.logger.warning(
                "gst_runner.py timed out after %s seconds, killing process",
                self.hard_timeout,
            )
            self._graceful_terminate(proc)
            stdout, stderr = proc.communicate()
            errors = self._parse_validation_stderr(stderr)
            errors.append(
                "Pipeline validation timed out: gst_runner.py did not finish "
                "within the allowed time and had to be terminated."
            )
            return PipelineResult(
                exit_code=proc.returncode if proc.returncode is not None else -1,
                cancelled=False,
                stdout=stdout.splitlines() if stdout else [],
                stderr=errors,
                # Validation mode does not parse tracer samples. Propagate
                # the instance map as-is so the API semantics documented on
                # `PipelineResult.latency_tracer_metrics` hold:
                # `None` → tracer disabled, `{}` → enabled but no samples
                # were (or could be) collected.
                latency_tracer_metrics=self.latency_tracer_metrics,
            )

        return PipelineResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            cancelled=False,
            stdout=stdout.splitlines() if stdout else [],
            stderr=self._parse_validation_stderr(stderr),
            # See note above: validation mode never populates the map,
            # so this reflects only whether the tracer was enabled.
            latency_tracer_metrics=self.latency_tracer_metrics,
        )

    def _run_normal(self, pipeline_command: str, total_streams: int) -> PipelineResult:
        """
        Run pipeline in normal mode and extract FPS metrics.

        This method executes gst_runner.py with --mode normal and monitors
        the output for FPS metrics from gvafpscounter.

        After pipeline completion (success or failure), writes 0.0 to the FPS
        file to indicate that the pipeline is no longer running.

        ## gvafpscounter emits three types of FPS metrics:

        - **last**: FPS measured over only the most recent N-second window.
          Resets after each print. Highly volatile — can spike during queue
          flush at shutdown (e.g. 330 fps in a 0.47s window).

        - **average**: Cumulative mean FPS from the first measured frame to
          now. Printed every ~1 second, never resets. Represents the stable
          steady-state throughput while the pipeline is actively running.

        - **overall**: Same cumulative formula as average, but printed only
          once when the pipeline terminates. Crucially, it includes the
          shutdown period — during which GStreamer flushes buffered frames
          rapidly and then streams finish unevenly. With many streams the
          teardown can take several seconds, inflating the time denominator
          while the frame numerator barely grows, resulting in a significantly
          lower FPS than the true steady-state.

        ## Why we prefer average over overall:

        With looped pipelines stopped via max_runtime, all streams are alive
        for the full measurement window (good for average stability), but the
        forced SIGINT shutdown creates a flush burst and uneven stream
        teardown. The more streams, the longer the teardown, and the bigger
        the gap between average and overall. Using overall for benchmark
        decisions causes the binary search to systematically underestimate
        pipeline capacity.

        ## Metric selection priority (post-run):

        1. Last average line matching total_streams — best steady-state metric.
        2. Overall line matching total_streams — fallback, includes shutdown.
        3. Last average line for closest total_streams — stream count mismatch
           but still a steady-state number.
        4. Last "last" line — volatile, last resort.

        Args:
            pipeline_command: GStreamer pipeline description string.
            total_streams: Total number of streams to expect in metrics.

        Returns:
            PipelineResult containing FPS metrics, exit code, and captured output.

        Raises:
            RuntimeError: If pipeline execution fails (non-zero exit code without
                cancellation, or inactivity timeout).
        """
        # Construct the command using gst_runner.py
        pipeline_cmd = [
            sys.executable,
            "gst_runner.py",
            "--mode",
            "normal",
            "--max-runtime",
            str(self.max_runtime),
            "--log-level",
            self.logger_level,
            pipeline_command,
        ]

        self.logger.info(f"Pipeline Command: {' '.join(pipeline_cmd)}")

        try:
            # Spawn command in a subprocess
            process = Popen(
                pipeline_cmd,
                stdout=PIPE,
                stderr=PIPE,
                env=self._build_subprocess_env(),
            )

            exit_code = None
            total_fps = None
            per_stream_fps = None
            num_streams = None
            details: str | None = None

            # Reset the latency_tracer map at the start of each run so
            # repeated invocations on the same runner instance (e.g. the
            # density `Benchmark` loop, which reuses a single
            # `PipelineRunner` across many pipeline runs) only expose
            # samples from the MOST RECENT run. Stays `None` when the
            # tracer is disabled — callers can rely on that to detect
            # "no metrics collected at all".
            if self.latency_tracer_metrics is not None:
                self.latency_tracer_metrics = {}

            # Storage for parsed metrics collected during the run.
            # - last_fps: most recent "last" metric (any stream count)
            # - avg_fps_dict: keyed by number_streams, value is the most recent
            #   "average" metric for that stream count (overwritten each time)
            # - overall_fps_dict: keyed by number_streams, value is the "overall"
            #   metric for that stream count (should appear at most once)
            last_fps: dict | None = None
            avg_fps_dict: dict[int, dict] = {}
            overall_fps_dict: dict[int, dict] = {}
            process_output: list[bytes] = []
            process_stderr: list[bytes] = []

            # ----------------------------------------------------------------
            # Regex patterns for the three gvafpscounter metric types.
            #
            # These patterns are MUTUALLY EXCLUSIVE: each line contains exactly
            # one of the keywords "overall", "average", or "last" inside the
            # FpsCounter(...) parentheses, so at most one pattern can match per
            # line. We use `continue` after each successful match to skip
            # unnecessary regex checks.
            # ----------------------------------------------------------------
            overall_pattern = r"FpsCounter\(overall ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            avg_pattern = r"FpsCounter\(average ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"
            last_pattern = r"FpsCounter\(last ([\d.]+)sec\): total=([\d.]+) fps, number-streams=(\d+), per-stream=([\d.]+) fps"

            # Track last activity time for inactivity timeout
            last_activity_time = time.time()

            # Poll the process to check if it is still running
            while process.poll() is None:
                if self.cancelled:
                    self._graceful_terminate(process)
                    self.logger.info(
                        "Process cancelled, sent SIGINT for graceful shutdown"
                    )
                    break

                reads, _, _ = select.select(
                    [process.stdout, process.stderr], [], [], self.poll_interval
                )

                if reads:
                    # We saw some activity on stdout/stderr
                    last_activity_time = time.time()

                for r in reads:
                    if r is None:
                        continue
                    line = r.readline()
                    if not line:
                        continue

                    if r == process.stdout:
                        process_output.append(line)

                        line_str = line.decode("utf-8")

                        # ----------------------------------------------------------
                        # Log ALL FpsCounter lines (last, average, overall) as info
                        # for diagnostics.
                        # Also log gst_runner lines at INFO level and above (skip
                        # DEBUG) so the user can see pipeline lifecycle events
                        # (e.g. "Pipeline parsed successfully", "Stopping pipeline").
                        # ----------------------------------------------------------
                        stripped = line_str.strip()
                        if stripped.startswith(
                            "FpsCounter"
                        ) or self._is_loggable_gst_runner_line(stripped):
                            self.logger.info(stripped)

                        # ----------------------------------------------------------
                        # Write the average FPS to file in real-time for monitoring.
                        # Only average is used here — it's the stable running metric.
                        # ----------------------------------------------------------
                        match = re.search(avg_pattern, line_str)
                        if match:
                            result = {
                                "total_fps": float(match.group(2)),
                                "number_streams": int(match.group(3)),
                                "per_stream_fps": float(match.group(4)),
                            }

                            # Skip the result if the number of streams does not match
                            if result["number_streams"] != total_streams:
                                continue

                            latest_fps = result["per_stream_fps"]

                            # Push latest FPS to metrics-service
                            self._push_fps_metric(latest_fps)

                        # ----------------------------------------------------------
                        # latency_tracer_pipeline_interval parsing
                        #
                        # The tracer emits one interval line per running
                        # stream every 1000 ms. The in-memory map of
                        # last-seen samples is updated live in this hot
                        # loop (not post-run) so the map on the runner
                        # always reflects the most recent sample while
                        # the pipeline is still running.
                        #
                        # A cheap prefix check avoids running the full
                        # regex on every single line; the match is only
                        # attempted after the marker substring is
                        # confirmed to be present. When the tracer is
                        # disabled, `latency_tracer_metrics is None`
                        # short-circuits the whole branch.
                        # ----------------------------------------------------------
                        if (
                            self.latency_tracer_metrics is not None
                            and self._LATENCY_TRACER_INTERVAL_MARKER in line_str
                        ):
                            self._parse_and_record_latency_sample(line_str)

                    elif r == process.stderr:
                        process_stderr.append(line)

                    try:
                        if ps.Process(process.pid).status() == "zombie":
                            exit_code = process.wait()
                            break
                    except ps.NoSuchProcess:
                        # Process has already terminated
                        exit_code = process.wait()
                        break

                # If there was no activity for a prolonged period, treat as hang
                if (
                    not self.cancelled
                    and (time.time() - last_activity_time) > self.inactivity_timeout
                ):
                    self.logger.error(
                        "No new logs on stdout/stderr for %s seconds; "
                        "terminating pipeline as potentially hung",
                        self.inactivity_timeout,
                    )
                    self._graceful_terminate(process, timeout=5.0)

                    raise RuntimeError(
                        f"Pipeline execution terminated due to inactivity timeout "
                        f"({self.inactivity_timeout} seconds without stdout/stderr logs)."
                    )

            # Capture remaining output after process ends
            # Ensure we fully drain any remaining stdout/stderr from the pipes
            # before parsing metrics to avoid losing final FPS lines printed
            # right at shutdown.
            try:
                remaining_stdout, remaining_stderr = process.communicate()
            except Exception:
                remaining_stdout, remaining_stderr = (b"", b"")

            if remaining_stdout:
                process_output.append(remaining_stdout)
            if remaining_stderr:
                process_stderr.append(remaining_stderr)

            if exit_code is None:
                exit_code = process.returncode

            # ================================================================
            # POST-RUN: Parse all collected stdout lines to extract FPS metrics.
            #
            # We collect:
            # - overall_fps_dict: keyed by number_streams (printed once at end)
            # - avg_fps_dict: keyed by number_streams (last value wins, since
            #   average is cumulative and the last print is the most complete)
            # - last_fps: the very last "last" line regardless of stream count
            #
            # The three patterns are mutually exclusive (different keyword in
            # parentheses), so we use continue after each match.
            # ================================================================
            for line in process_output:
                line_str = line.decode("utf-8")

                match = re.search(overall_pattern, line_str)
                if match:
                    parsed = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    overall_fps_dict[parsed["number_streams"]] = parsed
                    continue

                match = re.search(avg_pattern, line_str)
                if match:
                    parsed = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    # Overwrite: we want the LAST average for each stream count
                    avg_fps_dict[parsed["number_streams"]] = parsed
                    continue

                match = re.search(last_pattern, line_str)
                if match:
                    parsed = {
                        "total_fps": float(match.group(2)),
                        "number_streams": int(match.group(3)),
                        "per_stream_fps": float(match.group(4)),
                    }
                    # Always overwrite: we only care about the very last one
                    last_fps = parsed
                    continue

            # ================================================================
            # METRIC SELECTION with fallback chain.
            #
            # Priority 1: Last average for exact total_streams match.
            #   Best steady-state metric — cumulative mean that excludes
            #   shutdown artifacts. The last printed value covers the longest
            #   measurement window.
            #
            # Priority 2: Overall for exact total_streams match.
            #   Includes the shutdown/flush period so it tends to be lower
            #   than average, but at least the stream count is correct.
            #
            # Priority 3: Last average for closest total_streams match.
            #   Stream count mismatch (e.g. some streams started late), but
            #   still a steady-state number rather than a shutdown-polluted one.
            #
            # Priority 4: Last "last" line (any stream count).
            #   Volatile window-based metric. Last resort only.
            # ================================================================

            # --- Priority 1: last average for exact total_streams ---
            if total_streams in avg_fps_dict:
                source = avg_fps_dict[total_streams]
                total_fps = source["total_fps"]
                num_streams = source["number_streams"]
                per_stream_fps = source["per_stream_fps"]
                details = (
                    f"used last average fps for {total_streams} stream(s) "
                    f"(primary source, steady-state metric)"
                )

            # --- Priority 2: overall for exact total_streams ---
            if total_fps is None and total_streams in overall_fps_dict:
                source = overall_fps_dict[total_streams]
                total_fps = source["total_fps"]
                num_streams = source["number_streams"]
                per_stream_fps = source["per_stream_fps"]
                details = (
                    f"used overall fps for {total_streams} stream(s) "
                    f"(fallback 1, includes shutdown period)"
                )

            # --- Priority 3: last average for closest total_streams ---
            if total_fps is None and avg_fps_dict:
                closest_match = min(
                    avg_fps_dict.keys(),
                    key=lambda x: abs(x - total_streams),
                    default=None,
                )
                if closest_match is not None:
                    source = avg_fps_dict[closest_match]
                    total_fps = source["total_fps"]
                    num_streams = source["number_streams"]
                    per_stream_fps = source["per_stream_fps"]
                    details = (
                        f"used last average fps for {closest_match} stream(s) "
                        f"(fallback 2, closest match to requested {total_streams})"
                    )

            # --- Priority 4: last "last" line ---
            if total_fps is None and last_fps:
                total_fps = last_fps["total_fps"]
                num_streams = last_fps["number_streams"]
                per_stream_fps = last_fps["per_stream_fps"]
                details = (
                    f"used last instantaneous fps for {num_streams} stream(s) "
                    f"(fallback 3, volatile window-based metric)"
                )

            # --- No FPS data found at all ---
            if total_fps is None:
                details = "no fps metrics found in pipeline output"

            # Convert None to appropriate defaults
            if total_fps is None:
                total_fps = 0.0
            if num_streams is None:
                num_streams = 0
            if per_stream_fps is None:
                per_stream_fps = 0.0

            # Prepare output strings
            stdout_lines = [
                line.decode("utf-8", errors="replace").rstrip("\n")
                for line in process_output
            ]
            stderr_lines = [
                line.decode("utf-8", errors="replace").rstrip("\n")
                for line in process_stderr
            ]

            stdout_str = "\n".join(stdout_lines)
            stderr_str = "\n".join(stderr_lines)

            # Log the final results and raise error if exit code is non-zero without cancellation
            if exit_code != 0:
                self.logger.error("Pipeline failed with exit_code=%s", exit_code)
                self.logger.error("STDOUT:\n%s", stdout_str)
                self.logger.error("STDERR:\n%s", stderr_str)
                # Only raise an error if the failure was not due to cancellation
                if not self.is_cancelled():
                    raise RuntimeError(
                        f"Pipeline execution failed: {stderr_str.strip()}"
                    )

            # Log the output if the pipeline succeeded or was cancelled (non-zero exit code due to cancellation is not treated as an error)
            if exit_code == 0 or self.is_cancelled():
                self.logger.debug(
                    "Output from pipeline execution (exit_code=%s):", exit_code
                )
                self.logger.debug("STDOUT:\n%s", stdout_str)
                self.logger.debug("STDERR:\n%s", stderr_str)

            return PipelineResult(
                total_fps=total_fps,
                per_stream_fps=per_stream_fps,
                num_streams=num_streams,
                exit_code=exit_code,
                cancelled=self.is_cancelled(),
                stdout=stdout_lines,
                stderr=stderr_lines,
                details=details,
                # Stays `None` when the tracer was not enabled (no
                # sampling happened); otherwise a dict with one entry
                # per stream that produced at least one interval line.
                latency_tracer_metrics=self.latency_tracer_metrics,
            )

        except Exception as e:
            self.logger.error(f"Pipeline execution error: {e}")
            raise
        finally:
            # Push 0.0 to metrics-service after pipeline completion (success or failure)
            self._push_fps_metric(0.0)

    def _push_fps_metric(self, fps: float) -> None:
        """
        Push the given FPS value to metrics-service via REST API.
        This method is called:
        - During pipeline execution to report current FPS metrics for monitoring
        - After pipeline completion (with 0.0) to signal that pipeline is no longer running
        Args:
            fps: FPS value to push.
        """
        try:
            data = json.dumps({"name": "fps", "value": fps}).encode()
            req = urllib.request.Request(
                self._metrics_service_fps_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            # Use a context manager so the underlying socket / file
            # descriptor is released deterministically after every POST,
            # instead of waiting for GC to reclaim the response object.
            with urllib.request.urlopen(req, timeout=1):
                pass
        except Exception as e:
            self.logger.warning(
                "Failed to push FPS metric to %s: %s",
                self._metrics_service_fps_url,
                e,
            )

    def _parse_and_record_latency_sample(self, line: str) -> None:
        """
        Parse a single `latency_tracer_pipeline_interval` line and
        update ``self.latency_tracer_metrics`` for the reported stream.

        Called from the stdout hot loop; callers are expected to pre-filter
        with the ``_LATENCY_TRACER_INTERVAL_MARKER`` substring check so the
        compiled regex only runs on likely matches.

        Silently ignores lines that contain the marker substring but do
        not match the full pattern, so the runner stays resilient to
        tracer format variations and to log-line truncation.

        Also silently drops samples whose ``stream_id`` is not in
        ``self._allowed_stream_ids`` (when that filter is set). This
        discards tracer rows for internal bin sinks (commonly named
        ``sink``) and intermediate ``splitmuxsink`` elements that are
        not part of the user-facing stream surface.

        Only the last sample per stream_id is retained: when a line
        arrives for a stream already present in the map, the previous
        entry is overwritten. No history is kept.

        Args:
            line: Raw stdout line from the subprocess. May include any
                prefix (e.g. ``"gst_runner - INFO - ..."``); the regex
                scans without anchoring.
        """
        # Defensive: this should not happen when the caller respects
        # the `is not None` precondition, but re-checking keeps the
        # method safe to call from anywhere.
        if self.latency_tracer_metrics is None:
            return

        match = self._LATENCY_TRACER_INTERVAL_PATTERN.search(line)
        if match is None:
            return

        # Build the composite stream_id used as the dict key. This must
        # match the format produced by `InternalStreamInfo.stream_id`
        # so downstream code can correlate entries back to streams
        # declared by `PipelineManager.build_pipeline_command`.
        source_name = match.group("source")
        sink_name = match.group("sink")
        stream_id = f"{source_name}__{sink_name}"

        # Drop samples that refer to elements other than the user-facing
        # main source/sink pair of a running stream. The DLStreamer
        # latency_tracer emits one row per GStreamer sink it sees,
        # which includes internal bin sinks (typically named ``sink``)
        # and, in recorder pipelines, the intermediate ``splitmuxsink``.
        # Without this filter the metrics map would contain rows like
        # ``src_p0_s0_0_0__sink`` or ``src_p0_s0_0_0__splitmuxsink0``
        # that are not addressable by ViPPET callers.
        if (
            self._allowed_stream_ids is not None
            and stream_id not in self._allowed_stream_ids
        ):
            return

        metrics = LatencyTracerSample(
            interval_ms=float(match.group("interval")),
            avg_ms=float(match.group("avg")),
            min_ms=float(match.group("min")),
            max_ms=float(match.group("max")),
            latency_ms=float(match.group("latency")),
        )
        self.latency_tracer_metrics[stream_id] = metrics

        # TODO(PipelineRunner): push each new sample to a live metrics
        # stream (WebSocket / SSE) instead of only updating the in-memory
        # map and logging it here.
        # TODO(PipelineRunner): drop this per-sample INFO log once the
        # live metrics stream above is in place — while it is missing,
        # this log is the only runtime-visible surface for tracer values.
        self.logger.info(
            "latency_tracer sample: stream=%s interval_ms=%.3f avg_ms=%.3f "
            "min_ms=%.3f max_ms=%.3f latency_ms=%.3f",
            stream_id,
            metrics.interval_ms,
            metrics.avg_ms,
            metrics.min_ms,
            metrics.max_ms,
            metrics.latency_ms,
        )

    def _build_subprocess_env(self) -> dict[str, str]:
        """
        Build the environment for the gst_runner.py subprocess.

        Starts from a copy of the current process environment. When
        ``enable_latency_metrics`` is True, augments the environment to
        activate the DLStreamer ``latency_tracer`` in pipeline-only mode
        with a 1000 ms interval:

        - ``GST_DEBUG``: if already set, ``GST_TRACER:7`` is appended with a
          comma separator so the existing debug categories are preserved.
          If unset, it is created with the single value ``GST_TRACER:7``.
        - ``GST_TRACERS``: set (and overwritten if previously present) to
          ``latency_tracer(flags=pipeline,interval=1000)``.

        When ``enable_latency_metrics`` is False, the environment is passed
        through unchanged so neither variable is created nor modified.

        Returns:
            A new dict suitable for passing as the ``env`` argument to
            ``subprocess.Popen``.
        """
        env = os.environ.copy()

        if not self.enable_latency_metrics:
            return env

        existing_gst_debug = env.get("GST_DEBUG")
        if existing_gst_debug:
            # Preserve existing debug categories, append our tracer category.
            env["GST_DEBUG"] = f"{existing_gst_debug},{self.LATENCY_TRACER_GST_DEBUG}"
        else:
            env["GST_DEBUG"] = self.LATENCY_TRACER_GST_DEBUG

        env["GST_TRACERS"] = self.LATENCY_TRACER_GST_TRACERS
        return env

    def cancel(self):
        """Cancel the currently running pipeline."""
        self.cancelled = True

    def is_cancelled(self) -> bool:
        """Check if the pipeline run has been cancelled."""
        return self.cancelled

    @staticmethod
    def _get_log_level() -> str:
        """Get the log level string from RUNNER_LOG_LEVEL env var, defaulting to INFO."""
        level = os.environ.get("RUNNER_LOG_LEVEL", "INFO").upper()
        valid_levels = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
        if level not in valid_levels:
            return "INFO"
        return level

    @staticmethod
    def _is_loggable_gst_runner_line(line: str) -> bool:
        """
        Check if a gst_runner log line should be forwarded to our logger.

        Matches lines starting with "gst_runner - " at any log level above
        DEBUG (i.e. INFO, WARNING, ERROR, CRITICAL). Lines at DEBUG level
        are suppressed to avoid noise.

        Args:
            line: Stripped stdout line from the subprocess.

        Returns:
            True if the line should be logged, False otherwise.
        """
        if not line.startswith("gst_runner - "):
            return False
        # Reject DEBUG lines explicitly; accept everything else
        return not line.startswith("gst_runner - DEBUG")

    @staticmethod
    def _parse_validation_stderr(raw_stderr: str) -> list[str]:
        """
        Parse raw stderr from gst_runner.py into a list of error messages.

        This method:
        - Splits stderr into lines
        - Filters only lines starting with "gst_runner - ERROR - "
        - Strips that prefix from each line
        - Trims surrounding whitespace
        - Discards empty lines

        Args:
            raw_stderr: Raw stderr output from gst_runner.py.

        Returns:
            List of error message strings.
        """
        if not raw_stderr:
            return []

        messages: list[str] = []
        prefix = "gst_runner - ERROR - "

        for line in raw_stderr.splitlines():
            if not line.startswith(prefix):
                continue

            content = line[len(prefix) :].strip()
            if not content:
                continue

            messages.append(content)

        return messages

    @staticmethod
    def _graceful_terminate(proc: subprocess.Popen, timeout: float = 10.0) -> None:
        """Send SIGINT for graceful shutdown, fall back to SIGKILL.

        Args:
            proc: The subprocess to terminate.
            timeout: Seconds to wait after SIGINT before sending SIGKILL.
        """
        if proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        except OSError:
            pass
