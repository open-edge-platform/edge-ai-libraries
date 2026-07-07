# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline Manager for DLSPS 2.0

Manages the lifecycle of GStreamer pipeline instances: launching, tracking,
and stopping. Each pipeline runs as a separate gst_runner.py subprocess,
allowing clean cancellation via SIGINT → SIGKILL

FPS metrics are parsed from gvafpscounter output lines in real-time from the
subprocess stdout, matching the status fields of the original DLSPS.
"""

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Absolute path to gst_runner.py (sibling file in core/)
_GST_RUNNER = os.path.join(os.path.dirname(__file__), "gst_runner.py")

# gvafpscounter output patterns (same format as original DLSPS)
# e.g. "FpsCounter(average 1.00sec): total=29.97 fps, number-streams=1, per-stream=29.97 fps"
_FPS_AVG_RE = re.compile(
    r"FpsCounter\(average [^)]+\): total=([\d.]+) fps.*per-stream=([\d.]+) fps"
)
_FPS_LAST_RE = re.compile(
    r"FpsCounter\(last [^)]+\): total=([\d.]+) fps.*per-stream=([\d.]+) fps"
)


class PipelineState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class PipelineInstance:
    """Represents a single running or completed pipeline instance."""

    instance_id: str
    pipeline_description: str
    state: PipelineState = PipelineState.QUEUED
    error: Optional[str] = None

    # Metrics (updated live from subprocess stdout)
    avg_fps: float = 0.0
    frame_fps: float = 0.0
    start_time: Optional[float] = None
    stop_time: Optional[float] = None

    _process: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)
    _thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)

    def elapsed_time(self) -> Optional[float]:
        if self.start_time is None:
            return None
        end = self.stop_time if self.stop_time is not None else time.time()
        return max(0.0, end - self.start_time)

    def to_dict(self) -> dict:
        return {
            "id": self.instance_id,
            "state": self.state.value,
            "avg_fps": self.avg_fps,
            "frame_fps": self.frame_fps,
            "start_time": self.start_time,
            "elapsed_time": self.elapsed_time(),
            "message": self.error or "",
        }


class PipelineManager:
    """
    Manages GStreamer pipeline instances.

    Each pipeline is launched as a gst_runner.py subprocess in a dedicated
    daemon thread. FPS metrics are parsed live from subprocess stdout.
    Cancellation sends SIGINT to the subprocess, falling back to SIGKILL.
    """

    _SIGINT_TIMEOUT = 10.0  # seconds to wait after SIGINT before SIGKILL

    def __init__(self) -> None:
        self._instances: Dict[str, PipelineInstance] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, pipeline_description: str) -> str:
        """Launch a new pipeline instance as a subprocess.

        Args:
            pipeline_description: GStreamer pipeline string.

        Returns:
            instance_id (UUID string) assigned to this instance.
        """
        instance_id = str(uuid.uuid4())
        instance = PipelineInstance(
            instance_id=instance_id,
            pipeline_description=pipeline_description,
        )

        with self._lock:
            self._instances[instance_id] = instance

        thread = threading.Thread(
            target=self._run,
            args=(instance,),
            name=f"pipeline-{instance_id[:8]}",
            daemon=True,
        )
        instance._thread = thread
        thread.start()

        logger.info("Started pipeline instance %s", instance_id)
        return instance_id

    def stop(self, instance_id: str) -> bool:
        """Stop a running pipeline via SIGINT → SIGKILL.

        Returns:
            True if the instance was running and termination was initiated,
            False if the instance was not found or not in RUNNING state.
        """
        with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                return False
            if instance.state != PipelineState.RUNNING:
                return False
            instance.state = PipelineState.ABORTED
            process = instance._process

        if process:
            self._graceful_terminate(process)

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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, instance: PipelineInstance) -> None:
        """Worker thread: launch gst_runner.py, stream stdout for FPS metrics."""
        cmd = [sys.executable, _GST_RUNNER, instance.pipeline_description]

        with self._lock:
            instance.state = PipelineState.RUNNING
            instance.start_time = time.time()

        logger.debug("Pipeline %s launching subprocess", instance.instance_id)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            with self._lock:
                instance._process = process

            # Stream stdout line-by-line to parse FPS metrics in real-time.
            stderr_lines = []
            stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(process, stderr_lines, instance.instance_id),
                daemon=True,
            )
            stderr_thread.start()

            for line in process.stdout:
                stripped = line.rstrip()
                if stripped:
                    logger.debug("[pipeline %s] %s", instance.instance_id, stripped)
                self._parse_fps(instance, line)

            process.wait()
            stderr_thread.join(timeout=2)
            exit_code = process.returncode

        except Exception as exc:
            logger.error(
                "Pipeline %s failed to launch subprocess: %r",
                instance.instance_id,
                exc,
                exc_info=True,
            )
            with self._lock:
                instance.state = PipelineState.FAILED
                instance.stop_time = time.time()
                instance.error = str(exc)
            return

        with self._lock:
            instance.stop_time = time.time()
            # Don't overwrite ABORTED if stop() was called while running.
            if instance.state != PipelineState.ABORTED:
                if exit_code == 0:
                    instance.state = PipelineState.COMPLETED
                else:
                    instance.state = PipelineState.FAILED
                    if stderr_lines:
                        instance.error = stderr_lines[-1].strip()

        logger.info(
            "Pipeline %s finished (exit_code=%d, state=%s, avg_fps=%.2f)",
            instance.instance_id,
            exit_code,
            instance.state.value,
            instance.avg_fps,
        )

    def _parse_fps(self, instance: PipelineInstance, line: str) -> None:
        """Parse a gvafpscounter output line and update instance metrics."""
        m = _FPS_AVG_RE.search(line)
        if m:
            with self._lock:
                instance.avg_fps = float(m.group(1))
            return
        m = _FPS_LAST_RE.search(line)
        if m:
            with self._lock:
                instance.frame_fps = float(m.group(1))

    @staticmethod
    def _drain_stderr(
        process: subprocess.Popen, lines: list, instance_id: str
    ) -> None:
        """Read stderr into a list (prevents pipe buffer blocking) and log it."""
        for line in process.stderr:
            lines.append(line)
            stripped = line.rstrip()
            if stripped:
                logger.error("[pipeline %s] %s", instance_id, stripped)

    @staticmethod
    def _graceful_terminate(proc: subprocess.Popen, timeout: float = _SIGINT_TIMEOUT) -> None:
        """Send SIGINT for graceful GLib.MainLoop shutdown, fall back to SIGKILL."""
        if proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("SIGINT timed out, sending SIGKILL")
            proc.kill()
            proc.wait()
        except OSError:
            pass
