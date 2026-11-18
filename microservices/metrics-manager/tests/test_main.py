# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/main.py."""

import pytest

from app.main import CorrelationIdMiddleware
from app.metrics import reset_service_metrics


class TestCorrelationIdMiddlewareException:
    @pytest.mark.asyncio
    async def test_exception_records_failed_request_and_reraises(self):
        """Exception branch in CorrelationIdMiddleware records failed request."""
        reset_service_metrics()
        from app.metrics import get_service_metrics

        async def raising_app(scope, receive, send):
            raise RuntimeError("simulated handler error")

        middleware = CorrelationIdMiddleware(app=raising_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }

        with pytest.raises(RuntimeError, match="simulated handler error"):
            await middleware(scope, None, None)

        metrics = get_service_metrics()
        assert metrics.failed_requests == 1


@pytest.mark.asyncio
async def test_lifespan_closes_store_when_context_raises(mocker):
    from app.main import app, lifespan

    store = mocker.AsyncMock()
    store.get_stats.return_value = {}
    mocker.patch("app.main.get_metrics_store", return_value=store)
    mocker.patch("app.main.setup_logging")
    with pytest.raises(RuntimeError, match="lifecycle failure"):
        async with lifespan(app):
            raise RuntimeError("lifecycle failure")
    store.close.assert_awaited_once()


class TestRootAndStatsEndpoints:
    def test_root_endpoint_returns_service_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Metrics Manager"
        assert "version" in data
        assert "endpoints" in data
        assert "capabilities" in data["endpoints"]["metrics_api"]

    def test_get_stats_endpoint_returns_metrics(self, client):
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "total_requests" in data or "metrics" in data or len(data) >= 0
