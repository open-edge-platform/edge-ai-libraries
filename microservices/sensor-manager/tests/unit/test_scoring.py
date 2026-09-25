# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.core.internal_types import (
    InternalCameraProfileInfo,
    InternalV4L2Format,
    InternalV4L2FormatSize,
)
from src.core.scoring import (
    score_capture_candidate,
    select_best_from_v4l2_formats,
    select_best_profile,
)


def _fmt(fourcc, width, height, fps_list):
    return InternalV4L2Format(
        fourcc=fourcc,
        sizes=[InternalV4L2FormatSize(width=width, height=height, fps_list=fps_list)],
    )


def test_score_h264_1080p_30fps_is_max():
    assert abs(score_capture_candidate("H264", 1920, 1080, 30.0) - 1.0) < 0.01


def test_score_mjpg_720p_15fps_is_mid():
    score = score_capture_candidate("MJPG", 1280, 720, 15.0)
    assert 0.5 < score < 0.7


def test_score_yuyv_low_fps_is_low():
    assert score_capture_candidate("YUYV", 640, 480, 5.0) < 0.4


def test_select_best_from_empty_formats():
    assert select_best_from_v4l2_formats([]) is None


def test_select_best_single_format():
    result = select_best_from_v4l2_formats([_fmt("MJPG", 1920, 1080, [30.0])])
    assert result is not None
    assert (result.fourcc, result.width, result.height, result.fps) == ("MJPG", 1920, 1080, 30.0)


def test_select_best_prefers_h264():
    result = select_best_from_v4l2_formats(
        [_fmt("MJPG", 1920, 1080, [30.0]), _fmt("H264", 1920, 1080, [30.0])]
    )
    assert result is not None
    assert result.fourcc == "H264"


def test_select_best_prefers_acceptable_fps():
    result = select_best_from_v4l2_formats(
        [_fmt("H264", 1920, 1080, [5.0]), _fmt("MJPG", 1280, 720, [30.0])]
    )
    assert result is not None
    assert (result.fourcc, result.fps) == ("MJPG", 30.0)


def test_select_best_profile_empty():
    assert select_best_profile([]) is None


def test_select_best_profile_skips_missing_rtsp_url():
    profiles = [
        InternalCameraProfileInfo(
            name="P1", rtsp_url="", resolution="1920x1080", encoding="H264", framerate=30
        )
    ]
    assert select_best_profile(profiles) is None


def test_select_best_profile_picks_highest_score():
    profiles = [
        InternalCameraProfileInfo(
            name="LowRes",
            rtsp_url="rtsp://192.168.1.100/low",
            resolution="640x480",
            encoding="MJPEG",
            framerate=15,
        ),
        InternalCameraProfileInfo(
            name="HighRes",
            rtsp_url="rtsp://192.168.1.100/high",
            resolution="1920x1080",
            encoding="H264",
            framerate=30,
        ),
    ]
    result = select_best_profile(profiles)
    assert result is not None
    assert result.name == "HighRes"
