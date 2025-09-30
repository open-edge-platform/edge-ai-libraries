# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import pytest

from src.core.util import (
    calculate_intervals,
    extract_video_metadata,
    get_video_fps_and_frames,
    sanitize_input,
)


def test_sanitize_input():
    """Test how sanitize_input validator should behave on several inputs."""
    assert sanitize_input("") == None
    assert sanitize_input("  ") == None
    assert sanitize_input("test") == "test"
    assert sanitize_input("  test  ") == "test"


def test_get_video_fps_and_frames(mocker, tmp_path):
    """
    Test whether get_video_fps_and_frames can produce frames and fps properly
    """

    # Used to mock differing values based on parameters to cap.get()
    def mock_cap_get(val):
        if val == cv2.CAP_PROP_FPS:
            return 20.5
        elif val == cv2.CAP_PROP_FRAME_COUNT:
            return 200

    mock_cv2 = mocker.MagicMock()
    mock_cv2.isOpened.return_value = True
    mock_cv2.release.return_value = None
    mock_cv2.get.side_effect = mock_cap_get
    mocker.patch("cv2.VideoCapture", return_value=mock_cv2)

    fps, frames = get_video_fps_and_frames(tmp_path)
    assert type(fps) is float
    assert type(frames) is int
    assert fps == 20.5
    assert frames == 200


def test_get_video_fps_and_frames_exception(mocker, tmp_path):
    """
    Test whether get_video_fps_and_frames() raises an exception when video
    can't be opened.
    """
    mock_cv2 = mocker.MagicMock()
    mock_cv2.isOpened.return_value = None
    mocker.patch("cv2.VideoCapture", return_value=mock_cv2)

    with pytest.raises(Exception):
        get_video_fps_and_frames(tmp_path)

    cv2.VideoCapture.assert_called_once_with(str(tmp_path))


def test_calculate_intervals():
    """
    Test whether calculate_intervals can return proper valid values.
    """

    fps: float = 20.0
    total_frames: int = 200
    chunk_duration: int = 30
    clip_duration: int = 10

    intervals = calculate_intervals(fps, total_frames, chunk_duration, clip_duration)
    assert type(intervals) is list
    assert len(intervals) != 0

    for interval in intervals:
        assert type(interval) == tuple
        assert len(interval) == 4
        start_frame, end_frame, start_time, end_time = interval
        assert start_frame <= end_frame
        assert start_time <= end_time
