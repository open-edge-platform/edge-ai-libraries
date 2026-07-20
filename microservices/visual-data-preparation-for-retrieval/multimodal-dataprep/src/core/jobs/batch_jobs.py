# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-process asynchronous batch-job engine for video ingestion.

All batch ingestion surfaces (multi-file upload, batch-process-existing, and
directory ingest) converge onto this single engine. A submitted job owns a list
of :class:`BatchItem` records and is processed **sequentially** on a background
daemon thread, wrapping the same proven single-video processing path used by the
non-batch endpoints. Each item is isolated: a failure records an error on that
item and processing continues with the next one.

The engine is deliberately in-process (a registry ``dict`` guarded by a lock).
Job state is therefore lost on restart, which is acceptable for the current
scope; persistence can be layered on later without changing the public surface.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.common import logger, sanitize_for_log, settings
from src.common.schema import BatchItemStatusEnum, BatchJobStateEnum

# A processor takes a single item and returns the number of embeddings created.
# It must raise on failure; the engine isolates the failure to that item.
ItemProcessor = Callable[["BatchItem"], int]


@dataclass
class BatchItem:
    """A single unit of work within a batch job."""

    identifier: str
    bucket_name: Optional[str] = None
    video_id: Optional[str] = None
    video_name: Optional[str] = None
    frame_interval: int = 15
    enable_object_detection: bool = True
    detection_confidence: float = 0.85
    tags: List[str] = field(default_factory=list)
    status: BatchItemStatusEnum = BatchItemStatusEnum.pending
    message: Optional[str] = None
    embeddings_count: Optional[int] = None


@dataclass
class BatchJob:
    """A batch ingestion job and its per-item results."""

    job_id: str
    source: str
    items: List[BatchItem]
    state: BatchJobStateEnum = BatchJobStateEnum.pending
    created_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)
    _cancel: bool = False

    def counts(self) -> tuple[int, int]:
        """Return ``(completed, failed)`` counts across the job's items."""
        completed = sum(1 for i in self.items if i.status == BatchItemStatusEnum.success)
        failed = sum(1 for i in self.items if i.status == BatchItemStatusEnum.error)
        return completed, failed


_jobs: "OrderedDict[str, BatchJob]" = OrderedDict()
_lock = threading.Lock()


def _touch(job: BatchJob) -> None:
    job.updated_ts = time.time()


def _evict_if_needed() -> None:
    """Drop the oldest finished jobs once retention is exceeded (caller holds lock)."""
    retention = max(1, int(settings.BATCH_JOB_RETENTION))
    if len(_jobs) <= retention:
        return
    terminal = {
        BatchJobStateEnum.completed,
        BatchJobStateEnum.completed_with_errors,
        BatchJobStateEnum.failed,
        BatchJobStateEnum.cancelled,
    }
    for job_id in list(_jobs.keys()):
        if len(_jobs) <= retention:
            break
        if _jobs[job_id].state in terminal:
            del _jobs[job_id]


def _run_job(job: BatchJob, processor: ItemProcessor) -> None:
    """Sequentially process a job's items with per-item error isolation."""
    with _lock:
        job.state = BatchJobStateEnum.running
        _touch(job)

    for item in job.items:
        if job._cancel:
            with _lock:
                item.status = BatchItemStatusEnum.skipped
                item.message = "Job cancelled before this item was processed."
                _touch(job)
            continue

        with _lock:
            item.status = BatchItemStatusEnum.running
            _touch(job)

        try:
            count = processor(item)
            with _lock:
                item.embeddings_count = int(count)
                item.status = BatchItemStatusEnum.success
                item.message = f"{count} embeddings created."
                _touch(job)
        except Exception as exc:  # noqa: BLE001 - isolate per-item failures
            logger.error(
                "Batch job %s item %s failed: %s",
                sanitize_for_log(job.job_id, max_length=64),
                sanitize_for_log(item.identifier, max_length=256),
                sanitize_for_log(str(exc), max_length=512),
            )
            with _lock:
                item.status = BatchItemStatusEnum.error
                item.message = sanitize_for_log(str(exc), max_length=512)
                _touch(job)

    completed, failed = job.counts()
    with _lock:
        if job._cancel and (completed + failed) < len(job.items):
            job.state = BatchJobStateEnum.cancelled
        elif failed == len(job.items) and len(job.items) > 0:
            job.state = BatchJobStateEnum.failed
        elif failed > 0:
            job.state = BatchJobStateEnum.completed_with_errors
        else:
            job.state = BatchJobStateEnum.completed
        _touch(job)

    logger.info(
        "Batch job %s finished: state=%s completed=%d failed=%d",
        sanitize_for_log(job.job_id, max_length=64),
        job.state.value,
        completed,
        failed,
    )


def submit_job(source: str, items: List[BatchItem], processor: ItemProcessor) -> BatchJob:
    """Register a new job and start processing it on a background daemon thread."""
    job = BatchJob(job_id=uuid.uuid4().hex, source=source, items=items)
    with _lock:
        _jobs[job.job_id] = job
        _evict_if_needed()

    thread = threading.Thread(
        target=_run_job,
        args=(job, processor),
        name=f"batch-job-{job.job_id[:8]}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "Batch job %s submitted (source=%s, items=%d)",
        sanitize_for_log(job.job_id, max_length=64),
        sanitize_for_log(source, max_length=64),
        len(items),
    )
    return job


def get_job(job_id: str) -> Optional[BatchJob]:
    """Return the job with ``job_id`` or ``None`` if unknown."""
    with _lock:
        return _jobs.get(job_id)


def cancel_job(job_id: str) -> Optional[BatchJob]:
    """Request cooperative cancellation of a pending/running job.

    Returns the job if found (whether or not it was still cancellable), else None.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job.state in (BatchJobStateEnum.pending, BatchJobStateEnum.running):
            job._cancel = True
            _touch(job)
        return job


def reset_jobs() -> None:
    """Clear the job registry (test helper)."""
    with _lock:
        _jobs.clear()
