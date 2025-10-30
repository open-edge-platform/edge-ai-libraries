# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.core.util import extract_video_metadata

def test_extract_video_metadata(mocker, tmp_path):
    """
    Test the functionality to generate metadata for videos having details in config file.
    """
    video_id: str = "some-video-id"
    filename: str = "some-video.mp4"
    bucket_name: str = "some-bucket"

    fps: float = 20.0
    frames: int = 600
    mock_intervals = [(0, 200, 0, 5), (200, 400, 10, 15), (400, 600, 20, 25)]
    chunk_duration = 10
    clip_duration = 5

    mock_get_video_fps = mocker.patch("src.core.util.get_video_fps_and_frames", return_value=(fps, frames))
    mock_calc_intervals = mocker.patch("src.core.util.calculate_intervals", return_value=mock_intervals)

    result = extract_video_metadata(
        temp_video_path=tmp_path, 
        bucket_name=bucket_name, 
        video_id=video_id,
        video_filename=filename,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
    )

    # Type of response should be dict. Num of items in dict should be total num of intervals in all videos taken together.
    assert type(result) is dict
    assert len(result) == len(mock_intervals)

    # Assertion for the mocked function call count and call parameters
    mock_get_video_fps.assert_called_once_with(tmp_path)
    mock_calc_intervals.assert_called_with(fps, frames, chunk_duration, clip_duration)

    # Asserting the result values
    for _, (_, data) in enumerate(result.items()):
        assert data["fps"] == int(fps)
        assert data["total_frames"] == frames
        assert data["bucket_name"] == bucket_name
        assert data["clip_duration"] == clip_duration
        assert data["frames_in_clip"] == frames/len(mock_intervals)
        assert data["video_id"] == video_id
        assert data["video"] == filename
        assert data["video_remote_path"] == f"{video_id}/{filename}"

def test_calc_intervals_not_called(mocker, tmp_path):
    """
    Test the functionality to generate metadata function when no intervals are returned 
    from calculate_intervals function.
    """
    video_id: str = "some-video-id"
    filename: str = "some-video.mp4"
    bucket_name: str = "some-bucket"

    fps: float = 20.0
    frames: int = 600

    # Chunk duration is greater than clip duration, so no intervals should be returned.   
    chunk_duration = 10
    clip_duration = 15

    mock_get_video_fps = mocker.patch("src.core.util.get_video_fps_and_frames", return_value=(fps, frames))
    mock_calc_intervals = mocker.patch("src.core.util.calculate_intervals", return_value=[])

    new_result = extract_video_metadata(
        temp_video_path=tmp_path, 
        bucket_name=bucket_name, 
        video_id=video_id,
        video_filename=filename,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
    )

    mock_get_video_fps.assert_called_once_with(tmp_path)
    mock_calc_intervals.assert_not_called()

    assert len(new_result) == 0
    assert new_result == {}

