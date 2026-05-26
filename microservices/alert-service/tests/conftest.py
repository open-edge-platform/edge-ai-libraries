"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Ensure settings pick up test-friendly defaults before import
os.environ.setdefault("CONFIG_PATH", "config/config.yaml")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_concealment_alert() -> dict:
    return {
        "alert_type": "CONCEALMENT",
        "metadata": {
            "poi_id": "person-001",
            "camera_id": "cam-north-01",
        },
        "timestamp": "2025-01-15T10:30:00Z",
        "source": "loss-prevention",
    }


@pytest.fixture
def sample_loitering_alert() -> dict:
    return {
        "alert_type": "LOITERING",
        "metadata": {
            "zone_id": "zone-5",
        },
        "timestamp": "2025-01-15T10:31:00Z",
    }


@pytest.fixture
def sample_intrusion_alert() -> dict:
    return {
        "alert_type": "INTRUSION",
        "metadata": {
            "zone_id": "restricted-area-1",
        },
        "timestamp": "2025-01-15T10:32:00Z",
    }


@pytest.fixture
def config_yaml_content() -> str:
    return """\
service:
  retry_attempts: 2
  retry_interval_seconds: 1

subscriptions:
  - alert_type: CONCEALMENT
    dedup:
      enabled: true
      strategy: field_hash
      fields:
        - metadata.poi_id
        - metadata.camera_id
      window_seconds: 30
      on_missing: skip
      hash:
        algorithm: sha1
        truncate: 16
    delivery:
      - type: log

  - alert_type: LOITERING
    dedup:
      enabled: true
      strategy: field_hash
      fields:
        - metadata.zone_id
      window_seconds: 120
      on_missing: skip
      hash:
        algorithm: sha1
        truncate: 16
    delivery:
      - type: log

  - alert_type: INTRUSION
    dedup:
      enabled: false
    delivery:
      - type: log
"""


@pytest.fixture
def config_file(config_yaml_content: str, tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(config_yaml_content)
    return str(p)


@pytest.fixture
async def app_client(config_file: str) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with the alert service app."""
    os.environ["CONFIG_PATH"] = config_file

    # Re-import to pick up new CONFIG_PATH
    from src.core.settings import Settings

    settings = Settings()
    settings.CONFIG_PATH = config_file

    # Patch settings at module level
    import src.core.settings as settings_module
    original = settings_module.settings
    settings_module.settings = settings

    from src.core.config import load_config
    from src.worker import AlertWorker

    config = load_config(config_file)

    app = FastAPI()
    worker = AlertWorker(config)

    from src.api.router import api_router
    app.include_router(api_router, prefix="/api/v1")
    app.state.worker = worker
    app.state.config = config

    await worker.start()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await worker.stop()
    settings_module.settings = original
