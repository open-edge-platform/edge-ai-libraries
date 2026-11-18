# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import cast
from unittest.mock import patch

import pytest
from dlstreamer.onvif import CameraProfilesResult, ONVIFProfile

from src.core.internal_types import InternalCameraType, InternalNetworkCameraDetails
from src.core.onvif import (
    CameraAuthError,
    CameraUnreachableError,
    ONVIFCameraDiscovery,
    parse_network_camera_id,
)

DISCOVER = "src.core.onvif.discover_onvif_cameras"
READ_PROFILES = "src.core.onvif.read_camera_profiles"
CAMERA_ID = "network-camera-192.168.1.100-80"


def _profile(name, rtsp_url, width=1920, height=1080, encoding="H264", fps=30, bitrate=4096):
    return ONVIFProfile(
        name=name,
        token=f"{name}-token",
        rtsp_url=rtsp_url,
        vec_encoding=encoding,
        vec_resolution={"width": width, "height": height} if width else {},
        vec_framerate_limit=fps,
        vec_bitrate_limit=bitrate,
        username="admin",
        password="secret",
    )


def test_parse_network_camera_id():
    assert parse_network_camera_id(CAMERA_ID) == ("192.168.1.100", 80)
    assert parse_network_camera_id("network-camera-cam-1.local-8080") == ("cam-1.local", 8080)


@pytest.mark.parametrize(
    "camera_id",
    ["invalid_id", "network-camera-", "network-camera-192.168.1.100-abc", "network-camera-h-0"],
)
def test_parse_network_camera_id_rejects_invalid(camera_id):
    with pytest.raises(ValueError):
        parse_network_camera_id(camera_id)


@patch(DISCOVER)
def test_scan_once_stores_deduplicated_endpoints(mock_discover):
    mock_discover.return_value = iter(
        [
            {"hostname": "192.168.1.101", "port": 8080},
            {"hostname": "192.168.1.100", "port": 80},
            {"hostname": "192.168.1.100", "port": 80},
            {"hostname": None, "port": 80},
        ]
    )
    discovery = ONVIFCameraDiscovery()
    discovery.scan_once()

    cameras = discovery.discover_cameras()

    assert [c.device_id for c in cameras] == [
        "network-camera-192.168.1.100-80",
        "network-camera-192.168.1.101-8080",
    ]
    camera = cameras[0]
    assert camera.device_name == "ONVIF Camera 192.168.1.100"
    assert camera.device_type == InternalCameraType.NETWORK
    details = cast(InternalNetworkCameraDetails, camera.details)
    assert (details.ip, details.port, details.profiles, details.best_profile) == (
        "192.168.1.100",
        80,
        [],
        None,
    )


@patch(DISCOVER)
def test_scan_once_keeps_previous_result_on_failure(mock_discover):
    discovery = ONVIFCameraDiscovery()
    mock_discover.return_value = iter([{"hostname": "10.0.0.1", "port": 80}])
    discovery.scan_once()

    mock_discover.side_effect = OSError("network down")
    discovery.scan_once()

    assert [c.device_id for c in discovery.discover_cameras()] == ["network-camera-10.0.0.1-80"]


@patch(DISCOVER)
def test_scan_once_replaces_result_with_latest_sweep(mock_discover):
    discovery = ONVIFCameraDiscovery()
    mock_discover.return_value = iter([{"hostname": "10.0.0.1", "port": 80}])
    discovery.scan_once()
    mock_discover.return_value = iter([])
    discovery.scan_once()

    assert discovery.discover_cameras() == []


@patch(DISCOVER, return_value=iter([]))
def test_start_and_stop_background_thread(_mock_discover):
    discovery = ONVIFCameraDiscovery(interval_s=1)
    discovery.start()
    discovery.start()
    discovery.stop()
    assert discovery._thread is None


@patch(READ_PROFILES)
def test_load_camera_profiles_maps_profiles_and_selects_best(mock_read):
    mock_read.return_value = iter(
        [
            CameraProfilesResult(
                hostname="192.168.1.100",
                port=80,
                profiles=[
                    _profile("Sub", "rtsp://192.168.1.100:554/sub", 640, 360, fps=15),
                    _profile("Main", "rtsp://192.168.1.100:554/main"),
                ],
            )
        ]
    )

    camera = ONVIFCameraDiscovery().load_camera_profiles(CAMERA_ID, "admin", "secret")

    mock_read.assert_called_once_with(
        [{"hostname": "192.168.1.100", "port": 80}], username="admin", password="secret"
    )
    assert camera.device_id == CAMERA_ID
    details = cast(InternalNetworkCameraDetails, camera.details)
    assert [p.name for p in details.profiles] == ["Sub", "Main"]
    main = details.profiles[1]
    assert (main.rtsp_url, main.resolution, main.encoding, main.framerate, main.bitrate) == (
        "rtsp://192.168.1.100:554/main",
        "1920x1080",
        "H264",
        30,
        4096,
    )
    assert details.best_profile is not None
    assert details.best_profile.name == "Main"
    assert not hasattr(details, "password")


@patch(READ_PROFILES)
def test_load_camera_profiles_without_resolution(mock_read):
    mock_read.return_value = iter(
        [
            CameraProfilesResult(
                hostname="192.168.1.100",
                port=80,
                profiles=[_profile("P", "rtsp://x/1", width=0)],
            )
        ]
    )
    camera = ONVIFCameraDiscovery().load_camera_profiles(CAMERA_ID, "admin", "secret")
    details = cast(InternalNetworkCameraDetails, camera.details)
    assert details.profiles[0].resolution is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("ONVIFError: Unknown error: Sender not Authorized", CameraAuthError),
        ("ONVIFError: Unknown error: 401 Client Error: Unauthorized", CameraAuthError),
        (
            "ONVIFError: Unknown error: HTTPConnectionPool(host='192.168.1.100', port=80): "
            "Max retries exceeded with url: /onvif/device_service",
            CameraUnreachableError,
        ),
        ("ONVIFError: Unknown error: timed out", CameraUnreachableError),
        ("ONVIFError: Unknown error: Device doesn`t support service: media", RuntimeError),
    ],
)
@patch(READ_PROFILES)
def test_load_camera_profiles_classifies_errors(mock_read, error, expected):
    mock_read.return_value = iter(
        [CameraProfilesResult(hostname="192.168.1.100", port=80, error=error)]
    )
    with pytest.raises(expected):
        ONVIFCameraDiscovery().load_camera_profiles(CAMERA_ID, "admin", "wrong")


@patch(READ_PROFILES)
def test_load_camera_profiles_rejects_invalid_id(mock_read):
    with pytest.raises(ValueError):
        ONVIFCameraDiscovery().load_camera_profiles("usb-camera-x-0", "admin", "secret")
    mock_read.assert_not_called()
