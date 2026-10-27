# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry metrics export for DLSPS 2.0.

Pushes per-pipeline FPS metrics to an OTLP/HTTP collector. Values are read
from the in-memory ``PipelineInstance`` state that ``PipelineManager`` keeps
up to date from the worker's ``fps`` events, so nothing polls the REST API.

Enable with ``ENABLE_OPEN_TELEMETRY=true``. The collector location and the
export interval come from ``OTEL_COLLECTOR_HOST``, ``OTEL_COLLECTOR_PORT`` and
``OTEL_EXPORT_INTERVAL_MILLIS``, matching DLSPS 1.0.
"""

import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Tuple

if TYPE_CHECKING:
    from core.pipeline_manager import PipelineInstance, PipelineManager

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}

# (metric name, unit, description). fps_per_pipeline keeps its DLSPS 1.0 name.
_GAUGES = (
    ("fps_per_pipeline", "", "Average FPS of a pipeline instance, excluding warmup frames"),
    ("frame_fps_per_pipeline", "", "FPS of a pipeline instance over its latest measurement window"),
    ("frame_fps_window_seconds", "s", "Length of the window frame_fps_per_pipeline was measured over"),
    ("pipeline_running", "", "1 while the pipeline instance is RUNNING, 0 once it is no longer running"),
    ("pipeline_start_timestamp_seconds", "s", "Unix time at which the pipeline instance started running"),
    ("pipeline_first_frame_timestamp_seconds", "s", "Unix time at which the pipeline instance received its first frame"),
    ("pipeline_end_timestamp_seconds", "s", "Unix time at which the pipeline instance stopped"),
)

# (metric name, value, attributes)
Observation = Tuple[str, float, Dict[str, str]]


def telemetry_enabled() -> bool:
    return os.environ.get("ENABLE_OPEN_TELEMETRY", "false").strip().lower() in _TRUE_VALUES


def _observations_for(instance: "PipelineInstance") -> List[Observation]:
    from core.pipeline_manager import PipelineState

    attrs = {"pipeline_id": instance.instance_id}

    observations: List[Observation] = [
        ("pipeline_running", 1.0 if instance.state == PipelineState.RUNNING else 0.0, attrs),
    ]
    # One read, so the values below always come from the same fps event.
    fps = instance.fps_sample
    # avg_fps stays 0.0 until warmup completes, and a real average is always > 0.
    if fps.avg_fps > 0:
        observations.append(("fps_per_pipeline", fps.avg_fps, attrs))
    # The worker only reports a window once frames arrived in it.
    if fps.frame_interval > 0:
        observations.append(("frame_fps_per_pipeline", fps.frame_fps, attrs))
        observations.append(("frame_fps_window_seconds", fps.frame_interval, attrs))
    # One read, so the three times below always belong to the same run.
    lifecycle = instance.lifecycle
    if lifecycle.start_time is not None:
        observations.append(("pipeline_start_timestamp_seconds", lifecycle.start_time, attrs))
    if lifecycle.first_frame_time is not None:
        observations.append(("pipeline_first_frame_timestamp_seconds", lifecycle.first_frame_time, attrs))
    if lifecycle.stop_time is not None:
        observations.append(("pipeline_end_timestamp_seconds", lifecycle.stop_time, attrs))
    return observations


class PipelineMetrics:
    """Turns pipeline state into metric observations; independent of the OTel SDK.

    Running instances are read live. A finished instance keeps being reported
    for ``retention_seconds`` so its final values reach the backend even when
    it ran for less than one export interval.
    """

    def __init__(
        self,
        manager: "PipelineManager",
        retention_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._manager = manager
        self._retention = retention_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._finished: Dict[str, Tuple[float, List[Observation]]] = {}

    def on_finished(self, instance: "PipelineInstance") -> None:
        # Rolling-window rates would look live if re-emitted after the run stopped.
        observations = [
            obs for obs in _observations_for(instance)
            if obs[0] not in ("frame_fps_per_pipeline", "frame_fps_window_seconds")
        ]
        if not observations:
            return
        with self._lock:
            self._finished[instance.instance_id] = (self._clock() + self._retention, observations)

    def collect(self) -> List[Observation]:
        observations: List[Observation] = []
        running = set()
        for instance in self._manager.list_running():
            running.add(instance.instance_id)
            observations.extend(_observations_for(instance))

        now = self._clock()
        with self._lock:
            # A restarted instance is live again, so its old snapshot would duplicate the series.
            stale = [pid for pid, (expires, _) in self._finished.items() if expires <= now or pid in running]
            for pid in stale:
                del self._finished[pid]
            for _, finished in self._finished.values():
                observations.extend(finished)
        return observations


def _json_exporter_class(base):
    """Subclass of the OTLP/HTTP metric exporter that posts OTLP JSON instead of protobuf."""
    from google.protobuf.json_format import MessageToJson
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest

    class JsonOTLPMetricExporter(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._session.headers["Content-Type"] = "application/json"

        # The base class only exposes serialized protobuf bytes, so re-encode them as OTLP JSON.
        def _export(self, serialized_data: bytes):
            request = ExportMetricsServiceRequest()
            request.ParseFromString(serialized_data)
            return super()._export(MessageToJson(request).encode("utf-8"))

    return JsonOTLPMetricExporter


class OpenTelemetryExporter:
    """Exports PipelineMetrics to an OTLP/HTTP collector on a fixed interval."""

    def __init__(self, manager: "PipelineManager") -> None:
        # Imported here so the SDK is only needed when export is enabled.
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.metrics import Observation as OtelObservation
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource

        service_name = os.environ.get("SERVICE_NAME", "dlstreamer-pipeline-server")
        host = os.environ.get("OTEL_COLLECTOR_HOST", "otel-collector")
        port = int(os.environ.get("OTEL_COLLECTOR_PORT", "4318"))
        path = os.environ.get("OTEL_COLLECTOR_PATH", "/v1/metrics")
        interval_ms = int(os.environ.get("OTEL_EXPORT_INTERVAL_MILLIS", "10000"))
        if interval_ms <= 0:
            raise ValueError("OTEL_EXPORT_INTERVAL_MILLIS must be positive")
        endpoint = f"http://{host}:{port}{path}"

        protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").strip().lower()
        if protocol not in ("http/protobuf", "http/json"):
            raise ValueError("OTEL_EXPORTER_OTLP_PROTOCOL must be 'http/protobuf' or 'http/json'")
        exporter_cls = _json_exporter_class(OTLPMetricExporter) if protocol == "http/json" else OTLPMetricExporter

        reader = PeriodicExportingMetricReader(
            exporter_cls(endpoint=endpoint),
            export_interval_millis=interval_ms,
        )
        self._provider = MeterProvider(
            resource=Resource(attributes={"service.name": service_name}),
            metric_readers=[reader],
        )

        self._metrics = PipelineMetrics(manager, retention_seconds=max(2 * interval_ms / 1000.0, 30.0))
        manager.set_finished_listener(self._metrics.on_finished)

        def make_callback(metric_name: str):
            def callback(_options):
                return [
                    OtelObservation(value, attrs)
                    for name, value, attrs in self._metrics.collect()
                    if name == metric_name
                ]

            return callback

        meter = self._provider.get_meter("dlsps2.pipelines")
        for name, unit, description in _GAUGES:
            meter.create_observable_gauge(
                name,
                callbacks=[make_callback(name)],
                unit=unit,
                description=description,
            )

        logger.info(
            "OpenTelemetry metrics export enabled: %s every %d ms (service.name=%s)",
            endpoint,
            interval_ms,
            service_name,
        )

    def shutdown(self) -> None:
        """Flush a final export and stop the background reader."""
        self._provider.shutdown()
