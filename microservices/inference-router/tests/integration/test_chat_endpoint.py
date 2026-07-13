# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for chat endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.config import RouterConfig, ProviderConfig, TelemetryConfig
from src.router import RouterOrchestrator
from src.api.app import create_app
from src.observability import InMemoryTelemetry


@pytest.fixture
def test_router_config():
    """Create test router config."""
    return RouterConfig(
        providers=[
            ProviderConfig(
                name="test-vllm",
                type="vllm",
                model="test-model",
                enabled=True,
                settings={
                    "endpoint": "http://localhost:9999",  # Fake endpoint
                    "timeout": 5.0,
                },
            )
        ],
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )


@pytest.fixture
async def test_router(test_router_config):
    """Create test router."""
    router = RouterOrchestrator(test_router_config)
    await router.initialize()
    yield router
    router.shutdown()


@pytest.fixture
def test_app(test_router, test_router_config):
    """Create test FastAPI app."""
    telemetry = InMemoryTelemetry()
    return create_app(test_router, test_router_config, telemetry)


@pytest.mark.integration
def test_root_endpoint(test_app):
    """Root path advertises the public endpoints."""
    client = TestClient(test_app)
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Inference Router API"
    assert data["endpoints"]["metrics"] == "/v1/metrics"
    assert data["endpoints"]["chat"] == "/v1/chat/completions"


@pytest.mark.integration
def test_health_endpoint(test_app):
    """Test health check endpoint."""
    client = TestClient(test_app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "concurrency" in data
    assert "active_requests" in data["concurrency"]


@pytest.mark.integration
def test_health_detailed_endpoint(test_app):
    """Test detailed health check endpoint."""
    client = TestClient(test_app)
    response = client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers" in data


@pytest.mark.integration
def test_list_models_endpoint(test_app):
    """``/v1/models`` reports backend model names with provider in ``owned_by``."""
    client = TestClient(test_app)
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    ids = [m["id"] for m in body["data"]]
    # Provider configured with model="test-model" plus the "auto" virtual model.
    assert "test-model" in ids
    assert "auto" in ids
    # ``owned_by`` carries the provider name for each provider entry.
    test_model_entry = next(m for m in body["data"] if m["id"] == "test-model")
    assert test_model_entry["owned_by"] == "test-vllm"


@pytest.mark.integration
def test_chat_completions_invalid_request(test_app):
    """Test chat completions with invalid request."""
    client = TestClient(test_app)

    # Missing required fields
    response = client.post("/v1/chat/completions", json={})

    assert response.status_code == 422  # Validation error
    # Custom validation handler echoes the offending body so 422s are debuggable.
    body = response.json()
    assert body["error"]["type"] == "RequestValidationError"


@pytest.mark.integration
def test_metrics_endpoint(test_app):
    """``/v1/metrics`` returns the per-provider telemetry shape."""
    client = TestClient(test_app)
    response = client.get("/v1/metrics")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {"routing_stats", "token_metrics", "latency_metrics"}
    assert "by_provider" in data["token_metrics"]
    assert "overall" in data["token_metrics"]


@pytest.mark.integration
def test_metrics_reset_endpoint(test_app):
    """``/v1/metrics/reset`` clears telemetry."""
    client = TestClient(test_app)
    response = client.post("/v1/metrics/reset")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.integration
def test_list_plugins_endpoint(test_app):
    """Test list plugins endpoint."""
    client = TestClient(test_app)
    response = client.get("/v1/plugins")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)


@pytest.mark.integration
def test_get_plugin_by_name_and_node(test_app):
    """Test get plugin endpoint."""
    client = TestClient(test_app)

    # First list all plugins to find one
    list_response = client.get("/v1/plugins")
    assert list_response.status_code == 200

    plugins = list_response.json()["data"]
    if plugins:
        # Get first plugin
        plugin = plugins[0]
        response = client.get(f"/v1/plugins/{plugin['name']}/{plugin['node']}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == plugin["name"]
        assert data["node"] == plugin["node"]
        assert "settings" in data
        assert "extra_config" in data["settings"]


@pytest.mark.integration
def test_get_nonexistent_plugin(test_app):
    """Test get nonexistent plugin returns 404."""
    client = TestClient(test_app)
    response = client.get("/v1/plugins/nonexistent/unknown")

    assert response.status_code == 404


@pytest.mark.integration
def test_update_plugin_settings(test_app):
    """Test update plugin settings endpoint."""
    client = TestClient(test_app)

    # First list plugins
    list_response = client.get("/v1/plugins")
    plugins = list_response.json()["data"]

    if plugins:
        plugin = plugins[0]
        # Update plugin settings
        update_data = {
            "settings": {
                "extra_config": {"key": "value"}
            }
        }
        response = client.put(
            f"/v1/plugins/{plugin['name']}/{plugin['node']}",
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["extra_config"] == {"key": "value"}


@pytest.mark.integration
def test_create_or_update_plugin(test_app):
    """Test create/update plugin endpoint."""
    client = TestClient(test_app)

    # First list plugins
    list_response = client.get("/v1/plugins")
    plugins = list_response.json()["data"]

    if plugins:
        plugin = plugins[0]
        # Create or update plugin
        update_data = {
            "settings": {
                "extra_config": {"test": "data"}
            }
        }
        response = client.post(
            f"/v1/plugins/{plugin['name']}/{plugin['node']}",
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == plugin["name"]
        assert data["node"] == plugin["node"]
