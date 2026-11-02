# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
from typing import cast
from unittest.mock import MagicMock, patch

from src.core.internal_types import InternalCameraType, InternalUSBCameraDetails
from src.core.usb import USBCameraDiscovery

RUN = "src.core.usb.subprocess.run"

FORMATS_1080P_MJPG = """[0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""
CAPS_VIDEO_CAPTURE = """Device Caps      : 0x84a00001
        Video Capture
        Streaming"""
CAPS_METADATA_ONLY = """Device Caps      : 0x84a00000
        Metadata Capture"""


def _result(stdout="", returncode=0):
    return MagicMock(returncode=returncode, stdout=stdout)


def _v4l2_side_effect(list_devices, caps_by_device, formats=FORMATS_1080P_MJPG):
    def side_effect(cmd, **kwargs):
        if "--list-devices" in cmd:
            return _result(list_devices)
        if "--all" in cmd:
            return _result(caps_by_device.get(cmd[2], ""))
        if "--list-formats-ext" in cmd:
            return _result(formats)
        return _result(returncode=1)

    return side_effect


def test_parse_formats_ext_output_single_format():
    output = """ioctl: VIDIOC_ENUM_FMT
    Type: Video Capture

    [0]: 'MJPG' (Motion-JPEG, compressed)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
        Size: Discrete 1280x720
            Interval: Discrete 0.033s (30.000 fps)
"""
    formats = USBCameraDiscovery._parse_formats_ext_output(output)
    assert len(formats) == 1
    assert formats[0].fourcc == "MJPG"
    assert [(s.width, s.height) for s in formats[0].sizes] == [(1920, 1080), (1280, 720)]
    assert 30.0 in formats[0].sizes[0].fps_list


def test_parse_formats_ext_output_multiple_formats():
    output = """    [0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)

    [1]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 640x480
            Interval: Discrete 0.033s (30.000 fps)
            Interval: Discrete 0.067s (15.000 fps)
"""
    formats = USBCameraDiscovery._parse_formats_ext_output(output)
    assert [f.fourcc for f in formats] == ["MJPG", "YUYV"]
    assert formats[1].sizes[0].fps_list == [30.0, 15.0]


def test_parse_formats_ext_output_empty():
    assert USBCameraDiscovery._parse_formats_ext_output("") == []


@patch(RUN)
def test_parse_v4l2_formats_calls_v4l2_ctl(mock_run):
    mock_run.return_value = _result(FORMATS_1080P_MJPG)
    formats = USBCameraDiscovery()._parse_v4l2_formats("/dev/video0")
    assert len(formats) == 1
    mock_run.assert_called_once_with(
        ["v4l2-ctl", "--device", "/dev/video0", "--list-formats-ext"],
        capture_output=True,
        text=True,
        timeout=5,
    )


@patch(RUN)
def test_parse_v4l2_formats_failure(mock_run):
    mock_run.return_value = _result(returncode=1)
    assert USBCameraDiscovery()._parse_v4l2_formats("/dev/video0") == []


@patch(RUN, side_effect=subprocess.TimeoutExpired("v4l2-ctl", 5))
def test_parse_v4l2_formats_timeout(_mock_run):
    assert USBCameraDiscovery()._parse_v4l2_formats("/dev/video0") == []


@patch(RUN)
def test_can_capture_video_true(mock_run):
    mock_run.return_value = _result(
        """Driver Info:
        Driver name      : uvcvideo
Device Caps      : 0x84a00001
        Video Capture
        Metadata Capture
        Streaming"""
    )
    assert USBCameraDiscovery()._can_capture_video("/dev/video0") is True


@patch(RUN)
def test_can_capture_video_false_for_metadata_only(mock_run):
    mock_run.return_value = _result(CAPS_METADATA_ONLY)
    assert USBCameraDiscovery()._can_capture_video("/dev/video1") is False


@patch(RUN, side_effect=subprocess.TimeoutExpired("v4l2-ctl", 3))
def test_can_capture_video_timeout(_mock_run):
    assert USBCameraDiscovery()._can_capture_video("/dev/video0") is False


@patch(RUN, side_effect=FileNotFoundError())
def test_can_capture_video_missing_tool(_mock_run):
    assert USBCameraDiscovery()._can_capture_video("/dev/video0") is False


@patch(RUN)
def test_discover_cameras_returns_capture_devices_with_best_capture(mock_run):
    mock_run.side_effect = _v4l2_side_effect(
        "Integrated Camera (usb-0000:00:14.0-8):\n\t/dev/video0\n\t/dev/video1\n",
        {"/dev/video0": CAPS_VIDEO_CAPTURE, "/dev/video1": CAPS_METADATA_ONLY},
    )

    cameras = USBCameraDiscovery().discover_cameras()

    assert len(cameras) == 1
    camera = cameras[0]
    assert camera.device_type == InternalCameraType.USB
    assert camera.device_name == "Integrated Camera"
    assert camera.device_id == "usb-camera-integrated-camera-0"
    details = cast(InternalUSBCameraDetails, camera.details)
    assert details.device_path == "/dev/video0"
    assert details.best_capture is not None
    assert (details.best_capture.fourcc, details.best_capture.fps) == ("MJPG", 30.0)


@patch(RUN)
def test_discover_cameras_skips_error_lines(mock_run):
    mock_run.side_effect = _v4l2_side_effect(
        "Cannot open device /dev/video3: Permission denied\n"
        "Integrated Camera (usb-0000:00:14.0-8):\n\t/dev/video0\n"
        "Failed to query device\n",
        {"/dev/video0": CAPS_VIDEO_CAPTURE},
    )
    cameras = USBCameraDiscovery().discover_cameras()
    assert [c.device_id for c in cameras] == ["usb-camera-integrated-camera-0"]


@patch(RUN)
def test_discover_cameras_normalizes_device_ids(mock_run):
    mock_run.side_effect = _v4l2_side_effect(
        "Thronmax StreamGo Webcam: Thron (usb-0000:00:14.0-8):\n\t/dev/video0\n",
        {"/dev/video0": CAPS_VIDEO_CAPTURE},
    )
    cameras = USBCameraDiscovery().discover_cameras()
    assert len(cameras) == 1
    assert cameras[0].device_id == "usb-camera-thronmax-streamgo-webcam-thron-0"
    assert cameras[0].device_name == "Thronmax StreamGo Webcam: Thron"


@patch(RUN, side_effect=FileNotFoundError())
def test_discover_cameras_missing_tool(_mock_run):
    assert USBCameraDiscovery().discover_cameras() == []


@patch(RUN, side_effect=subprocess.TimeoutExpired("v4l2-ctl", 5))
def test_discover_cameras_timeout(_mock_run):
    assert USBCameraDiscovery().discover_cameras() == []
