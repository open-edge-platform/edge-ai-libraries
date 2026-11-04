# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Extraction jobs: a graph source turning its pool's documents into OKF.

Extraction is slow (an LLM reads the whole corpus) and is not part of syncing.
A sync only notes that a source's extraction is out of date; a job here runs
the extractor, publishes the bundle as a pool asset and syncs the pool so the
graph builds it. Jobs are kept in memory -- the durable part, whether the
generated bundle is current, lives on the source's status.

One job per (library, pool, source) is active at a time. Asking again while
one is queued returns that job; asking while one is running returns it too
and schedules exactly one more run after it, so changes that landed mid-run
are not lost and a burst of uploads does not stack up runs.

A request may ask for a quiet period (`delay`, the `auto` trigger's debounce):
the job waits until no new document-change request has arrived for that long.
Unchanged syncs do not request again. A request without a delay makes a waiting
job due now; a follow-up only waits for quiet time not already spent in a run.

`ExtractionScheduler` is the one background thread that fires `schedule`
triggers, asking every library for its due extractions once per tick.
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = "queued", "running", "succeeded", "failed", "cancelled"
ACTIVE = (QUEUED, RUNNING)
#: Finished jobs kept per pool and source for `GET .../extractions`.
HISTORY = 20
#: Extractions running at once across the engine; each holds an extractor
#: request open for minutes.
WORKERS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _later(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _seconds_until(moment: str) -> float:
    return (datetime.fromisoformat(moment) - datetime.now(timezone.utc)).total_seconds()


@dataclass
class ExtractionJob:
    extraction_id: str
    library: str
    asset_pool_id: str
    source_id: str
    trigger: str                      # auto | manual
    force: bool = False
    state: str = QUEUED
    requested_at: str = field(default_factory=_now)
    # When a debounced job may start (None: as soon as a worker is free).
    not_before: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    # What the run did: {"outcome": "extracted" | "up_to_date" | "removed", ...}.
    result: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.library, self.asset_pool_id, self.source_id)

    def to_out(self) -> Dict[str, Any]:
        return asdict(self)


class ExtractionJobs:
    """Queue, run and remember extraction jobs for one asset library."""

    #: Run jobs on the caller's thread (tests); the API never waits on a job.
    inline = False

    def __init__(self, run: Callable[[ExtractionJob], Dict[str, Any]],
                 on_finished: Optional[Callable[[ExtractionJob], None]] = None):
        self._run = run
        self._on_finished = on_finished
        self._lock = threading.Lock()
        self._jobs: Dict[str, ExtractionJob] = {}
        self._active: Dict[Tuple[str, str, str], ExtractionJob] = {}
        # trigger, force, absolute quiet deadline (None means as soon as free).
        self._again: Dict[Tuple[str, str, str], Tuple[str, bool, Optional[str]]] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._detached_sources: set[str] = set()

    def request(self, library: str, asset_pool_id: str, source_id: str,
                trigger: str, force: bool = False, delay: float = 0.0) -> Tuple[ExtractionJob, bool]:
        """The job that will cover the pool's current documents, and whether it is new.

        `delay` seconds of quiet are waited for before it starts; each further
        delayed request restarts the wait, and one without a delay ends it.
        """
        key = (library, asset_pool_id, source_id)
        due = _later(delay) if delay > 0 and not self.inline else None
        with self._lock:
            if source_id in self._detached_sources:
                raise ValueError("Cannot queue extraction for a detached source")
            active = self._active.get(key)
            if active is not None:
                if active.state == RUNNING:
                    # It read the corpus already; run once more after it.
                    if key not in self._again:
                        logger.info("OKF extraction %s is running for pool %s source %s; "
                                    "one more (%s) will follow it", active.extraction_id,
                                    asset_pool_id, source_id, trigger)
                    earlier = self._again.get(key)
                    earlier_force = False
                    if earlier is not None:
                        earlier_trigger, earlier_force, earlier_due = earlier
                        if earlier_trigger == "manual":
                            trigger = "manual"
                        if earlier_due is None:
                            due = None
                    self._again[key] = (trigger, force or earlier_force, due)
                    return active, False
                active.force = active.force or force
                if due is None:
                    active.not_before = None
                elif active.not_before is not None:
                    active.not_before = max(active.not_before, due)
                submit_now = active.not_before is None
                job = active
            else:
                job = ExtractionJob(uuid.uuid4().hex, library, asset_pool_id, source_id,
                                    trigger, force, not_before=due)
                self._jobs[job.extraction_id] = job
                self._active[key] = job
                self._trim(key)
                submit_now = due is None
                logger.info("OKF extraction %s queued (%s) for pool %s source %s%s",
                            job.extraction_id, trigger, asset_pool_id, source_id,
                            f", starting after {delay:.0f}s without changes" if due else "")
        if submit_now:
            self._submit(job)
        elif job is not active:
            self._arm(job)
        return job, job is not active

    def get(self, extraction_id: str) -> Optional[ExtractionJob]:
        with self._lock:
            return self._jobs.get(extraction_id)

    def list(self, asset_pool_id: Optional[str] = None,
             source_id: Optional[str] = None) -> List[ExtractionJob]:
        """Newest first."""
        with self._lock:
            jobs = [
                job for job in self._jobs.values()
                if (asset_pool_id is None or job.asset_pool_id == asset_pool_id)
                and (source_id is None or job.source_id == source_id)
            ]
        return sorted(jobs, key=lambda job: job.requested_at, reverse=True)

    def active(self, library: str, asset_pool_id: str, source_id: str) -> Optional[ExtractionJob]:
        with self._lock:
            return self._active.get((library, asset_pool_id, source_id))

    def cancel(self, extraction_id: str) -> ExtractionJob:
        """Cancel a queued job. A running one cannot be: the extractor request
        is already in flight, and its result would be discarded, not stopped."""
        with self._lock:
            job = self._jobs.get(extraction_id)
            if job is None:
                raise KeyError(extraction_id)
            if job.state == RUNNING:
                raise ValueError("A running extraction cannot be cancelled")
            if job.state == QUEUED:
                job.state, job.finished_at = CANCELLED, _now()
                self._active.pop(job.key, None)
            return job

    def detach_source(self, source_id: str) -> None:
        """Cancel queued work atomically; an in-flight publication must finish first."""
        with self._lock:
            jobs = [job for job in self._active.values() if job.source_id == source_id]
            if any(job.state == RUNNING for job in jobs):
                raise ValueError(
                    "This source has a running OKF extraction. Wait for it to finish "
                    "before deleting the source, so its result is not published to a deleted binding."
                )
            self._detached_sources.add(source_id)
            for job in jobs:
                job.state, job.finished_at = CANCELLED, _now()
                self._active.pop(job.key, None)
                self._again.pop(job.key, None)

    # --- running ----------------------------------------------------------------

    def _arm(self, job: ExtractionJob) -> None:
        """Submit `job` once its quiet period ends (re-armed if it was extended)."""
        wait = max(0.0, _seconds_until(job.not_before)) if job.not_before else 0.0
        timer = threading.Timer(wait, self._due, (job,))
        timer.daemon = True
        timer.start()

    def _due(self, job: ExtractionJob) -> None:
        with self._lock:
            if job.state != QUEUED:
                return
            if job.not_before is not None and _seconds_until(job.not_before) > 0.05:
                waiting = True
            else:
                job.not_before, waiting = None, False
        if waiting:
            self._arm(job)
        else:
            self._submit(job)

    def _submit(self, job: ExtractionJob) -> None:
        if self.inline:
            self._work(job)
            return
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(WORKERS, thread_name_prefix="okf-extraction")
        self._executor.submit(self._work, job)

    def _work(self, job: ExtractionJob) -> None:
        with self._lock:
            if job.state != QUEUED or job.not_before is not None:
                return
            job.state, job.started_at = RUNNING, _now()
        logger.info("OKF extraction %s started (%s) for pool %s source %s",
                    job.extraction_id, job.trigger, job.asset_pool_id, job.source_id)
        began = time.monotonic()
        try:
            result = self._run(job)
            job.result = dict(result or {})
            job.state = SUCCEEDED
            logger.info("OKF extraction %s finished in %.0fs: %s", job.extraction_id,
                        time.monotonic() - began,
                        ", ".join(f"{key}={value}" for key, value in job.result.items()))
        except Exception as error:  # noqa: BLE001 - reported on the job
            logger.exception("OKF extraction %s failed after %.0fs", job.extraction_id,
                             time.monotonic() - began)
            job.error = f"{type(error).__name__}: {error}"
            job.state = FAILED
        finally:
            job.finished_at = _now()
            with self._lock:
                if self._active.get(job.key) is job:
                    del self._active[job.key]
                again = self._again.pop(job.key, None)
                if job.source_id in self._detached_sources:
                    again = None
        if self._on_finished is not None:
            try:
                self._on_finished(job)
            except Exception:  # noqa: BLE001 - the job itself is done
                logger.exception("Saving after extraction %s failed", job.extraction_id)
        if again is not None and job.state == FAILED and again[0] != "manual":
            # The same corpus would most likely fail the same way -- and after a
            # timeout the extractor may still be working on the abandoned task.
            # The source stays outdated: the next change or a request retries.
            logger.info("OKF extraction %s failed; not starting its automatic follow-up",
                        job.extraction_id)
            again = None
        if again is not None:
            trigger, force, due = again
            delay = max(0.0, _seconds_until(due)) if due else 0.0
            self.request(job.library, job.asset_pool_id, job.source_id, trigger, force, delay)

    def _trim(self, key: Tuple[str, str, str]) -> None:
        finished = sorted(
            (job for job in self._jobs.values() if job.key == key and job.state not in ACTIVE),
            key=lambda job: job.requested_at,
        )
        for job in finished[:-HISTORY] if len(finished) > HISTORY else []:
            del self._jobs[job.extraction_id]


class ExtractionScheduler:
    """Fire `schedule` triggers: every `TICK` seconds, ask each library from
    `libraries()` to request the extractions whose cron minute has come.

    The tick is shorter than a minute, so every matching minute is seen; a
    library remembers which minute it last fired for each source. Minutes
    that pass while the engine is down are not caught up -- the source stays
    `outdated` until its next scheduled minute (or a manual request).
    """

    TICK = 20.0

    def __init__(self, libraries: Callable[[], List[Any]]):
        self._libraries = libraries
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="okf-extraction-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        for library in self._libraries():
            run = getattr(library, "run_scheduled_extractions", None)
            if run is None:
                continue
            try:
                run(now)
            except Exception:  # noqa: BLE001 - one library must not stop the others
                logger.exception("Scheduled extraction check failed for %s", getattr(library, "name", "?"))

    def _loop(self) -> None:
        while not self._stop.wait(self.TICK):
            self.tick()
