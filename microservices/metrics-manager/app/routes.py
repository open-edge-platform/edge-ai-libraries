# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
REST API routes for metrics ingestion and health checks.

Provides multiple endpoints for pushing custom metrics in various formats:
- JSON format (recommended)
- InfluxDB Line Protocol
- OpenTelemetry format
- Simple single-value format
"""

import re
import time

import aiohttp
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client.parser import text_string_to_metric_families

from .logging_config import get_logger
from .metrics import get_service_metrics
from .models import (
    InfluxLineProtocolInput,
    MetricsBatch,
    OpenTelemetryMetric,
    SimpleMetric,
)
from .responses import (
    DetailedHealthResponse,
    HealthResponse,
    MetricData,
    MetricNamesResponse,
    MetricsAcceptedResponse,
    MetricsClearedResponse,
    MetricsLatestResponse,
    MetricsListResponse,
)
from .settings import get_settings
from .store import get_metrics_store

router = APIRouter(tags=["metrics"])
logger = get_logger("routes")


# ==============================================================================
# Health Check Endpoints
# ==============================================================================


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.

    Returns:
        HealthResponse with status "healthy"
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.service_version,
        uptime_seconds=get_service_metrics().uptime_seconds,
        checks={"store": True},
    )


@router.get("/api/health", response_model=DetailedHealthResponse)
async def api_health_check() -> DetailedHealthResponse:
    """
    Detailed health check with service status.

    Returns:
        DetailedHealthResponse with metrics-store stats and uptime.
    """
    settings = get_settings()
    store = get_metrics_store()
    store_stats = await store.get_stats()

    return DetailedHealthResponse(
        status="healthy",
        version=settings.service_version,
        uptime_seconds=get_service_metrics().uptime_seconds,
        checks={"store": True},
        metrics_store=store_stats,
    )


# ==============================================================================
# Metrics Ingestion Endpoints
# ==============================================================================


@router.post("/api/v1/metrics", status_code=status.HTTP_202_ACCEPTED)
async def push_metrics(batch: MetricsBatch) -> MetricsAcceptedResponse:
    """
    Push a batch of metrics in JSON format.

    This is the primary endpoint for pushing custom metrics. Metrics are stored
    in memory and asynchronously persisted to Telegraf's HTTP listener
    (:8186/write) so they appear in the Prometheus endpoint and the SSE stream
    on the next poll cycle.

    Request Body:
        ```json
        {
            "metrics": [
                {
                    "name": "custom_fps",
                    "fields": {"value": 29.97},
                    "tags": {"pipeline": "detection"},
                    "timestamp": 1704067200000000000
                }
            ]
        }
        ```

    Returns:
        {"accepted": int, "message": str}
    """
    store = get_metrics_store()
    count = await store.add_metrics(batch.metrics)

    # Track metrics
    get_service_metrics().record_metrics_received(count, source="json")

    # Per-request accept logs are emitted at DEBUG: under load (e.g. ViPPET
    # pushing fps every second) they would dominate the log stream. Counts
    # are preserved in service_metrics for observability.
    logger.debug("Accepted metrics via JSON API", extra={"count": count})
    return MetricsAcceptedResponse(accepted=count, message=f"Accepted {count} metrics")


@router.post("/api/v1/metrics/simple", status_code=status.HTTP_202_ACCEPTED)
async def push_simple_metric(metric: SimpleMetric) -> MetricsAcceptedResponse:
    """
    Push a single metric with simplified format.

    This endpoint provides the easiest way to push a custom metric when you
    just have a name and value.

    Request Body:
        ```json
        {
            "name": "fps",
            "value": 29.97,
            "tags": {"source": "camera1"}
        }
        ```

    Returns:
        {"accepted": 1, "message": str}
    """
    store = get_metrics_store()
    full_metric = metric.to_metric()
    await store.add_metric(full_metric)

    # Track metrics
    get_service_metrics().record_metrics_received(1, source="simple")

    logger.debug(
        "Accepted simple metric",
        extra={"metric_name": metric.name, "metric_value": metric.value},
    )
    return MetricsAcceptedResponse(accepted=1, message=f"Accepted metric '{metric.name}'")


@router.post("/api/v1/metrics/influx", status_code=status.HTTP_202_ACCEPTED)
async def push_influx_metrics(
    request: Request,
) -> MetricsAcceptedResponse:
    """
    Push metrics in InfluxDB Line Protocol format.

    Accepts plain text body with one or more lines in InfluxDB Line Protocol format.

    Request Body (text/plain):
        ```
        cpu_usage,host=server1,cpu=cpu0 usage=45.2 1704067200000000000
        memory,host=server1 used_percent=67.5 1704067200000000000
        ```

    Returns:
        {"accepted": int, "message": str}
    """
    body = await request.body()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UTF-8 encoding in request body: {e}",
        ) from e
    lines = text.strip().split("\n")

    metrics = []
    errors = []
    for i, line in enumerate(lines):
        metric = InfluxLineProtocolInput.parse_line(line)
        if metric:
            metrics.append(metric)
        elif line.strip():
            errors.append(f"Line {i + 1}: Failed to parse")
            get_service_metrics().record_error("parse")

    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid metrics found in input",
        )

    store = get_metrics_store()
    count = await store.add_metrics(metrics)

    # Track metrics
    get_service_metrics().record_metrics_received(count, source="influx")

    logger.debug(
        "Accepted metrics via InfluxDB Line Protocol", extra={"count": count}
    )
    return MetricsAcceptedResponse(
        accepted=count, message=f"Accepted {count} metrics", errors=errors
    )


@router.post("/api/v1/metrics/otlp", status_code=status.HTTP_202_ACCEPTED)
async def push_otlp_metrics(otlp_data: OpenTelemetryMetric) -> MetricsAcceptedResponse:
    """
    Push metrics in OpenTelemetry (OTLP) JSON format.

    Accepts metrics in the standard OTLP JSON format as used by OpenTelemetry
    exporters.

    Request Body:
        ```json
        {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "my-service"}}
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "http_requests_total",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "asDouble": 100,
                                                "timeUnixNano": "1704067200000000000"
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        ```

    Returns:
        {"accepted": int, "message": str}
    """
    metrics = otlp_data.to_metrics()

    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid metrics found in OTLP input",
        )

    store = get_metrics_store()
    count = await store.add_metrics(metrics)

    # Track metrics
    get_service_metrics().record_metrics_received(count, source="otlp")

    logger.debug("Accepted metrics via OTLP", extra={"count": count})
    return MetricsAcceptedResponse(accepted=count, message=f"Accepted {count} metrics")


# ==============================================================================
# Metrics Query Endpoints
# ==============================================================================


@router.get("/api/v1/metrics", response_model=MetricsListResponse)
async def get_metrics(
    name: str | None = Query(default=None, description="Filter by metric name"),
) -> MetricsListResponse:
    """
    Get stored custom metrics.

    Args:
        name: Optional metric name filter.

    Returns:
        MetricsListResponse with list of matching metrics and count.
    """
    store = get_metrics_store()
    metrics = await store.get_metrics(name)
    metric_data = [MetricData(**m.to_telegraf_json()) for m in metrics]
    return MetricsListResponse(metrics=metric_data, count=len(metric_data))


async def _fetch_prometheus_metrics(base_url: str) -> dict[str, MetricData]:
    """Fetch and parse metrics from a Prometheus text-format endpoint."""
    result: dict[str, MetricData] = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/metrics",
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as resp:
                if resp.status != 200:
                    return result
                text = await resp.text()
    except Exception as e:
        logger.warning(
            "Failed to fetch Prometheus metrics",
            extra={"url": base_url, "error": str(e)},
        )
        return result

    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            labels = dict(sample.labels)
            if labels:
                sorted_labels = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
                key = f"{sample.name}{{{sorted_labels}}}"
            else:
                key = sample.name
            ts_ns = int(sample.timestamp * 1e9) if sample.timestamp else int(time.time() * 1e9)
            result[key] = MetricData(
                name=sample.name,
                tags=labels,
                fields={"value": sample.value},
                timestamp=ts_ns,
            )

    return result


@router.get("/api/v1/metrics/latest", response_model=MetricsLatestResponse)
async def get_latest_metrics() -> MetricsLatestResponse:
    """
    Get the latest value for each metric.

    Merges custom metrics from the store with system metrics scraped from the
    Telegraf Prometheus endpoint. Custom metrics take precedence on name collision.

    Returns:
        MetricsLatestResponse mapping metric name (or name{labels}) to its most recent data point.
    """
    store = get_metrics_store()
    settings = get_settings()

    latest = await store.get_latest_metrics()
    metrics: dict[str, MetricData] = {
        name: MetricData(**m.to_telegraf_json()) for name, m in latest.items()
    }

    prom_metrics = await _fetch_prometheus_metrics(settings.prometheus_telegraf_endpoint)
    for key, data in prom_metrics.items():
        if key not in metrics:
            metrics[key] = data

    return MetricsLatestResponse(metrics=metrics)


@router.get("/api/v1/metrics/names", response_model=MetricNamesResponse)
async def get_metric_names() -> MetricNamesResponse:
    """
    Get list of all metric names currently stored.

    Returns:
        MetricNamesResponse with list of metric names and count.
    """
    store = get_metrics_store()
    names = await store.get_metric_names()
    return MetricNamesResponse(names=names, count=len(names))


@router.delete(
    "/api/v1/metrics",
    status_code=status.HTTP_200_OK,
    response_model=MetricsClearedResponse,
)
async def clear_metrics(
    name: str | None = Query(default=None, description="Metric name to clear"),
) -> MetricsClearedResponse:
    """
    Clear stored metrics.

    Args:
        name: Optional metric name. If provided, clears only that metric.

    Returns:
        MetricsClearedResponse with count of cleared metrics.
    """
    store = get_metrics_store()
    count = await store.clear_metrics(name)
    return MetricsClearedResponse(cleared=count, message=f"Cleared {count} metrics")


# ==============================================================================
# Prometheus/Telegraf Compatible Endpoints
# ==============================================================================


def _escape_prometheus_label_value(value: str) -> str:
    """Escape special characters in Prometheus label values per text format spec."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """
    Prometheus-compatible metrics endpoint.

    Returns stored custom metrics in Prometheus text format.

    This endpoint can be scraped by Prometheus or used by Telegraf's
    prometheus input plugin.
    """
    store = get_metrics_store()
    latest = await store.get_latest_metrics()

    lines: list[str] = []
    seen_metric_names: set = set()
    for name, metric in latest.items():
        escaped_tags = {
            k: _escape_prometheus_label_value(str(v)) for k, v in (metric.tags or {}).items()
        }
        labels = ",".join(f'{k}="{v}"' for k, v in escaped_tags.items())
        label_str = f"{{{labels}}}" if labels else ""

        ts_ms = metric.timestamp // int(1e6) if metric.timestamp else None
        timestamp_str = f" {ts_ms}" if ts_ms else ""

        for field_name, field_value in metric.fields.items():
            if isinstance(field_value, bool):
                field_value = 1 if field_value else 0
            if isinstance(field_value, (int, float)):
                raw_name = f"{name}_{field_name}" if field_name != "value" else name
                metric_name = re.sub(r"[^a-zA-Z0-9_:]", "_", raw_name)
                if metric_name not in seen_metric_names:
                    lines.append(f"# HELP {metric_name} Custom metric")
                    lines.append(f"# TYPE {metric_name} gauge")
                    seen_metric_names.add(metric_name)
                lines.append(f"{metric_name}{label_str} {field_value}{timestamp_str}")
            else:
                logger.debug(
                    "Dropping string field from Prometheus output",
                    extra={"metric": name, "field": field_name},
                )

    return "\n".join(lines) + "\n"


@router.post("/write", status_code=status.HTTP_204_NO_CONTENT)
async def influx_write(request: Request) -> Response:
    """
    InfluxDB-compatible write endpoint.

    Accepts data in InfluxDB Line Protocol format, compatible with
    InfluxDB client libraries and Telegraf output plugins.
    """
    body = await request.body()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UTF-8 encoding in request body: {e}",
        ) from e
    lines = text.strip().split("\n")

    metrics = []
    for line in lines:
        metric = InfluxLineProtocolInput.parse_line(line)
        if metric:
            metrics.append(metric)

    if metrics:
        store = get_metrics_store()
        count = await store.add_metrics(metrics)
        get_service_metrics().record_metrics_received(count, source="influx")
        logger.debug("Accepted metrics via /write", extra={"count": len(metrics)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)
