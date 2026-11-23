# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/routes.py."""

import pytest
from fastapi.testclient import TestClient
from prometheus_client.core import Metric as PrometheusMetric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Timestamp

from app import capabilities


class TestPrometheusMetricsEndpoint:
    def test_tagged_series_keep_valid_metric_names(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics",
            json={
                "metrics": [
                    {"name": "fps", "fields": {"value": 10}, "tags": {"pipeline": "a"}},
                    {"name": "fps", "fields": {"value": 20}, "tags": {"pipeline": "b"}},
                ]
            },
        )
        assert response.status_code == 202
        response = client.get("/metrics")
        assert response.status_code == 200
        samples = [
            sample
            for family in text_string_to_metric_families(response.text)
            for sample in family.samples
            if sample.name == "fps"
        ]
        assert {(sample.labels["pipeline"], sample.value) for sample in samples} == {
            ("a", 10),
            ("b", 20),
        }

    def test_empty_store_returns_empty_body(self, client: TestClient):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.text.strip() == ""

    def test_metric_produces_help_and_type_lines(self, client: TestClient):
        """GET /metrics must emit # HELP and # TYPE for each custom metric."""
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 29.97})
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "# HELP fps" in response.text
        assert "# TYPE fps gauge" in response.text
        assert "fps 29.97" in response.text

    def test_multi_field_metric_has_help_per_field(self, client: TestClient):
        client.post(
            "/api/v1/metrics",
            json={"metrics": [{"name": "cpu", "fields": {"user": 10.0, "system": 5.0}}]},
        )
        response = client.get("/metrics")
        assert "# HELP cpu_user" in response.text
        assert "# TYPE cpu_user gauge" in response.text
        assert "# HELP cpu_system" in response.text
        assert "# TYPE cpu_system gauge" in response.text

    def test_voice_round_trip_metric_preserves_field_name_and_tags(
        self, client: TestClient
    ):
        response = client.post(
            "/api/v1/metrics",
            json={
                "metrics": [
                    {
                        "name": "voice_asr",
                        "fields": {"service_round_trip_ms": 321.5},
                        "tags": {"device": "service-default", "language": "en"},
                    }
                ]
            },
        )
        assert response.status_code == 202

        response = client.get("/metrics")
        assert "# TYPE voice_asr_service_round_trip_ms gauge" in response.text
        assert (
            'voice_asr_service_round_trip_ms{device="service-default",language="en"} 321.5'
            in response.text
        )


class TestHealthEndpoints:
    def test_basic_health_returns_healthy(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_api_health_returns_healthy(self, client: TestClient):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "metrics_store" in data


class TestCapabilitiesEndpoint:
    def test_capabilities_minimal_returns_categorized_high_level_data(self, client: TestClient):
        response = client.get("/api/v1/capabilities")
        assert response.status_code == 200

        payload = response.json()
        assert "generated_at" in payload
        assert payload["profile"] == "minimal"
        assert "categories" in payload
        assert "platform" in payload
        assert "devices" in payload
        assert "system_memory" in payload["platform"]
        assert "device_summary" in payload["platform"]
        assert "platform_overview" in payload["categories"]
        assert "compute_device_overview" in payload["categories"]

    def test_capabilities_minimal_includes_cpu_high_level_details(self, client: TestClient):
        response = client.get("/api/v1/capabilities")
        payload = response.json()
        cpu_devices = [d for d in payload["devices"] if d["category"] == "cpu"]
        assert len(cpu_devices) == 1
        assert cpu_devices[0]["present"] is True
        assert "commercial_reference" in cpu_devices[0]
        assert "cores" in cpu_devices[0]["details"]

    def test_capabilities_expanded_includes_technical_specs(self, client: TestClient):
        response = client.get("/api/v1/capabilities?profile=expanded")
        payload = response.json()
        assert payload["profile"] == "expanded"
        cpu_devices = [d for d in payload["devices"] if d["category"] == "cpu"]
        assert len(cpu_devices) == 1
        assert "specs" in cpu_devices[0]
        assert "topology" in cpu_devices[0]["specs"]
        assert "frequency" in cpu_devices[0]["specs"]
        assert "cache" in cpu_devices[0]["specs"]

    def test_capabilities_rejects_invalid_profile(self, client: TestClient):
        response = client.get("/api/v1/capabilities?profile=full")
        assert response.status_code == 422

    def test_capabilities_does_not_expose_runtime_metric_names(self, client: TestClient):
        response = client.get("/api/v1/capabilities")
        payload = response.json()
        flat_caps = [cap for device in payload["devices"] for cap in device.get("capabilities", [])]
        assert "cpu_usage" not in flat_caps
        assert "npu_power" not in flat_caps
        assert "gpu_power" not in flat_caps

    def test_capabilities_prefers_host_hostname_over_container_hostname(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("METRICS_MANAGER_HOSTNAME", raising=False)

        # Keep the original reader so the fake does not call itself.
        real_read_text = capabilities._read_text

        def fake_read_text(path: str) -> str | None:
            if path == "/proc/1/root/etc/hostname":
                return "host-visible-name"
            return real_read_text(path)

        monkeypatch.setattr(capabilities, "_read_text", fake_read_text)

        response = client.get("/api/v1/capabilities")

        assert response.status_code == 200
        payload = response.json()
        assert payload["platform"]["hostname"] == "host-visible-name"
        assert payload["platform"]["system"]["hostname"] == "host-visible-name"


class TestMetricsIngestion:
    def test_push_simple_metric(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/simple",
            json={"name": "fps", "value": 30.0},
        )
        assert response.status_code == 202
        assert response.json()["accepted"] == 1

    def test_push_batch(self, client: TestClient):
        batch = {
            "metrics": [
                {"name": "cpu", "fields": {"usage": 45.0}},
                {"name": "mem", "fields": {"used_percent": 70.0}},
            ]
        }
        response = client.post("/api/v1/metrics", json=batch)
        assert response.status_code == 202
        assert response.json()["accepted"] == 2

    def test_push_influx(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/influx",
            content=b"cpu,host=srv usage=45.2 1704067200000000000",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 202

    def test_push_invalid_influx_returns_400(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/influx",
            content=b"",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 400

    def test_get_metrics_empty(self, client: TestClient):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_get_latest_metrics(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 30.0})
        response = client.get("/api/v1/metrics/latest")
        assert response.status_code == 200
        assert "fps" in response.json()["metrics"]

    def test_get_metric_names(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        response = client.get("/api/v1/metrics/names")
        assert response.status_code == 200
        assert "fps" in response.json()["names"]

    def test_clear_metrics(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        response = client.delete("/api/v1/metrics")
        assert response.status_code == 200
        assert response.json()["cleared"] >= 1

    def test_influx_write_endpoint(self, client: TestClient):
        response = client.post(
            "/write",
            content=b"cpu usage=45.2 1704067200000000000",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 204


# ---------------------------------------------------------------------------
# OTLP ingestion
# ---------------------------------------------------------------------------

_OTLP_GAUGE = {
    "resourceMetrics": [
        {
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "test-service"}}]
            },
            "scopeMetrics": [
                {
                    "metrics": [
                        {
                            "name": "http_requests_total",
                            "gauge": {
                                "dataPoints": [
                                    {
                                        "asDouble": 42.0,
                                        "timeUnixNano": "1704067200000000000",
                                        "attributes": [
                                            {"key": "method", "value": {"stringValue": "GET"}}
                                        ],
                                    }
                                ]
                            },
                        }
                    ]
                }
            ],
        }
    ]
}

_OTLP_EMPTY = {"resourceMetrics": []}


class TestOtlpIngestion:
    def test_push_valid_otlp_returns_202(self, client: TestClient):
        response = client.post("/api/v1/metrics/otlp", json=_OTLP_GAUGE)
        assert response.status_code == 202

    def test_push_otlp_accepted_count_matches_data_points(self, client: TestClient):
        response = client.post("/api/v1/metrics/otlp", json=_OTLP_GAUGE)
        assert response.json()["accepted"] == 1

    def test_push_otlp_metric_is_stored_and_retrievable(self, client: TestClient):
        client.post("/api/v1/metrics/otlp", json=_OTLP_GAUGE)
        response = client.get("/api/v1/metrics/names")
        assert "http_requests_total" in response.json()["names"]

    def test_push_otlp_resource_attributes_become_tags(self, client: TestClient):
        """Resource attributes (service.name) are propagated as metric tags."""
        client.post("/api/v1/metrics/otlp", json=_OTLP_GAUGE)
        response = client.get("/api/v1/metrics")
        metrics = response.json()["metrics"]
        assert any(m.get("tags", {}).get("service.name") == "test-service" for m in metrics)

    def test_push_otlp_empty_resource_metrics_returns_400(self, client: TestClient):
        """Empty resourceMetrics list yields no parseable metrics → 400."""
        response = client.post("/api/v1/metrics/otlp", json=_OTLP_EMPTY)
        assert response.status_code == 400

    def test_push_otlp_sum_type_metric_is_accepted(self, client: TestClient):
        """Sum (counter) metric type is converted and accepted."""
        payload = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "requests_total",
                                    "sum": {
                                        "dataPoints": [
                                            {"asInt": 100, "timeUnixNano": "1704067200000000000"}
                                        ]
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        response = client.post("/api/v1/metrics/otlp", json=payload)
        assert response.status_code == 202
        assert response.json()["accepted"] == 1

    def test_push_otlp_histogram_stores_summary_fields(self, client: TestClient):
        """A real histogram point (count/sum/min/max, no asDouble) is not stored as 0."""
        payload = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "genai_ttft_ms",
                                    "histogram": {
                                        "aggregationTemporality": 1,
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1704067200000000000",
                                                "count": "2",
                                                "sum": 30.0,
                                                "min": 10.0,
                                                "max": 20.0,
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        assert client.post("/api/v1/metrics/otlp", json=payload).status_code == 202
        stored = client.get("/api/v1/metrics?name=genai_ttft_ms").json()["metrics"]
        assert stored[0]["fields"] == {
            "count": 2,
            "sum": 30.0,
            "min": 10.0,
            "max": 20.0,
            "avg": 15.0,
        }
        assert stored[0]["tags"] == {"temporality": "delta"}

    def test_push_otlp_histogram_with_overflowing_sum_keeps_count(self, client: TestClient):
        """A sum beyond double range must not fail the request or its sibling points."""
        points = [
            {"timeUnixNano": "1704067200000000000", "count": "1", "sum": 4.0},
            {"timeUnixNano": "1704067201000000000", "count": "3", "sum": 10**400},
        ]
        payload = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {"name": "genai_tpot_ms", "histogram": {"dataPoints": points}}
                            ]
                        }
                    ]
                }
            ]
        }
        response = client.post("/api/v1/metrics/otlp", json=payload)
        assert response.status_code == 202
        assert response.json()["accepted"] == 2
        stored = client.get("/api/v1/metrics?name=genai_tpot_ms").json()["metrics"]
        assert sorted(m["fields"]["count"] for m in stored) == [1, 3]
        assert {"count": 3} in [m["fields"] for m in stored]

    def test_push_otlp_histogram_and_as_int_gauge_round_trip(self, client: TestClient):
        """Histogram summary fields, temporality and string asInt survive ingest and query."""
        payload = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]
                    },
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "request_latency_ms",
                                    "histogram": {
                                        "aggregationTemporality": (
                                            "AGGREGATION_TEMPORALITY_CUMULATIVE"
                                        ),
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1704067200000000000",
                                                "count": "4",
                                                "sum": 10.0,
                                                "bucketCounts": ["1", "3"],
                                                "explicitBounds": [2.0],
                                            }
                                        ],
                                    },
                                },
                                {
                                    "name": "frames_in_queue",
                                    "gauge": {
                                        "dataPoints": [
                                            {"asInt": "42", "timeUnixNano": "1704067200000000000"},
                                            {"asInt": "n/a", "timeUnixNano": "1704067201000000000"},
                                        ]
                                    },
                                },
                            ]
                        }
                    ],
                }
            ]
        }
        response = client.post("/api/v1/metrics/otlp", json=payload)
        assert response.status_code == 202
        assert response.json()["accepted"] == 2

        histogram = client.get("/api/v1/metrics?name=request_latency_ms").json()["metrics"]
        assert histogram[0]["fields"] == {"count": 4, "sum": 10.0, "avg": 2.5}
        assert histogram[0]["tags"] == {"service.name": "svc", "temporality": "cumulative"}

        gauge = client.get("/api/v1/metrics?name=frames_in_queue").json()["metrics"]
        assert len(gauge) == 1
        assert gauge[0]["fields"] == {"value": 42}
        assert gauge[0]["tags"] == {"service.name": "svc"}

        prometheus = client.get("/metrics").text.splitlines()

        def sample(metric: str) -> str:
            line = next(line for line in prometheus if line.startswith(metric + "{"))
            return line.split()[-2]

        assert sample("request_latency_ms_count") == "4"
        assert sample("request_latency_ms_sum") == "10.0"
        assert sample("frames_in_queue") == "42"

    def test_push_otlp_only_invalid_points_returns_400(self, client: TestClient):
        payload = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "frames_in_queue",
                                    "gauge": {"dataPoints": [{"asInt": "n/a"}]},
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        assert client.post("/api/v1/metrics/otlp", json=payload).status_code == 400


# ---------------------------------------------------------------------------
# GET /api/v1/metrics — name filter
# ---------------------------------------------------------------------------


class TestMetricsQueryFilter:
    def test_name_filter_returns_only_matching_metric(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 30.0})
        client.post("/api/v1/metrics/simple", json={"name": "latency", "value": 5.0})

        response = client.get("/api/v1/metrics?name=fps")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["metrics"][0]["name"] == "fps"

    def test_name_filter_excludes_other_metrics(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 30.0})
        client.post("/api/v1/metrics/simple", json={"name": "latency", "value": 5.0})

        response = client.get("/api/v1/metrics?name=fps")
        names = [m["name"] for m in response.json()["metrics"]]
        assert "latency" not in names

    def test_name_filter_nonexistent_name_returns_empty(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        response = client.get("/api/v1/metrics?name=no_such_metric")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_no_filter_returns_all_metrics(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        client.post("/api/v1/metrics/simple", json={"name": "latency", "value": 2.0})
        response = client.get("/api/v1/metrics")
        assert response.json()["count"] == 2


# ---------------------------------------------------------------------------
# DELETE /api/v1/metrics — specific metric deletion
# ---------------------------------------------------------------------------


class TestMetricsDeletion:
    def test_delete_specific_metric_by_name(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        client.post("/api/v1/metrics/simple", json={"name": "latency", "value": 2.0})

        response = client.delete("/api/v1/metrics?name=fps")
        assert response.status_code == 200
        assert response.json()["cleared"] == 1

    def test_delete_specific_metric_leaves_other_metrics_intact(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "fps", "value": 1.0})
        client.post("/api/v1/metrics/simple", json={"name": "latency", "value": 2.0})

        client.delete("/api/v1/metrics?name=fps")

        names = client.get("/api/v1/metrics/names").json()["names"]
        assert "fps" not in names
        assert "latency" in names

    def test_delete_nonexistent_metric_returns_zero(self, client: TestClient):
        response = client.delete("/api/v1/metrics?name=no_such_metric")
        assert response.status_code == 200
        assert response.json()["cleared"] == 0

    def test_delete_all_metrics_empties_store(self, client: TestClient):
        client.post("/api/v1/metrics/simple", json={"name": "a", "value": 1.0})
        client.post("/api/v1/metrics/simple", json={"name": "b", "value": 2.0})

        client.delete("/api/v1/metrics")

        assert client.get("/api/v1/metrics").json()["count"] == 0


# ---------------------------------------------------------------------------
# Additional coverage for edge cases
# ---------------------------------------------------------------------------


class TestInfluxEncodingErrors:
    def test_influx_invalid_utf8_returns_400(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/influx",
            content=b"\xff\xfe",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 400
        assert "UTF-8" in response.json()["detail"]

    def test_write_endpoint_invalid_utf8_returns_400(self, client: TestClient):
        response = client.post(
            "/write",
            content=b"\xff\xfe",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 400
        assert "UTF-8" in response.json()["detail"]


class TestInfluxParsingErrors:
    def test_influx_parse_errors_included_in_response(self, client: TestClient):
        response = client.post(
            "/api/v1/metrics/influx",
            content=b"invalid_line\ncpu usage=45.2 1704067200000000000",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 202
        assert "errors" in response.json()
        assert len(response.json()["errors"]) > 0


class TestFetchPrometheusMetrics:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("timestamp", "expected"),
        [(0.0, 0), (Timestamp(1704067200, 123456789), 1704067200123456789)],
    )
    async def test_fetch_preserves_zero_and_nanosecond_timestamp(self, mocker, timestamp, expected):
        from app.routes import _fetch_prometheus_metrics

        family = PrometheusMetric("fps", "test", "gauge")
        family.add_sample("fps", {}, 30, timestamp=timestamp)
        family.add_sample("fps", {"x": "a,y=b"}, 10, timestamp=timestamp)
        family.add_sample("fps", {"x": "a", "y": "b"}, 20, timestamp=timestamp)
        mocker.patch("app.routes.text_string_to_metric_families", return_value=[family])
        response = mocker.MagicMock()
        response.status = 200
        response.text = mocker.AsyncMock(return_value="")
        response.__aenter__ = mocker.AsyncMock(return_value=response)
        response.__aexit__ = mocker.AsyncMock(return_value=False)
        session = mocker.MagicMock()
        session.get.return_value = response
        session.__aenter__ = mocker.AsyncMock(return_value=session)
        session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("app.routes.aiohttp.ClientSession", return_value=session)
        result = await _fetch_prometheus_metrics("http://localhost:9273")
        assert len(result) == 3
        assert result["fps"].timestamp == expected

    @pytest.mark.asyncio
    async def test_fetch_prometheus_non_200_returns_empty(self, mocker):
        from app.routes import _fetch_prometheus_metrics

        mock_resp = mocker.MagicMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = mocker.AsyncMock(return_value=None)

        mock_session = mocker.MagicMock()
        mock_session.get = mocker.MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch("app.routes.aiohttp.ClientSession", return_value=mock_session)

        result = await _fetch_prometheus_metrics("http://localhost:9090")
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_prometheus_exception_returns_empty(self, mocker):
        from app.routes import _fetch_prometheus_metrics

        mocker.patch("app.routes.aiohttp.ClientSession", side_effect=Exception("Connection failed"))

        result = await _fetch_prometheus_metrics("http://localhost:9090")
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_prometheus_parses_metrics_with_labels(self, mocker):
        from app.routes import _fetch_prometheus_metrics

        prometheus_text = 'cpu{host="server1"} 45.2 1704067200000\n'

        mock_resp = mocker.MagicMock()
        mock_resp.status = 200
        mock_resp.text = mocker.AsyncMock(return_value=prometheus_text)
        mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = mocker.AsyncMock(return_value=None)

        mock_session = mocker.MagicMock()
        mock_session.get = mocker.MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch("app.routes.aiohttp.ClientSession", return_value=mock_session)

        result = await _fetch_prometheus_metrics("http://localhost:9090")
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fetch_prometheus_parses_metrics_without_labels(self, mocker):
        from app.routes import _fetch_prometheus_metrics

        prometheus_text = "memory 8192 1704067200000\n"

        mock_resp = mocker.MagicMock()
        mock_resp.status = 200
        mock_resp.text = mocker.AsyncMock(return_value=prometheus_text)
        mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = mocker.AsyncMock(return_value=None)

        mock_session = mocker.MagicMock()
        mock_session.get = mocker.MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=None)

        mocker.patch("app.routes.aiohttp.ClientSession", return_value=mock_session)

        result = await _fetch_prometheus_metrics("http://localhost:9090")
        assert "memory" in result


class TestPrometheusMetricsOutput:
    def test_bool_field_converted_to_numeric(self, client: TestClient):
        client.post(
            "/api/v1/metrics",
            json={"metrics": [{"name": "status", "fields": {"healthy": True, "value": 1}}]},
        )
        response = client.get("/metrics")
        assert "status_healthy 1" in response.text

    def test_bool_false_converted_to_zero(self, client: TestClient):
        client.post(
            "/api/v1/metrics",
            json={"metrics": [{"name": "status", "fields": {"healthy": False, "value": 1}}]},
        )
        response = client.get("/metrics")
        assert "status_healthy 0" in response.text

    def test_special_chars_escaped_in_labels(self, client: TestClient):
        client.post(
            "/api/v1/metrics/simple",
            json={"name": "cpu", "value": 45.2, "tags": {"host": 'srv"1'}},
        )
        response = client.get("/metrics")
        assert '\\"' in response.text

    def test_newline_escaped_in_labels(self, client: TestClient):
        client.post(
            "/api/v1/metrics/simple",
            json={"name": "cpu", "value": 45.2, "tags": {"msg": "line1\nline2"}},
        )
        response = client.get("/metrics")
        assert "\\n" in response.text

    def test_string_field_dropped_from_prometheus_output(self, client: TestClient):
        client.post(
            "/api/v1/metrics",
            json={"metrics": [{"name": "event", "fields": {"msg": "hello", "code": 1}}]},
        )
        response = client.get("/metrics")
        assert "event_code 1" in response.text
        assert "msg=" not in response.text
