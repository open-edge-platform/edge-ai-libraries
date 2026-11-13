# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.telemetry: metric selection, the manager's finished hook, and
structured DL Streamer metrics on the OTel path."""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core.pipeline_manager import FpsSample, Lifecycle, PipelineInstance, PipelineManager, PipelineState
from core.telemetry import PipelineMetrics, _CollectionSnapshot, _FlushOnFinish, telemetry_enabled


class _FakeManager:
    def __init__(self, instances=()):
        self.instances = list(instances)
        self.finished_listener = None
        self.metric_listener = None

    def list_running(self):
        return [i for i in self.instances if i.state in (PipelineState.RUNNING, PipelineState.STOPPING)]

    def set_finished_listener(self, listener):
        self.finished_listener = listener

    def set_metric_listener(self, listener):
        self.metric_listener = listener


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


def _window_event(count, sum_ms, min_ms, max_ms, source="src", sink="sink"):
    return {
        "event": "metric",
        "kind": "latency-window",
        "element": sink,
        "fields": {
            "pipeline": "ignored",
            "source": source,
            "sink": sink,
            "window_ms": 1000.0,
            "count": count,
            "sum_ms": sum_ms,
            "min_ms": min_ms,
            "max_ms": max_ms,
        },
    }


def _distribution_event(count, sum_ms, min_ms, max_ms, sum_sq_ms, bounds, counts):
    event = _window_event(count, sum_ms, min_ms, max_ms)
    event["fields"].update(sum_sq_ms=sum_sq_ms, bucket_bounds_ms=bounds, bucket_counts=counts)
    return event


def _genai_event(ttft_ms, tpot_ms, element="gvagenai0"):
    return {
        "event": "metric",
        "kind": "genai-request",
        "element": element,
        "fields": {
            "frames": 1,
            "ttft_ms": ttft_ms,
            "tpot_ms": tpot_ms,
            "generate_duration_ms": ttft_ms + 10 * tpot_ms,
            "inference_duration_ms": ttft_ms,
            "prepare_embeddings_duration_ms": 1.0,
            "num_input_tokens": 100,
            "num_generated_tokens": 11,
        },
    }


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

        assert set(metrics) == {"pipeline_running", "pipeline_start_timestamp_seconds"}
        assert metrics["pipeline_running"][0] == 1.0

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

    def test_stopping_instance_still_reports_running(self):
        inst = _instance(avg_fps=10.0)
        inst.state = PipelineState.STOPPING
        metrics = _by_name(PipelineMetrics(_FakeManager([inst]), 30.0).collect())

        assert metrics["pipeline_running"][0] == 1.0


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

    def test_finished_instance_without_values_reports_only_that_it_stopped(self):
        clock = _Clock()
        metrics = PipelineMetrics(_FakeManager(), retention_seconds=30.0, clock=clock)
        inst = _instance()
        inst.state = PipelineState.ERROR

        metrics.on_finished(inst)

        # pipeline_running drops to 0, so a backend does not keep the last 1 for a stopped pipeline.
        assert metrics.collect() == [("pipeline_running", 0.0, {"pipeline_id": "a"})]
        clock.now = 30.0
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

        assert [(name, value) for name, value, _ in observations] == [
            ("pipeline_running", 1.0),
            ("fps_per_pipeline", 26.0),
        ]


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


def _running(instance_id):
    return PipelineInstance(instance_id=instance_id, pipeline_description="x", state=PipelineState.RUNNING)


def _latency(observations):
    return {
        (name, attrs["pipeline_id"], attrs["source"]): value
        for name, value, attrs in observations
        if name.startswith("pipeline_latency_")
    }


class TestPipelineMetricsLatency:
    def test_windows_are_merged_until_collect_and_then_drained(self):
        a, b = _running("a"), _running("b")
        metrics = PipelineMetrics(_FakeManager([a, b]), retention_seconds=30)
        metrics.on_metric(a, _window_event(2, 20.0, 8.0, 12.0))
        metrics.on_metric(a, _window_event(2, 40.0, 15.0, 25.0))
        metrics.on_metric(b, _window_event(1, 300.0, 300.0, 300.0))

        values = _latency(metrics.collect())
        assert values[("pipeline_latency_avg", "a", "src")] == 15.0
        assert values[("pipeline_latency_min", "a", "src")] == 8.0
        assert values[("pipeline_latency_max", "a", "src")] == 25.0
        assert values[("pipeline_latency_frames", "a", "src")] == 4.0
        assert values[("pipeline_latency_avg", "b", "src")] == 300.0
        assert _latency(metrics.collect()) == {}

    def test_distribution_gauges_come_from_the_merged_period(self):
        a = _running("a")
        metrics = PipelineMetrics(_FakeManager([a]), retention_seconds=30)
        # frames 1, 2, 3 | 4, 10 with buckets <=2, (2, 5], >5
        metrics.on_metric(a, _distribution_event(3, 6.0, 1.0, 3.0, 14.0, [2.0, 5.0], [2, 1, 0]))
        metrics.on_metric(a, _distribution_event(2, 14.0, 4.0, 10.0, 116.0, [2.0, 5.0], [0, 1, 1]))
        values = _latency(metrics.collect())
        assert values[("pipeline_latency_avg", "a", "src")] == 4.0
        assert values[("pipeline_latency_stddev", "a", "src")] == pytest.approx(10.0 ** 0.5)
        assert values[("pipeline_latency_p50", "a", "src")] == pytest.approx(2.75)
        assert values[("pipeline_latency_p95", "a", "src")] == pytest.approx(8.75)
        assert values[("pipeline_latency_p99", "a", "src")] == pytest.approx(9.75)

    def test_period_mixing_an_older_tracer_window_exports_no_distribution(self):
        a = _running("a")
        metrics = PipelineMetrics(_FakeManager([a]), retention_seconds=30)
        metrics.on_metric(a, _distribution_event(3, 6.0, 1.0, 3.0, 14.0, [2.0, 5.0], [2, 1, 0]))
        metrics.on_metric(a, _window_event(1, 10.0, 10.0, 10.0))
        values = _latency(metrics.collect())
        assert values[("pipeline_latency_avg", "a", "src")] == 4.0
        assert not any(name in ("pipeline_latency_stddev", "pipeline_latency_p50") for name, _a, _s in values)

    def test_genai_events_are_not_latency(self):
        a = _running("a")
        metrics = PipelineMetrics(_FakeManager([a]), retention_seconds=30)
        metrics.on_metric(a, _genai_event(100.0, 20.0))
        assert _latency(metrics.collect()) == {}

    def test_finished_instance_reports_its_last_windows_once(self):
        a = _running("a")
        manager = _FakeManager([a])
        metrics = PipelineMetrics(manager, retention_seconds=30)
        metrics.on_metric(a, _window_event(1, 5.0, 5.0, 5.0))
        a.state = PipelineState.COMPLETED
        metrics.on_finished(a)
        assert _latency(metrics.collect())[("pipeline_latency_avg", "a", "src")] == 5.0
        assert _latency(metrics.collect()) == {}


class TestCollectionSnapshot:
    """Every gauge of one collection shares one collect(); each collection gets its own."""

    @staticmethod
    def _counting_collect(calls):
        def collect():
            calls.append(1)
            return [("a", float(len(calls)), {}), ("b", float(len(calls)), {})]

        return collect

    def test_gauges_of_one_collection_share_one_collect(self):
        calls = []
        snapshot = _CollectionSnapshot(self._counting_collect(calls))
        assert snapshot.get("a") == [("a", 1.0, {})]
        assert snapshot.get("b") == [("b", 1.0, {})]
        assert snapshot.get("absent") == []
        assert len(calls) == 1

    def test_back_to_back_collections_each_collect_once(self):
        calls = []
        snapshot = _CollectionSnapshot(self._counting_collect(calls))
        snapshot.get("a")
        snapshot.get("b")
        # No time passes: the second request for "a" alone starts the next collection.
        assert snapshot.get("a") == [("a", 2.0, {})]
        assert snapshot.get("b") == [("b", 2.0, {})]
        assert len(calls) == 2

    def test_windows_are_drained_exactly_once_across_collections(self):
        a = _running("a")
        metrics = PipelineMetrics(_FakeManager([a]), retention_seconds=30)
        snapshot = _CollectionSnapshot(metrics.collect)
        metrics.on_metric(a, _window_event(1, 5.0, 5.0, 5.0))
        assert [v for _n, v, _a in snapshot.get("pipeline_latency_avg")] == [5.0]
        assert [v for _n, v, _a in snapshot.get("pipeline_latency_max")] == [5.0]
        # A window arriving between two collections belongs to the second one only.
        metrics.on_metric(a, _window_event(1, 9.0, 9.0, 9.0))
        assert [v for _n, v, _a in snapshot.get("pipeline_latency_avg")] == [9.0]
        assert [v for _n, v, _a in snapshot.get("pipeline_latency_max")] == [9.0]
        assert snapshot.get("pipeline_latency_avg") == []


class TestManagerDispatch:
    def _manager_with(self, instance):
        manager = PipelineManager()
        manager._instances[instance.instance_id] = instance
        return manager

    def test_metric_event_reaches_listener_with_its_instance(self):
        a = _running("a")
        manager = self._manager_with(a)
        received = []
        manager.set_metric_listener(lambda inst, event: received.append((inst, event)))
        event = {"instance_id": "a", **_window_event(1, 1.0, 1.0, 1.0)}
        manager._handle_event(event)
        assert received == [(a, event)]

    def test_without_listener_metric_events_are_dropped(self):
        manager = self._manager_with(_running("a"))
        manager._handle_event({"instance_id": "a", **_window_event(1, 1.0, 1.0, 1.0)})

    def test_unknown_instance_and_failing_listener_do_not_raise(self):
        manager = self._manager_with(_running("a"))
        received = []
        manager.set_metric_listener(lambda inst, event: received.append(inst))
        manager._handle_event({"instance_id": "nope", **_window_event(1, 1.0, 1.0, 1.0)})
        assert received == []

        def boom(_inst, _event):
            raise RuntimeError("listener bug")

        manager.set_metric_listener(boom)
        manager._handle_event({"instance_id": "a", **_window_event(1, 1.0, 1.0, 1.0)})

    def test_final_metric_events_reach_the_listener_before_finished(self):
        a = _running("a")
        manager = self._manager_with(a)
        order = []
        manager.set_metric_listener(lambda inst, event: order.append("metric"))
        manager.set_finished_listener(lambda inst: order.append("finished"))
        # The worker forwards the tracer's EOS window before "eos", and "stopped" after both.
        for event in ({"instance_id": "a", **_window_event(1, 1.0, 1.0, 1.0)},
                      {"instance_id": "a", "event": "eos"},
                      {"instance_id": "a", "event": "stopped"}):
            manager._handle_event(event)
        assert order == ["metric", "finished"]

    def test_without_telemetry_finishing_is_a_no_op(self, monkeypatch):
        monkeypatch.delenv("ENABLE_OPEN_TELEMETRY", raising=False)
        assert not telemetry_enabled()
        a = _running("a")
        manager = self._manager_with(a)
        manager._handle_event({"instance_id": "a", "event": "stopped"})
        assert a.state == PipelineState.COMPLETED


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


class TestFlushOnFinish:
    def test_one_request_flushes_once_with_a_bounded_timeout(self):
        calls = []
        flusher = _FlushOnFinish(lambda **kwargs: calls.append(kwargs) or True, timeout_millis=1234)
        flusher.request()
        assert _wait_for(lambda: calls)
        flusher.stop()
        assert calls == [{"timeout_millis": 1234}]

    def test_requests_during_a_flush_cause_exactly_one_more(self):
        release = threading.Event()
        calls = []

        def slow_flush(**_kwargs):
            calls.append(1)
            release.wait(5)

        flusher = _FlushOnFinish(slow_flush, timeout_millis=1000)
        flusher.request()
        assert _wait_for(lambda: calls)
        for _ in range(3):
            flusher.request()
        release.set()
        assert _wait_for(lambda: len(calls) == 2)
        flusher.stop()
        assert len(calls) == 2

    def test_flush_errors_are_logged_not_raised(self, caplog):
        calls = []

        def failing_flush(**_kwargs):
            calls.append(1)
            raise RuntimeError("collector down")

        flusher = _FlushOnFinish(failing_flush, timeout_millis=1000)
        with caplog.at_level(logging.WARNING, logger="core.telemetry"):
            flusher.request()
            assert _wait_for(lambda: len(calls) == 1)
            # The thread survives the error and keeps serving requests.
            flusher.request()
            assert _wait_for(lambda: len(calls) == 2)
            flusher.stop()
        assert any("flush" in r.getMessage() for r in caplog.records)

    def test_stop_without_requests_does_not_flush(self):
        calls = []
        flusher = _FlushOnFinish(lambda **_kwargs: calls.append(1), timeout_millis=1000)
        flusher.stop()
        assert calls == []


class _Collector(BaseHTTPRequestHandler):
    bodies: list = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        _Collector.bodies.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args):
        pass


@pytest.fixture
def otlp_collector(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.metrics")
    _Collector.bodies = []
    server = HTTPServer(("127.0.0.1", 0), _Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OTEL_COLLECTOR_HOST", "127.0.0.1")
    monkeypatch.setenv("OTEL_COLLECTOR_PORT", str(server.server_port))
    monkeypatch.setenv("OTEL_COLLECTOR_PATH", "/api/v1/metrics/otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/json")
    monkeypatch.setenv("OTEL_EXPORT_INTERVAL_MILLIS", "600000")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    yield _Collector.bodies
    server.shutdown()


def _points(bodies):
    """(metric name, kind, attributes, data point) for every exported data point."""
    for body in bodies:
        for rm in body["resourceMetrics"]:
            for sm in rm["scopeMetrics"]:
                for metric in sm["metrics"]:
                    for kind in ("gauge", "histogram", "sum"):
                        if kind in metric:
                            for dp in metric[kind]["dataPoints"]:
                                attrs = {a["key"]: a["value"]["stringValue"] for a in dp.get("attributes", [])}
                                yield metric["name"], kind, metric[kind], attrs, dp


class TestOpenTelemetryExport:
    def test_latency_and_genai_reach_otlp_with_identity(self, otlp_collector):
        from core.telemetry import OpenTelemetryExporter

        a, b = _running("job-a"), _running("job-b")
        manager = _FakeManager([a, b])
        exporter = OpenTelemetryExporter(manager)
        manager.metric_listener(a, _window_event(3, 30.0, 5.0, 15.0))
        manager.metric_listener(b, _window_event(1, 80.0, 80.0, 80.0))
        manager.metric_listener(a, _genai_event(100.0, 20.0))
        manager.metric_listener(a, _genai_event(300.0, 40.0))
        manager.metric_listener(b, _genai_event(1000.0, 50.0, element="gvagenai1"))
        exporter.shutdown()

        points = list(_points(otlp_collector))
        latency = {(n, attrs["pipeline_id"]): dp for n, kind, _m, attrs, dp in points if kind == "gauge"}
        assert latency[("pipeline_latency_avg", "job-a")]["asDouble"] == 10.0
        assert latency[("pipeline_latency_frames", "job-a")]["asDouble"] == 3.0
        assert latency[("pipeline_latency_max", "job-b")]["asDouble"] == 80.0
        gauge_attrs = next(attrs for n, kind, _m, attrs, _dp in points if n == "pipeline_latency_avg")
        assert set(gauge_attrs) == {"pipeline_id", "source", "sink"}

        ttft = {
            attrs["pipeline_id"]: (metric, attrs, dp)
            for n, kind, metric, attrs, dp in points
            if n == "genai_ttft" and kind == "histogram"
        }
        metric, attrs, dp = ttft["job-a"]
        assert metric["aggregationTemporality"] == "AGGREGATION_TEMPORALITY_DELTA"
        assert attrs == {"pipeline_id": "job-a", "element": "gvagenai0"}
        assert (int(dp["count"]), dp["sum"], dp["min"], dp["max"]) == (2, 400.0, 100.0, 300.0)
        assert ttft["job-b"][1]["element"] == "gvagenai1"
        assert int(ttft["job-b"][2]["count"]) == 1

    def test_token_histograms_use_token_buckets(self, otlp_collector):
        from core.metrics import TOKEN_BUCKETS
        from core.telemetry import OpenTelemetryExporter

        a = _running("job-a")
        manager = _FakeManager([a])
        exporter = OpenTelemetryExporter(manager)
        manager.metric_listener(a, _genai_event(100.0, 20.0))
        exporter.shutdown()

        metrics = {n: (metric, dp) for n, kind, metric, _attrs, dp in _points(otlp_collector) if kind == "histogram"}
        assert set(metrics) == {
            "genai_ttft", "genai_tpot", "genai_generate_duration", "genai_inference_duration",
            "genai_prepare_embeddings_duration", "genai_input_tokens", "genai_generated_tokens",
        }
        assert [float(b) for b in metrics["genai_input_tokens"][1]["explicitBounds"]] == list(TOKEN_BUCKETS)
        assert [float(b) for b in metrics["genai_ttft"][1]["explicitBounds"]] != list(TOKEN_BUCKETS)

    def test_back_to_back_flushes_export_each_window_once(self, otlp_collector):
        from core.telemetry import OpenTelemetryExporter

        a = _running("job-a")
        manager = _FakeManager([a])
        exporter = OpenTelemetryExporter(manager)
        manager.metric_listener(a, _window_event(1, 5.0, 5.0, 5.0))
        exporter._provider.force_flush()
        # Arrives right after a collection: the next flush must carry it, not a stale snapshot.
        manager.metric_listener(a, _window_event(1, 9.0, 9.0, 9.0))
        exporter._provider.force_flush()
        exporter.shutdown()

        per_export = [
            [dp["asDouble"] for n, _k, _m, _attrs, dp in _points([body]) if n == "pipeline_latency_avg"]
            for body in otlp_collector
        ]
        assert per_export == [[5.0], [9.0], []]

    def test_latency_gauge_units(self, otlp_collector):
        from core.telemetry import OpenTelemetryExporter

        a = _running("job-a")
        manager = _FakeManager([a])
        exporter = OpenTelemetryExporter(manager)
        manager.metric_listener(a, _distribution_event(2, 6.0, 2.0, 4.0, 20.0, [2.0, 5.0], [1, 1, 0]))
        exporter.shutdown()

        units = {}
        for body in otlp_collector:
            for rm in body["resourceMetrics"]:
                for sm in rm["scopeMetrics"]:
                    for metric in sm["metrics"]:
                        units[metric["name"]] = metric.get("unit", "")
        assert {name: units[name] for name in units if name.startswith("pipeline_latency_")} == {
            "pipeline_latency_avg": "ms",
            "pipeline_latency_min": "ms",
            "pipeline_latency_max": "ms",
            "pipeline_latency_window": "ms",
            "pipeline_latency_frames": "",
            "pipeline_latency_stddev": "ms",
            "pipeline_latency_p50": "ms",
            "pipeline_latency_p95": "ms",
            "pipeline_latency_p99": "ms",
        }

    def test_finishing_an_instance_exports_once_without_waiting_for_the_interval(self, otlp_collector):
        from core.telemetry import OpenTelemetryExporter

        a = _running("job-a")
        manager = _FakeManager([a])
        exporter = OpenTelemetryExporter(manager)
        flushes = []
        force_flush = exporter._flusher._flush
        exporter._flusher._flush = lambda **kwargs: flushes.append(kwargs) or force_flush(**kwargs)

        manager.metric_listener(a, _window_event(2, 6.0, 2.0, 4.0))
        a.state = PipelineState.COMPLETED
        a.set_lifecycle(stop_time=1234.5)
        manager.finished_listener(a)

        assert _wait_for(lambda: otlp_collector)
        exported = {n: dp for n, _kind, _m, attrs, dp in _points(otlp_collector) if attrs.get("pipeline_id") == "job-a"}
        assert exported["pipeline_latency_avg"]["asDouble"] == 3.0
        assert exported["pipeline_running"]["asDouble"] == 0.0
        assert exported["pipeline_end_timestamp_seconds"]["asDouble"] == 1234.5
        exporter.shutdown()
        assert len(flushes) == 1
