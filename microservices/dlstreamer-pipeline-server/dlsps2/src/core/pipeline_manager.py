# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline Manager for DLSPS 2.0

Manages the lifecycle of GStreamer pipeline instances: validating,
launching, tracking, and stopping.

Architecture
------------
Pipelines are multiplexed onto a pool of long-lived ``gst_worker.py``
subprocesses (see ``core.worker_pool``), one per distinct ``cpu_cores``
affinity, over a small JSON-lines protocol on their stdin/stdout.

Before a pipeline is handed to a shared worker, it is first validated by
running it in its own short-lived, fully-isolated ``gst_validator.py``
subprocess, which returns as soon as the pipeline reaches PLAYING (or
fails). This keeps a bad pipeline description from ever reaching (and
potentially destabilizing) a shared worker process, which may be
hosting other, unrelated pipelines at the same time. Only pipelines that
pass validation are submitted to a worker.

FPS metrics (``avg_fps``/``frame_fps``) are updated live from the worker's
structured ``{"event": "fps", ...}`` status lines, matching the status
fields of the original DLSPS.
"""

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from core.worker_pool import WorkerPool

logger = logging.getLogger(__name__)

_GST_VALIDATOR = os.path.join(os.path.dirname(__file__), "gst_validator.py")

# gst_validator.py has no internal timeout for reaching PLAYING (see its
# module docstring); this is the external hang safety-net bounding the
# whole validator subprocess -- e.g. an unreachable source that never lets
# the pipeline reach PLAYING.
_VALIDATION_SUBPROCESS_TIMEOUT_SECONDS = 30.0


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

    # CPU affinity: list of core indices to pin this pipeline to, or None for unpinned
    cpu_cores: Optional[List[int]] = None

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
                "cpu_cores": self.cpu_cores,
            }
        )
        return summary


class PipelineManager:
    """
    Manages GStreamer pipeline instances using a pool of gst_worker.py subprocesses.

    Each subprocess is keyed by CPU affinity (cpu_cores), allowing true per-pipeline
    CPU pinning while keeping pipelines with the same affinity multiplexed onto
    a shared worker for efficiency.

    Architecture:
    - One long-lived unpinned worker (key=None) for pipelines without cpu_cores
    - Multiple ephemeral pinned workers (key=tuple of sorted cores)
      - Auto-stop after 1 minute idle (no active pipelines)
    - Shared stdout/stderr reader threads (per worker) dispatch events to instances

    - ``start()`` validates the pipeline (in its own short-lived
      gst_validator.py subprocess) on a background thread, then submits
      it to the appropriate worker (based on cpu_cores).
    - ``stop()`` sends a "stop" command; the worker keeps running for other pipelines.
    - ``shutdown()`` (called on application shutdown) gracefully drains all workers.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, PipelineInstance] = {}
        self._lock = threading.RLock()

        # Worker pool: manages multiple gst_worker subprocesses keyed by CPU affinity
        self._worker_pool = WorkerPool(event_handler=self._handle_event)
        self._shutting_down = threading.Event()

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
        cpu_cores: Optional[List[int]] = None,
    ) -> str:
        """Validate and submit a new pipeline instance.

        Returns immediately with an instance_id in QUEUED state; validation
        and submission to the appropriate worker happen on a background thread.

        Args:
            pipeline_description: GStreamer pipeline string.
            name: Legacy pipeline "name" segment (e.g. "user_defined_pipelines"),
                if this instance was started via the named-pipeline API.
            version: Legacy pipeline "version" segment (the config pipeline name),
                if this instance was started via the named-pipeline API.
            request: The original request body (source/destination/parameters/tags),
                if this instance was started via the named-pipeline API.
            cpu_cores: List of CPU core indices to pin this pipeline to (e.g., [0, 1, 2]),
                or None for no affinity.

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
            cpu_cores=cpu_cores,
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
        """Request a graceful stop of one pipeline instance.

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

        success = self._worker_pool.send_command(
            instance_id,
            {"cmd": "stop"},
            cpu_cores=instance.cpu_cores,
        )
        if success:
            logger.info("Requested stop for pipeline instance %s", instance_id)
        return success

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
        """Shut down all worker processes. Call this on application shutdown."""
        self._shutting_down.set()
        self._worker_pool.shutdown()

    # ------------------------------------------------------------------
    # Validation (runs before a pipeline is ever submitted to the worker)
    # ------------------------------------------------------------------

    def _validate_and_submit(self, instance: PipelineInstance) -> None:
        """Background-thread body: validate, then submit to the appropriate worker."""
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

        success = self._worker_pool.send_command(
            instance.instance_id,
            {
                "cmd": "start",
                "pipeline": instance.pipeline_description,
            },
            cpu_cores=instance.cpu_cores,
        )

        if success:
            logger.info(
                "Pipeline %s passed validation and was submitted to gst_worker (affinity: %s)",
                instance.instance_id,
                instance.cpu_cores,
            )
        else:
            with self._lock:
                instance.state = PipelineState.ERROR
                instance.error = "failed to submit to worker"
                instance.stop_time = time.time()
            logger.error("Pipeline %s failed to submit to worker", instance.instance_id)

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
    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_event(self, event: dict) -> None:
        """Dispatch one JSON status event from any worker to its instance."""
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
            self._worker_pool.untrack_pipeline(instance_id, instance.cpu_cores)
        elif evt == "stopped":
            with self._lock:
                instance.stop_time = time.time()
                if instance.state != PipelineState.ABORTED:
                    instance.state = PipelineState.ERROR if instance.error else PipelineState.COMPLETED
            self._worker_pool.untrack_pipeline(instance_id, instance.cpu_cores)
            logger.info(
                "Pipeline %s finished (state=%s, avg_fps=%.2f)",
                instance_id,
                instance.state.value,
                instance.avg_fps,
            )
        else:
            logger.debug("Unknown event for pipeline %s: %s", instance_id, event)
