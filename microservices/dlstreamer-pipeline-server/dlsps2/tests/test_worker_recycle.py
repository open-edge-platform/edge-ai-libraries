# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for idle recycling of the unpinned gst_worker in WorkerPool."""

from unittest.mock import MagicMock, patch

import pytest

from core import worker_pool
from core.worker_pool import WorkerPool


@pytest.fixture
def pool(monkeypatch):
    """WorkerPool with a 5s recycle delay and no real subprocesses."""
    monkeypatch.setenv("DLSPS_WORKER_RECYCLE_IDLE_SECONDS", "5")
    return WorkerPool(event_handler=MagicMock())


def _idle_worker(affinity_key=None):
    worker = MagicMock()
    worker.affinity_key = affinity_key
    worker.is_idle.return_value = True
    worker.is_alive.return_value = True
    return worker


def test_recycle_delay_read_from_env(monkeypatch):
    monkeypatch.setenv("DLSPS_WORKER_RECYCLE_IDLE_SECONDS", "0")
    assert worker_pool._read_recycle_idle_seconds() is None
    monkeypatch.setenv("DLSPS_WORKER_RECYCLE_IDLE_SECONDS", "junk")
    assert worker_pool._read_recycle_idle_seconds() == worker_pool._DEFAULT_RECYCLE_IDLE_SECONDS


def test_disabled_recycling_schedules_no_timer(monkeypatch):
    monkeypatch.setenv("DLSPS_WORKER_RECYCLE_IDLE_SECONDS", "0")
    pool = WorkerPool(event_handler=MagicMock())
    pool._workers[None] = _idle_worker()

    pool._maybe_schedule_idle_reap(None)

    assert None not in pool._idle_timers


def test_idle_unpinned_worker_is_recycled_and_restarted(pool):
    old = _idle_worker()
    new = _idle_worker()
    pool._workers[None] = old

    with patch.object(pool, "_get_or_create_worker", return_value=new) as create:
        pool._reap_idle_worker(None)

    old.shutdown.assert_called_once()
    create.assert_called_once_with(None)


def test_busy_unpinned_worker_is_not_recycled(pool):
    worker = _idle_worker()
    worker.is_idle.return_value = False
    pool._workers[None] = worker

    with patch.object(pool, "_get_or_create_worker") as create:
        pool._reap_idle_worker(None)

    worker.shutdown.assert_not_called()
    create.assert_not_called()
    assert pool._workers[None] is worker


def test_untrack_last_pipeline_schedules_unpinned_recycle(pool):
    worker = _idle_worker()
    pool._workers[None] = worker

    with patch.object(worker_pool.threading, "Timer") as timer_cls:
        pool._maybe_schedule_idle_reap(None)

    timer_cls.assert_called_once()
    assert timer_cls.call_args.args[0] == 5.0
    assert None in pool._idle_timers


class _FakeWorker:
    """Minimal ManagedWorker stand-in that tracks pipelines like the real one."""

    def __init__(self, affinity_key, *_args):
        self.affinity_key = affinity_key
        self.pipelines = set()
        self.shut_down = False

    def start(self):
        return True

    def is_alive(self):
        return not self.shut_down

    def is_idle(self):
        return not self.pipelines

    def send_command(self, _command):
        return True

    def track_pipeline(self, instance_id):
        self.pipelines.add(instance_id)

    def untrack_pipeline(self, instance_id):
        self.pipelines.discard(instance_id)

    def shutdown(self, timeout=15.0):
        self.shut_down = True


def test_recycle_happens_once_per_pipeline_run(pool):
    """An idle worker is never recycled on its own; each pipeline stop yields one recycle."""
    with patch.object(worker_pool, "ManagedWorker", _FakeWorker):
        # First worker: created by a pipeline start, no timer while busy.
        assert pool.send_command("p1", {"cmd": "start"})
        assert None not in pool._idle_timers

        # Pipeline stops: one recycle timer is scheduled.
        pool.untrack_pipeline("p1")
        assert None in pool._idle_timers
        first = pool._workers[None]

        # Timer fires: old worker is shut down and a fresh one replaces it.
        pool._reap_idle_worker(None)
        assert first.shut_down
        second = pool._workers[None]
        assert second is not first
        assert not second.shut_down

        # The fresh idle worker schedules nothing by itself.
        assert None not in pool._idle_timers

        # Next pipeline run starts the cycle again.
        assert pool.send_command("p2", {"cmd": "start"})
        pool.untrack_pipeline("p2")
        assert None in pool._idle_timers

        pool.shutdown()
