# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.telemetry (metric selection) and the manager's finished hook."""

import pytest

from core.pipeline_manager import FpsSample, Lifecycle, PipelineInstance, PipelineManager, PipelineState
from core.telemetry import PipelineMetrics, telemetry_enabled


class _FakeManager:
    def __init__(self, instances=()):
        self.instances = list(instances)

    def list_running(self):
        return [i for i in self.instances if i.state == PipelineState.RUNNING]


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _instance(instance_id="a", **kwargs):
    inst = PipelineInstance(instance_id=instance_id, pipeline_description="fakesrc ! fakesink")
    inst.state = PipelineState.RUNNING
    fps = {key: kwargs.pop(key) for key in ("avg_fps", "frame_fps", "frame_interval") if key in kwargs}
    times = {key: kwargs.pop(key) for key in ("start_time", "first_frame_time", "stop_time") if key in kwargs}
    inst.fps_sample = FpsSample(**fps)
    inst.lifecycle = Lifecycle(**times)
    for key, value in kwargs.items():
        setattr(inst, key, value)
    return inst


def _by_name(observations):
    return {name: (value, attrs) for name, value, attrs in observations}


class TestTelemetryEnabled:
    @pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "on"])
    def test_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_OPEN_TELEMETRY", value)
        assert telemetry_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "", "off"])
    def test_other_values_disable(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_OPEN_TELEMETRY", value)
        assert telemetry_enabled() is False

    def test_unset_disables(self, monkeypatch):
        monkeypatch.delenv("ENABLE_OPEN_TELEMETRY", raising=False)
        assert telemetry_enabled() is False


class TestCollect:
    def test_reports_all_metrics_for_running_instance(self):
        inst = _instance(
            avg_fps=29.5, frame_fps=30.5, frame_interval=1.02, start_time=100.0, first_frame_time=100.75
        )
        metrics = _by_name(PipelineMetrics(_FakeManager([inst]), 30.0).collect())

        assert metrics["fps_per_pipeline"][0] == 29.5
        assert metrics["frame_fps_per_pipeline"][0] == 30.5
        assert metrics["frame_fps_window_seconds"][0] == 1.02
        assert metrics["pipeline_start_timestamp_seconds"][0] == 100.0
        assert metrics["pipeline_first_frame_timestamp_seconds"][0] == 100.75
        assert "pipeline_end_timestamp_seconds" not in metrics

    def test_skips_avg_fps_until_warmup_completes(self):
        inst = _instance(avg_fps=0.0, frame_fps=30.0, frame_interval=1.0)
        metrics = _by_name(PipelineMetrics(_FakeManager([inst]), 30.0).collect())

        assert "fps_per_pipeline" not in metrics
        assert "frame_fps_per_pipeline" in metrics

    def test_skips_window_metrics_before_first_window(self):
        inst = _instance(frame_fps=0.0, frame_interval=0.0)
        metrics = _by_name(PipelineMetrics(_FakeManager([inst]), 30.0).collect())

        assert "frame_fps_per_pipeline" not in metrics
        assert "frame_fps_window_seconds" not in metrics

    def test_reports_only_the_start_time_before_the_first_frame(self):
        inst = _instance(start_time=100.0, first_frame_time=None)
        metrics = _by_name(PipelineMetrics(_FakeManager([inst]), 30.0).collect())

        assert set(metrics) == {"pipeline_start_timestamp_seconds"}

    def test_pipeline_id_is_the_only_attribute(self):
        named = _instance("n", avg_fps=1.0, name="user_defined_pipelines", version="pdd")
        raw = _instance("r", avg_fps=1.0)
        metrics = PipelineMetrics(_FakeManager([named, raw]), 30.0).collect()

        attrs_by_id = {attrs["pipeline_id"]: attrs for _, _, attrs in metrics}
        assert attrs_by_id == {"n": {"pipeline_id": "n"}, "r": {"pipeline_id": "r"}}

    def test_ignores_instances_that_are_not_running(self):
        inst = _instance(avg_fps=10.0)
        inst.state = PipelineState.COMPLETED
        assert PipelineMetrics(_FakeManager([inst]), 30.0).collect() == []


class TestFinishedRetention:
    def test_end_timestamp_is_reported_once_the_instance_has_finished(self):
        clock = _Clock()
        inst = _instance(start_time=100.0, first_frame_time=100.5, stop_time=160.0)
        metrics = PipelineMetrics(_FakeManager([inst]), retention_seconds=30.0, clock=clock)

        inst.state = PipelineState.COMPLETED
        metrics.on_finished(inst)

        reported = _by_name(metrics.collect())
        assert reported["pipeline_start_timestamp_seconds"][0] == 100.0
        assert reported["pipeline_first_frame_timestamp_seconds"][0] == 100.5
        assert reported["pipeline_end_timestamp_seconds"][0] == 160.0

    def test_finished_instance_is_reported_until_retention_expires(self):
        clock = _Clock()
        inst = _instance(avg_fps=25.0)
        manager = _FakeManager([inst])
        metrics = PipelineMetrics(manager, retention_seconds=30.0, clock=clock)

        inst.state = PipelineState.COMPLETED
        metrics.on_finished(inst)

        clock.now = 29.9
        assert _by_name(metrics.collect())["fps_per_pipeline"][0] == 25.0

        clock.now = 30.0
        assert metrics.collect() == []

    def test_finished_instance_without_values_is_not_retained(self):
        clock = _Clock()
        metrics = PipelineMetrics(_FakeManager(), retention_seconds=30.0, clock=clock)

        metrics.on_finished(_instance())

        assert metrics.collect() == []

    def test_restarted_instance_is_not_reported_twice(self):
        clock = _Clock()
        inst = _instance(avg_fps=25.0)
        manager = _FakeManager([inst])
        metrics = PipelineMetrics(manager, retention_seconds=30.0, clock=clock)

        inst.state = PipelineState.COMPLETED
        metrics.on_finished(inst)
        inst.state = PipelineState.RUNNING
        inst.update_fps(avg_fps=26.0)

        observations = metrics.collect()

        assert [(name, value) for name, value, _ in observations] == [("fps_per_pipeline", 26.0)]


class TestLifecycle:
    def test_partial_change_keeps_the_other_times(self):
        inst = _instance(start_time=1.0, first_frame_time=2.0)

        inst.set_lifecycle(stop_time=3.0)

        assert inst.lifecycle == Lifecycle(1.0, 2.0, 3.0)

    def test_none_clears_a_time(self):
        inst = _instance(start_time=1.0, first_frame_time=2.0, stop_time=3.0)

        inst.set_lifecycle(start_time=9.0, first_frame_time=None, stop_time=None)

        assert inst.lifecycle == Lifecycle(9.0, None, None)

    def test_time_properties_read_the_lifecycle(self):
        inst = _instance(start_time=1.0, first_frame_time=2.0, stop_time=3.0)

        assert (inst.start_time, inst.first_frame_time, inst.stop_time) == (1.0, 2.0, 3.0)

    def test_elapsed_time_uses_stop_time_when_set(self):
        inst = _instance(start_time=100.0, stop_time=112.5)

        assert inst.elapsed_time() == 12.5

    def test_firstframe_event_sets_first_frame_time(self):
        inst = _instance("x", start_time=100.0)
        manager = PipelineManager()
        manager._instances["x"] = inst

        manager._handle_event({"instance_id": "x", "event": "firstframe", "first_frame_time": 101.25})

        assert inst.lifecycle == Lifecycle(100.0, 101.25, None)

    def test_stopped_event_sets_stop_time(self):
        inst = _instance("x", start_time=100.0)
        manager = PipelineManager()
        manager._instances["x"] = inst

        manager._handle_event({"instance_id": "x", "event": "stopped"})

        assert inst.start_time == 100.0
        assert inst.stop_time is not None


class TestFpsSample:
    def test_event_with_all_values_replaces_the_sample(self):
        inst = _instance(avg_fps=1.0, frame_fps=2.0, frame_interval=1.0)

        inst.update_fps(avg_fps=10.0, frame_fps=11.0, frame_interval=0.9)

        assert inst.fps_sample == FpsSample(10.0, 11.0, 0.9)

    def test_missing_avg_fps_keeps_the_previous_value(self):
        inst = _instance(avg_fps=10.0, frame_fps=2.0, frame_interval=1.0)

        inst.update_fps(frame_fps=30.0, frame_interval=0.5)

        assert inst.fps_sample == FpsSample(10.0, 30.0, 0.5)

    def test_event_without_a_window_keeps_the_previous_window(self):
        inst = _instance(avg_fps=10.0, frame_fps=30.0, frame_interval=1.0)

        inst.update_fps(avg_fps=11.0)

        assert inst.fps_sample == FpsSample(11.0, 30.0, 1.0)

    def test_half_a_window_is_ignored(self):
        inst = _instance(avg_fps=10.0, frame_fps=30.0, frame_interval=1.0)

        inst.update_fps(frame_fps=99.0)
        inst.update_fps(frame_interval=9.0)

        assert inst.fps_sample == FpsSample(10.0, 30.0, 1.0)

    def test_fps_event_updates_sample_in_one_assignment(self):
        inst = _instance("x")
        manager = PipelineManager()
        manager._instances["x"] = inst
        before = inst.fps_sample

        manager._handle_event(
            {"instance_id": "x", "event": "fps", "avg_fps": 5.0, "last_fps": 6.0, "frame_interval": 1.1}
        )

        assert inst.fps_sample is not before
        assert inst.fps_sample == FpsSample(5.0, 6.0, 1.1)

    def test_status_dict_is_built_from_one_sample(self):
        inst = _instance(avg_fps=5.0, frame_fps=6.0, frame_interval=1.1)

        status = inst.to_status_dict()

        assert (status["avg_fps"], status["frame_fps"], status["frame_interval"]) == (5.0, 6.0, 1.1)


class TestManagerFinishedListener:
    def _manager_with(self, inst):
        manager = PipelineManager()
        manager._instances[inst.instance_id] = inst
        return manager

    def test_listener_called_on_stopped_event(self):
        inst = _instance("x", avg_fps=12.0)
        manager = self._manager_with(inst)
        seen = []
        manager.set_finished_listener(seen.append)

        manager._handle_event({"instance_id": "x", "event": "stopped"})

        assert seen == [inst]
        assert inst.state == PipelineState.COMPLETED

    def test_listener_failure_does_not_break_event_handling(self):
        inst = _instance("x")
        manager = self._manager_with(inst)

        def boom(_instance):
            raise RuntimeError("exporter down")

        manager.set_finished_listener(boom)

        manager._handle_event({"instance_id": "x", "event": "stopped"})

        assert inst.state == PipelineState.COMPLETED

    def test_listener_not_called_for_other_events(self):
        inst = _instance("x")
        manager = self._manager_with(inst)
        seen = []
        manager.set_finished_listener(seen.append)

        manager._handle_event({"instance_id": "x", "event": "fps", "avg_fps": 5.0})

        assert seen == []
