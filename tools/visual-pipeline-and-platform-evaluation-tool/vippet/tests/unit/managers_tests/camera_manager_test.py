# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import unittest
from typing import cast

import httpx

from internal_types import (
    InternalCameraType,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
)
from managers.camera_manager import CameraManager, CameraServiceError

NET_ID = "network-camera-192.168.1.100-80"
MAIN_URL = "rtsp://192.168.1.100:554/main"

USB_CAMERA = {
    "device_id": "usb-camera-integrated-camera-0",
    "device_name": "Integrated Camera",
    "device_type": "USB",
    "details": {
        "device_path": "/dev/video0",
        "best_capture": {"fourcc": "MJPG", "width": 1920, "height": 1080, "fps": 30.0},
    },
}
NET_CAMERA = {
    "device_id": NET_ID,
    "device_name": "ONVIF Camera 192.168.1.100",
    "device_type": "NETWORK",
    "details": {
        "ip": "192.168.1.100",
        "port": 80,
        "profiles": [],
        "best_profile": None,
    },
}
MAIN_PROFILE = {
    "name": "Main",
    "rtsp_url": MAIN_URL,
    "resolution": "1920x1080",
    "encoding": "H265",
    "framerate": 30,
    "bitrate": 4096,
}
NET_CAMERA_WITH_PROFILES = {
    **NET_CAMERA,
    "details": {
        **NET_CAMERA["details"],
        "profiles": [MAIN_PROFILE],
        "best_profile": MAIN_PROFILE,
    },
}


class TestCameraManager(unittest.TestCase):
    """Unit tests for the sensor-manager backed CameraManager."""

    def setUp(self):
        CameraManager._instance = None
        self.requests: list[httpx.Request] = []
        self.sensors: list[dict] = [USB_CAMERA, NET_CAMERA]
        self.profiles_response = httpx.Response(
            200, json={"camera": NET_CAMERA_WITH_PROFILES}
        )
        self.manager = CameraManager()
        self.manager._transport = httpx.MockTransport(self._handle)

    def tearDown(self):
        CameraManager._instance = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and request.url.path == "/api/v1/sensors":
            return httpx.Response(200, json=self.sensors)
        if request.method == "POST" and request.url.path.endswith("/profiles"):
            return self.profiles_response
        return httpx.Response(404, json={"detail": "not found"})

    def _fail_transport(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def test_singleton(self):
        self.assertIs(CameraManager(), self.manager)

    def test_discover_all_cameras_parses_sensors(self):
        cameras = self.manager.discover_all_cameras()

        self.assertEqual(self.requests[0].url.path, "/api/v1/sensors")
        self.assertEqual(
            [c.device_type for c in cameras],
            [InternalCameraType.USB, InternalCameraType.NETWORK],
        )
        usb = cast(InternalUSBCameraDetails, cameras[0].details)
        self.assertEqual(usb.device_path, "/dev/video0")
        assert usb.best_capture is not None
        self.assertEqual(usb.best_capture.fourcc, "MJPG")
        net = cast(InternalNetworkCameraDetails, cameras[1].details)
        self.assertEqual((net.ip, net.port, net.profiles), ("192.168.1.100", 80, []))

    def test_discover_all_cameras_returns_cache_when_service_unavailable(self):
        self.manager.discover_all_cameras()
        self.manager._transport = httpx.MockTransport(self._fail_transport)

        cameras = self.manager.discover_all_cameras()

        self.assertEqual(len(cameras), 2)

    def test_discover_all_cameras_handles_invalid_payload(self):
        self.sensors = [{"device_id": "broken"}]
        self.assertEqual(self.manager.discover_all_cameras(), [])

    def test_get_camera_by_id_uses_cache_only(self):
        self.assertIsNone(self.manager.get_camera_by_id(NET_ID))
        self.manager.discover_all_cameras()
        request_count = len(self.requests)

        camera = self.manager.get_camera_by_id(NET_ID)

        assert camera is not None
        self.assertEqual(camera.device_id, NET_ID)
        self.assertEqual(len(self.requests), request_count)

    def test_get_usb_camera_details_by_device_path(self):
        self.manager.discover_all_cameras()

        details = self.manager.get_usb_camera_details_by_device_path("/dev/video0")

        assert details is not None
        assert details.best_capture is not None
        self.assertEqual(details.best_capture.fourcc, "MJPG")
        self.assertIsNone(
            self.manager.get_usb_camera_details_by_device_path("/dev/video9")
        )
        self.assertIsNone(self.manager.get_usb_camera_details_by_device_path(""))

    def test_load_camera_profiles_posts_credentials_and_caches_them(self):
        self.manager.discover_all_cameras()

        camera = self.manager.load_camera_profiles(NET_ID, "admin", "secret")

        post = self.requests[-1]
        self.assertEqual(post.url.path, f"/api/v1/sensors/{NET_ID}/profiles")
        self.assertEqual(
            json.loads(post.content), {"username": "admin", "password": "secret"}
        )
        net = cast(InternalNetworkCameraDetails, camera.details)
        self.assertEqual((net.username, net.password), ("admin", "secret"))

        details = self.manager.get_network_camera_details_by_rtsp_url(f" {MAIN_URL} ")
        assert details is not None
        self.assertEqual((details.username, details.password), ("admin", "secret"))
        self.assertEqual(self.manager.get_encoding_for_rtsp_url(MAIN_URL), "H265")
        self.assertIsNone(self.manager.get_encoding_for_rtsp_url("rtsp://other/stream"))

    def test_credentials_survive_rediscovery(self):
        self.manager.discover_all_cameras()
        self.manager.load_camera_profiles(NET_ID, "admin", "secret")
        self.sensors = [USB_CAMERA, NET_CAMERA_WITH_PROFILES]

        self.manager.discover_all_cameras()

        details = self.manager.get_network_camera_details_by_rtsp_url(MAIN_URL)
        assert details is not None
        self.assertEqual((details.username, details.password), ("admin", "secret"))

    def test_credentials_dropped_when_camera_disappears(self):
        self.manager.discover_all_cameras()
        self.manager.load_camera_profiles(NET_ID, "admin", "secret")
        self.sensors = [USB_CAMERA]
        self.manager.discover_all_cameras()
        self.sensors = [USB_CAMERA, NET_CAMERA_WITH_PROFILES]

        self.manager.discover_all_cameras()

        details = self.manager.get_network_camera_details_by_rtsp_url(MAIN_URL)
        assert details is not None
        self.assertIsNone(details.username)
        self.assertIsNone(details.password)

    def test_load_camera_profiles_raises_service_error_with_status(self):
        for status, body, detail in [
            (
                401,
                {"detail": "Failed to load profiles - invalid credentials"},
                "invalid credentials",
            ),
            (404, {"detail": "Camera not reachable"}, "Camera not reachable"),
            (422, {"detail": [{"msg": "too long"}]}, "Invalid camera request"),
        ]:
            self.profiles_response = httpx.Response(status, json=body)
            with self.assertRaises(CameraServiceError) as ctx:
                self.manager.load_camera_profiles(NET_ID, "admin", "wrong")
            self.assertEqual(ctx.exception.status_code, status)
            self.assertIn(detail, ctx.exception.detail)
        self.assertIsNone(self.manager.get_camera_by_id(NET_ID))

    def test_load_camera_profiles_service_unavailable(self):
        self.manager._transport = httpx.MockTransport(self._fail_transport)

        with self.assertRaises(CameraServiceError) as ctx:
            self.manager.load_camera_profiles(NET_ID, "admin", "secret")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "Camera service unavailable")

    def test_load_camera_profiles_escapes_camera_id(self):
        self.manager.load_camera_profiles("network-camera-a/b-80", "admin", "secret")
        self.assertEqual(
            self.requests[-1].url.raw_path,
            b"/api/v1/sensors/network-camera-a%2Fb-80/profiles",
        )


if __name__ == "__main__":
    unittest.main()
