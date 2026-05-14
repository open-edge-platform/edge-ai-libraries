# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Internal service metrics for observability.

Tracks operational metrics like request counts, latencies, errors,
and SSE statistics for monitoring and alerting.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ServiceMetrics:
    """
    Container for service-level metrics.

    Async-safe counters and gauges for tracking service health and performance.
    Operations are safe within a single asyncio event loop (single-threaded).
    Not safe for use across multiple OS threads without additional locking.
    """

    # Startup time for uptime calculation
    start_time: float = field(default_factory=time.monotonic)

    # Request counters
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0

    # Metrics ingestion counters
    total_metrics_received: int = 0
    metrics_received_json: int = 0
    metrics_received_influx: int = 0
    metrics_received_otlp: int = 0
    metrics_received_simple: int = 0
    metrics_received_poller: int = 0

    # SSE counters
    sse_events_sent: int = 0

    # Error counters by type
    parse_errors: int = 0
    storage_errors: int = 0
    sse_errors: int = 0

    # Latency tracking (in milliseconds)
    _max_latency_samples: int = 1000
    _request_latencies: deque = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._request_latencies = deque(maxlen=self._max_latency_samples)

    def record_request(self, success: bool = True, latency_ms: float = 0.0) -> None:
        """Record a request completion."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        if latency_ms > 0:
            self._request_latencies.append(latency_ms)

    def record_metrics_received(
        self,
        count: int,
        source: Literal["json", "influx", "otlp", "simple", "poller"] = "json",
    ) -> None:
        """Record metrics ingestion.

        Args:
            count: Number of metrics received.
            source: Input format used to submit the metrics.
        """
        self.total_metrics_received += count
        if source == "json":
            self.metrics_received_json += count
        elif source == "influx":
            self.metrics_received_influx += count
        elif source == "otlp":
            self.metrics_received_otlp += count
        elif source == "simple":
            self.metrics_received_simple += count
        elif source == "poller":
            self.metrics_received_poller += count

    def record_error(self, error_type: Literal["parse", "storage", "sse"]) -> None:
        """Record an error by type."""
        if error_type == "parse":
            self.parse_errors += 1
        elif error_type == "storage":
            self.storage_errors += 1
        elif error_type == "sse":
            self.sse_errors += 1

    @property
    def uptime_seconds(self) -> float:
        """Get service uptime in seconds."""
        return time.monotonic() - self.start_time

    @property
    def request_latency_avg_ms(self) -> float:
        """Get average request latency in milliseconds."""
        if not self._request_latencies:
            return 0.0
        return sum(self._request_latencies) / len(self._request_latencies)

    @property
    def request_latency_p99_ms(self) -> float:
        """Get 99th percentile request latency in milliseconds."""
        if not self._request_latencies:
            return 0.0
        sorted_latencies = sorted(self._request_latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def error_rate(self) -> float:
        """Get error rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for API response."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 2),
            "requests": {
                "total": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "rate_limited": self.rate_limited_requests,
                "error_rate_percent": round(self.error_rate, 2),
            },
            "latency_ms": {
                "avg": round(self.request_latency_avg_ms, 2),
                "p99": round(self.request_latency_p99_ms, 2),
            },
            "metrics_ingestion": {
                "total": self.total_metrics_received,
                "by_source": {
                    "json": self.metrics_received_json,
                    "influx": self.metrics_received_influx,
                    "otlp": self.metrics_received_otlp,
                    "simple": self.metrics_received_simple,
                    "poller": self.metrics_received_poller,
                },
            },
            "sse": {
                "events_sent": self.sse_events_sent,
            },
            "errors": {
                "parse": self.parse_errors,
                "storage": self.storage_errors,
                "sse": self.sse_errors,
            },
        }

    def to_prometheus(self) -> str:
        """Render service metrics in Prometheus text exposition format."""
        lines: list[str] = []

        def gauge(name: str, help_text: str, value: float, labels: str = "") -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
            label_str = f"{{{labels}}}" if labels else ""
            lines.append(f"{name}{label_str} {value}")

        def counter(name: str, help_text: str, value: float, labels: str = "") -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} counter")
            label_str = f"{{{labels}}}" if labels else ""
            lines.append(f"{name}{label_str} {value}")

        uptime = round(self.uptime_seconds, 3)
        gauge("metrics_manager_uptime_seconds", "Service uptime in seconds", uptime)
        counter(
            "metrics_manager_requests_total",
            "Total HTTP requests handled",
            self.total_requests,
        )

        msg = "Total metrics received by source"
        lines.append(f"# HELP metrics_manager_metrics_received_total {msg}")
        lines.append("# TYPE metrics_manager_metrics_received_total counter")
        for src, val in [
            ("json", self.metrics_received_json),
            ("influx", self.metrics_received_influx),
            ("otlp", self.metrics_received_otlp),
            ("simple", self.metrics_received_simple),
            ("poller", self.metrics_received_poller),
        ]:
            lines.append(f'metrics_manager_metrics_received_total{{source="{src}"}} {val}')

        gauge(
            "metrics_manager_sse_events_sent", "Total SSE events sent", self.sse_events_sent
        )
        avg_latency = round(self.request_latency_avg_ms, 3)
        gauge(
            "metrics_manager_request_latency_avg_ms",
            "Average request latency in ms",
            avg_latency,
        )
        error_count = (
            self.parse_errors + self.storage_errors + self.sse_errors
        )
        counter("metrics_manager_errors_total", "Total errors by type", error_count)

        return "\n".join(lines) + "\n"

# Global metrics instance
_service_metrics: ServiceMetrics | None = None


def get_service_metrics() -> ServiceMetrics:
    """Get or create the global service metrics instance."""
    global _service_metrics
    if _service_metrics is None:
        _service_metrics = ServiceMetrics()
    return _service_metrics


def reset_service_metrics() -> None:
    """Reset service metrics (for testing)."""
    global _service_metrics
    _service_metrics = ServiceMetrics()
