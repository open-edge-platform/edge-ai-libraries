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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from core.worker_pool import WorkerPool

logger = logging.getLogger(__name__)

_GST_VALIDATOR = os.path.join(os.path.dirname(__file__), "gst_validator.py")

# gst_validator.py has no internal timeout for reaching PLAYING (see its
# module docstring); this is the external hang safety-net bounding the
# whole validator subprocess -- e.g. an unreachable source that never lets
# the pipeline reach PLAYING.
_VALIDATION_SUBPROCESS_TIMEOUT_SECONDS = 30.0

# Wait for a worker to confirm a stopped pipeline is torn down before logging a warning.
_TEARDOWN_TIMEOUT_SECONDS = 30.0


class PipelineState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"  # Stop sent to the worker, teardown not yet confirmed
    RESTARTING = "RESTARTING"  # Previous run fully torn down, automatic restart scheduled
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


class FpsSample(NamedTuple):
    """FPS values of one instance, replaced as a whole so a reader never sees a mix of events."""

    avg_fps: float = 0.0
    frame_fps: float = 0.0
    frame_interval: float = 0.0  # Window in seconds that frame_fps was measured over


class Lifecycle(NamedTuple):
    """Unix epoch times of one run, replaced as a whole so a reader never mixes two runs."""

    start_time: Optional[float] = None  # When the instance transitioned to RUNNING
    first_frame_time: Optional[float] = None
    stop_time: Optional[float] = None


def _opt_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


@dataclass
class PipelineInstance:
    """Represents a single running or completed pipeline instance."""

    instance_id: str
    pipeline_description: str
    validate: bool = True
    state: PipelineState = PipelineState.QUEUED
    error: Optional[str] = None

    # Metrics (updated live from the shared worker's status events)
    fps_sample: FpsSample = FpsSample()
    lifecycle: Lifecycle = Lifecycle()

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
    fps_element: Optional[str] = None  # None counts frames at the terminal sink

    # Restart configuration and state
    restart_config: Optional[dict] = None  # {"enabled": bool, "max_attempts": int, "backoff_seconds": int}
    restart_attempts: int = 0  # Current restart attempt count
    restart_timer: Optional[Any] = None  # Scheduled restart GLib.timeout_source or thread timer

    # Stop lifecycle: finalized once the run's final state (ABORTED/COMPLETED/ERROR) is reported
    stop_requested: bool = False
    finalized: bool = False
    teardown_timer: Optional[threading.Timer] = None
    # Validator subprocess while QUEUED, so a cancel can kill it
    validator_process: Optional[subprocess.Popen] = None
    # Serialises start/restart/stop commands sent to the worker for this instance
    command_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def avg_fps(self) -> float:
        return self.fps_sample.avg_fps

    @property
    def frame_fps(self) -> float:
        return self.fps_sample.frame_fps

    @property
    def frame_interval(self) -> float:
        return self.fps_sample.frame_interval

    def update_fps(
        self,
        avg_fps: Optional[float] = None,
        frame_fps: Optional[float] = None,
        frame_interval: Optional[float] = None,
    ) -> None:
        """Apply one fps event; values it does not carry keep their previous value.

        frame_fps and frame_interval describe the same window, so they only change together.
        """
        prev = self.fps_sample
        window_complete = frame_fps is not None and frame_interval is not None
        self.fps_sample = FpsSample(
            prev.avg_fps if avg_fps is None else avg_fps,
            frame_fps if window_complete else prev.frame_fps,
            frame_interval if window_complete else prev.frame_interval,
        )

    @property
    def start_time(self) -> Optional[float]:
        return self.lifecycle.start_time

    @property
    def first_frame_time(self) -> Optional[float]:
        return self.lifecycle.first_frame_time

    @property
    def stop_time(self) -> Optional[float]:
        return self.lifecycle.stop_time

    def set_lifecycle(self, **changes: Optional[float]) -> None:
        """Change some of the run's times in one assignment; None clears a time."""
        self.lifecycle = self.lifecycle._replace(**changes)

    @staticmethod
    def _elapsed(lifecycle: Lifecycle) -> Optional[float]:
        if lifecycle.start_time is None:
            return None
        end = lifecycle.stop_time if lifecycle.stop_time is not None else time.time()
        return max(0.0, end - lifecycle.start_time)

    def elapsed_time(self) -> Optional[float]:
        return self._elapsed(self.lifecycle)

    def to_status_dict(self) -> dict:
        """Pure runtime-status view, matching legacy API GET /pipelines/{id}/status
        and GET /pipelines/status (no pipeline config/request data included).
        """
        fps = self.fps_sample
        lifecycle = self.lifecycle
        return {
            "id": self.instance_id,
            "state": self.state.value,
            "avg_fps": fps.avg_fps,
            "frame_fps": fps.frame_fps,
            "frame_interval": fps.frame_interval,
            "start_time": lifecycle.start_time,
            "first_frame_time": lifecycle.first_frame_time,
            "stop_time": lifecycle.stop_time,
            "elapsed_time": self._elapsed(lifecycle),
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
        self._finished_listener: Optional[Callable[[PipelineInstance], None]] = None
        self._metric_listener: Optional[Callable[[PipelineInstance, dict], None]] = None

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
        fps_element: Optional[str] = None,
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
            fps_element: Element whose input buffers are counted for FPS, or None for the terminal sink.

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
            fps_element=fps_element,
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
        """Request a stop of one pipeline instance.

        A QUEUED or RESTARTING instance has no live pipeline, so it is ABORTED at once.
        A RUNNING instance moves to STOPPING and is reported as ABORTED only after its worker confirms teardown.
        A STOPPING instance is already being stopped, so the request is accepted again.

        Returns:
            True if the instance is stopping or stopped, False if it cannot be stopped.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
        if not instance:
            return False

        with instance.command_lock:
            with self._lock:
                if instance.state in (PipelineState.QUEUED, PipelineState.RESTARTING):
                    previous_state = instance.state
                    instance.state = PipelineState.ABORTED
                    instance.stop_requested = True
                    instance.finalized = True
                    instance.set_lifecycle(stop_time=time.time())
                    if instance.validator_process is not None and instance.validator_process.poll() is None:
                        instance.validator_process.kill()
                    logger.info("Cancelled pipeline instance %s in state %s", instance_id, previous_state.value)
                    return True
                if instance.state == PipelineState.STOPPING:
                    return True
                if instance.state != PipelineState.RUNNING:
                    return False
                instance.state = PipelineState.STOPPING
                instance.stop_requested = True

            success = self._worker_pool.send_command(
                instance_id,
                {"cmd": "stop"},
                cpu_cores=instance.cpu_cores,
            )
            with self._lock:
                if not success:
                    instance.state = PipelineState.RUNNING
                    instance.stop_requested = False
                    return False
                if not instance.finalized:
                    instance.teardown_timer = self._start_teardown_timer(instance)
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
        """Return a snapshot of instances that are RUNNING or STOPPING."""
        with self._lock:
            return [i for i in self._instances.values() if i.state in (PipelineState.RUNNING, PipelineState.STOPPING)]

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

    def set_finished_listener(self, listener: Optional[Callable[[PipelineInstance], None]]) -> None:
        """Register a callback invoked with an instance after its worker reports "stopped"."""
        self._finished_listener = listener

    def set_metric_listener(self, listener: Optional[Callable[[PipelineInstance, dict], None]]) -> None:
        """Register a callback invoked with an instance and each "metric" event its worker reports.

        Without a listener, metric events are dropped.
        """
        self._metric_listener = listener

    # ------------------------------------------------------------------
    # Validation (runs before a pipeline is ever submitted to the worker)
    # ------------------------------------------------------------------

    def _validate_and_submit(self, instance: PipelineInstance) -> None:
        """Background-thread body: validate, then submit to the appropriate worker."""
        logger.debug("Processing pipeline %s (validate=%s)", instance.instance_id, instance.validate)
        if instance.validate:
            logger.info("Validating pipeline %s before submission", instance.instance_id)

            def track_validator(process: subprocess.Popen) -> None:
                # Kill at once if stop() ran between the state check and the spawn.
                with self._lock:
                    if instance.state == PipelineState.QUEUED:
                        instance.validator_process = process
                        return
                process.kill()

            ok, reason = self._validate(
                instance.pipeline_description,
                _VALIDATION_SUBPROCESS_TIMEOUT_SECONDS,
                on_spawn=track_validator,
            )
        else:
            logger.info("Skipping validation for pipeline %s before submission", instance.instance_id)
            ok, reason = True, None

        with instance.command_lock:
            with self._lock:
                instance.validator_process = None
                # stop() finalizes a queued instance it cancels; never submit that one.
                if instance.state != PipelineState.QUEUED:
                    logger.info("Pipeline %s was stopped while queued; not submitting", instance.instance_id)
                    return
                if not ok:
                    instance.state = PipelineState.ERROR
                    instance.error = f"validation failed: {reason}" if reason else "validation failed"
                    instance.set_lifecycle(stop_time=time.time())
                    logger.error("Pipeline %s failed validation: %s", instance.instance_id, reason)
                    return
                instance.state = PipelineState.RUNNING
                instance.set_lifecycle(start_time=time.time())

            success = self._worker_pool.send_command(
                instance.instance_id,
                {
                    "cmd": "start",
                    "pipeline": instance.pipeline_description,
                    "warmup_frames": instance.warmup_frames,
                    "fps_element": instance.fps_element,
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
                    instance.set_lifecycle(stop_time=time.time())
                logger.error("Pipeline %s failed to submit to worker", instance.instance_id)

    @staticmethod
    def _validate(
        pipeline_description: str,
        timeout: int = 30,
        on_spawn: Optional[Callable[[subprocess.Popen], None]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Run gst_validator.py in its own short-lived subprocess.

        ``on_spawn`` receives the process right after it starts, so the caller can kill it.

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
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"validation subprocess failed to launch: {exc!r}"

        if on_spawn is not None:
            on_spawn(process)

        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return False, "validation subprocess timed out"

        if process.returncode == 0:
            return True, None

        # Surface the most relevant diagnostic line from the validator's stderr.
        # gst_validator.py always logs its own generic
        # "Pipeline validation FAILED (reason: ...)" summary as the LAST
        # ERROR-level line; the actual root-cause GStreamer error (e.g. a
        # missing model file or element) is logged earlier. Prefer the
        # first specific ERROR line so callers see the real cause instead
        # of the generic summary.
        reason = None
        for line in stderr.splitlines():
            if "ERROR" in line and "Pipeline validation FAILED" not in line:
                reason = line.strip()
                break
        if reason is None:
            for line in reversed(stderr.splitlines()):
                if "ERROR" in line:
                    reason = line.strip()
                    break
        return False, reason or f"validator exited with code {process.returncode}"

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

        if evt == "metric":
            self._notify_metric(instance, event)
        elif evt == "fps":
            with self._lock:
                instance.update_fps(
                    avg_fps=_opt_float(event.get("avg_fps")),
                    frame_fps=_opt_float(event.get("last_fps")),
                    frame_interval=_opt_float(event.get("frame_interval")),
                )
        elif evt == "firstframe":
            # Reset restart attempts on first frame (restart was successful)
            with self._lock:
                instance.restart_attempts = 0
                first_frame_time = event.get("first_frame_time")
                if first_frame_time is not None:
                    instance.set_lifecycle(first_frame_time=first_frame_time)
            if instance.restart_attempts > 0:
                logger.info("Pipeline %s received first frame at %.3f (after restart attempts)", instance_id, instance.first_frame_time)
            else:
                logger.info("Pipeline %s received first frame at %.3f", instance_id, instance.first_frame_time)
        elif evt == "started":
            logger.debug("Pipeline %s started", instance_id)
        elif evt == "eos":
            # The worker tears the pipeline down after EOS and then reports "stopped", which decides any restart.
            logger.info("Pipeline %s reached EOS", instance_id)
        elif evt == "error":
            reason = event.get("reason")
            source = event.get("source")
            if reason and source:
                reason = f"{reason} (element: {source})"
            with self._lock:
                instance.error = reason or instance.error
            logger.error("Pipeline %s error: %s", instance_id, reason)
            if event.get("debug"):
                logger.error("Pipeline %s error debug: %s", instance_id, event["debug"])
            # The worker always follows an error with "stopped" (after teardown, or straight away if the pipeline was never registered), so the final state is decided there.
        elif evt == "stopped":
            restart_claimed = False
            with self._lock:
                if instance.teardown_timer is not None:
                    instance.teardown_timer.cancel()
                already_finalized = instance.finalized
                if not already_finalized:
                    if instance.stop_requested:
                        self._finalize_locked(instance, PipelineState.ABORTED)
                    else:
                        restart_claimed = self._claim_restart_locked(instance)
                        if not restart_claimed:
                            self._finalize_locked(instance, PipelineState.ERROR if instance.error else PipelineState.COMPLETED)
            self._worker_pool.untrack_pipeline(instance_id, instance.cpu_cores)
            if already_finalized:
                logger.info("Pipeline %s torn down after it was already reported as %s", instance_id, instance.state.value)
                return
            logger.info(
                "Pipeline %s finished (state=%s, avg_fps=%.2f)",
                instance_id,
                instance.state.value,
                instance.avg_fps,
            )
            self._notify_finished(instance)
            if restart_claimed:
                self._schedule_restart(instance)
        else:
            logger.debug("Unknown event for pipeline %s: %s", instance_id, event)

    def _start_teardown_timer(self, instance: PipelineInstance) -> threading.Timer:
        timer = threading.Timer(_TEARDOWN_TIMEOUT_SECONDS, self._on_teardown_timeout, args=(instance,))
        timer.daemon = True
        timer.start()
        return timer

    def _on_teardown_timeout(self, instance: PipelineInstance) -> None:
        """Log that a stop is still unconfirmed; the state stays until the worker reports "stopped"."""
        with self._lock:
            if instance.finalized:
                return
        logger.warning(
            "Pipeline %s teardown not confirmed within %gs; still waiting",
            instance.instance_id,
            _TEARDOWN_TIMEOUT_SECONDS,
        )

    def _notify_metric(self, instance: PipelineInstance, event: dict) -> None:
        listener = self._metric_listener
        if listener is None:
            return
        try:
            listener(instance, event)
        except Exception:  # noqa: BLE001
            logger.exception("Metric listener failed for %s", instance.instance_id)

    def _notify_finished(self, instance: PipelineInstance) -> None:
        listener = self._finished_listener
        if listener is None:
            return
        try:
            listener(instance)
        except Exception:  # noqa: BLE001
            logger.exception("Finished-pipeline listener failed for %s", instance.instance_id)

    def _finalize_locked(self, instance: PipelineInstance, state: PipelineState) -> None:
        """Set the final state of a run. Caller must hold ``self._lock``."""
        instance.state = state
        instance.finalized = True
        instance.set_lifecycle(stop_time=time.time())

    def _claim_restart_locked(self, instance: PipelineInstance) -> bool:
        """Move a torn-down run to RESTARTING if automatic restart applies. Caller must hold ``self._lock``."""
        if not instance.restart_config or not instance.restart_config.get("enabled"):
            return False

        max_attempts = instance.restart_config.get("max_attempts", 5)
        if instance.restart_attempts >= max_attempts:
            logger.warning(
                "Pipeline %s reached max restart attempts (%d); giving up",
                instance.instance_id,
                max_attempts,
            )
            return False

        instance.restart_attempts += 1
        instance.state = PipelineState.RESTARTING
        return True

    def _schedule_restart(self, instance: PipelineInstance) -> None:
        """Schedule a restart on a background thread after the backoff delay."""
        backoff_seconds = instance.restart_config.get("backoff_seconds", 30)
        logger.info(
            "Pipeline %s scheduled for restart (attempt %d/%d, backoff %.0fs)",
            instance.instance_id,
            instance.restart_attempts,
            instance.restart_config.get("max_attempts", 5),
            backoff_seconds,
        )

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

        with instance.command_lock:
            # Reset metrics for this restart attempt
            with self._lock:
                if instance.state != PipelineState.RESTARTING:
                    logger.warning("Pipeline %s no longer in RESTARTING state; aborting restart", instance.instance_id)
                    return
                instance.set_lifecycle(start_time=time.time(), first_frame_time=None, stop_time=None)
                instance.finalized = False
                instance.error = None
                instance.state = PipelineState.RUNNING

            success = self._worker_pool.send_command(
                instance.instance_id,
                {
                    "cmd": "start",
                    "pipeline": instance.pipeline_description,
                    "warmup_frames": instance.warmup_frames,
                    "fps_element": instance.fps_element,
                },
                cpu_cores=instance.cpu_cores,
            )

            if success:
                logger.info("Restart submitted for pipeline %s (attempt %d)", instance.instance_id, instance.restart_attempts)
            else:
                with self._lock:
                    self._finalize_locked(instance, PipelineState.ERROR)
                    instance.error = "restart failed to submit to worker"
                logger.error("Failed to submit restart for pipeline %s", instance.instance_id)
