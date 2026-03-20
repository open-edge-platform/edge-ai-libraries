"""Functional tests for health and status endpoints."""

import logging

import pytest
import requests

from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

VALID_APP_STATUSES: set[str] = {"starting", "initializing", "ready", "shutdown"}


@pytest.mark.smoke
def test_health_endpoint_returns_healthy_true(http_client: requests.Session) -> None:
    """Calls GET /health and asserts the response is 200 with healthy=true."""
    response = http_client.get(f"{BASE_URL}/health", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /health, got {response.status_code}, body={response.text}"
    )
    payload = response.json()
    assert isinstance(payload, dict), "Health response must be an object"
    assert payload.get("healthy") is True, (
        f"Expected healthy=true, got {payload.get('healthy')!r}"
    )


@pytest.mark.smoke
def test_status_endpoint_returns_valid_state(http_client: requests.Session) -> None:
    """Calls GET /status and asserts the response is 200 with a valid status value and ready flag."""
    response = http_client.get(f"{BASE_URL}/status", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /status, got {response.status_code}, body={response.text}"
    )
    payload = response.json()
    assert isinstance(payload, dict), "Status response must be an object"
    assert payload.get("status") in VALID_APP_STATUSES, (
        f"Unexpected status value {payload.get('status')!r}; "
        f"expected one of {VALID_APP_STATUSES}"
    )
    assert isinstance(payload.get("ready"), bool), (
        f"Expected 'ready' to be a bool, got {payload.get('ready')!r}"
    )
    logger.info(
        "Application status: status=%s ready=%s message=%s",
        payload.get("status"),
        payload.get("ready"),
        payload.get("message"),
    )
