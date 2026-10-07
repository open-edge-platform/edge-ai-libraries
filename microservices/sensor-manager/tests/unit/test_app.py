# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi.testclient import TestClient

from src.core.config import Settings


def test_settings_defaults(monkeypatch):
    for name in (
        "SENSOR_MANAGER_HOST",
        "SENSOR_MANAGER_PORT",
        "LOG_LEVEL",
        "ONVIF_DISCOVERY_ENABLED",
        "ONVIF_DISCOVERY_INTERVAL_S",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings == Settings(
        host="0.0.0.0",  # noqa: S104
        port=8090,
        log_level="INFO",
        onvif_discovery_enabled=True,
        onvif_discovery_interval_s=20.0,
    )


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SENSOR_MANAGER_HOST", "127.0.0.1")
    monkeypatch.setenv("SENSOR_MANAGER_PORT", "9100")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("ONVIF_DISCOVERY_ENABLED", "false")
    monkeypatch.setenv("ONVIF_DISCOVERY_INTERVAL_S", "5")

    settings = Settings.from_env()

    assert (settings.host, settings.port, settings.log_level) == ("127.0.0.1", 9100, "DEBUG")
    assert settings.onvif_discovery_enabled is False
    assert settings.onvif_discovery_interval_s == 5.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SENSOR_MANAGER_PORT", "0"),
        ("SENSOR_MANAGER_PORT", "70000"),
        ("ONVIF_DISCOVERY_INTERVAL_S", "0"),
    ],
)
def test_settings_rejects_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_app_lifespan_creates_camera_manager(monkeypatch):
    from src.api import main

    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            host="127.0.0.1",
            port=8090,
            log_level="INFO",
            onvif_discovery_enabled=False,
            onvif_discovery_interval_s=20.0,
        ),
    )
    monkeypatch.setattr("src.core.usb.USBCameraDiscovery.discover_cameras", lambda self: [])

    with TestClient(main.app) as client:
        assert client.get("/api/v1/health").json() == {"healthy": True}
        assert client.get("/api/v1/sensors").json() == []
