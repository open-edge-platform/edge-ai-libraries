# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Worker Pool for DLSPS 2.0 with CPU Affinity Support

Manages a pool of gst_worker.py subprocesses, keyed by CPU affinity.

Architecture:
- One long-lived unpinned worker (key=None) for pipelines without cpu_cores
- Multiple ephemeral pinned workers (key=tuple of sorted cores)
  - Auto-stop after 1 minute idle (no active pipelines)
- Shared stdout/stderr reader threads dispatch events to all tracked instances

This allows true per-pipeline CPU pinning while maintaining the efficiency
benefit of multiplexing pipelines onto fewer workers.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Absolute path to gst_worker.py
_GST_WORKER = os.path.join(os.path.dirname(__file__), "gst_worker.py")

# Idle timeout (seconds) before a pinned worker is reaped if empty
_IDLE_TIMEOUT_SECONDS = 60.0

# gst_worker.py logs to stderr as JSON; map level names to Python logging levels
_WORKER_LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _normalize_cpu_cores(cpu_cores: Optional[List[int]]) -> Optional[Tuple[int, ...]]:
    """Normalize CPU cores list to sorted tuple (or None).
    
    Args:
        cpu_cores: List of CPU core indices, or None.
        
    Returns:
        Sorted tuple of core indices, or None if input is None.
    """
    if cpu_cores is None:
        return None
    if not cpu_cores:
        return None
    return tuple(sorted(set(cpu_cores)))


class ManagedWorker:
    """Wraps a single gst_worker.py subprocess with stdin/stdout management."""

    def __init__(
        self,
        affinity_key: Optional[Tuple[int, ...]],
        event_handler: Callable[[dict], None],
        on_unexpected_exit: Callable[["ManagedWorker"], None],
    ) -> None:
        """
        Args:
            affinity_key: Tuple of sorted CPU cores to pin to, or None (unpinned).
            event_handler: Callback to dispatch JSON status events.
            on_unexpected_exit: Called (from the stdout reader thread) if the
                subprocess exits without shutdown() having been requested.
        """
        self.affinity_key = affinity_key
        self._event_handler = event_handler
        self._on_unexpected_exit = on_unexpected_exit
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._stdin_lock = threading.Lock()
        self._shutting_down = threading.Event()
        self._last_activity_time = time.time()
        self._active_pipelines = set()  # Set of instance_ids currently running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Launch the subprocess. Returns True if successful."""
        with self._lock:
            if self._process is not None:
                return True
            return self._start_subprocess()

    def _start_subprocess(self) -> bool:
        """Internal: start the subprocess and attach reader threads."""
        cmd = [sys.executable, _GST_WORKER]
        logger.debug("Launching gst_worker subprocess (affinity: %s)", self.affinity_key)

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=self._preexec_fn if self.affinity_key else None,
            )
        except Exception as exc:
            logger.error("Failed to launch gst_worker subprocess: %s", exc)
            return False

        self._process = process
        self._last_activity_time = time.time()

        threading.Thread(
            target=self._read_stdout,
            name=f"gst-worker-stdout-{self.affinity_key}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            name=f"gst-worker-stderr-{self.affinity_key}",
            daemon=True,
        ).start()

        logger.info("Started gst_worker subprocess (affinity: %s)", self.affinity_key)
        return True

    def _preexec_fn(self) -> None:
        """Apply CPU affinity in the forked child before exec."""
        # Runs post-fork in a multithreaded parent: no logging/locks here, only the syscall.
        os.sched_setaffinity(0, self.affinity_key)

    def send_command(self, command: dict) -> bool:
        """Send a JSON command to the worker. Returns True if successful."""
        with self._lock:
            process = self._process
            if process is None or process.stdin is None or process.poll() is not None:
                return False

        try:
            with self._stdin_lock:
                process.stdin.write(json.dumps(command) + "\n")
                process.stdin.flush()
            self._last_activity_time = time.time()
            return True
        except (BrokenPipeError, OSError) as exc:
            logger.error("Failed to send command to worker (affinity: %s): %s", self.affinity_key, exc)
            return False

    def track_pipeline(self, instance_id: str) -> None:
        """Mark a pipeline as active in this worker."""
        with self._lock:
            self._active_pipelines.add(instance_id)
        self._last_activity_time = time.time()

    def untrack_pipeline(self, instance_id: str) -> None:
        """Mark a pipeline as no longer active in this worker."""
        with self._lock:
            self._active_pipelines.discard(instance_id)
        self._last_activity_time = time.time()

    def drain_active(self) -> List[str]:
        """Clear and return the instance_ids still tracked on this worker."""
        with self._lock:
            active = list(self._active_pipelines)
            self._active_pipelines.clear()
        return active

    def is_idle(self) -> bool:
        """Check if the worker has no active pipelines."""
        with self._lock:
            return len(self._active_pipelines) == 0

    def has_pipelines(self) -> int:
        """Return the count of active pipelines."""
        with self._lock:
            return len(self._active_pipelines)

    def is_alive(self) -> bool:
        """Check if the subprocess is still running."""
        with self._lock:
            if self._process is None:
                return False
            return self._process.poll() is None

    def idle_duration(self) -> float:
        """Return how long (seconds) the worker has been idle."""
        with self._lock:
            if not self.is_idle():
                return 0.0
            return time.time() - self._last_activity_time

    def shutdown(self, timeout: float = 15.0) -> None:
        """Gracefully shutdown the worker process."""
        self._shutting_down.set()

        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return

        self.send_command({"cmd": "shutdown"})
        try:
            process.wait(timeout=timeout)
            logger.info("Worker shutdown gracefully (affinity: %s)", self.affinity_key)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Worker did not exit within %.1fs, killing (affinity: %s)",
                timeout,
                self.affinity_key,
            )
            try:
                process.kill()
                process.wait()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _read_stdout(self) -> None:
        """Background thread: read and dispatch JSON status events."""
        with self._lock:
            process = self._process
        if process is None:
            return

        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                logger.debug("[gst_worker:%s] %s", self.affinity_key, stripped)
                continue

            self._event_handler(event)

        if self._shutting_down.is_set():
            logger.debug("Worker stdout closed (expected shutdown, affinity: %s)", self.affinity_key)
            return

        logger.warning("Worker stdout closed unexpectedly (affinity: %s)", self.affinity_key)
        self._on_unexpected_exit(self)

    def _read_stderr(self) -> None:
        """Background thread: parse and re-log JSON log lines."""
        with self._lock:
            process = self._process
        if process is None:
            return

        for line in process.stderr:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
                level = _WORKER_LOG_LEVELS.get(record.get("level"), logging.INFO)
                message = record.get("message", stripped)
            except json.JSONDecodeError:
                level = logging.WARNING
                message = stripped

            logger.log(level, "[gst_worker:%s] %s", self.affinity_key, message)


class WorkerPool:
    """Manages a pool of ManagedWorker instances keyed by CPU affinity."""

    def __init__(self, event_handler: Callable[[dict], None]) -> None:
        """
        Args:
            event_handler: Callback to dispatch JSON status events from all workers.
        """
        self._event_handler = event_handler
        self._workers: Dict[Optional[Tuple[int, ...]], ManagedWorker] = {}
        self._lock = threading.RLock()
        self._idle_timers: Dict[Optional[Tuple[int, ...]], threading.Timer] = {}
        self._shutting_down = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_command(
        self,
        instance_id: str,
        command_base: dict,
        cpu_cores: Optional[List[int]] = None,
    ) -> bool:
        """Send a command to the appropriate worker for this CPU affinity.
        
        Args:
            instance_id: Pipeline instance ID.
            command_base: Base command dict (will add instance_id if not present).
            cpu_cores: CPU cores for this pipeline (or None for unpinned).
            
        Returns:
            True if the command was sent successfully.
        """
        affinity_key = _normalize_cpu_cores(cpu_cores)
        is_start = command_base.get("cmd") == "start"

        with self._lock:
            if self._shutting_down.is_set():
                return False
            if is_start:
                worker = self._get_or_create_worker(affinity_key)
                if worker is None:
                    return False
                # Track under the pool lock so a pending idle reap cannot pick this worker.
                worker.track_pipeline(instance_id)
                self._cancel_idle_timer(affinity_key)
            else:
                worker = self._workers.get(affinity_key)
                if worker is None:
                    return False

        command = dict(command_base)
        command["instance_id"] = instance_id
        success = worker.send_command(command)

        if not success and is_start:
            self.untrack_pipeline(instance_id, cpu_cores)

        return success

    def untrack_pipeline(self, instance_id: str, cpu_cores: Optional[List[int]] = None) -> None:
        """Mark a pipeline as finished; call on its terminal event (stopped/error)."""
        affinity_key = _normalize_cpu_cores(cpu_cores)
        with self._lock:
            worker = self._workers.get(affinity_key)
        if worker:
            worker.untrack_pipeline(instance_id)
            self._maybe_schedule_idle_reap(affinity_key)

    def shutdown(self) -> None:
        """Gracefully shutdown all workers. Call on application shutdown."""
        self._shutting_down.set()

        # Cancel any pending idle timers
        with self._lock:
            for timer in self._idle_timers.values():
                if timer.is_alive():
                    timer.cancel()
            self._idle_timers.clear()

        # Shutdown unpinned worker last
        with self._lock:
            workers_to_shutdown = sorted(self._workers.items(), key=lambda kv: kv[0] is None)

        for affinity_key, worker in workers_to_shutdown:
            logger.info("Shutting down worker (affinity: %s)", affinity_key)
            worker.shutdown()

        with self._lock:
            self._workers.clear()

    # ------------------------------------------------------------------
    # Internal: worker management
    # ------------------------------------------------------------------

    def _get_or_create_worker(self, affinity_key: Optional[Tuple[int, ...]]) -> Optional[ManagedWorker]:
        """Get or create a worker for the given affinity key. Caller must hold self._lock."""
        worker = self._workers.get(affinity_key)
        if worker is not None and worker.is_alive():
            return worker

        worker = ManagedWorker(affinity_key, self._event_handler, self._on_worker_exit)
        if not worker.start():
            return None

        self._workers[affinity_key] = worker
        return worker

    def _on_worker_exit(self, worker: ManagedWorker) -> None:
        """Drop a crashed worker and fail its pipelines; the next request recreates it."""
        with self._lock:
            if self._workers.get(worker.affinity_key) is worker:
                del self._workers[worker.affinity_key]
                self._cancel_idle_timer(worker.affinity_key)

        for instance_id in worker.drain_active():
            self._event_handler({
                "instance_id": instance_id,
                "event": "error",
                "reason": "gst_worker process exited unexpectedly",
            })
            self._event_handler({"instance_id": instance_id, "event": "stopped"})

    def _cancel_idle_timer(self, affinity_key: Optional[Tuple[int, ...]]) -> None:
        """Cancel a pending idle reap timer. Caller must hold self._lock."""
        timer = self._idle_timers.pop(affinity_key, None)
        if timer is not None:
            timer.cancel()

    def _maybe_schedule_idle_reap(self, affinity_key: Optional[Tuple[int, ...]]) -> None:
        """Schedule idle reaping for a pinned worker if it just became idle."""
        if affinity_key is None:
            # Never reap the unpinned worker
            return

        with self._lock:
            if self._shutting_down.is_set():
                return
            worker = self._workers.get(affinity_key)
            if worker is None or not worker.is_idle():
                return

            self._cancel_idle_timer(affinity_key)
            timer = threading.Timer(
                _IDLE_TIMEOUT_SECONDS,
                self._reap_idle_worker,
                args=(affinity_key,),
            )
            timer.daemon = True
            self._idle_timers[affinity_key] = timer
            timer.start()
        logger.debug(
            "Scheduled idle reap for worker in %.0fs (affinity: %s)",
            _IDLE_TIMEOUT_SECONDS,
            affinity_key,
        )

    def _reap_idle_worker(self, affinity_key: Optional[Tuple[int, ...]]) -> None:
        """Reap (shutdown) an idle pinned worker."""
        if affinity_key is None:
            return

        with self._lock:
            worker = self._workers.get(affinity_key)
            if worker is None or not worker.is_idle() or not worker.is_alive():
                return

            del self._workers[affinity_key]
            self._idle_timers.pop(affinity_key, None)

        logger.info("Reaped idle worker (affinity: %s)", affinity_key)
        worker.shutdown()
