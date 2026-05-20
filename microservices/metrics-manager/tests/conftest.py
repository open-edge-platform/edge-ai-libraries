# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""pytest configuration and fixtures for metrics-manager tests."""

from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.metrics import reset_service_metrics
from app.rate_limit import reset_rate_limiter
from app.store import reset_metrics_store


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    reset_metrics_store()
    reset_service_metrics()
    reset_rate_limiter()
    yield
    reset_metrics_store()
    reset_service_metrics()
    reset_rate_limiter()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a synchronous test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an asynchronous test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
