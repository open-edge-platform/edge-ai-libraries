# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""dlsps2_runner.py

``Dlsps2PipelineRunner`` executes ViPPET's pipelines on a running DLSPS 2.0
(``dlstreamer-pipeline-server``) instance through its REST API. It has two
modes:

* ``mode="validation"`` — maps onto ``POST /pipelines`` followed by polling
  ``GET /pipelines/{id}/status``. The pipeline is valid if it stays
  ``RUNNING`` for ``max_runtime`` seconds or
  reaches ``COMPLETED`` sooner; ``ERROR``/``ABORTED`` is invalid. The
  instance is then torn down with ``DELETE /pipelines/{id}``.
* ``mode="normal"`` (performance and density tests) — one launch string per
  pipeline, not yet validated by this runner, is checked first with
  ``POST /validate``, all at once, with its writing sinks swapped for
  ``fakesink`` so the check leaves no files or streams behind (see
  :func:`validation_launch_string`). Every stream then runs as its own
  instance (``POST /pipelines`` per stream with ``validate_pipeline=false``,
  all in the unpinned worker),
  so the instances start together. ``GET /pipelines/{id}/status`` is polled
  for each stream's ``frame_fps`` and ``frame_interval``; every instance is
  stopped with
  ``DELETE /pipelines/{id}`` once ``max_runtime`` elapses, all instances end,
  or the caller cancels.
  The result carries the FPS of each stream, so callers can judge the
  slowest one.

Latency and VLM metrics (normal mode) do not come from the REST API.
DLSPS 2.0 exports DL Streamer's own measurements over OpenTelemetry to
metrics-manager, each tagged with the instance's ``pipeline_id``:
``latency_tracer`` windows merged over every export period as the
``pipeline_latency_avg``/``_min``/``_max``/``_window``/``_frames`` gauges, and
``gvagenai`` requests as the ``genai_*`` delta histograms. Only ``_avg``,
``_min`` and ``_max`` are frame latencies; ``_window`` and ``_frames`` are the
window length and frame count, a throughput measure from which the deprecated
frame period ``latency_ms`` is derived. The runner reads
only these series, only for its own instances, and republishes every export
period as ViPPET's own ``pipeline_latency`` and ``vlm_metrics`` samples with
the job's tags. A sample aggregates every window or request of one export
period
(``DLSPS2_OTEL_INTERVAL_MS``). This needs the server started with
OpenTelemetry export to metrics-manager and, for latency, with
``GST_TRACERS=latency_tracer(flags=pipeline,interval=1000,post-metrics=true)``
(``DLSPS2_OTEL`` and ``DLSPS2_GST_TRACERS`` in ``compose.yml``, see
:func:`dlsps2_latency_configured`). ``gvagenai``
elements with ``metrics=true`` get ``post-metrics=true`` in the launch string
only when the server's own ``gvagenai`` has that property, as reported by
``GET /elements/gvagenai``; otherwise the launch string is left as is and no
VLM metrics are collected (see :func:`with_genai_post_metrics`).

Live pipeline events (proximity triggers and VLM answers) are read from
JSON Lines files the pipelines write into the shared metadata folder, see
:mod:`pipeline_events`; only runs given an ``on_event`` callback collect
them. The same VLM answers carry ``gvagenai``'s cumulative metric means,
used for ``vlm_metrics`` when the server's ``gvagenai`` has no
``post-metrics`` or metrics-manager cannot store its histograms.

Deliberately NOT supported:

* A combined multi-stream launch string without per-stream commands raises
  :class:`NotImplementedError`: DLSPS 2.0 counts frames on the first sink
  of an instance only.

Every caller (``managers.validation_manager``, ``managers.tests_manager``,
``benchmark`` and ``videos``) passes one launch string per stream.
"""

import json
import logging
import os
import re
import threading
import time
import urllib.request
from typing import Callable, Optional

import httpx

from pipeline_events import LAUNCH_ELEMENT, EventCapture
from pipeline_runner import LatencyTracerSample, PipelineEvent, PipelineResult

logger = logging.getLogger("dlsps2_runner")

# Base URL of metrics-manager, used to push a live "fps" metric while a
# normal-mode run is in progress, for the UI's live FPS chart, which polls
# metrics-manager filtered by `job_id`.
DEFAULT_METRICS_MANAGER_URL = "http://metrics-manager:9090"

# ----------------------------------------------------------------------
# Configuration (env-overridable), following the same convention as
# managers/model_manager.py's MODEL_DOWNLOAD_URL block.
# ----------------------------------------------------------------------

# Base URL of a running DLSPS 2.0 instance (no trailing slash).
DLSPS2_BASE_URL: str = os.environ.get(
    "DLSPS2_BASE_URL", "http://dlstreamer-pipeline-server:8080"
).rstrip("/")

# Whether to verify the DLSPS 2.0 server's TLS certificate when DLSPS2_BASE_URL
# is https (e.g. behind a TLS-terminating proxy with a self-signed certificate).
DLSPS2_VERIFY_TLS: bool = os.environ.get(
    "DLSPS2_VERIFY_TLS", "false"
).strip().lower() in (
    "1",
    "true",
    "yes",
)

# Per-request HTTP timeout, seconds.
DLSPS2_HTTP_TIMEOUT_S: float = float(os.environ.get("DLSPS2_HTTP_TIMEOUT_S", "30"))

# Default interval used to poll GET /pipelines/{id}/status, seconds.
DLSPS2_POLL_INTERVAL_S: float = float(os.environ.get("DLSPS2_POLL_INTERVAL_S", "1"))

# Seconds after every stream's first frame before FPS samples count.
DLSPS2_WARMUP_S: float = float(os.environ.get("DLSPS2_WARMUP_S", "5"))

# How long to retry DELETE on instances still in validation (capped at 30 s by DLSPS).
DLSPS2_STOP_TIMEOUT_S: float = float(os.environ.get("DLSPS2_STOP_TIMEOUT_S", "40"))

# How often metrics-manager is read for the DLSPS-exported latency/VLM series,
# seconds. Matches the default export interval, so every export reaches the chart.
DLSPS2_METRICS_POLL_S: float = float(os.environ.get("DLSPS2_METRICS_POLL_S", "1"))

# Per-request timeout of metrics-manager reads, seconds. Separate from, and much
# shorter than, DLSPS2_HTTP_TIMEOUT_S: the reads share the polling loop, so a hung
# metrics-manager must not stall FPS sampling or the max_runtime check.
DLSPS2_METRICS_HTTP_TIMEOUT_S: float = float(
    os.environ.get("DLSPS2_METRICS_HTTP_TIMEOUT_S", "2")
)

# OpenTelemetry export interval of the DLSPS 2.0 server, milliseconds (passed to the
# server as OTEL_EXPORT_INTERVAL_MILLIS by compose.yml).
DLSPS2_OTEL_INTERVAL_MS: float = float(
    os.environ.get("DLSPS2_OTEL_INTERVAL_MS", "1000")
)

# Wait for the final export after the instances stop, beyond one export interval.
_FINAL_EXPORT_GRACE_S = 2.0

# metrics-manager series exported by DLSPS 2.0 (see dlsps2/src/core/metrics.py), and
# the field each one becomes. Their names differ from ViPPET's own republished
# pipeline_latency / vlm_metrics series, so neither reader picks up the other.
_LATENCY_SERIES = {
    "pipeline_latency_avg": "avg_ms",
    "pipeline_latency_min": "min_ms",
    "pipeline_latency_max": "max_ms",
    "pipeline_latency_frames": "frames",
    "pipeline_latency_window": "window_ms",
}
_GENAI_SERIES = {
    "genai_ttft": "ttft_ms",
    "genai_tpot": "tpot_ms",
    "genai_generate_duration": "generate_duration_ms",
}
# 1 while an instance is RUNNING, 0 in every export after it finished. DLSPS
# exports it for every instance, so it shows whether an instance's final export
# reached metrics-manager.
_RUNNING_SERIES = "pipeline_running"

_TRUE_VALUES = ("1", "true", "yes", "on")


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def dlsps2_latency_configured() -> bool:
    """Whether DLSPS 2.0 is set up to export latency.

    Requires ``DLSPS2_OTEL=true`` and ``DLSPS2_GST_TRACERS`` running
    ``latency_tracer`` with ``post-metrics=true``; ``compose.yml`` passes both
    to the server and to ``vippet``. Tracers are process-wide in the server, so
    this is a server setting, not a per-test one.
    """
    tracers = os.environ.get("DLSPS2_GST_TRACERS", "").replace(" ", "")
    return (
        _env_true("DLSPS2_OTEL")
        and "latency_tracer" in tracers
        and "post-metrics=true" in tracers
    )


_LAUNCH_ELEMENT = LAUNCH_ELEMENT
_METRICS_ON = re.compile(r"(?:^|\s)metrics=(?:true|1|yes)(?:\s|$)", re.IGNORECASE)


# A property line of `gst-inspect-1.0 gvagenai` output, as returned by DLSPS 2.0.
_POST_METRICS_PROPERTY = re.compile(r"^\s+post-metrics\s*:", re.MULTILINE)
_POST_METRICS_ON = re.compile(
    r"(?:^|\s)post-metrics=(?:true|1|yes)(?:\s|!|$)", re.IGNORECASE
)


def _wants_post_metrics(element: str) -> bool:
    tokens = element.split()
    return (
        bool(tokens)
        and tokens[0] == "gvagenai"
        and "post-metrics" not in element
        and _METRICS_ON.search(element) is not None
    )


def wants_genai_post_metrics(command: str) -> bool:
    """Whether ``command`` has a ``gvagenai`` with ``metrics=true`` and no ``post-metrics``."""
    return any(
        _wants_post_metrics(m.group(0)) for m in _LAUNCH_ELEMENT.finditer(command)
    )


def with_genai_post_metrics(command: str) -> str:
    """Add ``post-metrics=true`` to ``gvagenai`` elements that run with ``metrics=true``.

    DLSPS 2.0 exports ``gvagenai`` requests only from elements that post them
    (``post-metrics``), which must be set in the launch string. Callers must
    first check that the server's ``gvagenai`` has the property (see
    :meth:`Dlsps2PipelineRunner._server_has_genai_post_metrics`): an unknown
    property makes the server reject the pipeline. An explicit
    ``post-metrics`` is kept.
    """

    def _add(match: re.Match) -> str:
        element = match.group(0)
        if not _wants_post_metrics(element):
            return element
        stripped = element.rstrip()
        return f"{stripped} post-metrics=true{element[len(stripped) :]}"

    return _LAUNCH_ELEMENT.sub(_add, command)


# A launch string token: whitespace-separated, double-quoted parts kept whole.
_LAUNCH_TOKEN = re.compile(r'(?:[^\s"]|"[^"]*")+')

# Parentheses attached to the text before them, without spaces inside: caps
# features (``video/x-raw(memory:VAMemory)``, also shell-escaped as
# ``\(...\)``) and typed caps fields (``format=(string)NV12``). A bin's
# parentheses stand apart from the elements they enclose.
_ATTACHED_PARENS = re.compile(r"(?<=[^\s()\\])\\?\([^\s()\\]*\\?\)")


def with_fps_chain_last(command: str, stream_id: str) -> str:
    """Move the chain DLSPS 2.0 should count FPS on to the end of ``command``.

    DLSPS 2.0 counts an instance's FPS at the first sink ``iterate_sinks()``
    returns, which is the sink parsed last. In a pipeline whose branches run
    at different rates (a VLM branch fed one frame per trigger), only one
    branch gives the stream's FPS:

    - the chain with ``gvafpscounter``, where the pipeline itself counts
      FPS, if exactly one chain has it and that chain ends in a sink;
    - otherwise the chain that ends in the stream's main sink, named after
      the second half of ``stream_id`` (``<source>__<sink>``).

    GStreamer resolves ``t.`` references after parsing, so a branch may come
    before its tee.

    The command is returned unchanged when no chain is found, the chain is
    already last, the command uses bins (``( ... )``) or a ``!`` without
    spaces around it. Caps features and typed caps fields
    (``video/x-raw(memory:VAMemory)``, ``format=(string)NV12``) are not bins.
    """
    chains: list[list[str]] = [[]]
    after_link = True
    for token in _LAUNCH_TOKEN.findall(command):
        unquoted = _ATTACHED_PARENS.sub("", re.sub(r'"[^"]*"', "", token))
        if token != "!" and ("!" in unquoted or "(" in unquoted or ")" in unquoted):
            # A link without spaces around it, or a bin: leave it as written.
            return command
        if token == "!":
            after_link = True
        elif not after_link and "=" not in token:
            # An element or pad reference not linked to the previous one
            # starts a new chain.
            chains.append([])
        else:
            after_link = False
        chains[-1].append(token)
    counted = [i for i, chain in enumerate(chains) if "gvafpscounter" in chain]
    if len(counted) == 1 and _ends_in_sink(chains[counted[0]]):
        target = counted
    else:
        _, _, sink = stream_id.partition("__")
        if not sink:
            return command
        names = {f"name={sink}", f'name="{sink}"'}
        target = [i for i, chain in enumerate(chains) if names & set(chain)]
    if len(target) != 1 or target[0] == len(chains) - 1:
        return command
    chains.append(chains.pop(target[0]))
    return " ".join(" ".join(chain) for chain in chains)


def _ends_in_sink(chain: list[str]) -> bool:
    """Whether the last element of a chain is a sink (``fakesink``, ``filesink``, ...)."""
    if "!" not in chain or chain[-1] == "!":
        return False
    last_link = len(chain) - 1 - chain[::-1].index("!")
    return chain[last_link + 1].endswith("sink")


# Elements that write files or send data out of the pipeline. A validation run
# gets a fakesink in their place (gvametapublish, a pass-through, an identity),
# so it leaves no files, metadata or streams behind.
_WRITING_SINKS = frozenset(
    {
        "filesink",
        "multifilesink",
        "splitmuxsink",
        "rtspclientsink",
        "whipclientsink",
        "whipsink",
        "hlssink",
        "hlssink2",
        "hlssink3",
        "srtsink",
        "udpsink",
        "tcpclientsink",
    }
)
_WRITING_PASSTHROUGHS = frozenset({"gvametapublish"})


def validation_launch_string(command: str) -> str:
    """``command`` with its writing elements swapped for side-effect-free ones.

    Each sink in ``_WRITING_SINKS`` becomes a ``fakesink`` with the same
    ``name`` (and ``sync``), and ``async=false``, so a branch that rarely gets
    a buffer cannot hold the validation run in preroll. ``gvametapublish``
    becomes an ``identity``. Everything upstream (sources, decoders,
    inference, encoders, muxers) is kept, so validation still checks the
    elements, models, devices and caps the real run uses. An element whose
    pads are referenced by name elsewhere (``name.pad``) is left as it is.
    """

    def _swap(match: re.Match) -> str:
        element = match.group(0)
        tokens = _LAUNCH_TOKEN.findall(element)
        if not tokens or tokens[0] not in _WRITING_SINKS | _WRITING_PASSTHROUGHS:
            return element
        end = 1
        while end < len(tokens) and "=" in tokens[end]:
            end += 1
        properties = dict(token.split("=", 1) for token in tokens[1:end])
        name = properties.get("name")
        bare = (name or "").strip('"')
        if bare and re.search(rf"(?:^|\s){re.escape(bare)}\.", command):
            return element
        swapped = ["fakesink", "async=false"]
        if tokens[0] in _WRITING_PASSTHROUGHS:
            swapped = ["identity"]
        elif "sync" in properties:
            swapped.append(f"sync={properties['sync']}")
        if name is not None:
            swapped.insert(1, f"name={name}")
        leading = element[: len(element) - len(element.lstrip())]
        trailing = element[len(element.rstrip()) :]
        return leading + " ".join(swapped + tokens[end:]) + trailing

    return _LAUNCH_ELEMENT.sub(_swap, command)


# States in which a DLSPS 2.0 instance may still hold devices.
_ACTIVE_STATES = frozenset({"QUEUED", "RUNNING", "RESTARTING"})

# Seconds for stopping leftover instances when vippet starts or stops.
DLSPS2_CLEANUP_TIMEOUT_S: float = float(os.environ.get("DLSPS2_CLEANUP_TIMEOUT_S", "5"))


def stop_leftover_instances(
    timeout_s: float | None = None, base_url: Optional[str] = None
) -> int:
    """Stop every DLSPS 2.0 instance that is still active. Never raises.

    ``vippet`` is the server's only client, so when ``vippet`` starts or
    stops no instance should be running: one that is was started by a
    ``vippet`` process that ended mid-run, and it would hold devices and skew
    every later measurement.

    Args:
        timeout_s: Overall budget, default ``DLSPS2_CLEANUP_TIMEOUT_S``.
        base_url: DLSPS 2.0 base URL, default ``DLSPS2_BASE_URL``.

    Returns:
        The number of instances asked to stop.
    """
    if timeout_s is None:
        timeout_s = DLSPS2_CLEANUP_TIMEOUT_S
    runner = Dlsps2PipelineRunner(base_url=base_url)
    try:
        with httpx.Client(
            timeout=min(DLSPS2_HTTP_TIMEOUT_S, timeout_s), verify=DLSPS2_VERIFY_TLS
        ) as client:
            response = client.get(f"{runner.base_url}/pipelines/status")
            response.raise_for_status()
            active = [
                item["id"]
                for item in response.json()
                if item.get("state") in _ACTIVE_STATES
            ]
            if active:
                logger.warning(
                    "Stopping %d DLSPS 2.0 instance(s) that no run tracks: %s",
                    len(active),
                    active,
                )
                runner._stop_all(client, active, timeout_s)
            return len(active)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Could not stop leftover DLSPS 2.0 instances: %s", exc)
        return 0


# States a dlsps2 pipeline instance can no longer leave on its own.
_TERMINAL_STATES = frozenset({"COMPLETED", "ERROR", "ABORTED"})


class Dlsps2PipelineRunner:
    """Executes pipelines via a running DLSPS 2.0 instance's REST API.

    The public interface is ``run()``, ``cancel()`` and ``is_cancelled()``;
    see the module docstring for what each mode does.
    """

    def __init__(
        self,
        mode: str = "normal",
        max_runtime: float = 0.0,
        poll_interval: int = 1,
        inactivity_timeout: int = 120,
        hard_timeout: Optional[int] = None,
        enable_latency_metrics: bool = False,
        job_id: Optional[str] = None,
        base_url: Optional[str] = None,
        validate_pipelines: bool = True,
        on_event: Optional[Callable[[PipelineEvent], None]] = None,
    ):
        """Initialize the runner.

        Args:
            mode: ``"normal"`` (performance and density runs, TS conversion)
                or ``"validation"``.
            max_runtime: Seconds to run. In normal mode the time counts from
                every stream's first frame, and ``0`` runs until every
                instance ends on its own. In validation mode, how long the
                pipeline must stay ``RUNNING`` to be valid.
            poll_interval: Seconds between status polls (default
                ``DLSPS2_POLL_INTERVAL_S``).
            inactivity_timeout: Seconds without frames from a stream, or
                without an answer from DLSPS, after which a normal run fails.
            hard_timeout: Validation mode only: seconds to reach a verdict
                (default ``max_runtime + 60``).
            enable_latency_metrics: Read latency samples from metrics-manager.
            job_id: Tag of the metrics pushed to metrics-manager.
            base_url: Base URL of the DLSPS 2.0 instance (default
                ``DLSPS2_BASE_URL``).
            validate_pipelines: Whether normal mode first checks each launch
                string with ``POST /validate``. Turn the check off for a
                pipeline that writes a file, since the check would run it
                once more before the real run.
            on_event: Called with each live pipeline event of a normal run.

        With ``enable_latency_metrics`` the latency samples are read from
        metrics-manager; see the module docstring for the server setup and
        :func:`dlsps2_latency_configured` for when callers use it.

        With ``on_event``, normal mode collects live pipeline events
        (proximity triggers and VLM answers) through event files, see
        :mod:`pipeline_events`, and calls it for each one while the run lasts.
        """
        self.mode = mode
        self.max_runtime = max_runtime
        self.poll_interval = poll_interval or DLSPS2_POLL_INTERVAL_S
        self.inactivity_timeout = inactivity_timeout
        self.hard_timeout = (
            hard_timeout if hard_timeout is not None else max_runtime + 60
        )
        self.enable_latency_metrics = enable_latency_metrics
        self.job_id = job_id
        self.base_url = (base_url or DLSPS2_BASE_URL).rstrip("/")
        self.validate_pipelines = validate_pipelines
        self.on_event = on_event
        self.cancelled = False
        self.logger = logger
        # Launch strings DLSPS 2.0 already accepted, reused across density iterations.
        self._validated: set[str] = set()
        # Last latency sample per stream_id.
        self.latency_tracer_metrics: dict[str, LatencyTracerSample] | None = (
            {} if enable_latency_metrics else None
        )
        # Per-run state of the metrics-manager reads, reset by _run_streams:
        # (timestamp, exports) already consumed per series, whether DLSPS exported
        # anything for the run's instances, and whether a failed read was logged.
        self._consumed: dict[tuple, tuple[int, int]] = {}
        self._export_seen = False
        self._metrics_read_failed = False
        # Whether the server's gvagenai has post-metrics; asked once per runner.
        self._genai_post_metrics: bool | None = None
        # Whether VLM metrics come from the answers' cumulative means, set per run.
        self._vlm_from_answers = False
        self._vlm_fallback_warned = False

        metrics_manager_url = os.environ.get(
            "METRICS_MANAGER_URL", DEFAULT_METRICS_MANAGER_URL
        ).rstrip("/")
        self._metrics_manager_url = metrics_manager_url
        self._metrics_manager_fps_url = f"{metrics_manager_url}/api/v1/metrics/simple"
        self._metrics_manager_batch_url = f"{metrics_manager_url}/api/v1/metrics"

    def cancel(self) -> None:
        """Cancel the currently running pipeline."""
        self.cancelled = True

    def is_cancelled(self) -> bool:
        """Check if the pipeline run has been cancelled."""
        return self.cancelled

    def run(
        self,
        pipeline_command: str,
        total_streams: int = 1,
        allowed_stream_ids: "set[str] | None" = None,
        stream_commands: dict[str, str] | None = None,
        validation_stream_ids: "set[str] | None" = None,
    ) -> PipelineResult:
        """Run a pipeline against DLSPS 2.0 and return a `PipelineResult`.

        Args:
            pipeline_command: Complete GStreamer pipeline description string.
                Validation mode submits it as is. Normal mode uses it only
                when ``stream_commands`` is not given.
            total_streams: Expected stream count. Without ``stream_commands``
                only ``1`` is supported in normal mode; ignored in
                validation mode.
            allowed_stream_ids: Latency samples of streams outside this set
                (internal bin sinks, ``splitmuxsink``) are dropped. ``None``
                keeps every stream.
            stream_commands: Normal mode only. One launch string per stream,
                keyed by ``stream_id`` (``PipelineCommand.stream_commands``);
                each runs as its own DLSPS 2.0 instance.
            validation_stream_ids: Normal mode only. Streams whose launch
                string is validated before the run, one per pipeline
                (``PipelineCommand.validation_stream_ids``); the other streams
                of a pipeline repeat it. ``None`` validates every stream.

        Returns:
            PipelineResult with ``exit_code``/``stderr`` (validation mode) or
            ``total_fps``/``per_stream_fps``/``stream_fps`` (normal mode).

        Raises:
            NotImplementedError: If ``mode == "normal"``, ``stream_commands``
                is not given and ``total_streams != 1``.
            RuntimeError: If the run fails on DLSPS 2.0 without having been
                cancelled (normal mode only).
        """
        if self.mode == "validation":
            return self._run_validation(pipeline_command)

        if stream_commands is None:
            if total_streams != 1:
                raise NotImplementedError(
                    "Dlsps2PipelineRunner needs one launch string per stream "
                    f"(stream_commands) to run total_streams={total_streams}."
                )
            stream_commands = {"stream": pipeline_command}
        return self._run_streams(
            stream_commands, allowed_stream_ids, validation_stream_ids
        )

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=DLSPS2_HTTP_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS)

    def _metrics_client(self) -> httpx.Client:
        return httpx.Client(timeout=DLSPS2_METRICS_HTTP_TIMEOUT_S)

    def _server_has_genai_post_metrics(self, client: httpx.Client) -> bool:
        """Whether the server's ``gvagenai`` has the ``post-metrics`` property.

        Read from the ``gst-inspect-1.0`` output that ``GET /elements/gvagenai``
        returns, once per runner. The server image may differ from the
        ``vippet`` one, and an unknown property would make the server reject
        the pipeline, so any failure to tell counts as "no": the run goes on
        without VLM metrics, with one warning.
        """
        if self._genai_post_metrics is None:
            try:
                response = client.get(f"{self.base_url}/elements/gvagenai")
                response.raise_for_status()
                details = response.json().get("details")
                supported = isinstance(details, str) and bool(
                    _POST_METRICS_PROPERTY.search(details)
                )
                reason = "its gvagenai has no post-metrics property"
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                supported = False
                reason = f"its gvagenai could not be inspected ({exc})"
            if not supported:
                self.logger.warning(
                    "VLM metrics are not collected on DLSPS 2.0: %s.", reason
                )
            self._genai_post_metrics = supported
        return self._genai_post_metrics

    def _start(
        self,
        client: httpx.Client,
        pipeline_command: str,
        validate_pipeline: bool = True,
    ) -> str:
        response = client.post(
            f"{self.base_url}/pipelines",
            json={
                "pipeline": pipeline_command,
                "validate_pipeline": validate_pipeline,
            },
        )
        response.raise_for_status()
        return response.json()["instance_id"]

    def _validate_new(self, client: httpx.Client, commands: list[str]) -> None:
        """Validate every command not validated yet, all at once.

        Uses ``POST /validate`` and polls ``GET /validate/status/{id}``.
        Stops early, without raising, once the run is cancelled.

        Raises:
            RuntimeError: If a command is invalid, a request fails, or not
                every verdict arrives within ``inactivity_timeout`` seconds.
        """
        pending: dict[str, str] = {}
        try:
            for command in dict.fromkeys(commands):
                if self.cancelled:
                    return
                if command in self._validated:
                    continue
                response = client.post(
                    f"{self.base_url}/validate",
                    json={"pipeline": command, "timeout": self.inactivity_timeout},
                )
                response.raise_for_status()
                pending[response.json()["validation_id"]] = command

            deadline = time.monotonic() + self.inactivity_timeout
            while pending and not self.cancelled:
                for validation_id, command in list(pending.items()):
                    response = client.get(
                        f"{self.base_url}/validate/status/{validation_id}"
                    )
                    response.raise_for_status()
                    status = response.json()
                    if status.get("state") == "INVALID":
                        raise RuntimeError(
                            "Pipeline validation failed on DLSPS 2.0: "
                            f"{status.get('message') or 'invalid pipeline'}"
                        )
                    if status.get("state") == "VALID":
                        self._validated.add(command)
                        del pending[validation_id]
                if not pending:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Pipeline validation timed out: DLSPS 2.0 gave no verdict "
                        f"for {len(pending)} launch string(s) within "
                        f"{self.inactivity_timeout}s"
                    )
                time.sleep(self.poll_interval)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Failed to validate pipeline on DLSPS 2.0: {self._error_detail(exc)}"
            ) from exc

    def _status(self, client: httpx.Client, instance_id: str) -> dict:
        response = client.get(f"{self.base_url}/pipelines/{instance_id}/status")
        response.raise_for_status()
        return response.json()

    def _statuses(
        self, client: httpx.Client, instances: dict[str, str]
    ) -> dict[str, dict]:
        """Status of each instance in ``{stream_id: instance_id}``.

        One ``GET /pipelines/{id}/status`` per instance, so the cost does not
        grow with the instances the server keeps from earlier runs. Instances
        DLSPS no longer knows (404) are left out.

        Raises:
            httpx.HTTPError: If a request fails for another reason.
        """
        statuses: dict[str, dict] = {}
        for stream_id, instance_id in instances.items():
            try:
                statuses[stream_id] = self._status(client, instance_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
        return statuses

    @staticmethod
    def _error_detail(exc: httpx.HTTPError) -> str:
        """Describe an HTTP error, preferring the server's FastAPI ``detail``."""
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                body = exc.response.json()
            except ValueError:
                body = None
            detail = body.get("detail") if isinstance(body, dict) else None
            if detail:
                return f"HTTP {exc.response.status_code}: {detail}"
        return str(exc)

    def _stop(self, client: httpx.Client, instance_id: str) -> None:
        """Best-effort DELETE /pipelines/{id}. Never raises."""
        try:
            response = client.delete(f"{self.base_url}/pipelines/{instance_id}")
            # 409: instance already finished; 404: already gone.
            if response.status_code not in (200, 404, 409):
                response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.warning(
                "Failed to stop DLSPS 2.0 instance %s: %s", instance_id, exc
            )

    def _stop_all(
        self,
        client: httpx.Client,
        instance_ids: list[str],
        timeout_s: float | None = None,
    ) -> None:
        """Stop every instance. Never raises.

        DLSPS 2.0 answers ``DELETE`` with 409 while an instance is still
        ``QUEUED`` in validation, and starts it afterwards. Such instances are
        retried until they leave ``QUEUED`` or ``timeout_s`` (default
        ``DLSPS2_STOP_TIMEOUT_S``) passes.
        """
        if timeout_s is None:
            timeout_s = DLSPS2_STOP_TIMEOUT_S
        pending = list(instance_ids)
        deadline = time.monotonic() + timeout_s
        while True:
            pending = [iid for iid in pending if not self._try_stop(client, iid)]
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(self.poll_interval)
        if pending:
            self.logger.warning(
                "DLSPS 2.0 instances still queued after %ss, not stopped: %s",
                timeout_s,
                pending,
            )

    def _try_stop(self, client: httpx.Client, instance_id: str) -> bool:
        """DELETE one instance; ``False`` only if it is still ``QUEUED``."""
        try:
            response = client.delete(f"{self.base_url}/pipelines/{instance_id}")
            if response.status_code == 409:
                return self._status(client, instance_id).get("state") != "QUEUED"
            if response.status_code not in (200, 404):
                response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.warning(
                "Failed to stop DLSPS 2.0 instance %s: %s", instance_id, exc
            )
        return True

    def _push_fps_metric(self, fps: float) -> None:
        """Fire-and-forget push of the current FPS value to metrics-manager.

        Posts to ``/api/v1/metrics/simple`` as ``{"name": "fps", "value":
        ..., "tags": {"job_id": ...}}``, which the UI's live FPS chart reads
        from metrics-manager filtered by ``job_id``. Runs the POST on a
        short-lived daemon thread so a slow/unreachable metrics-manager never
        delays polling.
        """
        payload: dict[str, object] = {"name": "fps", "value": fps}
        if self.job_id is not None:
            payload["tags"] = {"job_id": self.job_id}
        data = json.dumps(payload).encode()
        url = self._metrics_manager_fps_url
        logger_ = self.logger

        def _worker() -> None:
            try:
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=1):
                    pass
            except Exception as exc:  # noqa: BLE001 - best-effort, never raises
                logger_.warning("Failed to push fps metric to %s: %s", url, exc)

        threading.Thread(target=_worker, daemon=True).start()

    def _post_batch(self, metrics: list[dict], description: str) -> None:
        """Fire-and-forget POST of metrics to metrics-manager's batch endpoint."""
        if not metrics:
            return
        data = json.dumps({"metrics": metrics}).encode()
        url = self._metrics_manager_batch_url
        logger_ = self.logger

        def _worker() -> None:
            try:
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=1):
                    pass
            except Exception as exc:  # noqa: BLE001 - best-effort, never raises
                logger_.warning(
                    "Failed to push %s metrics to %s: %s", description, url, exc
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _tags(self, stream_id: str | None) -> dict[str, str]:
        tags: dict[str, str] = {}
        if self.job_id is not None:
            tags["job_id"] = self.job_id
        if stream_id is not None:
            tags["stream_id"] = stream_id
        return tags

    @staticmethod
    def _point_value(fields: dict, tags: dict) -> float | None:
        """Value of a stored DLSPS data point, or ``None`` to skip it.

        Gauges carry ``value``. Histograms carry ``count``, ``sum``, ``avg``,
        ``min`` and ``max``; their ``avg`` is used. DLSPS exports histograms
        with delta temporality, so each point covers one export period; a
        point tagged ``cumulative`` would average everything since the start
        and is skipped, as is a period without requests.
        """
        if "value" in fields:
            value = fields["value"]
        else:
            if tags.get("temporality") == "cumulative":
                return None
            count = fields.get("count")
            if not isinstance(count, (int, float)) or count <= 0:
                return None
            value = fields.get("avg")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    def _read_points(
        self,
        client: httpx.Client,
        name: str,
        instance_ids: set[str],
        histograms: bool = False,
    ) -> list[tuple[dict, int, float]]:
        """``(tags, timestamp, value)`` of the stored points of ``name`` for ``instance_ids``.

        Points of other instances, including ViPPET's own republished series
        (which carry no ``pipeline_id``), are left out. Points keep the order
        metrics-manager stored them in. With ``histograms``, a point that
        carries a plain ``value`` is left out too: a metrics-manager without
        histogram support stores DLSPS's histograms that way, as ``0``. VLM
        metrics then come from the answers instead (see
        :meth:`_push_answer_metrics`).
        """
        response = client.get(
            f"{self._metrics_manager_url}/api/v1/metrics", params={"name": name}
        )
        response.raise_for_status()
        points = []
        for metric in response.json().get("metrics", []):
            tags = metric.get("tags") or {}
            if tags.get("pipeline_id") not in instance_ids:
                continue
            if histograms and "value" in (metric.get("fields") or {}):
                self._histograms_unsupported()
                continue
            value = self._point_value(metric.get("fields") or {}, tags)
            if value is None:
                continue
            points.append((tags, int(metric.get("timestamp") or 0), value))
        if points:
            self._export_seen = True
        return points

    def _read_exports(
        self,
        client: httpx.Client,
        names: dict[str, str],
        key_tags: tuple[str, ...],
        instance_ids: set[str],
    ) -> list[tuple[tuple, int, list[dict[str, float]]]]:
        """Read DLSPS-exported series for ``instance_ids`` and group them per export.

        A series is ``(pipeline_id, *key_tags)``. One export stores one point
        per name and series, all stamped with nearly the same time, which
        metrics-manager returns in whole seconds. Points are grouped by second;
        an export split over two consecutive seconds is joined, and several
        exports within one second are told apart by their storage order.

        Returns:
            ``(series, timestamp, exports)`` per series and second, with every
            export as ``{field: value}`` holding all fields of ``names``.
        """
        fields = set(names.values())
        buckets: dict[tuple, dict[int, dict[str, list[float]]]] = {}
        histograms = names is _GENAI_SERIES
        for name, field in names.items():
            for tags, timestamp, value in self._read_points(
                client, name, instance_ids, histograms
            ):
                series = (tags["pipeline_id"], *(tags.get(t) for t in key_tags))
                by_field = buckets.setdefault(series, {}).setdefault(timestamp, {})
                by_field.setdefault(field, []).append(value)

        result = []
        for series, by_second in buckets.items():
            split: tuple[int, dict[str, list[float]]] | None = None
            for timestamp in sorted(by_second):
                values = by_second[timestamp]
                if split is not None:
                    split_at, first_part = split
                    split = None
                    if (
                        timestamp == split_at + 1
                        and not first_part.keys() & values.keys()
                        and first_part.keys() | values.keys() == fields
                    ):
                        values = {**first_part, **values}
                if values.keys() != fields:
                    split = (timestamp, values)
                    continue
                count = min(len(v) for v in values.values())
                exports = [{f: values[f][i] for f in fields} for i in range(count)]
                result.append((series, timestamp, exports))
        return result

    def _fresh(self, exports: list[tuple[tuple, int, list[dict[str, float]]]]):
        """Yield ``(series, values)`` of every export not consumed yet, oldest first."""
        for series, timestamp, values in sorted(exports, key=lambda e: e[1]):
            last, used = self._consumed.get(series, (-1, 0))
            if timestamp < last:
                continue
            start = used if timestamp == last else 0
            if start >= len(values):
                continue
            self._consumed[series] = (timestamp, len(values))
            for export in values[start:]:
                yield series, export

    def _poll_metrics_manager(
        self,
        client: httpx.Client,
        instances: dict[str, str],
        allowed_stream_ids: "set[str] | None",
        genai: bool,
    ) -> dict[str, float]:
        """Republish new DLSPS latency/VLM export periods with the job's tags.

        Returns:
            The latest ``pipeline_running`` value per instance id. It is read
            first, so the series read afterwards include the export it came
            from.
        """
        instance_ids = set(instances.values())
        stream_of = {iid: sid for sid, iid in instances.items()}
        running = {
            tags["pipeline_id"]: value
            for tags, _, value in self._read_points(
                client, _RUNNING_SERIES, instance_ids
            )
        }
        if self.latency_tracer_metrics is not None:
            pushes = []
            exports = self._read_exports(
                client, _LATENCY_SERIES, ("source", "sink"), instance_ids
            )
            for (_, source, sink), v in self._fresh(exports):
                stream_id = f"{source}__{sink}"
                if (
                    allowed_stream_ids is not None
                    and stream_id not in allowed_stream_ids
                ):
                    continue
                if v["frames"] <= 0:
                    continue
                # Merged over the export period: the mean frame latency and the
                # extremes of its windows. window_ms / frames is the mean time
                # between output frames (the deprecated latency_ms, a frame
                # period, not a latency).
                sample = LatencyTracerSample(
                    interval_ms=v["window_ms"],
                    avg_ms=v["avg_ms"],
                    min_ms=v["min_ms"],
                    max_ms=v["max_ms"],
                    latency_ms=v["window_ms"] / v["frames"],
                )
                self.latency_tracer_metrics[stream_id] = sample
                pushes.append(
                    {
                        "name": "pipeline_latency",
                        "fields": {
                            "avg_ms": sample.avg_ms,
                            "min_ms": sample.min_ms,
                            "max_ms": sample.max_ms,
                            "latency_ms": sample.latency_ms,
                        },
                        "tags": self._tags(stream_id),
                    }
                )
            self._post_batch(pushes, "latency")
        if genai:
            pushes = []
            exports = self._read_exports(
                client, _GENAI_SERIES, ("element",), instance_ids
            )
            for (pipeline_id, element), v in self._fresh(exports):
                # Each value is the mean over the requests of one export period
                # (a delta histogram's avg), not the value of a single request.
                # One stream per instance: tag with the stream, as the local
                # runner does with the stream-unique gvagenai element name.
                entry: dict[str, object] = {"name": "vlm_metrics", "fields": v}
                tags = self._tags(element or stream_of.get(pipeline_id))
                if tags:
                    entry["tags"] = tags
                pushes.append(entry)
            self._post_batch(pushes, "vlm")
        return running

    def _try_poll_metrics_manager(self, *args) -> dict[str, float] | None:
        """:meth:`_poll_metrics_manager`, logging a failure instead of raising.

        Only the first failure of a run is logged as a warning. Returns
        ``None`` when the read failed.
        """
        try:
            return self._poll_metrics_manager(*args)
        except (httpx.HTTPError, ValueError) as exc:
            log = (
                self.logger.debug if self._metrics_read_failed else self.logger.warning
            )
            self._metrics_read_failed = True
            log("Failed to read DLSPS metrics from metrics-manager: %s", exc)
            return None

    def _read_final_metrics(
        self,
        client: httpx.Client,
        instances: dict[str, str],
        allowed_stream_ids: "set[str] | None",
        genai: bool,
        run_seconds: float,
    ) -> None:
        """Read metrics-manager after the instances stopped, until their final export arrives.

        DLSPS exports the last export period of an instance, with
        ``pipeline_running`` 0, right after the instance finishes, but in the
        background: ``DELETE`` returns before that export reaches
        metrics-manager. A DLSPS without that flush exports it with its next
        periodic export instead. So metrics-manager is read until every
        instance reported ``pipeline_running`` 0, for at most one export
        interval plus ``_FINAL_EXPORT_GRACE_S``.

        Read once, without waiting, when the run was cancelled, or when DLSPS
        exported nothing for the run's instances although the run lasted
        longer than that wait (export not set up).
        """
        wait_s = DLSPS2_OTEL_INTERVAL_MS / 1000.0 + _FINAL_EXPORT_GRACE_S
        deadline = time.monotonic() + wait_s
        wait = not self.cancelled and (self._export_seen or run_seconds <= wait_s)
        while True:
            running = self._try_poll_metrics_manager(
                client, instances, allowed_stream_ids, genai
            )
            if running is None or not wait:
                return
            if all(running.get(iid) == 0 for iid in instances.values()):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.logger.debug(
                    "Final DLSPS export of %s not seen within %.1fs",
                    sorted(instances.values()),
                    wait_s,
                )
                return
            time.sleep(min(self.poll_interval, remaining))

    # ------------------------------------------------------------------
    # Validation mode
    # ------------------------------------------------------------------

    def _run_validation(self, pipeline_command: str) -> PipelineResult:
        """Run pipeline in validation mode against DLSPS 2.0.

        The pipeline is valid if it stays ``RUNNING`` for ``max_runtime`` seconds without error, or
        reaches ``COMPLETED`` (EOS) sooner. ``ERROR``/``ABORTED`` is invalid,
        and so is not reaching a verdict within ``hard_timeout``. The
        instance is always stopped afterwards regardless of outcome, since a
        validation check should never leave a pipeline running.
        """
        deadline = time.monotonic() + self.hard_timeout
        running_since: Optional[float] = None

        with self._client() as client:
            try:
                instance_id = self._start(client, pipeline_command)
            except httpx.HTTPError as exc:
                return PipelineResult(
                    exit_code=1,
                    stderr=[
                        "Failed to submit pipeline to DLSPS 2.0: "
                        f"{self._error_detail(exc)}"
                    ],
                )

            try:
                while True:
                    try:
                        status = self._status(client, instance_id)
                    except httpx.HTTPError as exc:
                        return PipelineResult(
                            exit_code=1,
                            stderr=[
                                f"Failed to poll DLSPS 2.0 instance {instance_id}: {exc}"
                            ],
                        )

                    state = status.get("state")
                    if state == "COMPLETED":
                        return PipelineResult(exit_code=0, stderr=[])
                    if state == "RUNNING":
                        now = time.monotonic()
                        if running_since is None:
                            running_since = now
                        if now - running_since >= self.max_runtime:
                            return PipelineResult(exit_code=0, stderr=[])
                    elif state in _TERMINAL_STATES:
                        # Terminal but not valid: ERROR / ABORTED.
                        message = status.get("message") or (
                            f"Pipeline validation failed (state={state})"
                        )
                        return PipelineResult(exit_code=1, stderr=[message])

                    if time.monotonic() >= deadline:
                        return PipelineResult(
                            exit_code=1,
                            stderr=[
                                "Pipeline validation timed out: DLSPS 2.0 did not "
                                f"reach a verdict within {self.hard_timeout}s "
                                f"(last state={state})"
                            ],
                        )

                    time.sleep(self.poll_interval)
            finally:
                self._stop(client, instance_id)

    # ------------------------------------------------------------------
    # Normal (performance and density) mode
    # ------------------------------------------------------------------

    def _capture_events(
        self, stream_commands: dict[str, str], genai: bool
    ) -> EventCapture | None:
        """Event files for this run, or ``None`` without ``on_event`` or event elements.

        Without ``post-metrics`` on the server's ``gvagenai`` (``genai`` false),
        VLM metrics fall back to the cumulative means in each answer's JSON.
        """
        self._vlm_from_answers = not genai
        if self.on_event is None:
            return None
        return EventCapture.create(
            stream_commands,
            self.job_id,
            self.on_event,
            on_vlm_metrics=self._push_answer_metrics,
        )

    def _histograms_unsupported(self) -> None:
        """Switch VLM metrics to the answers once metrics-manager stores no histograms."""
        if self._vlm_from_answers:
            return
        self._vlm_from_answers = True
        self.logger.warning(
            "metrics-manager stores the DLSPS 2.0 genai histograms without their "
            "values (it needs histogram support), so they are skipped. VLM "
            "metrics come only from gvagenai answers, read in performance tests."
        )

    def _push_answer_metrics(
        self, fields: dict[str, float], element: str | None
    ) -> None:
        """Push VLM metrics from the cumulative means in a ``gvagenai`` answer.

        Only when the server's own export cannot provide them: its
        ``gvagenai`` has no ``post-metrics``, or metrics-manager cannot store
        histograms. The means average every request since the element started.
        """
        if not self._vlm_from_answers:
            return
        if not self._vlm_fallback_warned:
            self._vlm_fallback_warned = True
            self.logger.warning(
                "VLM metrics come from the means in the gvagenai JSON metadata, "
                "which average every request since the element started."
            )
        entry: dict[str, object] = {"name": "vlm_metrics", "fields": fields}
        tags = self._tags(element)
        if tags:
            entry["tags"] = tags
        self._post_batch([entry], "vlm")

    def _warmup(self) -> float:
        """Warm-up before FPS samples count, never more than half the run."""
        if self.max_runtime > 0:
            return min(DLSPS2_WARMUP_S, self.max_runtime / 2)
        return DLSPS2_WARMUP_S

    def _run_streams(
        self,
        stream_commands: dict[str, str],
        allowed_stream_ids: "set[str] | None" = None,
        validation_stream_ids: "set[str] | None" = None,
    ) -> PipelineResult:
        """Run every stream as its own DLSPS 2.0 instance and measure each one.

        Unless ``validate_pipelines`` is off, the launch strings of
        ``validation_stream_ids`` (every stream if ``None``) are validated
        first, with their writing elements swapped out (see
        :func:`validation_launch_string` and :meth:`_validate_new`), so
        validation writes no files and publishes nothing. The instances then
        skip DLSPS's own per-instance validation and start together. All instances go to the unpinned worker. The run lasts
        ``max_runtime`` seconds from the moment every stream reports a
        ``first_frame_time`` (``0``: until every instance ends on its own),
        or until :meth:`cancel`. Every instance is stopped before returning;
        a cancel before or while the instances start starts no further one.

        DLSPS reports each stream's ``frame_fps`` over its last
        ``frame_interval`` seconds, and keeps both unchanged while no frames
        arrive. A status counts as a new window only when that pair changes,
        so a stalled stream is seen as one without frames and a window polled
        twice counts once. A stream's FPS is its frames over its seconds,
        summed over the new windows reported while all streams are running,
        after the warm-up. A stream without such windows (a run too short, or
        one that ended early) falls back to its final ``avg_fps``. This stands
        in for a DLSPS lifecycle timeline (ITEP-97433).

        Latency and VLM samples are read from metrics-manager every
        ``DLSPS2_METRICS_POLL_S`` seconds, with a client of its own and a
        short timeout, and after the instances stop until their final export
        arrives (see :meth:`_read_final_metrics`). The samples of earlier runs
        on the same runner are dropped first.

        Raises:
            RuntimeError: If validation fails, a submit fails, an instance
                ends in ``ERROR`` or ``ABORTED``, a stream produces no frames for
                ``inactivity_timeout`` seconds, or DLSPS stays unreachable for
                that long. Not raised once the run is cancelled.
        """
        instances: dict[str, str] = {}
        frames = dict.fromkeys(stream_commands, 0.0)
        seconds = dict.fromkeys(stream_commands, 0.0)
        windows: dict[str, tuple] = {}
        statuses: dict[str, dict] = {}
        if self.latency_tracer_metrics is not None:
            self.latency_tracer_metrics = {}
        self._consumed = {}
        self._export_seen = False
        self._metrics_read_failed = False
        started_at = time.monotonic()
        metrics_polled_at = started_at

        # DLSPS 2.0 counts FPS at the sink parsed last.
        stream_commands = {
            sid: with_fps_chain_last(command, sid)
            for sid, command in stream_commands.items()
        }
        with self._client() as client, self._metrics_client() as metrics_client:
            if any(
                wants_genai_post_metrics(c) for c in stream_commands.values()
            ) and self._server_has_genai_post_metrics(client):
                stream_commands = {
                    sid: with_genai_post_metrics(command)
                    for sid, command in stream_commands.items()
                }
            # Only elements that post their requests produce VLM metrics.
            genai = any(
                _POST_METRICS_ON.search(command) for command in stream_commands.values()
            )
            read_metrics = self.latency_tracer_metrics is not None or genai
            to_validate = [
                validation_launch_string(command)
                for sid, command in stream_commands.items()
                if validation_stream_ids is None or sid in validation_stream_ids
            ]
            capture = self._capture_events(stream_commands, genai)
            if capture is not None:
                stream_commands = capture.commands
            try:
                if self.validate_pipelines:
                    self._validate_new(client, to_validate)
                if self.cancelled:
                    return PipelineResult(exit_code=0, cancelled=True, stderr=[])
                if capture is not None:
                    capture.start()
                try:
                    for stream_id, command in stream_commands.items():
                        if self.cancelled:
                            break
                        try:
                            instances[stream_id] = self._start(
                                client, command, validate_pipeline=False
                            )
                        except httpx.HTTPError as exc:
                            raise RuntimeError(
                                f"Failed to submit stream {stream_id} to DLSPS 2.0: "
                                f"{self._error_detail(exc)}"
                            ) from exc

                    last_contact = time.monotonic()
                    last_frame = dict.fromkeys(instances, last_contact)
                    playing_since: float | None = None

                    while not self.cancelled:
                        now = time.monotonic()
                        if (
                            playing_since is not None
                            and self.max_runtime > 0
                            and now - playing_since >= self.max_runtime
                        ):
                            break

                        try:
                            statuses = self._statuses(client, instances)
                        except httpx.HTTPError as exc:
                            if now - last_contact > self.inactivity_timeout:
                                raise RuntimeError(
                                    "Lost contact with DLSPS 2.0 for over "
                                    f"{self.inactivity_timeout}s: {exc}"
                                ) from exc
                            time.sleep(self.poll_interval)
                            continue
                        last_contact = now

                        lost = [sid for sid in instances if sid not in statuses]
                        if lost:
                            raise RuntimeError(
                                f"DLSPS 2.0 no longer reports stream(s) "
                                f"{', '.join(lost)}; the server restarted or "
                                "dropped them"
                            )

                        states = {sid: s.get("state") for sid, s in statuses.items()}
                        for sid, state in states.items():
                            if state in ("ERROR", "ABORTED"):
                                message = (
                                    statuses[sid].get("message") or f"state={state}"
                                )
                                raise RuntimeError(
                                    f"Stream {sid} failed on DLSPS 2.0: {message}"
                                )
                        if len(states) == len(instances) and all(
                            state == "COMPLETED" for state in states.values()
                        ):
                            break

                        fps = {
                            sid: float(statuses[sid].get("frame_fps") or 0.0)
                            if sid in statuses
                            else 0.0
                            for sid in instances
                        }
                        fresh: list[str] = []
                        for sid, value in fps.items():
                            window = (
                                value,
                                statuses.get(sid, {}).get("frame_interval"),
                            )
                            if value > 0 and window != windows.get(sid):
                                windows[sid] = window
                                last_frame[sid] = now
                                fresh.append(sid)
                        stalled = [
                            sid
                            for sid in instances
                            if states.get(sid) != "COMPLETED"
                            and now - last_frame[sid] > self.inactivity_timeout
                        ]
                        if stalled:
                            raise RuntimeError(
                                f"No frames from stream(s) {', '.join(stalled)} on "
                                f"DLSPS 2.0 for over {self.inactivity_timeout}s"
                            )

                        all_playing = all(
                            states.get(sid) == "RUNNING"
                            and statuses[sid].get("first_frame_time") is not None
                            for sid in instances
                        )
                        if all_playing and playing_since is None:
                            playing_since = now
                        if (
                            all_playing
                            and playing_since is not None
                            and now - playing_since >= self._warmup()
                        ):
                            for sid in fresh:
                                interval = float(
                                    statuses[sid].get("frame_interval")
                                    or self.poll_interval
                                )
                                frames[sid] += fps[sid] * interval
                                seconds[sid] += interval

                        # Mean per stream for the live chart.
                        self._push_fps_metric(sum(fps.values()) / len(instances))
                        if (
                            read_metrics
                            and now - metrics_polled_at >= DLSPS2_METRICS_POLL_S
                        ):
                            metrics_polled_at = now
                            self._try_poll_metrics_manager(
                                metrics_client, instances, allowed_stream_ids, genai
                            )
                        time.sleep(self.poll_interval)
                finally:
                    if instances:
                        self._stop_all(client, list(instances.values()))
                        try:
                            statuses.update(self._statuses(client, instances))
                        except httpx.HTTPError:
                            pass
                        self._push_fps_metric(0.0)
                        if read_metrics:
                            self._read_final_metrics(
                                metrics_client,
                                instances,
                                allowed_stream_ids,
                                genai,
                                time.monotonic() - started_at,
                            )
            finally:
                if capture is not None:
                    capture.close()
        if self.latency_tracer_metrics == {} and not self.cancelled:
            self.logger.warning(
                "Latency metrics were enabled but no DLSPS latency samples reached "
                "metrics-manager: check that DLSPS 2.0 exports OpenTelemetry to "
                "metrics-manager and runs latency_tracer with post-metrics=true."
            )

        stream_fps: dict[str, float] = {}
        fallback = 0
        for sid in instances:
            if seconds[sid] > 0:
                stream_fps[sid] = frames[sid] / seconds[sid]
            else:
                stream_fps[sid] = float(statuses.get(sid, {}).get("avg_fps") or 0.0)
                fallback += 1

        total_fps = sum(stream_fps.values())
        details = (
            f"DLSPS 2.0: {len(instances)} instance(s) in the unpinned worker, "
            "fps over the common window"
        )
        if fallback:
            details += f"; final avg_fps used for {fallback} stream(s)"
        return PipelineResult(
            total_fps=total_fps,
            per_stream_fps=total_fps / len(instances) if instances else 0.0,
            num_streams=len(instances),
            exit_code=0,
            cancelled=self.cancelled,
            stdout=[],
            stderr=[
                f"{sid}: {status['message']}"
                for sid, status in statuses.items()
                if status.get("message")
            ],
            details=details,
            latency_tracer_metrics=self.latency_tracer_metrics,
            stream_fps=stream_fps,
        )
