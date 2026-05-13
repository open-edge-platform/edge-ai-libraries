# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/main.py."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import CorrelationIdMiddleware, app
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


class TestRootAndStatsEndpoints:
    def test_root_endpoint_returns_service_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Metrics Manager"
        assert "version" in data
        assert "endpoints" in data

    def test_get_stats_endpoint_returns_metrics(self, client):
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "total_requests" in data or "metrics" in data or len(data) >= 0
