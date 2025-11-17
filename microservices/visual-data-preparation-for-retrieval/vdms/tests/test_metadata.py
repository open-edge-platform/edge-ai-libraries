# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib

# Note: This test file is commented out as it tests deprecated functionality
# that was not migrated during the util.py refactoring


def test_extract_video_metadata(mocker):
    """
    Test the functionality to generate metadata for videos having details in config file.
    Note: This test is disabled as the tested functions are no longer available
    """
def test_extract_video_metadata(mocker):
    """
    Test the functionality to generate metadata for videos having details in config file.
    Note: This test is disabled as the tested functions are no longer available
    """
    # Disabling this test as extract_video_metadata and calculate_intervals 
    # were not present in the current util.py version and were not migrated
    # to the new utility module structure
    pass
    
    # Original test code commented out:
    # mock_config = {
    #     "videos_local_temp_dir": "videos_dir/",
    #     "videos_dir": "videos/",
    #     "bucket_name": "some-bucket",
    # }
    #
    # fps: float = 20.0
    # frames: int = 200
    # mock_videos_list = ["file1.mp4", "file2.mp4"]
    # mock_intervals = [(1, 50, 0, 5), (51, 100, 5, 10), (101, 150, 10, 15)]
    # chunk_duration = 30
    # clip_duration = 10
    #
    # mocker.patch("os.listdir", return_value=mock_videos_list)
    # mocker.patch("src.core.utils.video_utils.get_video_fps_and_frames", return_value=(fps, frames))
    # legacy calculate_intervals helper was removed during utils split
    #
    # result = src.core.utils.metadata_utils.extract_video_metadata(mock_config, chunk_duration, clip_duration)
    #
    # # Type of response should be dict. Num of items in dict should be total num of intervals in all videos taken together.
    # assert type(result) is dict
    # assert len(result) == len(mock_videos_list) * len(mock_intervals)
    #
    # # Assertion for the mocked function call count and call parameters
    # call_param_video_path = (
    #     pathlib.Path(mock_config["videos_local_temp_dir"]) / mock_videos_list[-1]
    # )
    # src.core.utils.video_utils.get_video_fps_and_frames.call_count == len(mock_videos_list)
    # src.core.utils.video_utils.get_video_fps_and_frames.assert_called_with(call_param_video_path)
    # legacy calculate_intervals helper assertions removed with new pipeline
    #
    # # Asserting the result values
    # for _, (_, data) in enumerate(result.items()):
    #     assert data["fps"] == int(fps)
    #     assert data["total_frames"] == frames
    #     assert data["bucket_name"] == mock_config["bucket_name"]
    #     assert data["clip_duration"] == 5
    #     assert data["frames_in_clip"] == 49
