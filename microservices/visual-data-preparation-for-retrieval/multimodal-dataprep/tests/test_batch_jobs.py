# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the async batch-job engine and directory-ingest path guard.

Covers the job state machine, per-item error isolation, cancellation, retention
eviction, and the traversal-safe ingest-directory resolver. No real storage or
embedding backend is exercised (processors are stubbed).
"""

import time

import pytest

from src.common.schema import BatchItemStatusEnum, BatchJobStateEnum
from src.core.jobs.batch_jobs import (
    BatchItem,
    cancel_job,
    get_job,
    reset_jobs,
    submit_job,
)


def _wait_terminal(job_id, timeout=5.0):
    terminal = {
        BatchJobStateEnum.completed,
        BatchJobStateEnum.completed_with_errors,
        BatchJobStateEnum.failed,
        BatchJobStateEnum.cancelled,
    }
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job and job.state in terminal:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal state")


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_jobs()
    yield
    reset_jobs()


def test_all_items_succeed_completes():
    job = submit_job("t", [BatchItem(identifier="a"), BatchItem(identifier="b")], lambda i: 7)
    done = _wait_terminal(job.job_id)
    assert done.state == BatchJobStateEnum.completed
    assert done.counts() == (2, 0)
    assert all(i.status == BatchItemStatusEnum.success for i in done.items)
    assert all(i.embeddings_count == 7 for i in done.items)


def test_partial_failure_isolated():
    def proc(item):
        if item.identifier == "bad":
            raise ValueError("boom")
        return 3

    items = [BatchItem(identifier="a"), BatchItem(identifier="bad"), BatchItem(identifier="c")]
    job = submit_job("t", items, proc)
    done = _wait_terminal(job.job_id)
    assert done.state == BatchJobStateEnum.completed_with_errors
    assert done.counts() == (2, 1)
    statuses = [i.status for i in done.items]
    assert statuses == [
        BatchItemStatusEnum.success,
        BatchItemStatusEnum.error,
        BatchItemStatusEnum.success,
    ]
    assert "boom" in done.items[1].message


def test_all_items_fail_marks_failed():
    job = submit_job("t", [BatchItem(identifier="x")], lambda i: (_ for _ in ()).throw(RuntimeError("nope")))
    done = _wait_terminal(job.job_id)
    assert done.state == BatchJobStateEnum.failed


def test_unknown_job_returns_none():
    assert get_job("does-not-exist") is None
    assert cancel_job("does-not-exist") is None


def test_cancel_skips_remaining_items():
    barrier = {"first_started": False}

    def slow(item):
        if item.identifier == "a":
            barrier["first_started"] = True
            time.sleep(0.3)
        return 1

    items = [BatchItem(identifier="a"), BatchItem(identifier="b"), BatchItem(identifier="c")]
    job = submit_job("t", items, slow)
    while not barrier["first_started"]:
        time.sleep(0.01)
    cancel_job(job.job_id)
    done = _wait_terminal(job.job_id)
    assert done.state == BatchJobStateEnum.cancelled
    # At least one later item should have been skipped.
    assert any(i.status == BatchItemStatusEnum.skipped for i in done.items)


def test_retention_evicts_oldest(monkeypatch):
    from src.common import settings

    monkeypatch.setattr(settings, "BATCH_JOB_RETENTION", 2)
    ids = []
    for _ in range(4):
        job = submit_job("t", [BatchItem(identifier="a")], lambda i: 1)
        _wait_terminal(job.job_id)
        ids.append(job.job_id)
    # Only the most recent 2 should still be retrievable.
    present = [jid for jid in ids if get_job(jid) is not None]
    assert len(present) <= 2
    assert ids[-1] in present


def test_ingest_dir_traversal_blocked(monkeypatch, tmp_path):
    from src.common import settings
    from src.common.exception import DataPrepException
    from src.core.utils.file_utils import resolve_under_ingest_root

    root = tmp_path / "ingest_root"
    root.mkdir()
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT", str(root))

    with pytest.raises(DataPrepException):
        resolve_under_ingest_root("../../etc", must_be_dir=True)


def test_ingest_dir_valid_resolves(monkeypatch, tmp_path):
    from src.common import settings
    from src.core.utils.file_utils import resolve_under_ingest_root

    root = tmp_path / "ingest_root"
    sub = root / "clips"
    sub.mkdir(parents=True)
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT", str(root))

    resolved = resolve_under_ingest_root("clips", must_be_dir=True)
    assert resolved == sub.resolve()
