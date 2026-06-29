"""Tests for the alert API endpoints."""

from __future__ import annotations

import asyncio

import pytest

from src.delivery.ws_manager import ws_manager


class TestHealthEndpoint:
    async def test_health(self, app_client):
        """Returns 200 with status healthy."""
        response = await app_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAlertIngestion:
    async def test_accept_concealment_alert(
        self, app_client, sample_concealment_alert
    ):
        """Accepts a CONCEALMENT alert and returns accepted status."""
        response = await app_client.post(
            "/api/v1/alerts", json=sample_concealment_alert
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["alert_type"] == "CONCEALMENT"

    async def test_accept_loitering_alert(
        self, app_client, sample_loitering_alert
    ):
        """Accepts a LOITERING alert and returns accepted status."""
        response = await app_client.post(
            "/api/v1/alerts", json=sample_loitering_alert
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["alert_type"] == "LOITERING"

    async def test_accept_intrusion_alert(
        self, app_client, sample_intrusion_alert
    ):
        """Accepts an INTRUSION alert and returns accepted status."""
        response = await app_client.post(
            "/api/v1/alerts", json=sample_intrusion_alert
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["alert_type"] == "INTRUSION"

    async def test_accept_unknown_alert_type(self, app_client):
        """Accepts an unrecognised alert type gracefully."""
        response = await app_client.post(
            "/api/v1/alerts",
            json={"alert_type": "UNKNOWN_TYPE", "metadata": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    async def test_accept_minimal_payload(self, app_client):
        """Accepts a payload without alert_type, defaulting to UNKNOWN."""
        response = await app_client.post(
            "/api/v1/alerts", json={"foo": "bar"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alert_type"] == "UNKNOWN"

    async def test_duplicate_alert_still_accepted(
        self, app_client, sample_concealment_alert
    ):
        """API always returns accepted; dedup happens in the worker."""
        r1 = await app_client.post(
            "/api/v1/alerts", json=sample_concealment_alert
        )
        r2 = await app_client.post(
            "/api/v1/alerts", json=sample_concealment_alert
        )
        assert r1.status_code == 200
        assert r2.status_code == 200


class TestWebSocketEndpoint:
    def test_ws_connect_and_disconnect(self, config_file):
        """WebSocket endpoint accepts connections and handles disconnect."""
        import os
        os.environ["CONFIG_PATH"] = config_file

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.router import api_router
        from src.core.config import load_config
        from src.worker import AlertWorker

        config = load_config(config_file)
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        worker = AlertWorker(config)
        app.state.worker = worker
        app.state.config = config

        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws") as ws:
            assert ws_manager.active_count >= 1

        # After disconnect, count should be back to 0
        assert ws_manager.active_count == 0
