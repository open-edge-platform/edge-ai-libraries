# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for stop handling in PipelineManager."""

from unittest.mock import patch

import pytest

from core.pipeline_manager import PipelineInstance, PipelineManager, PipelineState


@pytest.fixture
def manager():
    """Create a fresh PipelineManager for each test; worker bookkeeping is stubbed out."""
    mgr = PipelineManager()
    with patch.object(mgr._worker_pool, "untrack_pipeline"):
        yield mgr


def _add(manager, instance_id, state=PipelineState.RUNNING, **fields):
    instance = PipelineInstance(
        instance_id=instance_id,
        pipeline_description="fakesrc ! fakesink",
        validate=False,
        state=state,
        **fields,
    )
    with manager._lock:
        manager._instances[instance_id] = instance
    return instance


def _add_running(manager, instance_id, **fields):
    return _add(manager, instance_id, PipelineState.RUNNING, **fields)


def test_stop_racing_failed_start_ends_aborted(manager):
    """A stop sent before a failed start's error is handled must still finish as ABORTED."""
    instance = _add_running(manager, "race")
    with patch.object(manager._worker_pool, "send_command", return_value=True):
        assert manager.stop("race")

    manager._handle_event({"instance_id": "race", "event": "error", "reason": "fps_element 'x' not found in pipeline"})
    manager._handle_event({"instance_id": "race", "event": "stopped"})

    assert instance.state == PipelineState.ABORTED
    assert instance.finalized is True


def test_stop_of_running_instance_reports_aborted_only_on_stopped(manager):
    """A running instance is STOPPING after stop is sent and becomes ABORTED only on "stopped"."""
    instance = _add_running(manager, "running")
    with patch.object(manager._worker_pool, "send_command", return_value=True):
        assert manager.stop("running")
    assert instance.state == PipelineState.STOPPING

    manager._handle_event({"instance_id": "running", "event": "stopped"})

    assert instance.state == PipelineState.ABORTED
    assert instance.finalized is True


def test_stop_while_stopping_is_accepted_without_second_command(manager):
    _add_running(manager, "dup")
    with patch.object(manager._worker_pool, "send_command", return_value=True) as send:
        assert manager.stop("dup")
        assert manager.stop("dup")
    assert send.call_count == 1


def test_failed_stop_send_leaves_instance_running(manager):
    instance = _add_running(manager, "nosend")
    with patch.object(manager._worker_pool, "send_command", return_value=False):
        assert manager.stop("nosend") is False
    assert instance.state == PipelineState.RUNNING
    assert instance.stop_requested is False


def test_stop_of_queued_instance_aborts_without_worker_command(manager):
    instance = _add(manager, "queued", state=PipelineState.QUEUED)
    with patch.object(manager._worker_pool, "send_command") as send:
        assert manager.stop("queued")
    send.assert_not_called()
    assert instance.state == PipelineState.ABORTED
    assert instance.finalized is True


def test_stop_during_restarting_aborts_at_once(manager):
    instance = _add(manager, "waiting", state=PipelineState.RESTARTING)
    assert manager.stop("waiting")
    assert instance.state == PipelineState.ABORTED


def test_error_alone_does_not_finalize_running_instance(manager):
    instance = _add_running(manager, "err")
    manager._handle_event({"instance_id": "err", "event": "error", "reason": "boom"})
    assert instance.state == PipelineState.RUNNING
    assert instance.error == "boom"
    assert instance.finalized is False


def test_stopped_after_error_without_restart_finishes_as_error(manager):
    instance = _add_running(manager, "fail")
    manager._handle_event({"instance_id": "fail", "event": "error", "reason": "boom"})
    manager._handle_event({"instance_id": "fail", "event": "stopped"})
    assert instance.state == PipelineState.ERROR
    assert instance.finalized is True


def test_stopped_after_eos_without_restart_finishes_as_completed(manager):
    instance = _add_running(manager, "done")
    manager._handle_event({"instance_id": "done", "event": "eos"})
    manager._handle_event({"instance_id": "done", "event": "stopped"})
    assert instance.state == PipelineState.COMPLETED


def test_failed_run_is_restarted_only_on_stopped(manager):
    restart = {"enabled": True, "max_attempts": 2, "backoff_seconds": 0}
    instance = _add_running(manager, "restart", restart_config=restart)
    with patch.object(manager, "_schedule_restart") as schedule:
        manager._handle_event({"instance_id": "restart", "event": "error", "reason": "boom"})
        schedule.assert_not_called()
        manager._handle_event({"instance_id": "restart", "event": "stopped"})

    assert instance.state == PipelineState.RESTARTING
    assert instance.restart_attempts == 1
    schedule.assert_called_once_with(instance)


def test_stop_during_run_prevents_restart(manager):
    restart = {"enabled": True, "max_attempts": 2, "backoff_seconds": 0}
    instance = _add_running(manager, "stopped-run", restart_config=restart)
    with patch.object(manager._worker_pool, "send_command", return_value=True):
        assert manager.stop("stopped-run")
    with patch.object(manager, "_schedule_restart") as schedule:
        manager._handle_event({"instance_id": "stopped-run", "event": "stopped"})

    schedule.assert_not_called()
    assert instance.state == PipelineState.ABORTED


def test_restart_gives_up_at_max_attempts(manager):
    restart = {"enabled": True, "max_attempts": 2, "backoff_seconds": 0}
    instance = _add_running(manager, "maxed", restart_config=restart, restart_attempts=2, error="boom")
    with patch.object(manager, "_schedule_restart") as schedule:
        manager._handle_event({"instance_id": "maxed", "event": "stopped"})

    schedule.assert_not_called()
    assert instance.state == PipelineState.ERROR


def test_restart_is_not_submitted_after_cancel(manager):
    restart = {"enabled": True, "max_attempts": 2, "backoff_seconds": 0}
    instance = _add(manager, "cancel", state=PipelineState.RESTARTING, restart_config=restart, restart_attempts=1)
    assert manager.stop("cancel")
    with patch.object(manager._worker_pool, "send_command") as send:
        manager._restart_pipeline(instance)
    send.assert_not_called()
    assert instance.state == PipelineState.ABORTED


def test_restart_resubmits_and_clears_previous_error(manager):
    restart = {"enabled": True, "max_attempts": 2, "backoff_seconds": 0}
    instance = _add(
        manager,
        "again",
        state=PipelineState.RESTARTING,
        restart_config=restart,
        restart_attempts=1,
        error="boom",
        finalized=True,
    )
    with patch.object(manager._worker_pool, "send_command", return_value=True) as send:
        manager._restart_pipeline(instance)

    send.assert_called_once()
    assert send.call_args.args[1]["cmd"] == "start"
    assert instance.state == PipelineState.RUNNING
    assert instance.finalized is False
    assert instance.error is None


def test_list_running_includes_stopping_instances(manager):
    _add_running(manager, "a")
    _add(manager, "b", state=PipelineState.STOPPING)
    _add(manager, "c", state=PipelineState.ABORTED)
    assert {i.instance_id for i in manager.list_running()} == {"a", "b"}
