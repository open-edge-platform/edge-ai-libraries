# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import health, sensors
from src.core.camera_manager import CameraNotFoundError
from src.core.internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalCameraType,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
    InternalV4L2BestCapture,
)
from src.core.onvif import CameraAuthError, CameraUnreachableError

NET_ID = "network-camera-192.168.1.100-80"
CREDS = {"username": "admin", "password": "secret"}


def _usb_camera():
    return InternalCamera(
        device_id="usb-camera-integrated-camera-0",
        device_name="Integrated Camera",
        device_type=InternalCameraType.USB,
        details=InternalUSBCameraDetails(
            device_path="/dev/video0",
            best_capture=InternalV4L2BestCapture(fourcc="MJPG", width=1920, height=1080, fps=30),
        ),
    )


def _net_camera(profiles=None):
    profiles = profiles or []
    return InternalCamera(
        device_id=NET_ID,
        device_name="ONVIF Camera 192.168.1.100",
        device_type=InternalCameraType.NETWORK,
        details=InternalNetworkCameraDetails(
            ip="192.168.1.100",
            port=80,
            profiles=profiles,
            best_profile=profiles[0] if profiles else None,
        ),
    )


@pytest.fixture
def manager():
    return MagicMock()


@pytest.fixture
def client(manager):
    app = FastAPI()
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(sensors.router, prefix="/api/v1/sensors")
    app.state.camera_manager = manager
    return TestClient(app)


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"healthy": True}


def test_get_sensors(client, manager):
    manager.discover_all_cameras.return_value = [_usb_camera(), _net_camera()]

    response = client.get("/api/v1/sensors")

    assert response.status_code == 200
    data = response.json()
    assert [s["device_type"] for s in data] == ["USB", "NETWORK"]
    assert data[0]["details"] == {
        "device_path": "/dev/video0",
        "best_capture": {"fourcc": "MJPG", "width": 1920, "height": 1080, "fps": 30.0},
    }
    assert data[1]["details"] == {
        "ip": "192.168.1.100",
        "port": 80,
        "profiles": [],
        "best_profile": None,
    }


def test_get_sensors_empty(client, manager):
    manager.discover_all_cameras.return_value = []
    assert client.get("/api/v1/sensors").json() == []


def test_get_sensors_error(client, manager):
    manager.discover_all_cameras.side_effect = RuntimeError("boom")
    response = client.get("/api/v1/sensors")
    assert response.status_code == 500
    assert response.json() == {"message": "Unexpected error when discovering sensors"}


def test_get_sensor(client, manager):
    manager.get_camera_by_id.return_value = _net_camera()
    response = client.get(f"/api/v1/sensors/{NET_ID}")
    assert response.status_code == 200
    assert response.json()["device_id"] == NET_ID
    manager.get_camera_by_id.assert_called_once_with(NET_ID)


def test_get_sensor_not_found(client, manager):
    manager.get_camera_by_id.return_value = None
    assert client.get("/api/v1/sensors/usb-camera-x-9").status_code == 404


def test_get_sensor_rejects_invalid_id(client, manager):
    assert client.get("/api/v1/sensors/bad%20id").status_code == 422
    assert client.get("/api/v1/sensors/" + "a" * 300).status_code == 422
    manager.get_camera_by_id.assert_not_called()


def test_load_sensor_profiles(client, manager):
    profile = InternalCameraProfileInfo(
        name="Main",
        rtsp_url="rtsp://192.168.1.100:554/main",
        resolution="1920x1080",
        encoding="H264",
        framerate=30,
        bitrate=4096,
    )
    manager.load_camera_profiles.return_value = _net_camera([profile])

    response = client.post(f"/api/v1/sensors/{NET_ID}/profiles", json=CREDS)

    assert response.status_code == 200
    details = response.json()["camera"]["details"]
    assert details["best_profile"]["rtsp_url"] == "rtsp://192.168.1.100:554/main"
    assert details["profiles"][0]["resolution"] == "1920x1080"
    assert "secret" not in response.text
    manager.load_camera_profiles.assert_called_once_with(NET_ID, "admin", "secret")


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (ValueError("Invalid camera_id format"), 400, "Invalid camera_id format"),
        (CameraNotFoundError("not found"), 404, "not found"),
        (CameraAuthError("Sender not Authorized"), 401, "invalid credentials"),
        (CameraUnreachableError("timed out"), 404, "Camera not reachable"),
        (RuntimeError("zeep fault"), 500, "Unexpected error"),
    ],
)
def test_load_sensor_profiles_errors(client, manager, error, status, detail):
    manager.load_camera_profiles.side_effect = error

    response = client.post(f"/api/v1/sensors/{NET_ID}/profiles", json=CREDS)

    assert response.status_code == status
    assert detail in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"password": "secret"},
        {"username": "admin"},
        {"username": "admin", "password": "x" * 257},
    ],
)
def test_load_sensor_profiles_validates_body(client, manager, body):
    response = client.post(f"/api/v1/sensors/{NET_ID}/profiles", json=body)
    assert response.status_code == 422
    manager.load_camera_profiles.assert_not_called()
