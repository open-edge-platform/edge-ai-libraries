from datetime import datetime

import httpx
import pytest

from src.main import app
from src.config import settings


@pytest.mark.asyncio
async def test_health_endpoint_returns_expected_payload():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{settings.API_V1_PREFIX}/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "healthy"
    assert payload["adk_enabled"] is settings.AGENT_MODE
    assert payload["mcp_enabled"] is settings.MCP_ENABLED
    assert isinstance(payload["uptime_seconds"], (int, float))
    assert payload["uptime_seconds"] >= 0
    assert "timestamp" in payload
    assert datetime.fromisoformat(payload["timestamp"])


@pytest.mark.asyncio
async def test_metrics_endpoint_is_not_exposed():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{settings.API_V1_PREFIX}/metrics")

    assert response.status_code == 404


def test_alerts_openapi_includes_request_payload_example():
    schema = app.openapi()
    operation = schema["paths"][f"{settings.API_V1_PREFIX}/alerts"]["post"]
    request_body = operation["requestBody"]["content"]["application/json"]

    assert request_body["schema"]["type"] == "object"
    assert request_body["schema"]["additionalProperties"] is True
    assert request_body["example"]["alert_type"] == "fire_detection"
    assert request_body["example"]["source_id"] == "cam-01"
