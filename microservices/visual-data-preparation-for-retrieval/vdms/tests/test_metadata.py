# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib

import src.core.util


def test_extract_video_metadata(mocker):
    """
    Test the functionality to generate metadata for videos having details in config file.
    """
    mock_config = {
        "videos_local_temp_dir": "videos_dir/",
        "videos_dir": "videos/",
        "bucket_name": "some-bucket",
    }

    fps: float = 20.0
    frames: int = 200
    mock_videos_list = ["file1.mp4", "file2.mp4"]
    mock_intervals = [(1, 50, 0, 5), (51, 100, 5, 10), (101, 150, 10, 15)]
    chunk_duration = 30
    clip_duration = 10

    mocker.patch("os.listdir", return_value=mock_videos_list)
    mocker.patch("src.core.util.get_video_fps_and_frames", return_value=(fps, frames))
    mocker.patch("src.core.util.calculate_intervals", return_value=mock_intervals)

    result = src.core.util.extract_video_metadata(mock_config, chunk_duration, clip_duration)

    # Type of response should be dict. Num of items in dict should be total num of intervals in all videos taken together.
    assert type(result) is dict
    assert len(result) == len(mock_videos_list) * len(mock_intervals)

    # Assertion for the mocked function call count and call parameters
    call_param_video_path = (
        pathlib.Path(mock_config["videos_local_temp_dir"]) / mock_videos_list[-1]
    )
    src.core.util.get_video_fps_and_frames.call_count == len(mock_videos_list)
    src.core.util.get_video_fps_and_frames.assert_called_with(call_param_video_path)
    src.core.util.calculate_intervals.assert_called_with(fps, frames, chunk_duration, clip_duration)

    # Asserting the result values
    for _, (_, data) in enumerate(result.items()):
        assert data["fps"] == int(fps)
        assert data["total_frames"] == frames
        assert data["bucket_name"] == mock_config["bucket_name"]
        assert data["clip_duration"] == 5
        assert data["frames_in_clip"] == 49
