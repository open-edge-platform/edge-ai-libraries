# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import threading
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from src.core.gige import (
    ARV_TOOL,
    GigECameraDiscovery,
    make_gige_camera_id,
    parse_device_list,
    parse_features,
)
from src.core.internal_types import InternalCameraType, InternalGigECameraDetails

LIST_OUTPUT = """Basler-acA1300-30gm-21234567 (192.168.10.20)
Aravis-USB-Cam-001 (usb:1-2)
-evil (192.168.10.21)
"""

# Format of arv-tool-0.8 (Aravis 0.8.34) output.
CONTROL_OUTPUT = """DeviceVendorName = Basler
DeviceModelName = acA1300-30gm
DeviceSerialNumber = 21234567
Feature 'DeviceID' not found
PixelFormat = Mono8
Width = 1280 min:16 max:1280
Height = 1024 min:16 max:1024
AcquisitionFrameRate = 30 min:0.1 max:1000
"""


def _completed(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def _fake_run(list_output=LIST_OUTPUT, control_output=CONTROL_OUTPUT):
    def run(args, **kwargs):
        assert args[0] == ARV_TOOL
        if len(args) == 1:
            return _completed(list_output)
        return _completed(control_output)

    return run


def test_make_gige_camera_id():
    assert make_gige_camera_id("Basler AG", "SN 123") == "gige-camera-basler-ag-sn-123"


def test_parse_device_list_keeps_only_valid_gige_devices():
    assert parse_device_list(LIST_OUTPUT) == [("Basler-acA1300-30gm-21234567", "192.168.10.20")]


def test_parse_device_list_empty():
    assert parse_device_list("No device found\n") == []


def test_parse_features_ignores_unknown_lines():
    features = parse_features(CONTROL_OUTPUT + "Foo = bar\nerror: something\n")
    assert features["DeviceVendorName"] == "Basler"
    assert "Foo" not in features


@patch("src.core.gige.subprocess.run")
def test_scan_reads_identity_and_capture(mock_run):
    mock_run.side_effect = _fake_run()
    discovery = GigECameraDiscovery()

    discovery.scan_once()
    cameras = discovery.discover_cameras()

    assert len(cameras) == 1
    camera = cameras[0]
    assert camera.device_id == "gige-camera-basler-21234567"
    assert camera.device_name == "Basler acA1300-30gm"
    assert camera.device_type == InternalCameraType.GIGE
    details = cast(InternalGigECameraDetails, camera.details)
    assert (details.ip, details.vendor, details.model, details.serial) == (
        "192.168.10.20",
        "Basler",
        "acA1300-30gm",
        "21234567",
    )
    assert details.current_capture is not None
    assert details.current_capture.pixel_format == "Mono8"
    assert (details.current_capture.width, details.current_capture.height) == (1280, 1024)
    assert details.current_capture.fps == 30.0
    control_args = mock_run.call_args_list[1].args[0]
    assert control_args[1] == "--name=Basler-acA1300-30gm-21234567"


@patch("src.core.gige.subprocess.run")
def test_scan_reads_features_once_per_device(mock_run):
    mock_run.side_effect = _fake_run()
    discovery = GigECameraDiscovery()

    discovery.scan_once()
    discovery.scan_once()

    assert mock_run.call_count == 3


@patch("src.core.gige.subprocess.run")
def test_scan_without_identity_lists_camera_and_retries(mock_run):
    mock_run.side_effect = _fake_run(control_output="")
    discovery = GigECameraDiscovery()

    discovery.scan_once()
    camera = discovery.discover_cameras()[0]

    assert camera.device_id == "gige-camera-basler-aca1300-30gm-21234567"
    details = cast(InternalGigECameraDetails, camera.details)
    assert details.serial is None
    assert details.current_capture is None

    mock_run.side_effect = _fake_run()
    discovery.scan_once()
    assert discovery.discover_cameras()[0].device_id == "gige-camera-basler-21234567"


@patch("src.core.gige.subprocess.run")
def test_scan_uses_device_id_as_serial_fallback(mock_run):
    mock_run.side_effect = _fake_run(
        control_output="DeviceVendorName = Aravis\nDeviceModelName = Fake\n"
        "Feature 'DeviceSerialNumber' not found\nDeviceID = GV01\n"
    )
    discovery = GigECameraDiscovery()

    discovery.scan_once()

    assert discovery.discover_cameras()[0].device_id == "gige-camera-aravis-gv01"


@patch("src.core.gige.subprocess.run")
def test_scan_without_size_has_no_capture(mock_run):
    mock_run.side_effect = _fake_run(
        control_output="DeviceVendorName = Basler\nDeviceSerialNumber = 1\n"
    )
    discovery = GigECameraDiscovery()

    discovery.scan_once()

    details = cast(InternalGigECameraDetails, discovery.discover_cameras()[0].details)
    assert details.model is None
    assert details.current_capture is None


@patch("src.core.gige.subprocess.run")
def test_control_timeout_keeps_camera_listed(mock_run):
    def run(args, **kwargs):
        if len(args) == 1:
            return _completed(LIST_OUTPUT)
        raise subprocess.TimeoutExpired(args, 10)

    mock_run.side_effect = run
    discovery = GigECameraDiscovery()

    discovery.scan_once()

    assert len(discovery.discover_cameras()) == 1


@pytest.mark.parametrize(
    "error", [FileNotFoundError("arv-tool-0.8"), subprocess.TimeoutExpired("arv-tool-0.8", 10)]
)
@patch("src.core.gige.subprocess.run")
def test_failed_sweep_keeps_previous_result(mock_run, error):
    mock_run.side_effect = _fake_run()
    discovery = GigECameraDiscovery()
    discovery.scan_once()

    mock_run.side_effect = error
    discovery.scan_once()

    assert [c.device_id for c in discovery.discover_cameras()] == ["gige-camera-basler-21234567"]


@patch("src.core.gige.subprocess.run")
def test_vanished_camera_is_dropped(mock_run):
    mock_run.side_effect = _fake_run()
    discovery = GigECameraDiscovery()
    discovery.scan_once()

    mock_run.side_effect = _fake_run(list_output="")
    discovery.scan_once()

    assert discovery.discover_cameras() == []


def test_start_and_stop():
    discovery = GigECameraDiscovery(interval_s=60)
    scanned = threading.Event()
    with patch.object(discovery, "scan_once", side_effect=scanned.set):
        discovery.start()
        assert scanned.wait(timeout=5)
        discovery.stop()
