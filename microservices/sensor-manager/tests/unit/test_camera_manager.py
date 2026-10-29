# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import cast
from unittest.mock import MagicMock

import pytest

from src.core.camera_manager import CameraManager, CameraNotFoundError
from src.core.internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalCameraType,
    InternalGigECameraDetails,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
)

NET_ID = "network-camera-192.168.1.100-80"
GIGE_ID = "gige-camera-basler-aca1300-30gm-21234567"


def _gige(device_id=GIGE_ID):
    return InternalCamera(
        device_id=device_id,
        device_name="Basler acA1300-30gm",
        device_type=InternalCameraType.GIGE,
        details=InternalGigECameraDetails(ip="192.168.10.20", vendor="Basler", serial="21234567"),
    )


def _usb(device_id="usb-camera-cam-0", path="/dev/video0"):
    return InternalCamera(
        device_id=device_id,
        device_name="Cam",
        device_type=InternalCameraType.USB,
        details=InternalUSBCameraDetails(device_path=path),
    )


def _net(device_id=NET_ID, profiles=None):
    return InternalCamera(
        device_id=device_id,
        device_name="ONVIF Camera 192.168.1.100",
        device_type=InternalCameraType.NETWORK,
        details=InternalNetworkCameraDetails(ip="192.168.1.100", port=80, profiles=profiles or []),
    )


@pytest.fixture
def usb_discovery():
    return MagicMock()


@pytest.fixture
def onvif_discovery():
    return MagicMock()


@pytest.fixture
def gige_discovery():
    return MagicMock()


@pytest.fixture
def manager(usb_discovery, onvif_discovery, gige_discovery):
    usb_discovery.discover_cameras.return_value = []
    onvif_discovery.discover_cameras.return_value = []
    gige_discovery.discover_cameras.return_value = []
    return CameraManager(usb_discovery, onvif_discovery, gige_discovery)


def test_discover_all_combines_usb_network_and_gige(
    manager, usb_discovery, onvif_discovery, gige_discovery
):
    usb_discovery.discover_cameras.return_value = [_usb()]
    onvif_discovery.discover_cameras.return_value = [_net()]
    gige_discovery.discover_cameras.return_value = [_gige()]

    ids = [c.device_id for c in manager.discover_all_cameras()]

    assert ids == ["usb-camera-cam-0", NET_ID, GIGE_ID]


def test_gige_discovery_error_keeps_cache(manager, gige_discovery):
    gige_discovery.discover_cameras.return_value = [_gige()]
    manager.discover_gige_cameras()
    gige_discovery.discover_cameras.side_effect = RuntimeError("boom")

    assert [c.device_id for c in manager.discover_gige_cameras()] == [GIGE_ID]


def test_gige_details_are_refreshed_under_same_id(manager, gige_discovery):
    busy = InternalCamera(
        device_id=GIGE_ID,
        device_name="GigE Camera 192.168.10.20",
        device_type=InternalCameraType.GIGE,
        details=InternalGigECameraDetails(ip="192.168.10.20"),
    )
    gige_discovery.discover_cameras.return_value = [busy]
    manager.discover_gige_cameras()
    gige_discovery.discover_cameras.return_value = [_gige()]

    cameras = manager.discover_gige_cameras()

    assert [c.device_id for c in cameras] == [GIGE_ID]
    assert cast(InternalGigECameraDetails, cameras[0].details).serial == "21234567"


def test_get_gige_camera_by_id(manager, gige_discovery):
    gige_discovery.discover_cameras.return_value = [_gige()]

    camera = manager.get_camera_by_id(GIGE_ID)

    assert camera is not None
    assert camera.device_type == InternalCameraType.GIGE


def test_load_camera_profiles_rejects_gige_id(manager, onvif_discovery):
    with pytest.raises(ValueError):
        manager.load_camera_profiles(GIGE_ID, "admin", "secret")
    onvif_discovery.load_camera_profiles.assert_not_called()


def test_cache_removes_vanished_and_adds_new(manager, usb_discovery):
    usb_discovery.discover_cameras.return_value = [_usb("a"), _usb("b")]
    manager.discover_usb_cameras()
    usb_discovery.discover_cameras.return_value = [_usb("b"), _usb("c")]

    assert [c.device_id for c in manager.discover_usb_cameras()] == ["b", "c"]


def test_discovery_error_keeps_cache(manager, usb_discovery):
    usb_discovery.discover_cameras.return_value = [_usb()]
    manager.discover_usb_cameras()
    usb_discovery.discover_cameras.side_effect = RuntimeError("boom")

    assert [c.device_id for c in manager.discover_usb_cameras()] == ["usb-camera-cam-0"]


def test_get_camera_by_id_refreshes_on_miss(manager, onvif_discovery):
    onvif_discovery.discover_cameras.return_value = [_net()]

    camera = manager.get_camera_by_id(NET_ID)

    assert camera is not None
    assert camera.device_id == NET_ID
    assert manager.get_camera_by_id("missing") is None


def test_load_camera_profiles_updates_cache_and_survives_rediscovery(manager, onvif_discovery):
    onvif_discovery.discover_cameras.return_value = [_net()]
    profile = InternalCameraProfileInfo(name="Main", rtsp_url="rtsp://192.168.1.100/main")
    onvif_discovery.load_camera_profiles.return_value = _net(profiles=[profile])

    loaded = manager.load_camera_profiles(NET_ID, "admin", "secret")

    onvif_discovery.load_camera_profiles.assert_called_once_with(NET_ID, "admin", "secret")
    assert cast(InternalNetworkCameraDetails, loaded.details).profiles == [profile]
    cached = manager.discover_network_cameras()
    assert cast(InternalNetworkCameraDetails, cached[0].details).profiles == [profile]


def test_load_camera_profiles_rejects_non_network_id(manager, onvif_discovery):
    with pytest.raises(ValueError):
        manager.load_camera_profiles("usb-camera-cam-0", "admin", "secret")
    onvif_discovery.load_camera_profiles.assert_not_called()


def test_load_camera_profiles_unknown_camera(manager, onvif_discovery):
    with pytest.raises(CameraNotFoundError):
        manager.load_camera_profiles(NET_ID, "admin", "secret")
    onvif_discovery.load_camera_profiles.assert_not_called()


def test_load_camera_profiles_propagates_errors(manager, onvif_discovery):
    onvif_discovery.discover_cameras.return_value = [_net()]
    onvif_discovery.load_camera_profiles.side_effect = ConnectionError("down")

    with pytest.raises(ConnectionError):
        manager.load_camera_profiles(NET_ID, "admin", "secret")
