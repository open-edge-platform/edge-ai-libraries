"""pipeline_runner.py

Result types shared by the pipeline runner (:mod:`dlsps2_runner`) and its
callers: :class:`PipelineResult`, :class:`LatencyTracerSample` and
:class:`PipelineEvent`.
"""

from dataclasses import dataclass, field


@dataclass
class PipelineEvent:
    """
    Live, human-readable event observed while a pipeline is running.

    Mirrored by :class:`internal_types.InternalPipelineEvent`, for the same
    reason as :class:`LatencyTracerSample`.

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

    This is a deliberately runner-level dataclass: it MIRRORS
    :class:`internal_types.InternalLatencyMetrics` one-to-one in terms
    of fields and semantics, but lives here so the runner does not need
    to import from ``internal_types`` (that would create a circular
    import: ``dlsps2_runner`` → ``internal_types`` → ``graph`` →
    ``videos`` → ``dlsps2_runner``).

    Callers of :meth:`Dlsps2PipelineRunner.run` are expected to map this
    type onto ``InternalLatencyMetrics`` when copying the result into
    an internal job-status object — see
    ``TestsManager._execute_performance_test`` for the canonical
    conversion site.

    All timing fields are in milliseconds (as reported by the tracer).
    ``fps`` is intentionally NOT stored because FPS is already exposed
    on :class:`PipelineResult`, so re-reporting it here would just
    duplicate state.

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
        exit_code: 0 on success.
        cancelled: Whether the run was cancelled by the user.
        stdout: Output lines of the run, when the runner has any.
        stderr: Error messages of the run, e.g. the DLSPS 2.0 status message
            of each failed stream.
        details: Human-readable description of which FPS metric source was
            selected and for how many streams, or None if not applicable.
        latency_tracer_metrics: Last observed DLStreamer `latency_tracer`
            sample per stream, keyed by ``stream_id``
            (``"{source_name}__{sink_name}"``).

            * ``None`` when the runner was started with
              ``enable_latency_metrics=False`` — no latency samples are
              read.
            * Empty ``dict`` when samples were read but none arrived (e.g.
              the pipeline stopped before the server's first export).
            * Non-empty ``dict`` otherwise. Only the latest sample per
              stream is kept; earlier samples for the same stream are
              overwritten as new samples arrive.
        stream_fps: Measured FPS per stream, keyed by ``stream_id``.
            Empty when FPS cannot be attributed to individual streams.
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
