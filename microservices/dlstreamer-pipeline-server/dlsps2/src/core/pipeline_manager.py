# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline Manager for DLSPS 2.0

Manages the lifecycle of GStreamer pipeline instances: validating,
launching, tracking, and stopping.

Architecture
------------
A single, long-lived ``gst_worker.py`` subprocess is shared by every
pipeline instance (started once, in ``PipelineManager.__init__``), rather
than one subprocess per pipeline. Pipelines are multiplexed onto that one
worker over a small JSON-lines protocol on its stdin/stdout.

Before a pipeline is handed to the shared worker, it is first validated by
running it in its own short-lived, fully-isolated ``gst_validator.py``
subprocess, which returns as soon as the pipeline reaches PLAYING (or
fails). This keeps a bad pipeline description from ever reaching (and
potentially destabilizing) the shared worker process, which may be
hosting other, unrelated pipelines at the same time. Only pipelines that
pass validation are submitted to the worker.

FPS metrics (``avg_fps``/``frame_fps``) are updated live from the worker's
structured ``{"event": "fps", ...}`` status lines, matching the status
fields of the original DLSPS.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Absolute paths to sibling scripts in core/
_GST_WORKER = os.path.join(os.path.dirname(__file__), "gst_worker.py")
_GST_VALIDATOR = os.path.join(os.path.dirname(__file__), "gst_validator.py")

# gst_validator.py has no internal timeout for reaching PLAYING (see its
# module docstring); this is the external hang safety-net bounding the
# whole validator subprocess -- e.g. an unreachable source that never lets
# the pipeline reach PLAYING.
_VALIDATION_SUBPROCESS_TIMEOUT_SECONDS = 30.0

# gst_worker.py logs to stderr as one JSON object per line (see its
# _JsonLogFormatter): {"level": "INFO", "name": "gst_worker", "message": ...}.
# Map its level name back to a Python logging level number so each line can
# be re-logged here at its own actual severity, instead of collapsing every
# line (including plain INFO/DEBUG messages) into logger.error().
_WORKER_LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

# If the shared worker keeps crashing immediately after restart, stop trying
# rather than busy-looping forever.
_MAX_RESTART_ATTEMPTS = 5
_RESTART_WINDOW_SECONDS = 60.0


class PipelineState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


@dataclass
class PipelineInstance:
    """Represents a single running or completed pipeline instance."""

    instance_id: str
    pipeline_description: str
    state: PipelineState = PipelineState.QUEUED
    error: Optional[str] = None

    # Metrics (updated live from the shared worker's status events)
    avg_fps: float = 0.0
    frame_fps: float = 0.0
    start_time: Optional[float] = None
    stop_time: Optional[float] = None

    # Optional request metadata, populated when the instance was started via
    # the legacy named-pipeline API (POST /pipelines/{name}/{version}). Mirrors
    # the "params" summary (name/version/request body) that legacy API exposes
    # on GET /pipelines/{instance_id}. Left as None for instances started via
    # the raw inline POST /pipelines endpoint, since there is no request body
    # to echo back in that case.
    name: Optional[str] = None
    version: Optional[str] = None
    request: Optional[dict] = None

    def elapsed_time(self) -> Optional[float]:
        if self.start_time is None:
            return None
        end = self.stop_time if self.stop_time is not None else time.time()
        return max(0.0, end - self.start_time)

    def to_status_dict(self) -> dict:
        """Pure runtime-status view, matching legacy API GET /pipelines/{id}/status
        and GET /pipelines/status (no pipeline config/request data included).
        """
        return {
            "id": self.instance_id,
            "state": self.state.value,
            "avg_fps": self.avg_fps,
            "frame_fps": self.frame_fps,
            "start_time": self.start_time,
            "elapsed_time": self.elapsed_time(),
            "message": self.error or "",
        }

    def to_dict(self) -> dict:
        """Full summary view (status + pipeline config), matching legacy API
        GET /pipelines/{instance_id}.
        """
        summary = self.to_status_dict()
        summary.update(
            {
                # Legacy API parity fields (see GET /pipelines/{instance_id} in
                # the original REST API): pipeline "type" is always a raw
                # GStreamer launch string in dlsps2, so "type" is fixed at
                # "GStreamer" (capitalized, matching the literal value DLSPS 1.0
                # writes into its generated pipeline.json / echoes back).
                "type": "GStreamer",
                "launch_command": self.pipeline_description,
                "name": self.name,
                "version": self.version,
                "request": self.request,
            }
        )
        return summary


class PipelineManager:
    """
    Manages GStreamer pipeline instances on top of a single shared
    gst_worker.py subprocess.

    - ``start()`` validates the pipeline (in its own short-lived
      gst_validator.py subprocess) on a background thread, and only submits
      it to the shared worker if validation passes.
    - A single background thread reads the shared worker's stdout and
      dispatches each JSON status event to the matching PipelineInstance.
    - ``stop()`` sends a "stop" command for just that instance_id; the
      shared worker keeps running for other pipelines.
    - ``shutdown()`` (called on application shutdown) tells the shared
      worker to shut down entirely, falling back to SIGKILL if needed.
    - If the shared worker exits on its own (a crash, not a deliberate
      ``shutdown()``), every pipeline it was hosting is marked ERROR and a
      fresh worker subprocess is started automatically, up to
      ``_MAX_RESTART_ATTEMPTS`` times per ``_RESTART_WINDOW_SECONDS``.
    """

    _SHUTDOWN_TIMEOUT = 15.0  # seconds to wait for graceful worker shutdown

    def __init__(self) -> None:
        self._instances: Dict[str, PipelineInstance] = {}
        self._lock = threading.RLock()
        self._stdin_lock = threading.Lock()

        self._worker_process: Optional[subprocess.Popen] = None
        self._shutting_down = threading.Event()
        self._restart_timestamps: list = []
        self._start_worker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        pipeline_description: str,
        *,
        name: Optional[str] = None,
        version: Optional[str] = None,
        request: Optional[dict] = None,
    ) -> str:
        """Validate and submit a new pipeline instance.

        Returns immediately with an instance_id in QUEUED state; validation
        and submission to the shared worker happen on a background thread.

        Args:
            pipeline_description: GStreamer pipeline string.
            name: Legacy pipeline "name" segment (e.g. "user_defined_pipelines"),
                if this instance was started via the named-pipeline API.
            version: Legacy pipeline "version" segment (the config pipeline name),
                if this instance was started via the named-pipeline API.
            request: The original request body (source/destination/parameters/tags),
                if this instance was started via the named-pipeline API.

        Returns:
            instance_id (UUID string) assigned to this instance.
        """
        instance_id = str(uuid.uuid4())
        instance = PipelineInstance(
            instance_id=instance_id,
            pipeline_description=pipeline_description,
            name=name,
            version=version,
            request=request,
        )

        with self._lock:
            self._instances[instance_id] = instance

        thread = threading.Thread(
            target=self._validate_and_submit,
            args=(instance,),
            name=f"pipeline-{instance_id[:8]}",
            daemon=True,
        )
        thread.start()

        logger.info("Submitted pipeline instance %s for validation", instance_id)
        return instance_id

    def stop(self, instance_id: str) -> bool:
        """Request a graceful stop of one pipeline instance on the shared worker.

        Returns:
            True if the instance was running and the stop request was sent,
            False if the instance was not found or not in RUNNING state.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                return False
            if instance.state != PipelineState.RUNNING:
                return False
            instance.state = PipelineState.ABORTED

        self._send_command({"cmd": "stop", "instance_id": instance_id})
        logger.info("Requested stop for pipeline instance %s", instance_id)
        return True

    def get(self, instance_id: str) -> Optional[PipelineInstance]:
        """Return the instance for the given ID, or None if not found."""
        with self._lock:
            return self._instances.get(instance_id)

    def list_all(self) -> list[PipelineInstance]:
        """Return a snapshot of all instances."""
        with self._lock:
            return list(self._instances.values())

    def list_running(self) -> list[PipelineInstance]:
        """Return a snapshot of instances currently in RUNNING state."""
        with self._lock:
            return [i for i in self._instances.values() if i.state == PipelineState.RUNNING]

    def shutdown(self) -> None:
        """Shut down the shared worker process. Call this on application shutdown."""
        self._shutting_down.set()

        process = self._worker_process
        if process is None or process.poll() is not None:
            return

        self._send_command({"cmd": "shutdown"})
        try:
            process.wait(timeout=self._SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning(
                "gst_worker did not exit within %.1fs of shutdown request, killing it",
                self._SHUTDOWN_TIMEOUT,
            )
            try:
                process.kill()
                process.wait()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Validation (runs before a pipeline is ever submitted to the worker)
    # ------------------------------------------------------------------

    def _validate_and_submit(self, instance: PipelineInstance) -> None:
        """Background-thread body: validate, then submit to the shared worker."""
        logger.debug("Validating pipeline %s before submission", instance.instance_id)
        ok, reason = self._validate(instance.pipeline_description)

        if not ok:
            with self._lock:
                instance.state = PipelineState.ERROR
                instance.error = f"validation failed: {reason}" if reason else "validation failed"
                instance.stop_time = time.time()
            logger.error("Pipeline %s failed validation: %s", instance.instance_id, reason)
            return

        with self._lock:
            # Don't override a stop() that raced in while validation was running.
            if instance.state == PipelineState.QUEUED:
                instance.state = PipelineState.RUNNING
                instance.start_time = time.time()

        self._send_command({
            "cmd": "start",
            "instance_id": instance.instance_id,
            "pipeline": instance.pipeline_description,
        })
        logger.info("Pipeline %s passed validation and was submitted to gst_worker", instance.instance_id)

    @staticmethod
    def _validate(pipeline_description: str) -> Tuple[bool, Optional[str]]:
        """Run gst_validator.py in its own short-lived subprocess.

        Returns:
            (True, None)      if the pipeline is valid.
            (False, reason)   if the pipeline is invalid or validation itself
                              could not be completed.
        """
        cmd = [
            sys.executable,
            _GST_VALIDATOR,
            "--log-level",
            "WARNING",
            pipeline_description,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=_VALIDATION_SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, "validation subprocess timed out"
        except Exception as exc:  # noqa: BLE001
            return False, f"validation subprocess failed to launch: {exc!r}"

        if result.returncode == 0:
            return True, None

        # Surface the most relevant diagnostic line from the validator's stderr.
        # gst_validator.py always logs its own generic
        # "Pipeline validation FAILED (reason: ...)" summary as the LAST
        # ERROR-level line; the actual root-cause GStreamer error (e.g. a
        # missing model file or element) is logged earlier. Prefer the
        # first specific ERROR line so callers see the real cause instead
        # of the generic summary.
        reason = None
        for line in result.stderr.splitlines():
            if "ERROR" in line and "Pipeline validation FAILED" not in line:
                reason = line.strip()
                break
        if reason is None:
            for line in reversed(result.stderr.splitlines()):
                if "ERROR" in line:
                    reason = line.strip()
                    break
        return False, reason or f"validator exited with code {result.returncode}"

    # ------------------------------------------------------------------
    # Shared worker process management
    # ------------------------------------------------------------------

    def _start_worker(self) -> None:
        """Launch the single, long-lived gst_worker.py subprocess."""
        cmd = [sys.executable, _GST_WORKER]
        logger.debug("Launching shared gst_worker subprocess")

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._worker_process = process

        threading.Thread(
            target=self._read_worker_stdout,
            args=(process,),
            name="gst-worker-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_worker_stderr,
            args=(process,),
            name="gst-worker-stderr",
            daemon=True,
        ).start()

    def _send_command(self, command: dict) -> None:
        """Write one JSON command line to the shared worker's stdin."""
        process = self._worker_process
        if process is None or process.stdin is None or process.poll() is not None:
            logger.error("Cannot send command %s: worker process not available", command)
            return
        try:
            with self._stdin_lock:
                process.stdin.write(json.dumps(command) + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            logger.error("Failed to send command %s to gst_worker: %r", command, exc)

    def _read_worker_stdout(self, process: subprocess.Popen) -> None:
        """Background thread: dispatch the shared worker's JSON status events.

        If the worker exits on its own (i.e. not as part of a deliberate
        ``shutdown()``), every instance it was hosting is marked ERROR (no
        further events will ever arrive for them) and a fresh worker
        subprocess is started to take its place, so the manager keeps
        working for subsequently submitted pipelines.
        """
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                # Some elements (e.g. gvafpscounter) may still write raw,
                # non-JSON text directly to stdout; just log it.
                logger.debug("[gst_worker] %s", stripped)
                continue
            self._handle_event(event)

        if self._shutting_down.is_set():
            logger.info("gst_worker stdout closed (expected — shutdown in progress)")
            return

        logger.warning("gst_worker stdout closed unexpectedly — the shared worker process has exited")
        self._fail_all_running("gst_worker process exited unexpectedly")
        self._restart_worker()

    def _restart_worker(self) -> None:
        """Restart the shared worker after an unexpected exit, with backoff.

        Gives up (logging a CRITICAL message) if the worker has crashed
        ``_MAX_RESTART_ATTEMPTS`` times within the last
        ``_RESTART_WINDOW_SECONDS`` — at that point something is
        persistently wrong (e.g. a broken environment) and restarting again
        immediately would just busy-loop.
        """
        now = time.time()
        with self._lock:
            self._restart_timestamps = [
                t for t in self._restart_timestamps if now - t < _RESTART_WINDOW_SECONDS
            ]
            if len(self._restart_timestamps) >= _MAX_RESTART_ATTEMPTS:
                logger.critical(
                    "gst_worker crashed %d times within %.0fs — giving up on automatic "
                    "restart. New pipeline submissions will fail until the service is restarted.",
                    len(self._restart_timestamps),
                    _RESTART_WINDOW_SECONDS,
                )
                return
            self._restart_timestamps.append(now)
            attempt = len(self._restart_timestamps)

        logger.warning(
            "Restarting shared gst_worker subprocess (attempt %d/%d within the last %.0fs)",
            attempt,
            _MAX_RESTART_ATTEMPTS,
            _RESTART_WINDOW_SECONDS,
        )
        self._start_worker()

    def _read_worker_stderr(self, process: subprocess.Popen) -> None:
        """Background thread: parse and re-log the shared worker's JSON log lines.

        Each line is a JSON object produced by gst_worker.py's own logging
        setup (``{"level": ..., "name": ..., "message": ...}``). Re-logging
        at the level it actually reports (rather than unconditionally at
        ERROR) keeps routine INFO/DEBUG output from being misreported as an
        error here.
        """
        for line in process.stderr:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
                level = _WORKER_LOG_LEVELS.get(record.get("level"), logging.INFO)
                message = record.get("message", stripped)
            except json.JSONDecodeError:
                # Non-JSON output (e.g. a raw GLib/Gst assertion) — severity
                # unknown, so don't assume it's an error.
                level = logging.WARNING
                message = stripped
            logger.log(level, "[gst_worker] %s", message)

    def _handle_event(self, event: dict) -> None:
        """Dispatch one JSON status event from the shared worker to its instance."""
        instance_id = event.get("instance_id")
        evt = event.get("event")

        with self._lock:
            instance = self._instances.get(instance_id)
        if instance is None:
            logger.debug("Received event for unknown/finished instance %s: %s", instance_id, event)
            return

        if evt == "fps":
            with self._lock:
                if event.get("avg_fps") is not None:
                    instance.avg_fps = float(event["avg_fps"])
                if event.get("last_fps") is not None:
                    instance.frame_fps = float(event["last_fps"])
        elif evt == "started":
            logger.debug("Pipeline %s started", instance_id)
        elif evt == "eos":
            logger.info("Pipeline %s reached EOS", instance_id)
        elif evt == "error":
            with self._lock:
                instance.error = event.get("reason") or instance.error
                # Some failures (e.g. Gst.parse_launch() raising before the
                # pipeline is ever registered with gst_worker) are terminal
                # and never followed by a "stopped" event, since there is no
                # Gst.Pipeline to tear down. Mark the instance ERROR right
                # away so it doesn't stay stuck in RUNNING/QUEUED forever; if
                # a "stopped" event does still arrive later (e.g. a bus
                # ERROR message on an already-running pipeline), it will just
                # confirm the same ERROR state and set the final stop_time.
                if instance.state not in (
                    PipelineState.ABORTED, PipelineState.ERROR, PipelineState.COMPLETED,
                ):
                    instance.state = PipelineState.ERROR
                    instance.stop_time = time.time()
            logger.error("Pipeline %s error: %s", instance_id, event.get("reason"))
        elif evt == "stopped":
            with self._lock:
                instance.stop_time = time.time()
                if instance.state != PipelineState.ABORTED:
                    instance.state = PipelineState.ERROR if instance.error else PipelineState.COMPLETED
            logger.info(
                "Pipeline %s finished (state=%s, avg_fps=%.2f)",
                instance_id,
                instance.state.value,
                instance.avg_fps,
            )
        else:
            logger.debug("Unknown event for pipeline %s: %s", instance_id, event)

    def _fail_all_running(self, reason: str) -> None:
        """Mark every currently RUNNING/QUEUED instance as ERROR.

        Used when the shared worker process itself exits unexpectedly, since
        no further status events will ever arrive for those instances.
        """
        with self._lock:
            affected = [
                i for i in self._instances.values()
                if i.state in (PipelineState.RUNNING, PipelineState.QUEUED)
            ]
            for instance in affected:
                instance.state = PipelineState.ERROR
                instance.error = reason
                instance.stop_time = time.time()
        for instance in affected:
            logger.error("Pipeline %s marked ERROR: %s", instance.instance_id, reason)
