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
  ``GET /pipelines/{id}/status`` until the instance leaves ``QUEUED``
  (``RUNNING``/``COMPLETED`` ⇒ valid, ``ERROR``/``ABORTED`` ⇒ invalid), then
  ``DELETE /pipelines/{id}`` to tear the instance back down.
* ``mode="normal"`` with ``total_streams == 1`` (single-stream performance
  tests) — maps onto ``POST /pipelines``, polling
  ``GET /pipelines/{id}/status`` for ``avg_fps``, and
  ``DELETE /pipelines/{id}`` once ``max_runtime`` elapses, the pipeline
  reaches a terminal state, or the caller cancels the run.

Deliberately NOT supported — ``run()`` raises :class:`NotImplementedError`:

* ``enable_latency_metrics=True``: DLSPS 2.0 has no ``latency_tracer``
  support at all — there is no REST-exposed way to read per-stream latency
  samples from a running instance.
* ``mode="normal"`` with ``total_streams != 1`` (density tests / multi-stream
  performance tests): DLSPS 2.0's FPS probe attaches to a single sink
  element and reports one ``avg_fps``/``frame_fps`` pair per instance. A
  VIPPET density/multi-stream pipeline combines several *independent*
  source/sink chains into one launch string, and dlsps2 cannot currently
  report a correct per-stream FPS breakdown for that shape (see repo notes
  on the pad-probe fix, which assumes multiple sinks are duplicates of one
  stream via a ``tee``, not independent streams).

Callers should catch :class:`NotImplementedError` and fall back to the local
:class:`~pipeline_runner.PipelineRunner` for unsupported cases — see
``managers.validation_manager`` and ``managers.tests_manager`` for the
selection logic.
"""

import json
import logging
import os
import threading
import time
import urllib.request
from typing import Optional

import httpx

from pipeline_runner import PipelineResult

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
    "DLSPS2_BASE_URL", "https://dlstreamer-pipeline-server:8443"
).rstrip("/")

# Whether to verify the DLSPS 2.0 server's TLS certificate. Defaults to
# False because dlsps2 deployments in this repo commonly terminate TLS with
# a self-signed certificate behind an nginx sidecar.
DLSPS2_VERIFY_TLS: bool = os.environ.get("DLSPS2_VERIFY_TLS", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Per-request HTTP timeout, seconds.
DLSPS2_HTTP_TIMEOUT_S: float = float(os.environ.get("DLSPS2_HTTP_TIMEOUT_S", "30"))

# Default interval used to poll GET /pipelines/{id}/status, seconds.
DLSPS2_POLL_INTERVAL_S: float = float(os.environ.get("DLSPS2_POLL_INTERVAL_S", "1"))

# States a dlsps2 pipeline instance can no longer leave on its own.
_TERMINAL_STATES = frozenset({"COMPLETED", "ERROR", "ABORTED"})
# States that mean "the pipeline was accepted and is/was executing".
_VALID_STATES = frozenset({"RUNNING", "COMPLETED"})


class Dlsps2PipelineRunner:
    """Executes one pipeline via a running DLSPS 2.0 instance's REST API.

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
    ):
        """Initialize the runner.

        Args mirror :class:`pipeline_runner.PipelineRunner.__init__` — see
        that docstring for full semantics. ``base_url`` is adapter-specific:
        the base URL of the DLSPS 2.0 instance to talk to (defaults to
        ``DLSPS2_BASE_URL``).

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
        self.cancelled = False
        self.logger = logger

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
    ) -> PipelineResult:
        """Run a pipeline against DLSPS 2.0 and return a `PipelineResult`.

        Args:
            pipeline_command: Complete GStreamer pipeline description string
                (VIPPET already builds one complete string per test via
                ``PipelineManager.build_pipeline_command()``, so this maps
                directly onto ``POST /pipelines``'s ``pipeline`` field).
            total_streams: Expected stream count. Only ``1`` is supported in
                normal mode (see module docstring); ignored in validation
                mode.
            allowed_stream_ids: Unused — accepted only so this method has the
                same signature as ``PipelineRunner.run()``. DLSPS 2.0 exposes
                no latency_tracer / per-stream data to filter.

        Returns:
            PipelineResult with ``exit_code``/``stderr`` (validation mode) or
            ``total_fps``/``per_stream_fps``/``exit_code`` (normal mode).

        Raises:
            NotImplementedError: If ``mode == "normal"`` and
                ``total_streams != 1``.
            RuntimeError: If the pipeline fails on DLSPS 2.0 without having
                been cancelled (normal mode only, mirroring
                ``PipelineRunner``'s contract).
        """
        if self.mode == "validation":
            return self._run_validation(pipeline_command)

        if total_streams != 1:
            raise NotImplementedError(
                "Dlsps2PipelineRunner only supports single-stream "
                f"('normal', total_streams=1) performance runs; got "
                f"total_streams={total_streams}. Multi-stream/density tests "
                "still require the local PipelineRunner."
            )
        return self._run_normal(pipeline_command)

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=DLSPS2_HTTP_TIMEOUT_S, verify=DLSPS2_VERIFY_TLS)

    def _start(self, client: httpx.Client, pipeline_command: str) -> str:
        response = client.post(
            f"{self.base_url}/pipelines", json={"pipeline": pipeline_command}
        )
        response.raise_for_status()
        return response.json()["instance_id"]

    def _status(self, client: httpx.Client, instance_id: str) -> dict:
        response = client.get(f"{self.base_url}/pipelines/{instance_id}/status")
        response.raise_for_status()
        return response.json()

    def _stop(self, client: httpx.Client, instance_id: str) -> None:
        """Best-effort DELETE /pipelines/{id}. Never raises."""
        try:
            response = client.delete(f"{self.base_url}/pipelines/{instance_id}")
            if response.status_code not in (200, 404):
                response.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.warning(
                "Failed to stop DLSPS 2.0 instance %s: %s", instance_id, exc
            )

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

        Validity is determined by whether the submitted instance leaves
        ``QUEUED`` into ``RUNNING``/``COMPLETED`` (valid) or
        ``ERROR``/``ABORTED`` (invalid) before ``hard_timeout`` elapses. The
        instance is always stopped afterwards regardless of outcome, since a
        validation check should never leave a pipeline running.
        """
        deadline = time.monotonic() + self.hard_timeout

        with self._client() as client:
            try:
                instance_id = self._start(client, pipeline_command)
            except httpx.HTTPError as exc:
                return PipelineResult(
                    exit_code=1,
                    stderr=[f"Failed to submit pipeline to DLSPS 2.0: {exc}"],
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
                    if state in _VALID_STATES:
                        return PipelineResult(exit_code=0, stderr=[])
                    if state in _TERMINAL_STATES:
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
                                f"accept the pipeline within {self.hard_timeout}s "
                                f"(last state={state})"
                            ],
                        )

                    time.sleep(self.poll_interval)
            finally:
                self._stop(client, instance_id)

    # ------------------------------------------------------------------
    # Normal (single-stream performance) mode
    # ------------------------------------------------------------------

    def _run_normal(self, pipeline_command: str) -> PipelineResult:
        """Run a single-stream pipeline in normal mode against DLSPS 2.0.

        Polls ``GET /pipelines/{id}/status`` every ``poll_interval`` seconds
        until ``max_runtime`` elapses (``0`` means run until the pipeline
        reaches a terminal state on its own), the pipeline reaches a
        terminal state, or the caller calls :meth:`cancel`. The instance is
        always stopped via ``DELETE /pipelines/{id}`` before returning.
        """
        with self._client() as client:
            try:
                instance_id = self._start(client, pipeline_command)
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"Failed to submit pipeline to DLSPS 2.0: {exc}"
                ) from exc

            start_time = time.monotonic()
            last_activity_time = start_time
            last_status: Optional[dict] = None

            try:
                while not self.cancelled:
                    if (
                        self.max_runtime > 0
                        and (time.monotonic() - start_time) >= self.max_runtime
                    ):
                        break

                    try:
                        last_status = self._status(client, instance_id)
                    except httpx.HTTPError as exc:
                        if (
                            time.monotonic() - last_activity_time
                            > self.inactivity_timeout
                        ):
                            raise RuntimeError(
                                f"Lost contact with DLSPS 2.0 instance {instance_id} "
                                f"for over {self.inactivity_timeout}s: {exc}"
                            ) from exc
                        time.sleep(self.poll_interval)
                        continue

                    last_activity_time = time.monotonic()
                    # Push the instantaneous ('last interval') fps, not the
                    # cumulative avg_fps, so the UI's live chart reacts to
                    # real fluctuations the same way it does for the local
                    # PipelineRunner (which reports gvafpscounter's rolling
                    # 1s-window average, not a since-start cumulative one).
                    frame_fps = last_status.get("frame_fps")
                    if frame_fps is not None:
                        self._push_fps_metric(float(frame_fps))

                    if last_status.get("state") in _TERMINAL_STATES:
                        break

                    time.sleep(self.poll_interval)
            finally:
                self._stop(client, instance_id)
                # One last poll after stopping, so the returned metrics
                # reflect the instance's final reported state where possible.
                try:
                    last_status = self._status(client, instance_id) or last_status
                except httpx.HTTPError:
                    pass
                # Signal to the UI's live chart that the pipeline is no
                # longer running, mirroring PipelineRunner's own final
                # `_push_fps_metric(0.0)` call at shutdown.
                self._push_fps_metric(0.0)

            if last_status is None:
                raise RuntimeError(
                    f"No status was ever received for DLSPS 2.0 instance {instance_id}"
                )

            state = last_status.get("state")
            avg_fps = last_status.get("avg_fps") or 0.0
            exit_code = 1 if state == "ERROR" and not self.cancelled else 0

            if exit_code != 0:
                # Mirror PipelineRunner's contract: a non-cancelled failure
                # raises, it is not returned as a "failed" PipelineResult.
                raise RuntimeError(
                    "Pipeline execution failed on DLSPS 2.0: "
                    f"{last_status.get('message') or f'state={state}'}"
                )

            return PipelineResult(
                total_fps=avg_fps,
                per_stream_fps=avg_fps,
                num_streams=1,
                exit_code=0,
                cancelled=self.cancelled,
                stdout=[],
                stderr=[last_status.get("message")] if last_status.get("message") else [],
                details=f"DLSPS 2.0 instance {instance_id} (state={state})",
                latency_tracer_metrics=None,
            )
