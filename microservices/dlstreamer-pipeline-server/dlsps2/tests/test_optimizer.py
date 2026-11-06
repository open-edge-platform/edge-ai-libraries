# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the pipeline optimizer: request schema, worker, and job manager.

The DL Streamer ``optimizer`` module is replaced with a fake, so these tests
run without GStreamer or OpenVINO.
"""

import json
import sys
import types

import pytest
from pydantic import ValidationError

from api.schema import OptimizeRequest
from core import optimizer_worker
from core.optimizer_manager import OptimizerBusyError, OptimizerJob, OptimizerManager, OptimizerState


PIPELINE = "videotestsrc ! gvafpscounter ! fakesink"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeOptimizer:
    """Stands in for DLSOptimizer. Records calls and yields scripted candidates."""

    def __init__(self, candidates=None):
        self.calls = []
        self._candidates = candidates if candidates is not None else [
            ("cand-1", {"fps": 2.0}),
            ("cand-2", {"fps": 3.0}),
        ]

    def __getattr__(self, name):
        if name.startswith(("set_", "enable_")):
            return lambda *args: self.calls.append((name, args))
        raise AttributeError(name)

    def _iterate(self, kind, pipeline):
        self.calls.append((kind, pipeline))
        yield from self._candidates

    def iter_optimize_for_fps(self, pipeline):
        return self._iterate("iter_fps", pipeline)

    def iter_optimize_for_power(self, pipeline):
        return self._iterate("iter_power", pipeline)

    def get_baseline_pipeline(self):
        return ("baseline-pipeline", {"fps": 1.0})

    def get_optimal_pipeline(self):
        return ("best-pipeline", {"fps": 3.0})

    def called(self, name):
        return [args for call_name, args in self.calls if call_name == name]


@pytest.fixture
def fake_optimizer(monkeypatch):
    """Install a FakeOptimizer as the ``optimizer`` module the worker imports."""
    fake = FakeOptimizer()
    module = types.ModuleType("optimizer")
    module.DLSOptimizer = lambda: fake
    monkeypatch.setitem(sys.modules, "optimizer", module)
    return fake


def _start_payload(job_id="job-1", **overrides):
    """Build the start command the manager sends, from a validated request."""
    settings = OptimizeRequest(pipeline=PIPELINE, **overrides).model_dump()
    return {"cmd": "start", "job_id": job_id, **settings}


def _events(captured):
    return [json.loads(line) for line in captured.out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# OptimizeRequest schema
# ---------------------------------------------------------------------------

class TestOptimizeRequestDefaults:
    def test_defaults_match_optimizer_cli(self):
        request = OptimizeRequest(pipeline=PIPELINE)

        assert request.mode == "fps"
        assert request.optimization_profile == "default"
        assert request.search_duration == 300
        assert request.sample_duration == 10
        assert request.detection_threshold == 0.95
        assert request.enable_cross_stream_batching is False
        assert request.maximize_streams is False
        assert request.batch_sizes is None
        assert request.nireq_sizes is None
        assert request.allowed_devices is None


class TestOptimizeRequestValidation:
    @pytest.mark.parametrize("kwargs", [
        {"mode": "power"},
        {"maximize_streams": True},
    ])
    def test_rejects_missing_required_options(self, kwargs):
        with pytest.raises(ValidationError):
            OptimizeRequest(pipeline=PIPELINE, **kwargs)

    def test_power_mode_accepts_metrics_endpoint(self):
        request = OptimizeRequest(
            pipeline=PIPELINE, mode="power", power_metrics_endpoint="http://metrics:8080/metrics"
        )
        assert request.mode == "power"

    def test_maximize_streams_accepts_fps_limit(self):
        request = OptimizeRequest(pipeline=PIPELINE, maximize_streams=True, fps_limit=30)
        assert request.maximize_streams is True

    @pytest.mark.parametrize("kwargs", [
        {"batch_sizes": []},
        {"batch_sizes": [0]},
        {"nireq_sizes": [-1]},
        {"allowed_devices": []},
        {"allowed_devices": [" "]},
        {"detection_threshold": 1.5},
        {"fps_limit": 0},
        {"power_limit": -5},
        {"optimization_profile": "turbo"},
        {"mode": "latency"},
    ])
    def test_rejects_invalid_values(self, kwargs):
        with pytest.raises(ValidationError):
            OptimizeRequest(pipeline=PIPELINE, **kwargs)


# ---------------------------------------------------------------------------
# Worker: settings and profiles
# ---------------------------------------------------------------------------

class TestConfigure:
    def test_default_profile_applies_request_values(self, fake_optimizer):
        start = _start_payload(search_duration=120, sample_duration=7, allowed_devices=["CPU"])

        search_duration = optimizer_worker._configure(fake_optimizer, start)

        assert search_duration == 120
        assert fake_optimizer.called("set_sample_duration") == [(7.0,)]
        assert fake_optimizer.called("set_allowed_devices") == [(["CPU"],)]
        # batch and nireq are left to the optimizer defaults when not provided
        assert fake_optimizer.called("set_batch_sizes") == []
        assert fake_optimizer.called("set_nireq_sizes") == []

    def test_coarse_profile_overrides_timing_and_sizes(self, fake_optimizer):
        start = _start_payload(optimization_profile="coarse", search_duration=120, sample_duration=10)

        search_duration = optimizer_worker._configure(fake_optimizer, start)

        assert search_duration == 15.0
        assert fake_optimizer.called("set_sample_duration") == [(5.0,)]
        assert fake_optimizer.called("set_batch_sizes") == [([],)]
        assert fake_optimizer.called("set_nireq_sizes") == [([],)]

    def test_fine_profile_overrides_timing_and_sizes(self, fake_optimizer):
        start = _start_payload(optimization_profile="fine", batch_sizes=[16], nireq_sizes=[2])

        search_duration = optimizer_worker._configure(fake_optimizer, start)

        assert search_duration == 50.0
        assert fake_optimizer.called("set_batch_sizes") == [([1, 4, 8],)]
        assert fake_optimizer.called("set_nireq_sizes") == [([4, 8],)]

    def test_limits_and_metrics_endpoint_are_applied_when_set(self, fake_optimizer):
        start = _start_payload(
            mode="power",
            power_metrics_endpoint="http://metrics:8080/metrics",
            power_limit=60,
            fps_limit=25,
            maximize_streams=True,
            enable_cross_stream_batching=True,
        )

        optimizer_worker._configure(fake_optimizer, start)

        assert fake_optimizer.called("set_metrics_url") == [("http://metrics:8080/metrics",)]
        assert fake_optimizer.called("set_power_limit") == [(60.0,)]
        assert fake_optimizer.called("set_fps_limit") == [(25.0,)]
        assert fake_optimizer.called("set_maximize_streams") == [(True,)]
        assert fake_optimizer.called("enable_cross_stream_batching") == [(True,)]

    def test_unset_limits_are_not_applied(self, fake_optimizer):
        optimizer_worker._configure(fake_optimizer, _start_payload())

        assert fake_optimizer.called("set_fps_limit") == []
        assert fake_optimizer.called("set_power_limit") == []
        assert fake_optimizer.called("set_metrics_url") == []


# ---------------------------------------------------------------------------
# Worker: optimization run and events
# ---------------------------------------------------------------------------

class TestWorkerRun:
    def test_fps_mode_uses_fps_iterator_and_emits_events(self, fake_optimizer, capsys):
        worker = optimizer_worker.OptimizerWorker("job-1")

        worker._optimize(_start_payload(mode="fps"))

        assert ("iter_fps", PIPELINE) in fake_optimizer.calls
        assert ("iter_power", PIPELINE) not in fake_optimizer.calls
        events = _events(capsys.readouterr())
        assert [event["event"] for event in events] == ["baseline", "candidate", "candidate", "finished"]
        assert events[-1]["cancelled"] is False
        assert events[-1]["candidates_evaluated"] == 2
        assert events[-1]["best"]["pipeline"] == "best-pipeline"

    def test_power_mode_dispatches_to_power_iterator(self, fake_optimizer, capsys):
        worker = optimizer_worker.OptimizerWorker("job-1")

        worker._optimize(_start_payload(
            mode="power", power_metrics_endpoint="http://metrics:8080/metrics", power_limit=60
        ))

        assert ("iter_power", PIPELINE) in fake_optimizer.calls
        assert ("iter_fps", PIPELINE) not in fake_optimizer.calls
        assert fake_optimizer.called("set_metrics_url") == [("http://metrics:8080/metrics",)]
        assert _events(capsys.readouterr())[-1]["event"] == "finished"

    def test_cancel_stops_after_current_candidate(self, fake_optimizer, capsys):
        worker = optimizer_worker.OptimizerWorker("job-1")
        worker._cancel.set()

        worker._optimize(_start_payload())

        events = _events(capsys.readouterr())
        candidates = [event for event in events if event["event"] == "candidate"]
        assert len(candidates) == 1
        assert events[-1]["event"] == "finished"
        assert events[-1]["cancelled"] is True

    def test_search_budget_stops_new_candidates(self, fake_optimizer, capsys, monkeypatch):
        # monotonic() reads: start time, then the elapsed check after the first candidate
        clock = iter([0.0, 1000.0])
        monkeypatch.setattr(optimizer_worker, "time", types.SimpleNamespace(monotonic=lambda: next(clock)))
        worker = optimizer_worker.OptimizerWorker("job-1")

        worker._optimize(_start_payload(search_duration=60))

        events = _events(capsys.readouterr())
        assert len([event for event in events if event["event"] == "candidate"]) == 1
        assert events[-1]["event"] == "finished"
        assert events[-1]["cancelled"] is False

    def test_no_candidates_still_reports_baseline_and_finished(self, fake_optimizer, capsys):
        fake_optimizer._candidates = []
        worker = optimizer_worker.OptimizerWorker("job-1")

        worker._optimize(_start_payload())

        events = _events(capsys.readouterr())
        assert [event["event"] for event in events] == ["baseline", "finished"]
        assert events[-1]["candidates_evaluated"] == 0


# ---------------------------------------------------------------------------
# Manager: one-job rule, partial results, final states
# ---------------------------------------------------------------------------

def _job(settings_overrides=None, job_id="job-1"):
    settings = OptimizeRequest(pipeline=PIPELINE, **(settings_overrides or {})).model_dump()
    return OptimizerJob(job_id=job_id, settings=settings)


class TestManager:
    def test_submit_rejected_while_job_is_active(self):
        manager = OptimizerManager()
        manager._active_job_id = "running-job"

        with pytest.raises(OptimizerBusyError):
            manager.submit(OptimizeRequest(pipeline=PIPELINE).model_dump())

    def test_partial_result_is_visible_while_running(self):
        manager = OptimizerManager()
        job = _job()
        manager._jobs[job.job_id] = job
        manager._active_job_id = job.job_id

        manager._handle_event(job, {
            "event": "candidate",
            "pipeline": "cand-1",
            "metrics": {"fps": 2.0},
            "candidates_evaluated": 1,
            "best": {"pipeline": "cand-1", "metrics": {"fps": 2.0}},
        })

        result = job.result_dict()
        assert result["final"] is False
        assert result["state"] == OptimizerState.RUNNING.value
        assert result["best"]["fps"] == 2.0
        assert len(result["candidates"]) == 1
        assert job.status_dict()["candidates_evaluated"] == 1
        assert manager._active_job_id == job.job_id

    def test_finished_event_completes_job_and_frees_slot(self):
        manager = OptimizerManager()
        job = _job()
        manager._jobs[job.job_id] = job
        manager._active_job_id = job.job_id

        manager._handle_event(job, {
            "event": "finished",
            "cancelled": False,
            "candidates_evaluated": 2,
            "baseline": {"pipeline": "base", "metrics": {"fps": 1.0}},
            "best": {"pipeline": "best", "metrics": {"fps": 3.0}},
        })

        assert job.state == OptimizerState.COMPLETED
        assert job.final is True
        assert manager._active_job_id is None
        assert job.status_dict()["best_fps"] == 3.0

    def test_finished_after_cancel_request_is_cancelled(self):
        manager = OptimizerManager()
        job = _job()
        job.cancel_requested = True
        manager._jobs[job.job_id] = job
        manager._active_job_id = job.job_id

        manager._handle_event(job, {
            "event": "finished",
            "cancelled": True,
            "candidates_evaluated": 1,
            "baseline": {"pipeline": "base", "metrics": {"fps": 1.0}},
            "best": {"pipeline": "cand-1", "metrics": {"fps": 2.0}},
        })

        assert job.state == OptimizerState.CANCELLED
        assert job.result_dict()["best"]["fps"] == 2.0

    def test_error_event_sets_error_state_with_reason(self):
        manager = OptimizerManager()
        job = _job()
        manager._jobs[job.job_id] = job
        manager._active_job_id = job.job_id

        manager._handle_event(job, {"event": "error", "reason": "device not found"})

        assert job.state == OptimizerState.ERROR
        assert job.message == "device not found"
        assert manager._active_job_id is None

    def test_power_mode_reports_mode_and_power_values(self):
        manager = OptimizerManager()
        job = _job({"mode": "power", "power_metrics_endpoint": "http://metrics:8080/metrics"})
        manager._jobs[job.job_id] = job
        manager._active_job_id = job.job_id

        manager._handle_event(job, {
            "event": "candidate",
            "pipeline": "cand-1",
            "metrics": {"fps": 20.0, "power": 45.0},
            "candidates_evaluated": 1,
            "best": {"pipeline": "cand-1", "metrics": {"fps": 20.0, "power": 45.0}},
        })

        assert job.status_dict()["mode"] == "power"
        assert job.result_dict()["best"]["power"] == 45.0
