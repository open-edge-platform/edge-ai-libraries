# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/metrics.py (ServiceMetrics)."""

from collections import deque

import app.metrics as metrics_module
from app.metrics import ServiceMetrics, get_service_metrics, reset_service_metrics


class TestServiceMetricsRecording:
    def setup_method(self):
        reset_service_metrics()

    def test_record_request_failure(self):
        m = ServiceMetrics()
        m.record_request(success=False, latency_ms=5.0)
        assert m.failed_requests == 1
        assert m.successful_requests == 0

    def test_record_request_latency_evicts_oldest_when_limit_exceeded(self):
        """deque(maxlen=N) automatically drops the oldest entry when full."""
        m = ServiceMetrics()
        # Replace the deque with a capacity-3 one to keep the test fast
        m._request_latencies = deque(maxlen=3)
        for i in range(4):
            m.record_request(success=True, latency_ms=float(i + 1))
        assert len(m._request_latencies) == 3
        # Oldest (1.0) should be evicted; newest three (2.0, 3.0, 4.0) remain
        assert 1.0 not in m._request_latencies
        assert list(m._request_latencies) == [2.0, 3.0, 4.0]

    def test_record_metrics_received_all_sources(self):
        """All source branches including new 'poller' source."""
        m = ServiceMetrics()
        m.record_metrics_received(10, source="json")
        m.record_metrics_received(5, source="influx")
        m.record_metrics_received(3, source="otlp")
        m.record_metrics_received(2, source="simple")
        m.record_metrics_received(7, source="poller")
        assert m.metrics_received_json == 10
        assert m.metrics_received_influx == 5
        assert m.metrics_received_otlp == 3
        assert m.metrics_received_simple == 2
        assert m.metrics_received_poller == 7
        assert m.total_metrics_received == 27

    def test_record_error_all_types(self):
        m = ServiceMetrics()
        m.record_error("parse")
        m.record_error("storage")
        m.record_error("sse")
        assert m.parse_errors == 1
        assert m.storage_errors == 1
        assert m.sse_errors == 1

    def test_request_latency_avg_ms_with_data(self):
        """Line 136: non-empty latencies path."""
        m = ServiceMetrics()
        m.record_request(success=True, latency_ms=10.0)
        m.record_request(success=True, latency_ms=20.0)
        assert m.request_latency_avg_ms == 15.0

    def test_request_latency_avg_ms_empty(self):
        m = ServiceMetrics()
        assert m.request_latency_avg_ms == 0.0

    def test_request_latency_p99_with_data(self):
        """Lines 143-145: non-empty latencies for p99."""
        m = ServiceMetrics()
        for i in range(1, 101):
            m.record_request(success=True, latency_ms=float(i))
        p99 = m.request_latency_p99_ms
        assert p99 >= 99.0

    def test_request_latency_p99_empty(self):
        m = ServiceMetrics()
        assert m.request_latency_p99_ms == 0.0

    def test_error_rate_with_requests(self):
        """Line 152: non-zero total_requests path."""
        m = ServiceMetrics()
        m.record_request(success=True)
        m.record_request(success=False)
        assert m.error_rate == 50.0

    def test_error_rate_zero_requests(self):
        m = ServiceMetrics()
        assert m.error_rate == 0.0

    def test_to_dict_structure(self):
        m = ServiceMetrics()
        d = m.to_dict()
        assert "uptime_seconds" in d
        assert "requests" in d
        assert "latency_ms" in d
        assert "metrics_ingestion" in d
        assert "sse" in d
        assert "errors" in d
        assert "poller" in d["metrics_ingestion"]["by_source"]

    def test_to_prometheus_output(self):
        """to_prometheus() produces valid Prometheus text including 'poller' label."""
        m = ServiceMetrics()
        m.record_request(success=True, latency_ms=5.0)
        m.record_metrics_received(2, source="json")
        m.record_metrics_received(4, source="poller")
        output = m.to_prometheus()
        assert "metrics_manager_uptime_seconds" in output
        assert "metrics_manager_requests_total" in output
        assert "metrics_manager_metrics_received_total" in output
        assert 'source="poller"' in output
        assert "metrics_manager_sse_events_sent" in output
        assert "metrics_manager_request_latency_avg_ms" in output
        assert "metrics_manager_errors_total" in output
        assert output.endswith("\n")


class TestGetServiceMetricsSingleton:
    def setup_method(self):
        reset_service_metrics()

    def test_get_service_metrics_creates_when_none(self):
        """Line 250: creation branch inside get_service_metrics."""
        metrics_module._service_metrics = None
        result = get_service_metrics()
        assert isinstance(result, ServiceMetrics)

    def test_get_service_metrics_returns_same_instance(self):
        m1 = get_service_metrics()
        m2 = get_service_metrics()
        assert m1 is m2

    def test_reset_creates_fresh_instance(self):
        m1 = get_service_metrics()
        reset_service_metrics()
        m2 = get_service_metrics()
        assert m1 is not m2
