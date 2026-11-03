# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""dlsps2_runner.py

``Dlsps2PipelineRunner`` is a :class:`~pipeline_runner.PipelineRunner`-compatible
adapter that executes a pipeline against a running DLSPS 2.0
(``dlstreamer-pipeline-server``) instance's REST API instead of spawning a
local ``gst_runner.py`` subprocess.

Only a subset of :class:`~pipeline_runner.PipelineRunner`'s behaviour is
supported today:

* ``mode="validation"`` — maps onto ``POST /pipelines`` followed by polling
  ``GET /pipelines/{id}/status``. Like ``gst_runner.py --mode validation``,
  the pipeline is valid if it stays ``RUNNING`` for ``max_runtime`` seconds or
  reaches ``COMPLETED`` sooner; ``ERROR``/``ABORTED`` is invalid. The
  instance is then torn down with ``DELETE /pipelines/{id}``.
* ``mode="normal"`` (performance and density tests) — every launch string
  not yet validated by this runner is checked first with ``POST /validate``,
  all at once. Every stream then runs as its own instance (``POST /pipelines``
  per stream with ``validate_pipeline=false``, all in the unpinned worker),
  so the instances start together. ``GET /pipelines/status`` is polled for
  each stream's ``frame_fps`` and ``frame_interval``; every instance is
  stopped with
  ``DELETE /pipelines/{id}`` once ``max_runtime`` elapses, all instances end,
  or the caller cancels.
  The result carries the FPS of each stream, so callers can judge the
  slowest one.

Deliberately NOT supported:

* ``enable_latency_metrics=True`` raises :class:`NotImplementedError`:
  DLSPS 2.0 has no ``latency_tracer`` support at all — there is no
  REST-exposed way to read per-stream latency samples from a running
  instance.
* A combined multi-stream launch string without per-stream commands raises
  :class:`NotImplementedError`: DLSPS 2.0 counts frames on the first sink
  of an instance only.

Callers fall back to the local :class:`~pipeline_runner.PipelineRunner` for
unsupported cases — see ``managers.validation_manager``,
``managers.tests_manager`` and ``benchmark`` for the selection logic.
"""

import json
import logging
import os
import threading
import time
import urllib.request
from typing import Optional

import httpx

from pipeline_runner import LatencyTracerSample, PipelineResult

logger = logging.getLogger("dlsps2_runner")

# Base URL of metrics-manager, used to push a live "fps" metric while a
# normal-mode run is in progress (mirrors pipeline_runner.PipelineRunner's
# own metrics-manager pushes, so the UI's live FPS chart -- which polls
# metrics-manager filtered by `job_id` -- works the same way regardless of
# which runner backend executed the job).
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

# States a dlsps2 pipeline instance can no longer leave on its own.
_TERMINAL_STATES = frozenset({"COMPLETED", "ERROR", "ABORTED"})


class Dlsps2PipelineRunner:
    """Executes pipelines via a running DLSPS 2.0 instance's REST API.

    Mirrors the subset of :class:`~pipeline_runner.PipelineRunner`'s public
    interface (constructor keyword args, ``run()``, ``cancel()``,
    ``is_cancelled()``) that ``managers.validation_manager`` and
    ``managers.tests_manager`` rely on, so it can be substituted in as a
    drop-in for the supported cases (see module docstring).
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
    ):
        """Initialize the runner.

        Args mirror :class:`pipeline_runner.PipelineRunner.__init__` — see
        that docstring for full semantics. ``base_url`` and
        ``validate_pipelines`` are adapter-specific: the base URL of the
        DLSPS 2.0 instance to talk to (defaults to ``DLSPS2_BASE_URL``), and
        whether normal mode first checks each launch string with
        ``POST /validate``. Turn the check off for a pipeline that writes a
        file, since the check would run it once more before the real run.

        Raises:
            NotImplementedError: If ``enable_latency_metrics`` is True —
                DLSPS 2.0 has no latency_tracer support to expose.
        """
        if enable_latency_metrics:
            raise NotImplementedError(
                "Dlsps2PipelineRunner does not support enable_latency_metrics: "
                "DLSPS 2.0 has no latency_tracer support."
            )

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
        self.cancelled = False
        self.logger = logger
        # Launch strings DLSPS 2.0 already accepted, reused across density iterations.
        self._validated: set[str] = set()
        # Same attribute as PipelineRunner; DLSPS 2.0 has no latency tracer.
        self.latency_tracer_metrics: dict[str, LatencyTracerSample] | None = None

        metrics_manager_url = os.environ.get(
            "METRICS_MANAGER_URL", DEFAULT_METRICS_MANAGER_URL
        ).rstrip("/")
        self._metrics_manager_fps_url = f"{metrics_manager_url}/api/v1/metrics/simple"

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
    ) -> PipelineResult:
        """Run a pipeline against DLSPS 2.0 and return a `PipelineResult`.

        Args:
            pipeline_command: Complete GStreamer pipeline description string.
                Validation mode submits it as is. Normal mode uses it only
                when ``stream_commands`` is not given.
            total_streams: Expected stream count. Without ``stream_commands``
                only ``1`` is supported in normal mode; ignored in
                validation mode.
            allowed_stream_ids: Unused — accepted only so this method has the
                same signature as ``PipelineRunner.run()``. DLSPS 2.0 exposes
                no latency_tracer data to filter.
            stream_commands: Normal mode only. One launch string per stream,
                keyed by ``stream_id`` (``PipelineCommand.stream_commands``);
                each runs as its own DLSPS 2.0 instance.

        Returns:
            PipelineResult with ``exit_code``/``stderr`` (validation mode) or
            ``total_fps``/``per_stream_fps``/``stream_fps`` (normal mode).

        Raises:
            NotImplementedError: If ``mode == "normal"``, ``stream_commands``
                is not given and ``total_streams != 1``.
            RuntimeError: If the run fails on DLSPS 2.0 without having been
                cancelled (normal mode only, mirroring ``PipelineRunner``'s
                contract).
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
        return self._run_streams(stream_commands)

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=DLSPS2_HTTP_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS)

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
        """Status of each instance in ``{stream_id: instance_id}``, in one request.

        Instances DLSPS no longer reports are left out.
        """
        response = client.get(f"{self.base_url}/pipelines/status")
        response.raise_for_status()
        by_id = {item.get("id"): item for item in response.json()}
        return {
            stream_id: by_id[instance_id]
            for stream_id, instance_id in instances.items()
            if instance_id in by_id
        }

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

    def _stop_all(self, client: httpx.Client, instance_ids: list[str]) -> None:
        """Stop every instance. Never raises.

        DLSPS 2.0 answers ``DELETE`` with 409 while an instance is still
        ``QUEUED`` in validation, and starts it afterwards. Such instances are
        retried until they leave ``QUEUED`` or ``DLSPS2_STOP_TIMEOUT_S``
        passes.
        """
        pending = list(instance_ids)
        deadline = time.monotonic() + DLSPS2_STOP_TIMEOUT_S
        while True:
            pending = [iid for iid in pending if not self._try_stop(client, iid)]
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(self.poll_interval)
        if pending:
            self.logger.warning(
                "DLSPS 2.0 instances still queued after %ss, not stopped: %s",
                DLSPS2_STOP_TIMEOUT_S,
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

        Mirrors ``PipelineRunner._push_fps_metric``: same endpoint
        (``/api/v1/metrics/simple``) and payload shape (``{"name": "fps",
        "value": ..., "tags": {"job_id": ...}}``), so the UI's live FPS
        chart -- which reads metrics-manager filtered by ``job_id`` -- works
        identically whether a job ran via the local ``PipelineRunner`` or
        this DLSPS 2.0 adapter. Runs the POST on a short-lived daemon thread
        so a slow/unreachable metrics-manager never delays polling.
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

    # ------------------------------------------------------------------
    # Validation mode
    # ------------------------------------------------------------------

    def _run_validation(self, pipeline_command: str) -> PipelineResult:
        """Run pipeline in validation mode against DLSPS 2.0.

        Mirrors ``gst_runner.py --mode validation``: the pipeline is valid if
        it stays ``RUNNING`` for ``max_runtime`` seconds without error, or
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

    def _warmup(self) -> float:
        """Warm-up before FPS samples count, never more than half the run."""
        if self.max_runtime > 0:
            return min(DLSPS2_WARMUP_S, self.max_runtime / 2)
        return DLSPS2_WARMUP_S

    def _run_streams(self, stream_commands: dict[str, str]) -> PipelineResult:
        """Run every stream as its own DLSPS 2.0 instance and measure each one.

        Launch strings are validated first (see :meth:`_validate_new`, unless
        ``validate_pipelines`` is off), so the instances skip DLSPS's own per-instance validation and start
        together. All instances go to the unpinned worker. The run lasts
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

        with self._client() as client:
            if self.validate_pipelines:
                self._validate_new(client, list(stream_commands.values()))
            if self.cancelled:
                return PipelineResult(exit_code=0, cancelled=True, stderr=[])
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

                    states = {sid: s.get("state") for sid, s in statuses.items()}
                    for sid, state in states.items():
                        if state in ("ERROR", "ABORTED"):
                            message = statuses[sid].get("message") or f"state={state}"
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
                        window = (value, statuses.get(sid, {}).get("frame_interval"))
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

                    # Mean per stream, as PipelineRunner pushes for the live chart.
                    self._push_fps_metric(sum(fps.values()) / len(instances))
                    time.sleep(self.poll_interval)
            finally:
                if instances:
                    self._stop_all(client, list(instances.values()))
                    try:
                        statuses.update(self._statuses(client, instances))
                    except httpx.HTTPError:
                        pass
                    self._push_fps_metric(0.0)

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
            latency_tracer_metrics=None,
            stream_fps=stream_fps,
        )
