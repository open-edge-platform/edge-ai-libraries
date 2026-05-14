# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/routes.py."""

import pytest
from fastapi.testclient import TestClient


class TestPrometheusMetricsEndpoint:
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
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}}
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
        assert any(
            m.get("tags", {}).get("service.name") == "test-service"
            for m in metrics
        )

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

        mocker.patch(
            "app.routes.aiohttp.ClientSession",
            side_effect=Exception("Connection failed")
        )

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

        prometheus_text = 'memory 8192 1704067200000\n'

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
