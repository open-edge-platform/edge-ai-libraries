# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-process chat endpoint tests."""

import asyncio

import pytest
import yaml
from fastapi.testclient import TestClient

from src.config import RouterConfig, ProviderConfig, PluginConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from src.router import RouterOrchestrator
from src.api.app import create_app
from src.api.v1 import _config_runtime
from src.observability import InMemoryTelemetry


@pytest.fixture
def test_router_config():
    """Create test router config.

    Includes a real ``dummy_logger`` plugin so the plugin endpoints have
    something to read/update against a live ``RouterOrchestrator``.
    """
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
        plugins=[
            PluginConfig(
                name="pre-logger",
                node="dummy_logger",
                trigger="prerouting",
                settings={"label": "pre"},
            )
        ],
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY, enabled=True),
    )


@pytest.fixture
def test_router(test_router_config):
    """Create test router."""
    router = RouterOrchestrator(test_router_config)
    asyncio.run(router.initialize())
    try:
        yield router
    finally:
        router.shutdown()


@pytest.fixture
def test_app(test_router, test_router_config, tmp_path):
    """Create test FastAPI app.

    Writes the config to a real path so plugin mutations can persist through
    ``apply_and_persist_config`` (which requires ``config_path``).
    """
    telemetry = InMemoryTelemetry()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            _config_runtime.serialize_router_config(test_router_config),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return create_app(test_router, test_router_config, telemetry, config_path=config_path)


def test_root_endpoint(test_app):
    """Root path advertises the public endpoints."""
    client = TestClient(test_app)
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Inference Router API"
    assert data["endpoints"]["metrics"] == "/v1/metrics"
    assert data["endpoints"]["chat"] == "/v1/chat/completions"


def test_health_endpoint(test_app):
    """Test health check endpoint."""
    client = TestClient(test_app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "concurrency" in data
    assert "active_requests" in data["concurrency"]


def test_health_detailed_endpoint(test_app):
    """Test detailed health check endpoint."""
    client = TestClient(test_app)
    response = client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "providers" in data


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


def test_chat_completions_invalid_request(test_app):
    """Test chat completions with invalid request."""
    client = TestClient(test_app)

    # Missing required fields
    response = client.post("/v1/chat/completions", json={})

    assert response.status_code == 422  # Validation error
    # Custom validation handler echoes the offending body so 422s are debuggable.
    body = response.json()
    assert body["error"]["type"] == "RequestValidationError"


def test_metrics_endpoint(test_app):
    """``/v1/metrics`` returns the per-provider telemetry shape."""
    client = TestClient(test_app)
    response = client.get("/v1/metrics")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {"routing_stats", "token_metrics", "latency_metrics"}
    assert "by_provider" in data["token_metrics"]
    assert "overall" in data["token_metrics"]


def test_metrics_reset_endpoint(test_app):
    """``/v1/metrics/reset`` clears telemetry."""
    client = TestClient(test_app)
    response = client.post("/v1/metrics/reset")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_list_plugins_endpoint(test_app):
    """List plugins reports the seeded plugin from the running config."""
    client = TestClient(test_app)
    response = client.get("/v1/plugins")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    names = {plugin["name"] for plugin in data["data"]}
    assert "pre-logger" in names


def test_get_plugin_by_name_and_node(test_app):
    """Get the seeded plugin and validate its full configuration."""
    client = TestClient(test_app)

    response = client.get("/v1/plugins/dummy_logger/pre-logger")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "pre-logger"
    assert data["node"] == "dummy_logger"
    assert data["trigger"] == "prerouting"
    assert data["enabled"] is True
    assert data["settings"] == {"label": "pre"}


def test_get_nonexistent_plugin(test_app):
    """Test get nonexistent plugin returns 404."""
    client = TestClient(test_app)
    response = client.get("/v1/plugins/unknown/nonexistent")

    assert response.status_code == 404


def test_update_plugin_settings(test_app):
    """Updating a plugin changes the response and the live runtime state."""
    client = TestClient(test_app)

    response = client.post(
        "/v1/plugins/dummy_logger/pre-logger",
        json={"enabled": False, "settings": {"label": "updated"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["settings"] == {"label": "updated"}

    # A subsequent GET reads from the swapped-in runtime config, proving the
    # update took effect and was not just echoed back.
    follow = client.get("/v1/plugins/dummy_logger/pre-logger").json()
    assert follow["enabled"] is False
    assert follow["settings"] == {"label": "updated"}


def test_create_or_update_plugin(test_app):
    """Creating a plugin returns it and makes it visible in the runtime listing."""
    client = TestClient(test_app)

    response = client.post(
        "/v1/plugins/dummy_logger/post-logger",
        json={"trigger": "postresponse", "settings": {"label": "created"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "post-logger"
    assert data["node"] == "dummy_logger"
    assert data["trigger"] == "postresponse"
    assert data["settings"] == {"label": "created"}

    # The newly created plugin now appears alongside the seeded one.
    names = {plugin["name"] for plugin in client.get("/v1/plugins").json()["data"]}
    assert {"pre-logger", "post-logger"} <= names
