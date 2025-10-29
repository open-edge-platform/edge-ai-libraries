# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
from http import HTTPStatus

from src.common import Strings
from src.core.util import read_config, save_metadata_at_temp, store_video_metadata


def test_prep_data_upload_endpoint(test_client, video_file, mocker, tmp_path):
    mock_config = {
        "videos_local_temp_dir": tmp_path,
        "metadata_local_temp_dir": tmp_path,
        "cunk_duration": 30,
        "clip_duration": 10,
    }
    dummy_ids = ["idrtyyus-uevalop-itwsjl"]

    # Name of the mocked file
    filename = video_file["file"][0]
    
    # Storing common module name where all functions to be mocked are present
    endpoint_module = "src.endpoints.video_processing.upload_and_process_video"

    mock_readconfig = mocker.patch(f"{endpoint_module}.read_config", return_value=mock_config)

    # Mock datetime to have a fixed video_id value
    test_timestamp = 1697059200
    mock_datetime = mocker.MagicMock(wraps=datetime.datetime)
    mock_datetime.now.return_value.timestamp.return_value = test_timestamp
    mocker.patch(f"{endpoint_module}.datetime.datetime", new=mock_datetime)
    video_id = f"dp_video_{test_timestamp}"

    # Mock settings.DEFAULT_BUCKET_NAME to have a fixed bucket name
    mocker.patch("src.common.settings.DEFAULT_BUCKET_NAME", "some-bucket")

    # Mock MinioClient and its methods used in the endpoint
    mock_minio = mocker.MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.upload_video.return_value = None
    minio_client = mocker.patch(f"{endpoint_module}.get_minio_client", return_value=mock_minio)

    # Mock other important method calls
    mock_generate_embedding = mocker.patch(f"{endpoint_module}.generate_video_embedding", return_value=dummy_ids)
    mock_cleanup = mocker.patch(f"{endpoint_module}.shutil.rmtree", return_value=None)

    # Hit upload endpoint
    response = test_client.post("/videos/upload", files=video_file)
    assert response.status_code == HTTPStatus.CREATED

    # Assert calls to various methods with proper parameters
    mock_readconfig.assert_called_once()
    minio_client.assert_called_once()
    mock_minio.ensure_bucket_exists.assert_called_once_with("some-bucket")
    mock_minio.upload_video.assert_called_once_with(
        "some-bucket", f"{video_id}/{filename}", b"$binary content$"
    )

    mock_generate_embedding.assert_called_once_with(
        bucket_name="some-bucket",
        video_id=video_id,
        filename=filename,
        temp_video_path=tmp_path / video_id / filename,
        metadata_temp_path=tmp_path / video_id,
        chunk_duration=mock_config["cunk_duration"],
        clip_duration=mock_config["clip_duration"],
        tags=[],
    )

    # Make sure mock_cleanup is to clear the temp directories
    mock_cleanup.assert_any_call(tmp_path / video_id, ignore_errors=True)


def test_read_config_error(test_client, video_file, mocker):
    """
    Test what happens when read_config call fails to read the config file
    """

    endpoint_module = "src.endpoints.video_processing.process_minio_video"
    mocker.patch(f"{endpoint_module}.read_config", return_value=None)

    response = test_client.post(
        "/videos/upload", files=video_file
    )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["message"] == Strings.server_error


def test_prep_data_invalid_video_file(test_client, invalid_video_file, mocker):
    response = test_client.post("/videos/upload", files=invalid_video_file)
    assert response.status_code == HTTPStatus.BAD_REQUEST

def test_save_metadata_at_temp(tmp_path, mocker):
    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    metadata_filename = "test_metadata.json"

    test_metadata = {
        "clip_duration": 10,
        "chunk_duration": 30,
        "fps": 20,
        "total_frames": 100,
    }

    # Mock settings.METADATA_FILENAME to have a fixed metadata filename
    mocker.patch("src.common.settings.METADATA_FILENAME", metadata_filename)

    metadata_path = tmp_path / metadata_filename
    assert  metadata_path == save_metadata_at_temp(tmp_path, test_metadata)

    mock_open.assert_called_once_with(metadata_path, "w")


def test_store_video_metadata(mocker, tmp_path):
    """
    Test store_video_metadata function to store metadata for videos in temp location.
    """
    # mock extract_video_metadata to return some dummy metadata
    dummy_metadata = {
        "0_200": {
            "bucket_name": "some-bucket",
            "video_id": "some-video-id",
            "video": "some-video.mp4",
            "video_remote_path": "some-video-id/some-video.mp4",
            "fps": 20,
            "total_frames": 600,
            "clip_duration": 5,
            "frames_in_clip": 200,
        },
    }
    bucket_name = "some-bucket"
    video_id = "some-video-id"
    video_filename = "some-video.mp4"
    temp_video_path = tmp_path / video_filename
    chunk_duration = 10
    clip_duration = 5
    metadata_temp_path = tmp_path
    tags = ["tag1", "tag2"]

    # Mock the function which extracts metadata from video
    mock_extract_metadata = mocker.patch("src.core.util.extract_video_metadata", return_value=dummy_metadata)
    
    # Mock save_metadata_at_temp to return a dummy path
    dummy_metadata_path = metadata_temp_path / "some-metadata.json"
    mock_save_metadata = mocker.patch("src.core.util.save_metadata_at_temp", return_value=dummy_metadata_path)

    # Call the function under test
    result = store_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=video_filename,
        temp_video_path=temp_video_path,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        metadata_temp_path=metadata_temp_path,
        tags=tags,
    )

    # Assert the result is the dummy path returned by mock_save_metadata
    assert result == dummy_metadata_path

    # Assert internal function calls with proper parameters
    mock_extract_metadata.assert_called_once_with(
        temp_video_path=temp_video_path,
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=video_filename,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        tags=tags
    )

    mock_save_metadata.assert_called_once_with(metadata_temp_path, dummy_metadata)


def test_read_config(tmp_path, mocker):
    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    mocker.patch("yaml.safe_load", return_value={})
    mocker.patch("json.load", return_value={})

    assert type(read_config(tmp_path, type="yaml")) is dict
    mock_open.assert_called_once_with(tmp_path.absolute(), "r")
    assert type(read_config(tmp_path, type="json")) is dict
