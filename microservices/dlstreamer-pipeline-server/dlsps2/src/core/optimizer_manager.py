# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Asynchronous pipeline optimizer jobs for DLSPS 2.0.

Each job runs in its own ``optimizer_worker.py`` subprocess. Only one job may
be active at a time. Partial results (best candidate so far) are kept on the
job while it runs.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_OPTIMIZER_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "optimizer_worker.py")
_CANCEL_GRACE_MIN_SECONDS = 30.0
_SHUTDOWN_TIMEOUT_SECONDS = 15.0


class OptimizerState(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class OptimizerBusyError(RuntimeError):
    """Raised when a job is submitted while another optimizer job is still active."""


@dataclass
class OptimizerJob:
    job_id: str
    settings: Dict[str, Any]  # validated OptimizeRequest fields, including pipeline
    state: OptimizerState = OptimizerState.RUNNING
    message: str = ""
    baseline: Optional[Dict[str, Any]] = None
    best: Optional[Dict[str, Any]] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    candidates_evaluated: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    cancel_requested: bool = False
    process: Optional[subprocess.Popen] = field(default=None, repr=False)

    @property
    def final(self) -> bool:
        return self.state != OptimizerState.RUNNING

    @property
    def mode(self) -> str:
        return self.settings.get("mode", "fps")

    def elapsed_time(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    @staticmethod
    def _fps(result: Optional[Dict[str, Any]]) -> Optional[float]:
        if not result or not result.get("metrics"):
            return None
        return result["metrics"].get("fps")

    def status_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "final": self.final,
            "message": self.message,
            "mode": self.mode,
            "candidates_evaluated": self.candidates_evaluated,
            "baseline_fps": self._fps(self.baseline),
            "best_fps": self._fps(self.best),
            "elapsed_time": round(self.elapsed_time(), 3),
        }

    def result_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "final": self.final,
            "message": self.message,
            "mode": self.mode,
            "baseline": self._pipeline_result(self.baseline),
            "best": self._pipeline_result(self.best),
            "candidates": [self._pipeline_result(c) for c in self.candidates],
        }

    @staticmethod
    def _pipeline_result(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not result:
            return None
        metrics = result.get("metrics")
        return {
            "pipeline": result.get("pipeline"),
            "fps": metrics.get("fps") if metrics else None,
            "power": metrics.get("power") if metrics else None,
            "metrics": metrics,
        }


def _result_or_none(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    return {"pipeline": payload.get("pipeline"), "metrics": payload.get("metrics")}


class OptimizerManager:
    """Owns optimizer jobs and their worker subprocesses."""

    def __init__(self) -> None:
        self._jobs: Dict[str, OptimizerJob] = {}
        self._active_job_id: Optional[str] = None
        self._lock = threading.RLock()
        self._shutting_down = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, settings: Dict[str, Any]) -> str:
        """Start a job with validated OptimizeRequest fields. Raises OptimizerBusyError if one is active."""
        with self._lock:
            if self._shutting_down.is_set():
                raise RuntimeError("optimizer is shutting down")
            if self._active_job_id is not None:
                raise OptimizerBusyError(f"optimizer job {self._active_job_id} is still running")
            job = OptimizerJob(job_id=str(uuid.uuid4()), settings=dict(settings))
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id

        try:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, _OPTIMIZER_WORKER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._finish(job, OptimizerState.ERROR, f"failed to launch optimizer worker: {exc}")
            return job.job_id

        job.process = process
        sent = self._send(job, {"cmd": "start", "job_id": job.job_id, **job.settings})
        if not sent:
            self._finish(job, OptimizerState.ERROR, "failed to send start command to optimizer worker")
            self._kill(job)
            return job.job_id

        threading.Thread(
            target=self._read_events, args=(job,), name=f"optimizer-stdout-{job.job_id[:8]}", daemon=True
        ).start()
        threading.Thread(
            target=self._read_stderr, args=(job,), name=f"optimizer-stderr-{job.job_id[:8]}", daemon=True
        ).start()
        logger.info("Started optimizer job %s", job.job_id)
        return job.job_id

    def get(self, job_id: str) -> Optional[OptimizerJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> List[OptimizerJob]:
        with self._lock:
            return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns False if the job is not running."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.final:
                return False
            if job.cancel_requested:
                return True
            job.cancel_requested = True

        self._send(job, {"cmd": "cancel", "job_id": job_id})
        grace = max(_CANCEL_GRACE_MIN_SECONDS, 3 * float(job.settings["sample_duration"]))
        timer = threading.Timer(grace, self._kill_if_running, args=(job,))
        timer.daemon = True
        timer.start()
        return True

    def shutdown(self) -> None:
        self._shutting_down.set()
        with self._lock:
            job_id = self._active_job_id
        if job_id is None:
            return

        job = self.get(job_id)
        self.cancel(job_id)
        if job is None or job.process is None:
            return
        try:
            job.process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning("Optimizer job %s did not stop in time, killing worker", job_id)
            self._kill(job)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send(self, job: OptimizerJob, command: Dict[str, Any]) -> bool:
        process = job.process
        if process is None or process.stdin is None or process.poll() is not None:
            return False
        try:
            with self._lock:
                process.stdin.write(json.dumps(command) + "\n")
                process.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError) as exc:
            logger.error("Failed to send command to optimizer job %s: %s", job.job_id, exc)
            return False

    def _read_events(self, job: OptimizerJob) -> None:
        process = job.process
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.info("[optimizer_worker %s] %s", job.job_id[:8], line)
                continue
            self._handle_event(job, event)

        returncode = process.wait()
        with self._lock:
            if job.final:
                return
            if job.cancel_requested:
                self._finish(job, OptimizerState.CANCELLED, "cancelled")
            else:
                self._finish(
                    job,
                    OptimizerState.ERROR,
                    f"optimizer worker exited unexpectedly (exit code {returncode})",
                )

    def _read_stderr(self, job: OptimizerJob) -> None:
        for line in job.process.stderr:
            line = line.rstrip()
            if line:
                logger.info("[optimizer_worker %s] %s", job.job_id[:8], line)

    def _handle_event(self, job: OptimizerJob, event: Dict[str, Any]) -> None:
        kind = event.get("event")
        with self._lock:
            if kind == "baseline":
                job.baseline = _result_or_none(event)
            elif kind == "candidate":
                job.candidates_evaluated = event.get("candidates_evaluated", job.candidates_evaluated)
                job.candidates.append({"pipeline": event.get("pipeline"), "metrics": event.get("metrics")})
                job.best = _result_or_none(event.get("best"))
            elif kind == "finished":
                job.candidates_evaluated = event.get("candidates_evaluated", job.candidates_evaluated)
                job.baseline = _result_or_none(event.get("baseline")) or job.baseline
                job.best = _result_or_none(event.get("best")) or job.best
                state = OptimizerState.CANCELLED if job.cancel_requested else OptimizerState.COMPLETED
                self._finish(job, state, "cancelled" if state == OptimizerState.CANCELLED else "")
            elif kind == "error":
                self._finish(job, OptimizerState.ERROR, str(event.get("reason", "unknown error")))

    def _finish(self, job: OptimizerJob, state: OptimizerState, message: str = "") -> None:
        with self._lock:
            if job.final:
                return
            job.state = state
            job.message = message
            job.end_time = time.time()
            if self._active_job_id == job.job_id:
                self._active_job_id = None
        logger.info("Optimizer job %s finished with state %s", job.job_id, state.value)

    def _kill(self, job: OptimizerJob) -> None:
        if job.process is not None and job.process.poll() is None:
            job.process.kill()

    def _kill_if_running(self, job: OptimizerJob) -> None:
        if not job.final:
            logger.warning("Optimizer job %s did not stop after cancel, killing worker", job.job_id)
            self._kill(job)
