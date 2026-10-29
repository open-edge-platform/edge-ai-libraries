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
from typing import Any, Dict, List, Optional, Tuple

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
    RESTARTING = "RESTARTING"  # Pipeline stopped/errored, attempting automatic restart
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


class ValidationState(str, Enum):
    QUEUED = "QUEUED"
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass
class ValidationTicket:
    """Represents a single pipeline validation request."""

    validation_id: str
    pipeline_description: str
    timeout: int = 30  # Timeout in seconds for the validation request
    state: ValidationState = ValidationState.QUEUED
    message: Optional[str] = None  # error reason if state is INVALID
    submitted_time: Optional[float] = None


@dataclass
class PipelineInstance:
    """Represents a single running or completed pipeline instance."""

    instance_id: str
    pipeline_description: str
    validate: bool = True
    state: PipelineState = PipelineState.QUEUED
    error: Optional[str] = None

    # Metrics (updated live from the shared worker's status events)
    avg_fps: float = 0.0
    frame_fps: float = 0.0
    frame_interval: float = 0.0  # Time window in seconds for last_fps calculation
    start_time: Optional[float] = None
    stop_time: Optional[float] = None
    first_frame_time: Optional[float] = None  # Unix epoch time when first frame was received

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
    warmup_frames: Optional[int] = 0

    # Restart configuration and state
    restart_config: Optional[dict] = None  # {"enabled": bool, "max_attempts": int, "backoff_seconds": int}
    restart_attempts: int = 0  # Current restart attempt count
    restart_timer: Optional[Any] = None  # Scheduled restart GLib.timeout_source or thread timer

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
            "frame_interval": self.frame_interval,
            "start_time": self.start_time,
            "first_frame_time": self.first_frame_time,
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
        self._validations: Dict[str, ValidationTicket] = {}
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
        validate: Optional[bool] = True,
        name: Optional[str] = None,
        version: Optional[str] = None,
        request: Optional[dict] = None,
        cpu_cores: Optional[List[int]] = None,
        warmup_frames: Optional[int] = 0,
        restart_config: Optional[dict] = None,
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
            validate=validate,
            name=name,
            version=version,
            request=request,
            cpu_cores=cpu_cores,
            warmup_frames=warmup_frames,
            restart_config=restart_config,
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

        validation_status = "validation enabled" if validate else "validation skipped"
        logger.info("Submitted pipeline instance %s (%s)", instance_id, validation_status)
        return instance_id

    def stop(self, instance_id: str) -> bool:
        """Request a graceful stop of one pipeline instance.

        Returns:
            True if the instance was running/restarting and the stop request was sent,
            False if the instance was not found or not in RUNNING/RESTARTING state.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                return False
            if instance.state not in (PipelineState.RUNNING, PipelineState.RESTARTING):
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

    def validate(self, pipeline_description: str, timeout: int = 30) -> str:
        """Start validation of a pipeline in the background.

        Returns immediately with a validation_id; the validation runs on
        a background thread and the result can be polled via get_validation().

        Args:
            pipeline_description: GStreamer pipeline string.
            timeout: Timeout in seconds for the validation request.

        Returns:
            validation_id (UUID string) assigned to this validation.
        """
        validation_id = str(uuid.uuid4())
        ticket = ValidationTicket(
            validation_id=validation_id,
            pipeline_description=pipeline_description,
            submitted_time=time.time(),
            timeout=timeout,
        )

        with self._lock:
            self._validations[validation_id] = ticket

        thread = threading.Thread(
            target=self._run_validation,
            args=(ticket,),
            name=f"validate-{validation_id[:8]}",
            daemon=True,
        )
        thread.start()

        logger.info("Submitted validation request %s", validation_id)
        return validation_id

    def get_validation(self, validation_id: str) -> Optional[ValidationTicket]:
        """Return the validation ticket for the given ID, or None if not found."""
        with self._lock:
            return self._validations.get(validation_id)

    def list_validations(self) -> list[ValidationTicket]:
        """Return a snapshot of all validations."""
        with self._lock:
            return list(self._validations.values())

    def shutdown(self) -> None:
        """Shut down all worker processes. Call this on application shutdown."""
        self._shutting_down.set()
        self._worker_pool.shutdown()

    # ------------------------------------------------------------------
    # Validation (runs before a pipeline is ever submitted to the worker)
    # ------------------------------------------------------------------

    def _validate_and_submit(self, instance: PipelineInstance) -> None:
        """Background-thread body: validate, then submit to the appropriate worker."""
        logger.debug("Processing pipeline %s (validate=%s)", instance.instance_id, instance.validate)
        if instance.validate:
            logger.info("Validating pipeline %s before submission", instance.instance_id)
            ok, reason = self._validate(instance.pipeline_description, _VALIDATION_SUBPROCESS_TIMEOUT_SECONDS)
        else:
            logger.info("Skipping validation for pipeline %s before submission", instance.instance_id)
            ok, reason = True, None

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
                "warmup_frames": instance.warmup_frames,
            },
            cpu_cores=instance.cpu_cores,
        )

        if success:
            validation_status = "passed validation" if instance.validate else "submitted (validation skipped)"
            logger.info(
                "Pipeline %s %s to gst_worker (affinity: %s)",
                instance.instance_id,
                validation_status,
                instance.cpu_cores,
            )
        else:
            with self._lock:
                instance.state = PipelineState.ERROR
                instance.error = "failed to submit to worker"
                instance.stop_time = time.time()
            logger.error("Pipeline %s failed to submit to worker", instance.instance_id)

    @staticmethod
    def _validate(pipeline_description: str, timeout: int = 30) -> Tuple[bool, Optional[str]]:
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
                timeout=timeout,
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

    def _run_validation(self, ticket: ValidationTicket) -> None:
        """Background-thread body: run validation on a ticket."""
        logger.debug("Validating pipeline %s", ticket.validation_id)
        ok, reason = self._validate(ticket.pipeline_description, ticket.timeout)

        with self._lock:
            if ok:
                ticket.state = ValidationState.VALID
                ticket.message = ""
                logger.info("Pipeline %s validation PASSED", ticket.validation_id)
            else:
                ticket.state = ValidationState.INVALID
                ticket.message = reason or "validation failed"
                logger.warning("Pipeline %s validation FAILED: %s", ticket.validation_id, reason)

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
                if event.get("frame_interval") is not None:
                    instance.frame_interval = float(event["frame_interval"])
        elif evt == "firstframe":
            # Reset restart attempts on first frame (restart was successful)
            with self._lock:
                instance.restart_attempts = 0
                first_frame_time = event.get("first_frame_time")
                if first_frame_time is not None:
                    instance.first_frame_time = first_frame_time
            if instance.restart_attempts > 0:
                logger.info("Pipeline %s received first frame at %.3f (after restart attempts)", instance_id, instance.first_frame_time)
            else:
                logger.info("Pipeline %s received first frame at %.3f", instance_id, instance.first_frame_time)
        elif evt == "started":
            logger.debug("Pipeline %s started", instance_id)
        elif evt == "eos":
            logger.info("Pipeline %s reached EOS", instance_id)
            if instance.restart_config and instance.restart_config.get("enabled"):
                self._attempt_restart(instance)
        elif evt == "error":
            reason = event.get("reason")
            source = event.get("source")
            if reason and source:
                reason = f"{reason} (element: {source})"
            with self._lock:
                instance.error = reason or instance.error
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
            logger.error("Pipeline %s error: %s", instance_id, reason)
            if event.get("debug"):
                logger.error("Pipeline %s error debug: %s", instance_id, event["debug"])
            self._worker_pool.untrack_pipeline(instance_id, instance.cpu_cores)
            if instance.restart_config and instance.restart_config.get("enabled"):
                self._attempt_restart(instance)
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

    def _attempt_restart(self, instance: PipelineInstance) -> None:
        """Check if automatic restart should be triggered for a failed/stopped pipeline."""
        with self._lock:
            # Not enabled or already restarting/aborted
            if not instance.restart_config or not instance.restart_config.get("enabled"):
                return
            if instance.state in (PipelineState.RESTARTING, PipelineState.ABORTED):
                return

            max_attempts = instance.restart_config.get("max_attempts", 5)
            # Check if we haven't exceeded max attempts yet
            if instance.restart_attempts >= max_attempts:
                logger.warning(
                    "Pipeline %s reached max restart attempts (%d); giving up",
                    instance.instance_id,
                    max_attempts,
                )
                return

            instance.restart_attempts += 1
            instance.state = PipelineState.RESTARTING

        backoff_seconds = instance.restart_config.get("backoff_seconds", 30)
        logger.info(
            "Pipeline %s scheduled for restart (attempt %d/%d, backoff %.0fs)",
            instance.instance_id,
            instance.restart_attempts,
            instance.restart_config.get("max_attempts", 5),
            backoff_seconds,
        )

        # Schedule restart on a background thread after backoff
        thread = threading.Thread(
            target=self._restart_pipeline_delayed,
            args=(instance, backoff_seconds),
            name=f"restart-{instance.instance_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _restart_pipeline_delayed(self, instance: PipelineInstance, backoff_seconds: float) -> None:
        """Background thread: wait for backoff, then restart the pipeline."""
        time.sleep(backoff_seconds)
        self._restart_pipeline(instance)

    def _restart_pipeline(self, instance: PipelineInstance) -> None:
        """Restart a failed pipeline: resubmit without revalidation."""
        logger.info("Restarting pipeline %s (attempt %d)", instance.instance_id, instance.restart_attempts)

        # Reset metrics for this restart attempt
        with self._lock:
            if instance.state != PipelineState.RESTARTING:
                logger.warning("Pipeline %s no longer in RESTARTING state; aborting restart", instance.instance_id)
                return
            instance.first_frame_time = None
            instance.error = None
            instance.stop_time = None
            instance.state = PipelineState.RUNNING
            instance.start_time = time.time()

        success = self._worker_pool.send_command(
            instance.instance_id,
            {
                "cmd": "start",
                "pipeline": instance.pipeline_description,
                "warmup_frames": instance.warmup_frames,
            },
            cpu_cores=instance.cpu_cores,
        )

        if success:
            logger.info("Restart submitted for pipeline %s (attempt %d)", instance.instance_id, instance.restart_attempts)
        else:
            with self._lock:
                instance.state = PipelineState.ERROR
                instance.error = "restart failed to submit to worker"
                instance.stop_time = time.time()
            logger.error("Failed to submit restart for pipeline %s", instance.instance_id)
