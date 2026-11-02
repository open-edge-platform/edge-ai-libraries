# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test configuration and fixtures."""

import pytest
import asyncio

from src.config import (
    RouterConfig,
    ProviderConfig,
    TelemetryConfig,
)
from src.observability import InMemoryTelemetry


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def litellm_provider_config():
    """ProviderConfig for a hosted-vLLM backend driven via litellm."""
    return ProviderConfig(
        name="test-vllm",
        type="hosted_vllm",
        model="test-model",
        enabled=True,
        settings={
            "endpoint": "http://localhost:8000/v1",
            "timeout": 10.0,
            "auth": {"scheme": "none", "api_key": None},
        },
    )


@pytest.fixture
def provider_config(litellm_provider_config):
    """Backwards-compatible alias for tests that ask for ``provider_config``."""
    return litellm_provider_config


@pytest.fixture
def router_config(litellm_provider_config):
    """Create test router config with a single hosted_vllm provider."""
    return RouterConfig(
        providers=[litellm_provider_config],
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )


@pytest.fixture
def telemetry():
    """Create in-memory telemetry for testing."""
    return InMemoryTelemetry()


@pytest.fixture
def mock_http_response():
    """Create mock HTTP response."""
    return {
        "id": "test-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello, world!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }
