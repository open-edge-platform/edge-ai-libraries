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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from subprocess import PIPE, Popen
from typing import Callable

import psutil as ps


@dataclass
class PipelineEvent:
    """
    Live, human-readable event observed while a pipeline is running.

    Runner-local for the same reason as :class:`LatencyTracerSample`;
    mirrored by :class:`internal_types.InternalPipelineEvent`.

    Attributes:
        timestamp_ms: Wall-clock time the event was parsed, in ms since epoch.
        source: Event origin, e.g. ``"proximity-trigger"`` or ``"vlm"``.
        text: Human-readable event description (or VLM answer).
        element: Emitting element name, when known.
        pts_seconds: Stream position the event refers to, when known.
        prompt: Prompt that produced a VLM answer, when known.
    """

    timestamp_ms: int
    source: str
    text: str
    element: str | None = None
    pts_seconds: float | None = None
    prompt: str | None = None


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
        latency_ms: The tracer's ``latency`` field: the window length
            divided by its frame count, i.e. the mean output frame period
            (``1000 / fps``), not an end-to-end delay.
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
              interval closed).
            * Non-empty ``dict`` otherwise. Only the latest sample per
              stream is kept; earlier samples for the same stream are
              overwritten as new tracer windows arrive.
        stream_fps: Measured FPS per stream, keyed by ``stream_id``.
            Empty when the runner cannot attribute FPS to individual
            streams (the local runner reports totals only).
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
    stream_fps: dict[str, float] = field(default_factory=dict)

    @property
    def min_stream_fps(self) -> float | None:
        """FPS of the slowest stream, or ``None`` without per-stream data."""
        return min(self.stream_fps.values()) if self.stream_fps else None

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

    # Default metrics-manager URL for pushing FPS metrics
    DEFAULT_METRICS_MANAGER_URL = "http://metrics-manager:9090"

    # ------------------------------------------------------------------
    # Shared worker pool for fire-and-forget metric pushes.
    #
    # Every metric push (`_push_fps_metric`, `_push_latency_sample`,
    # `_push_final_latency_metrics`, `_push_vlm_metrics_sample`)
    # schedules work through `_post_metrics_async`. Creating a brand-new `threading.Thread`
    # per push scales poorly: with N streams the runner emits one FPS
    # push + one latency push per stream every second, plus N final
    # latency pushes at shutdown. Under load this would spawn
    # hundreds of short-lived threads per second.
    #
    # A single class-level `ThreadPoolExecutor` caps concurrency at
    # `_METRICS_EXECUTOR_WORKERS` and reuses threads across pushes.
    # The executor is declared as a daemon pool — its worker threads
    # do not keep the Python process alive after the main thread
    # exits, mirroring the previous `daemon=True` thread behaviour.
    #
    # Shared at the class level (not per-instance) on purpose: many
    # runners may exist in the same process (density `Benchmark`
    # reuses one, the validation path creates one per job, etc.) and
    # metrics-manager traffic is I/O-bound, so one pool is enough to
    # absorb all of them and no coordination is needed across
    # instances. The executor is created lazily on first push so
    # importing this module stays side-effect free.
    # ------------------------------------------------------------------
    _METRICS_EXECUTOR_WORKERS = 4
    _metrics_executor: "ThreadPoolExecutor | None" = None

    # ------------------------------------------------------------------
    # DL Streamer metrics
    #
    # DL Streamer posts latency windows and GenAI requests as
    # `dlstreamer/*` element messages on the pipeline bus, and
    # `gst_runner.py` forwards each as one `Pipeline metric: {json}` stdout
    # line, which `_parse_and_handle_pipeline_metric` consumes:
    #
    # - `latency-window`: one `latency_tracer` window per stream. With
    #   `enable_latency_metrics=True` the subprocess runs the tracer in
    #   pipeline-only mode with a 1000 ms interval and `post-metrics=true`.
    # - `genai-request`: one `gvagenai` generation request. `gst_runner.py`
    #   sets `post-metrics=true` on every `gvagenai` with `metrics=true`
    #   whose DL Streamer supports it. Values describe that request only.
    #
    # A DL Streamer that predates `post-metrics` posts neither message, so
    # each run falls back to the log output it already parsed before:
    #
    # - latency: the tracer ignores the unknown parameter and only logs its
    #   windows as `latency_tracer_pipeline_interval` TRACE records.
    #   `gst_runner.py` raises the GST_TRACER threshold to log them (see
    #   `LATENCY_RECORD_FALLBACK_ENV`) and promotes them to INFO until the
    #   tracer posts its first window; it then restores the threshold. Which
    #   source a run uses is decided in `_parse_latency_record`.
    # - VLM: a `gvagenai` without `post-metrics` keeps the `metrics` block in
    #   its JSON metadata (see `_parse_genai_meta_line`). That block holds
    #   means over every request since the element started.
    # ------------------------------------------------------------------
    # Must match ``gst_runner.LATENCY_RECORD_FALLBACK_ENV``.
    LATENCY_RECORD_FALLBACK_ENV = "VIPPET_LATENCY_RECORD_FALLBACK"
    LATENCY_TRACER_GST_TRACERS = (
        "latency_tracer(flags=pipeline,interval=1000,post-metrics=true)"
    )
    # Must match ``gst_runner.PIPELINE_METRIC_MARKER``.
    _PIPELINE_METRIC_MARKER = "Pipeline metric:"
    # Message schema version this runner understands. Messages with any
    # other version are skipped, as their fields may have changed meaning.
    _METRIC_MESSAGE_VERSION = 1
    # genai-request field -> `vlm_metrics` field pushed to metrics-manager.
    _GENAI_REQUEST_FIELDS = ("ttft_ms", "tpot_ms", "generate_duration_ms")
    # Latency sources of a run, see `_parse_latency_record`.
    _LATENCY_FROM_MESSAGES = "messages"
    _LATENCY_FROM_RECORDS = "records"

    # ------------------------------------------------------------------
    # latency_tracer record parser (fallback)
    #
    # The tracer logs ONE record per running stream and window, for
    # example (single line, reformatted here for readability)::
    #
    #   latency_tracer_pipeline_interval,
    #   pipeline_name=(string)pipeline0,
    #   source_name=(string)src_p0_s0_0_0,
    #   sink_name=(string)sink_p0_s0_0_0,
    #   interval=(double)1000.25, avg=(double)364.31,
    #   min=(double)0.004, max=(double)529.26,
    #   latency=(double)21.28, fps=(double)46.99;
    #
    # The pattern anchors on the record name and tolerates any text between
    # the fields it captures, in the order the tracer emits them. Values are
    # plain decimals. `fps` is not used: `gvafpscounter` reports FPS.
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

    # ------------------------------------------------------------------
    # gvagenai metadata
    #
    # `gvagenai` logs every JSON metadata message it attaches to a
    # buffer at GStreamer INFO level for its own debug category. Raising
    # that single category to INFO lets the runner forward each generated
    # result as a `vlm` pipeline event, and read the fallback VLM metrics,
    # without depending on `metadata_mode` (the metadata file is a UI
    # feature and may be disabled).
    #
    # The category is only enabled for pipelines that actually contain a
    # `gvagenai` element (see `run`), so non-GenAI pipelines keep their
    # original log verbosity.
    # ------------------------------------------------------------------
    GENAI_METRICS_GST_DEBUG = "gvagenai:4"
    GENAI_PIPELINE_ELEMENT = "gvagenai"
    _GENAI_METRICS_MARKER = "Added meta message:"
    # Extracts the emitting element name from a genai log line of the
    # form ``... <element_name> Added meta message: {...}``. The
    # ``<name>`` prefix is added by ``gst_runner.gst_log_bridge`` when
    # the record carries a named ``GstObject`` — after
    # ``unify_all_element_names`` the name is unique per stream (e.g.
    # ``gvagenai_0_0``).
    _GENAI_METRICS_ELEMENT_PATTERN = re.compile(
        r"<(?P<element>[^>]+)>\s+Added meta message:"
    )
    # Fallback: OpenVINO™ GenAI VLMPerfMetrics means in the JSON metadata
    # -> `vlm_metrics` field pushed to metrics-manager.
    _GENAI_METRIC_FIELDS = {
        "ttft_ms": "ttft_mean",
        "tpot_ms": "tpot_mean",
        "generate_duration_ms": "generate_duration_mean",
    }

    # Must match ``gst_runner.PIPELINE_EVENT_MARKER``.
    _PIPELINE_EVENT_MARKER = "Pipeline event:"

    def __init__(
        self,
        mode: str = "normal",
        max_runtime: float = 0.0,
        poll_interval: int = 1,
        inactivity_timeout: int = 120,
        hard_timeout: int | None = None,
        enable_latency_metrics: bool = False,
        job_id: str | None = None,
        on_event: Callable[[PipelineEvent], None] | None = None,
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
                (see ``_build_subprocess_env``). When False (default), the
                tracer is not started.
            job_id: Identifier of the owning job. When provided, every
                metric pushed by this runner — both FPS and
                ``pipeline_latency`` — carries a ``tags.job_id`` field
                so metrics-manager can partition data per job; this is
                how concurrent jobs are distinguished in the metrics
                backend. When ``None`` (default), the ``job_id`` tag is
                omitted from every payload (FPS pushes then carry no
                ``tags`` field at all; latency pushes still carry
                ``stream_id``). Used by ad-hoc callers (e.g. video
                transcoding) that do not belong to any job. Accepted by
                both ``normal`` and ``validation`` modes for a uniform
                API, but validation mode never pushes metrics
                (no ``gvafpscounter`` / tracer is attached), so the
                value is effectively unused there.
            on_event: Optional callback invoked (from the runner thread)
                for every live :class:`PipelineEvent` parsed in normal
                mode: ``vippet-event`` element messages (e.g. proximity
                trigger fired) and ``gvagenai`` text results.
        """
        self.mode = mode
        self.max_runtime = max_runtime
        self.poll_interval = poll_interval
        self.inactivity_timeout = inactivity_timeout
        self.hard_timeout = hard_timeout
        # Resolve the metrics-manager base URL once and pre-compute the
        # two endpoint URLs used by the push helpers. Trailing slashes
        # on the configured base are stripped so concatenation with the
        # fixed paths cannot produce `//api/v1/...`, which some proxies
        # and routers treat as a distinct (and unmapped) path.
        #
        # Two endpoints are used:
        #   * `/api/v1/metrics/simple` — single {name, value} pair,
        #     used for FPS pushes (one metric per call).
        #   * `/api/v1/metrics` — batch endpoint accepting a list of
        #     {name, fields, tags} entries, used for latency pushes
        #     so all four tracer fields travel in one request per
        #     stream sample.
        self.metrics_manager_url = os.environ.get(
            "METRICS_MANAGER_URL", self.DEFAULT_METRICS_MANAGER_URL
        ).rstrip("/")
        self._metrics_manager_fps_url = (
            f"{self.metrics_manager_url}/api/v1/metrics/simple"
        )
        self._metrics_manager_batch_url = f"{self.metrics_manager_url}/api/v1/metrics"
        self.enable_latency_metrics = enable_latency_metrics
        self.job_id = job_id
        self.on_event = on_event
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
        # Per-run state of the structured metrics and their fallbacks, reset
        # by `_reset_dl_streamer_metrics_state` at the start of every run.
        # `_latency_source` is None until the run's latency source is known.
        self._latency_source: str | None = None
        self._held_latency_records: dict[str, LatencyTracerSample] = {}
        self._genai_fallback_warned = False
        self._unknown_metric_versions: set[tuple[str, object]] = set()

        # Set of stream_ids the latency_tracer parser is allowed to
        # record. Populated per-run from `PipelineRunner.run()`. `None`
        # means "no filtering — keep every parsed sample".
        self._allowed_stream_ids: set[str] | None = None

        # Whether the pipeline of the current run contains a `gvagenai`
        # element. Set per-run from `PipelineRunner.run()`.
        self._genai_metrics_enabled = False

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
        # can cheaply consult it via `_store_latency_sample`.
        # An empty set is treated as "no streams allowed" and will drop
        # every sample; that is only correct if the caller actually
        # passed an empty set, which is a programmer error we do not
        # try to hide.
        self._allowed_stream_ids: set[str] | None = allowed_stream_ids

        self._genai_metrics_enabled = self.GENAI_PIPELINE_ELEMENT in pipeline_command

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
        self._reset_dl_streamer_metrics_state()

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

                            # Push latest FPS to metrics-manager
                            self._push_fps_metric(latest_fps)

                        # ----------------------------------------------------------
                        # DL Streamer metrics
                        #
                        # `latency_tracer` windows, `gvagenai` requests and
                        # their log fallbacks. Cheap substring checks keep
                        # parsing off every other line. `gvagenai` JSON
                        # metadata also carries the generated result text,
                        # forwarded as a `vlm` pipeline event.
                        # ----------------------------------------------------------
                        self._handle_dl_streamer_metric_line(line_str, emit_events=True)

                        if (
                            self.on_event is not None
                            and self._PIPELINE_EVENT_MARKER in line_str
                        ):
                            self._parse_and_emit_pipeline_event(line_str)

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
                # Metrics drained by gst_runner at shutdown, such as the
                # last latency window posted at EOS, can arrive after the
                # loop above stopped reading.
                for tail_line in remaining_stdout.decode(
                    "utf-8", errors="replace"
                ).splitlines():
                    self._handle_dl_streamer_metric_line(tail_line, emit_events=False)
            self._finish_latency_records()
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

            if (
                self.latency_tracer_metrics is not None
                and self._latency_source is None
                and not self.is_cancelled()
            ):
                self.logger.warning(
                    "Latency metrics were enabled but no latency_tracer window "
                    "arrived, for example because the run ended before the first "
                    "interval closed."
                )

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
                # per stream that produced at least one tracer window.
                latency_tracer_metrics=self.latency_tracer_metrics,
            )

        except Exception as e:
            self.logger.error(f"Pipeline execution error: {e}")
            raise
        finally:
            # Push 0.0 to metrics-manager after pipeline completion (success or failure)
            self._push_fps_metric(0.0)
            # Re-push the last observed latency sample per stream so
            # that at least one final pipeline_latency point per stream
            # reaches metrics-manager even if the last in-flight live
            # push raced with pipeline teardown. No-op when the tracer
            # was disabled or produced no samples.
            self._push_final_latency_metrics()

    def _post_metrics_async(
        self,
        url: str,
        payload: dict,
        description: str,
    ) -> None:
        """
        Fire-and-forget HTTP POST to metrics-manager.

        Submits the POST to a shared class-level
        ``ThreadPoolExecutor`` (see ``_get_metrics_executor``) so the
        pipeline hot loop is never blocked by a slow or unavailable
        metrics-manager. The pool caps concurrency at
        ``_METRICS_EXECUTOR_WORKERS`` and reuses threads across
        pushes, which avoids the unbounded-thread-spawn pattern a
        per-push ``threading.Thread`` would create under load (many
        streams × 1 Hz FPS + latency + per-stream final pushes).
        Failures are logged at WARNING level from the worker and
        never propagate back to the caller.

        This is the single I/O primitive shared by both the FPS push
        (single-metric endpoint) and the latency push (batch endpoint);
        the two differ only in the target URL and the JSON body shape,
        both built by the respective wrappers (``_push_fps_metric``,
        ``_push_latency_sample``, ``_push_final_latency_metrics``).

        Args:
            url: Fully qualified endpoint URL. Pre-computed once in
                ``__init__`` — this method does not touch the base URL.
            payload: JSON-serializable request body. Encoded as UTF-8
                before scheduling the POST so the worker thread does
                not share the dict with the caller.
            description: Short label used in the WARNING log if the
                request fails (e.g. ``"fps"`` or ``"latency"``).
                Kept separate from the URL so logs are readable even
                when the endpoint path is unfamiliar.
        """
        # Snapshot everything the worker thread needs so it never
        # reaches back into `self` on the hot path — keeps the worker
        # self-contained and avoids any accidental lifetime coupling.
        logger = self.logger
        data = json.dumps(payload).encode()

        def _worker() -> None:
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                # Context manager releases the socket / file descriptor
                # deterministically after every POST, instead of
                # waiting for GC to reclaim the response object.
                with urllib.request.urlopen(req, timeout=1):
                    pass
            except Exception as e:
                logger.warning(
                    "Failed to push %s metric to %s: %s", description, url, e
                )

        # Submit the push to the shared worker pool. The pool caps
        # concurrency at `_METRICS_EXECUTOR_WORKERS` and reuses
        # threads, so bursts (many streams emitting latency every
        # second + per-stream final pushes at shutdown) cannot turn
        # into an unbounded thread spawn. We do not keep the returned
        # Future: each push is independent and never joined.
        self._get_metrics_executor().submit(_worker)

    @classmethod
    def _get_metrics_executor(cls) -> ThreadPoolExecutor:
        """
        Return (and lazily create) the shared metrics-push worker pool.

        The pool is a single class-level ``ThreadPoolExecutor`` used
        by every runner instance in the process. It is created on
        first use so importing this module does not spawn any
        threads, and its worker threads are daemons (via
        ``thread_name_prefix`` + the executor's own daemon behaviour)
        so they do not keep the Python process alive after the main
        thread exits.

        Lazy creation is race-safe enough for our use: the worst case
        under a tight race is two executors being created and one
        being immediately garbage-collected. Since the executor is
        never closed on purpose (metric pushes may continue until
        process exit), no resource leak results from the lost one.
        """
        if cls._metrics_executor is None:
            cls._metrics_executor = ThreadPoolExecutor(
                max_workers=cls._METRICS_EXECUTOR_WORKERS,
                thread_name_prefix="vippet-metrics",
            )
        return cls._metrics_executor

    def _push_fps_metric(self, fps: float) -> None:
        """
        Push the given FPS value to metrics-manager.

        Called:
        - During pipeline execution, every time a new average FPS line
          is parsed from ``gvafpscounter`` (roughly once per second).
        - Once at pipeline completion with ``0.0`` to signal that the
          pipeline is no longer running.

        Uses the ``/api/v1/metrics/simple`` endpoint: one metric name
        and one scalar value per request. When ``self.job_id`` is set,
        the payload carries ``tags.job_id`` so metrics-manager can
        partition data per job; otherwise the ``tags`` field is omitted.

        Args:
            fps: FPS value to push.
        """
        payload: dict[str, object] = {"name": "fps", "value": fps}
        if self.job_id is not None:
            payload["tags"] = {"job_id": self.job_id}

        self._post_metrics_async(
            url=self._metrics_manager_fps_url,
            payload=payload,
            description="fps",
        )

    def _push_latency_sample(
        self, stream_id: str, sample: "LatencyTracerSample"
    ) -> None:
        """
        Push a single ``latency_tracer`` sample to metrics-manager.

        Called live from the stdout hot loop every time a new
        latency window is parsed for an allowed stream (see
        ``_store_latency_sample``). No
        push is made when ``enable_latency_metrics`` is False, because
        the caller itself short-circuits on that condition.

        Uses the ``/api/v1/metrics`` batch endpoint with a single
        entry in the ``metrics`` list. The batch shape is used (even
        for one entry) so all four tracer fields travel in a single
        HTTP request — the alternative would be four separate calls
        to the ``simple`` endpoint per stream per second, which scales
        poorly with stream count.

        Fields sent: ``avg_ms``, ``min_ms``, ``max_ms``, ``latency_ms``.
        ``interval_ms`` is intentionally omitted — the emission cadence
        is fixed at 1000 ms and metrics-manager timestamps each sample
        on receipt, so the field would only add noise. ``fps`` is also
        intentionally omitted because it is already reported by
        ``gvafpscounter`` via ``_push_fps_metric`` — re-sending it
        here would double-count throughput in the dashboard.

        Tags: ``job_id`` (when set) and ``stream_id`` so the dashboard
        can distinguish concurrent streams on the same job.

        Args:
            stream_id: Composite ``"{source_name}__{sink_name}"`` used
                as the ``stream_id`` tag value. Matches the key under
                which the sample is stored in
                ``self.latency_tracer_metrics``.
            sample: The parsed tracer sample to push.
        """
        tags: dict[str, str] = {"stream_id": stream_id}
        if self.job_id is not None:
            tags["job_id"] = self.job_id

        payload = {
            "metrics": [
                {
                    "name": "pipeline_latency",
                    "fields": {
                        "avg_ms": sample.avg_ms,
                        "min_ms": sample.min_ms,
                        "max_ms": sample.max_ms,
                        "latency_ms": sample.latency_ms,
                    },
                    "tags": tags,
                }
            ]
        }

        self._post_metrics_async(
            url=self._metrics_manager_batch_url,
            payload=payload,
            description="latency",
        )

    def _push_final_latency_metrics(self) -> None:
        """
        Push one final ``pipeline_latency`` sample per stream after
        the subprocess exits.

        Runs once from the ``finally`` block of ``_run_normal``,
        iterating the in-memory ``latency_tracer_metrics`` map and
        re-pushing the last observed sample for every stream. This
        guarantees that at least one final sample per stream reaches
        metrics-manager even if the last in-flight per-sample push
        raced with pipeline teardown.

        No-op when ``enable_latency_metrics`` is False (the map stays
        ``None``) or when the map is empty (tracer was enabled but
        produced no samples — e.g. the pipeline exited before the
        first 1000 ms interval closed).
        """
        if not self.latency_tracer_metrics:
            return
        for stream_id, sample in self.latency_tracer_metrics.items():
            self._push_latency_sample(stream_id, sample)

    def _handle_dl_streamer_metric_line(self, line: str, emit_events: bool) -> None:
        """
        Dispatch one subprocess stdout line that may carry DL Streamer metrics.

        Handles ``Pipeline metric:`` lines, ``latency_tracer`` interval
        records (latency fallback) and ``gvagenai`` JSON metadata lines.
        Every other line is ignored after a few substring checks.

        Args:
            line: Raw stdout line from the subprocess.
            emit_events: Whether a ``gvagenai`` result is also forwarded
                as a ``vlm`` pipeline event. False for the output drained
                after the process exited.
        """
        if self._PIPELINE_METRIC_MARKER in line:
            self._parse_and_handle_pipeline_metric(line)
        elif (
            self.latency_tracer_metrics is not None
            and self._LATENCY_TRACER_INTERVAL_MARKER in line
        ):
            self._parse_latency_record(line)
        elif self._genai_metrics_enabled and self._GENAI_METRICS_MARKER in line:
            self._parse_genai_meta_line(line, emit_event=emit_events)

    def _parse_genai_meta_line(self, line: str, emit_event: bool = True) -> None:
        """
        Parse a ``gvagenai`` JSON metadata line.

        The generated ``result`` is forwarded as a ``vlm`` pipeline event
        when ``emit_event`` is set.

        A ``metrics`` block is only present when the element could not run
        with ``post-metrics=true``: ``gst_runner.gst_log_bridge`` drops it
        otherwise, because the per-request values then arrive as
        ``genai-request`` metric lines (see :meth:`_record_genai_request`).
        Its OpenVINO™ GenAI ``VLMPerfMetrics`` means (``ttft_mean``,
        ``tpot_mean``, ``generate_duration_mean``) are pushed as the
        fallback ``vlm_metrics`` sample, with one warning per run, because
        they average every request since the element started. Malformed
        lines and blocks without these means (e.g. the token usage of the
        ``openai-http`` backend) are dropped.

        The emitting ``gvagenai_*`` element name (added by
        ``gst_runner.gst_log_bridge`` as a ``<name>`` prefix) is used as
        the event's ``element`` and the sample's ``stream_id``.

        Args:
            line: Raw stdout line from the subprocess, including any
                log prefix (e.g. ``"gst_runner - INFO - ..."``).
            emit_event: Whether to forward the result as a pipeline event.
        """
        json_start = line.find("{", line.find(self._GENAI_METRICS_MARKER))
        if json_start == -1:
            return

        try:
            payload = json.loads(line[json_start:])
        except ValueError:
            return
        if not isinstance(payload, dict):
            return

        element_match = self._GENAI_METRICS_ELEMENT_PATTERN.search(line)
        element = element_match.group("element") if element_match else None

        result = payload.get("result")
        if emit_event and isinstance(result, str) and result.strip():
            pts_seconds = payload.get("timestamp_seconds")
            prompt = payload.get("prompt")
            self._emit_event(
                source="vlm",
                text=result.strip(),
                element=element,
                pts_seconds=pts_seconds
                if isinstance(pts_seconds, (int, float))
                else None,
                prompt=prompt if isinstance(prompt, str) else None,
            )

        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            return
        try:
            fields = {
                dst: float(metrics[src])
                for dst, src in self._GENAI_METRIC_FIELDS.items()
            }
        except (KeyError, TypeError, ValueError):
            return
        if not self._genai_fallback_warned:
            self._genai_fallback_warned = True
            self.logger.warning(
                "gvagenai element %s does not support post-metrics; VLM metrics "
                "fall back to the means in its JSON metadata, which average every "
                "request since the element started.",
                element,
            )
        self._push_vlm_metrics_sample(fields, stream_id=element)
        self.logger.debug(
            "gvagenai metrics (fallback): stream=%s fields=%s", element, fields
        )

    def _parse_and_emit_pipeline_event(self, line: str) -> None:
        """
        Parse a ``Pipeline event: {json}`` line logged by ``gst_runner``
        and forward it to ``on_event``. Malformed lines are dropped.
        """
        json_start = line.find("{", line.find(self._PIPELINE_EVENT_MARKER))
        if json_start == -1:
            return
        try:
            payload = json.loads(line[json_start:])
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        source = payload.get("source")
        element = payload.get("element")
        pts_seconds = payload.get("pts-seconds")
        self._emit_event(
            source=source if isinstance(source, str) else "pipeline",
            text=text.strip(),
            element=element if isinstance(element, str) else None,
            pts_seconds=pts_seconds if isinstance(pts_seconds, (int, float)) else None,
        )

    def _emit_event(
        self,
        source: str,
        text: str,
        element: str | None,
        pts_seconds: float | None,
        prompt: str | None = None,
    ) -> None:
        if self.on_event is None:
            return
        self.on_event(
            PipelineEvent(
                timestamp_ms=int(time.time() * 1000),
                source=source,
                text=text,
                element=element,
                pts_seconds=float(pts_seconds) if pts_seconds is not None else None,
                prompt=prompt,
            )
        )

    def _push_vlm_metrics_sample(
        self, fields: dict[str, float], stream_id: str | None = None
    ) -> None:
        """
        Push a single ``vlm_metrics`` sample to metrics-manager.

        Uses the ``/api/v1/metrics`` batch endpoint so all VLM fields
        travel in one request, mirroring ``_push_latency_sample``.

        Tags: ``job_id`` (when set) and ``stream_id`` (when the
        originating ``gvagenai_*`` element name was recovered from the
        log line) so the dashboard can partition VLM samples per job
        and per stream in multi-stream runs.

        Args:
            fields: Parsed VLM metric fields (``ttft_ms``, ``tpot_ms``,
                ``generate_duration_ms``).
            stream_id: Emitting ``gvagenai`` element name (unique per
                stream after ``unify_all_element_names``), or ``None``
                when it could not be recovered.
        """
        tags: dict[str, str] = {}
        if self.job_id is not None:
            tags["job_id"] = self.job_id
        if stream_id is not None:
            tags["stream_id"] = stream_id

        entry: dict[str, object] = {"name": "vlm_metrics", "fields": fields}
        if tags:
            entry["tags"] = tags

        self._post_metrics_async(
            url=self._metrics_manager_batch_url,
            payload={"metrics": [entry]},
            description="vlm",
        )

    def _parse_and_handle_pipeline_metric(self, line: str) -> None:
        """
        Parse a ``Pipeline metric: {json}`` line logged by ``gst_runner``
        and dispatch it by kind.

        The line carries one ``dlstreamer/*`` bus message as
        ``{"kind": ..., "element": ..., "fields": {...}}``. Malformed
        lines and unknown kinds are dropped, so the runner stays
        resilient to newer DL Streamer producers.

        Args:
            line: Raw stdout line from the subprocess, including any log
                prefix (e.g. ``"gst_runner - INFO - ..."``).
        """
        json_start = line.find("{", line.find(self._PIPELINE_METRIC_MARKER))
        if json_start == -1:
            return
        try:
            payload = json.loads(line[json_start:])
        except ValueError:
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
            return
        kind = payload.get("kind")
        element = payload.get("element")
        if kind == "latency-window":
            self._record_latency_window(payload["fields"])
        elif kind == "genai-request":
            self._record_genai_request(
                payload["fields"], element if isinstance(element, str) else None
            )

    def _reset_dl_streamer_metrics_state(self) -> None:
        """Forget the latency source and fallback warnings of the previous run."""
        self._latency_source = None
        self._held_latency_records = {}
        self._genai_fallback_warned = False
        self._unknown_metric_versions = set()

    def _is_known_metric_version(self, kind: str, fields: dict) -> bool:
        """
        Check the schema ``version`` of a ``dlstreamer/*`` metric message.

        A message with another version may have fields whose meaning
        changed, so it is skipped. One warning is logged per kind and
        version within a run.

        Args:
            kind: Message kind, e.g. ``"latency-window"``.
            fields: ``fields`` of the metric line.

        Returns:
            True if the message has the version this runner understands.
        """
        version = fields.get("version")
        if version == self._METRIC_MESSAGE_VERSION and not isinstance(version, bool):
            return True
        key = (kind, version)
        if key not in self._unknown_metric_versions:
            self._unknown_metric_versions.add(key)
            self.logger.warning(
                "Skipping DL Streamer %s messages with unsupported version %r "
                "(supported: %d).",
                kind,
                version,
                self._METRIC_MESSAGE_VERSION,
            )
        return False

    def _record_latency_window(self, fields: dict) -> None:
        """
        Record one ``latency_tracer`` window posted as a bus message.

        The window carries raw aggregates (``count``, ``sum_ms``,
        ``min_ms``, ``max_ms``, ``window_ms``); the sample fields are
        derived exactly as the tracer derives its own record:
        ``avg = sum_ms / count`` and ``latency = window_ms / count``.

        The first window makes messages the latency source of the run, and
        drops the interval records held back until then (see
        :meth:`_parse_latency_record`).

        Args:
            fields: ``fields`` of a ``latency-window`` metric line.
        """
        if self.latency_tracer_metrics is None:
            return
        if not self._is_known_metric_version("latency-window", fields):
            return
        if self._latency_source != self._LATENCY_FROM_MESSAGES:
            self._latency_source = self._LATENCY_FROM_MESSAGES
            self._held_latency_records = {}
        try:
            stream_id = f"{fields['source']}__{fields['sink']}"
            count = int(fields["count"])
            window_ms = float(fields["window_ms"])
            sum_ms = float(fields["sum_ms"])
            min_ms = float(fields["min_ms"])
            max_ms = float(fields["max_ms"])
        except (KeyError, TypeError, ValueError):
            return
        if count <= 0:
            return

        self._store_latency_sample(
            stream_id,
            LatencyTracerSample(
                interval_ms=window_ms,
                avg_ms=sum_ms / count,
                min_ms=min_ms,
                max_ms=max_ms,
                latency_ms=window_ms / count,
            ),
        )

    def _parse_latency_record(self, line: str) -> None:
        """
        Parse a ``latency_tracer_pipeline_interval`` record (fallback).

        ``gst_runner`` promotes these records until the tracer posts its
        first window as a bus message. The tracer logs the record of a
        window just before it posts the window, in the same thread, and
        ``gst_runner`` stops promoting records as soon as the first window
        is posted. So while the run's latency source is undecided, a record
        is held back per stream:

        * a ``latency-window`` message arrives: messages are the source and
          the held records are dropped (see :meth:`_record_latency_window`);
        * a second record of the same stream arrives: the tracer did not
          post the first one, so it predates ``post-metrics``. Records
          become the source, a warning is logged, and the held records are
          recorded (see :meth:`_use_latency_records`).

        Lines that do not match the full pattern are ignored.

        Args:
            line: Raw stdout line from the subprocess, including any log
                prefix (e.g. ``"gst_runner - INFO - ..."``).
        """
        if (
            self.latency_tracer_metrics is None
            or self._latency_source == self._LATENCY_FROM_MESSAGES
        ):
            return
        match = self._LATENCY_TRACER_INTERVAL_PATTERN.search(line)
        if match is None:
            return

        stream_id = f"{match.group('source')}__{match.group('sink')}"
        sample = LatencyTracerSample(
            interval_ms=float(match.group("interval")),
            avg_ms=float(match.group("avg")),
            min_ms=float(match.group("min")),
            max_ms=float(match.group("max")),
            latency_ms=float(match.group("latency")),
        )
        if self._latency_source is None:
            if stream_id not in self._held_latency_records:
                self._held_latency_records[stream_id] = sample
                return
            self._use_latency_records()
        self._store_latency_sample(stream_id, sample)

    def _use_latency_records(self) -> None:
        """Make interval records the latency source of the run and record the held ones."""
        self._latency_source = self._LATENCY_FROM_RECORDS
        self.logger.warning(
            "DL Streamer latency_tracer does not post latency-window messages "
            "(post-metrics); falling back to parsing its log records."
        )
        held, self._held_latency_records = self._held_latency_records, {}
        for stream_id, sample in held.items():
            self._store_latency_sample(stream_id, sample)

    def _finish_latency_records(self) -> None:
        """
        Resolve records still held back when the subprocess has exited.

        A run that ended within the first windows may never have shown a
        second record of a stream. Without any ``latency-window`` message
        the held records are the only latency data, so they are recorded.
        """
        if self._latency_source is None and self._held_latency_records:
            self._use_latency_records()

    def _store_latency_sample(
        self, stream_id: str, sample: LatencyTracerSample
    ) -> None:
        """
        Keep a latency sample of a stream and push it to metrics-manager.

        Samples whose ``stream_id`` is not in ``self._allowed_stream_ids``
        (when that filter is set) are dropped. This discards windows for
        internal bin sinks (commonly named ``sink``) and intermediate
        ``splitmuxsink`` elements that are not part of the user-facing
        stream surface. Only the last sample per stream is retained.

        Args:
            stream_id: ``"{source_name}__{sink_name}"`` of the window.
            sample: The window's latency sample.
        """
        if self.latency_tracer_metrics is None:
            return
        if (
            self._allowed_stream_ids is not None
            and stream_id not in self._allowed_stream_ids
        ):
            return
        self.latency_tracer_metrics[stream_id] = sample

        # Live push: fire-and-forget on the metrics executor, so a slow or
        # unavailable backend can never stall the stdout reader.
        self._push_latency_sample(stream_id, sample)
        self.logger.debug(
            "latency_tracer window: stream=%s interval_ms=%.3f avg_ms=%.3f "
            "min_ms=%.3f max_ms=%.3f latency_ms=%.3f",
            stream_id,
            sample.interval_ms,
            sample.avg_ms,
            sample.min_ms,
            sample.max_ms,
            sample.latency_ms,
        )

    def _record_genai_request(self, fields: dict, element: str | None) -> None:
        """
        Push the metrics of one ``gvagenai`` generation request.

        The values come from OpenVINO™ GenAI ``PerfMetrics`` of that
        request only: ``ttft_ms`` (time to first token), ``tpot_ms``
        (mean time per output token of the request) and
        ``generate_duration_ms``. Messages with an unknown ``version``
        are skipped.

        Args:
            fields: ``fields`` of a ``genai-request`` metric line.
            element: Emitting ``gvagenai`` element name, used as the
                ``stream_id`` tag (unique per stream after
                ``unify_all_element_names``).
        """
        if not self._is_known_metric_version("genai-request", fields):
            return
        try:
            values = {name: float(fields[name]) for name in self._GENAI_REQUEST_FIELDS}
        except (KeyError, TypeError, ValueError):
            return
        self._push_vlm_metrics_sample(values, stream_id=element)
        self.logger.debug("gvagenai request: stream=%s fields=%s", element, values)

    def _build_subprocess_env(self) -> dict[str, str]:
        """
        Build the environment for the gst_runner.py subprocess.

        Starts from a copy of the current process environment. Then:

        - Prepends the bundled ``gst_plugins/`` directory to
          ``GST_PLUGIN_PATH`` so custom Python elements shipped with ViPPET
          (e.g. ``gvaproximitytrigger_py``) are discovered by GStreamer at
          init time. Any ``.py`` file in ``gst_plugins/python/`` that defines
          ``__gstelementfactory__`` becomes usable from any pipeline
          description; unused ones are simply ignored.
        - Adds the GStreamer debug categories required by the metrics the
          runner parses off the subprocess stdout:

          - ``enable_latency_metrics`` sets ``GST_TRACERS`` to
            ``latency_tracer(flags=pipeline,interval=1000,post-metrics=true)``,
            activating the DLStreamer tracer in pipeline-only mode, and
            ``VIPPET_LATENCY_RECORD_FALLBACK=1``. The tracer posts its windows
            as bus messages; for a tracer that predates ``post-metrics``,
            ``gst_runner.py`` raises the GST_TRACER threshold to log its TRACE
            records instead, and restores the previous threshold once the
            first window is posted. ``GST_DEBUG`` is not changed for it.
          - a pipeline containing ``gvagenai`` adds ``gvagenai:4`` so the
            element logs its JSON metadata (the generated result, and the
            fallback VLM metrics) at INFO level.

        ``GST_DEBUG`` is never overwritten: any pre-existing categories are
        preserved and the required ones are appended with a comma
        separator. When no metric needs a category, the debug variables are
        left untouched.

        Returns:
            A new dict suitable for passing as the ``env`` argument to
            ``subprocess.Popen``.
        """
        env = os.environ.copy()

        # Make bundled custom GStreamer plugins discoverable. The path is
        # resolved relative to this file so it works regardless of the
        # subprocess working directory.
        custom_plugins_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "gst_plugins"
        )
        if os.path.isdir(custom_plugins_dir):
            existing_plugin_path = env.get("GST_PLUGIN_PATH", "")
            if existing_plugin_path:
                env["GST_PLUGIN_PATH"] = (
                    f"{custom_plugins_dir}{os.pathsep}{existing_plugin_path}"
                )
            else:
                env["GST_PLUGIN_PATH"] = custom_plugins_dir
            # Python-based plugins can only be loaded in-process; disabling
            # the registry-scan fork keeps GStreamer from silently skipping
            # them during the first-time cache build.
            env.setdefault("GST_REGISTRY_FORK", "no")

        gst_debug_categories: list[str] = []

        if self.enable_latency_metrics:
            env["GST_TRACERS"] = self.LATENCY_TRACER_GST_TRACERS
            env[self.LATENCY_RECORD_FALLBACK_ENV] = "1"

        if self._genai_metrics_enabled:
            gst_debug_categories.append(self.GENAI_METRICS_GST_DEBUG)

        if not gst_debug_categories:
            return env

        existing_gst_debug = env.get("GST_DEBUG")
        if existing_gst_debug:
            gst_debug_categories.insert(0, existing_gst_debug)
        env["GST_DEBUG"] = ",".join(gst_debug_categories)

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
