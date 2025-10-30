# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import datetime
from http import HTTPStatus

from src.common import Strings
from src.common.schema import VideoRequest
from src.core.util import read_config

def test_process_minio_video(test_client, mocker, monkeypatch, tmp_path):
    """
    Common mocking function to be used by all tests for /videos/minio endpoint.
    """
    mock_response = {
        "status": "success",
        "message": Strings.embedding_success
    }

    mock_config = {
        "videos_local_temp_dir": tmp_path,
        "metadata_local_temp_dir": tmp_path,
    }

    mock_video_request = {
        "bucket_name": "some-bucket",
        "video_id": "abcdef-efgty-itbw",
        "video_name": "some-video.mp4",
        "chunk_duration": 30,
        "clip_duration": 10,
        "tags": ["tag1", "tag2"],
    }

    video_request_obj = VideoRequest.model_validate(mock_video_request)
    assert type(video_request_obj) is VideoRequest
    dummy_ids = ["idrtyyus-uevalop-itwsjl"]
    video_data = io.BytesIO(b"test video content")

    # Storing common module name where all functions to be mocked are present
    endpoint_module = "src.endpoints.video_processing.process_minio_video"

    mock_read_config = mocker.patch(f"{endpoint_module}.read_config", return_value=mock_config)
    mock_sanitizer = mocker.patch(f"{endpoint_module}.sanitize_model", return_value=video_request_obj)
    mock_validator = mocker.patch(f"{endpoint_module}._validate_and_get_video_name", return_value=mock_video_request["video_name"])
    mock_get_video = mocker.patch(f"{endpoint_module}.get_video_from_minio", return_value=(video_data, mock_video_request['video_name']))
    mock_generate_embedding = mocker.patch(f"{endpoint_module}.generate_video_embedding", return_value=dummy_ids)
    mock_cleanup = mocker.patch(f"{endpoint_module}.shutil.rmtree", return_value=None)

    # Set mock value for request_id variable by mocking datatime module
    test_timestamp = 1697059200
    mock_datetime = mocker.MagicMock(wraps=datetime.datetime)
    mock_datetime.now.return_value.timestamp.return_value = test_timestamp
    mocker.patch(f"{endpoint_module}.datetime.datetime", new=mock_datetime)
    request_id = f"{mock_video_request['video_id']}_{test_timestamp}"
    
    # Hit Minio based video preparation endpoint
    response = test_client.post(
        "/videos/minio", json=mock_video_request
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == mock_response

    mock_read_config.assert_called_once()
    mock_sanitizer.assert_called_once_with(video_request_obj)
    mock_validator.assert_called_once_with(
        bucket_name=mock_video_request["bucket_name"],
        video_id=mock_video_request["video_id"],
        video_name=mock_video_request["video_name"],
    )
    mock_get_video.assert_called_once_with(
        mock_video_request["bucket_name"],
        mock_video_request["video_id"],
        mock_video_request["video_name"],
    )

    mock_generate_embedding.assert_called_once_with(
        bucket_name=mock_video_request["bucket_name"],
        video_id=mock_video_request["video_id"],
        filename=mock_video_request["video_name"],
        temp_video_path=tmp_path / request_id /  mock_video_request["video_name"],
        metadata_temp_path=tmp_path / request_id,
        chunk_duration=mock_video_request["chunk_duration"],
        clip_duration=mock_video_request["clip_duration"],
        tags=mock_video_request["tags"],
    )

    # Make sure mock_cleanup is to clear the temp directories
    mock_cleanup.assert_any_call(tmp_path / request_id, ignore_errors=True)

def test_read_config(tmp_path, mocker):
    mock_open = mocker.mock_open()
    mocker.patch("builtins.open", mock_open)
    mocker.patch("yaml.safe_load", return_value={})
    mocker.patch("json.load", return_value={})

    assert type(read_config(tmp_path, type="yaml")) is dict
    mock_open.assert_called_once_with(tmp_path.absolute(), "r")
    assert type(read_config(tmp_path, type="json")) is dict

def test_read_config_error(test_client, mocker):
    """
    Test what happens when read_config call fails to read the config file
    """

    endpoint_module = "src.endpoints.video_processing.process_minio_video"
    mocker.patch(f"{endpoint_module}.read_config", return_value=None)

    response = test_client.post(
        "/videos/minio", json={}
    )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["message"] == Strings.server_error


def test_process_minio_video_empty_bucket(test_client, mocker, tmp_path):
    """
    Test /videos/minio endpoint with an empty bucket_name.
    """
    mock_config = {
        "videos_local_temp_dir": tmp_path,
        "metadata_local_temp_dir": tmp_path,
    }
    mock_video_request = {
        "bucket_name": "",
        "video_id": "abcdef-efgty-itbw",
        "video_name": "some-video.mp4",
    }
    video_request_obj = VideoRequest.model_validate(mock_video_request)

    endpoint_module = "src.endpoints.video_processing.process_minio_video"
    mocker.patch(f"{endpoint_module}.read_config", return_value=mock_config)
    mocker.patch(f"{endpoint_module}.sanitize_model", return_value=video_request_obj)

    response = test_client.post("/videos/minio", json=mock_video_request)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["message"] == "Both bucket_name and video_id must be provided."


def test_process_minio_video_empty_video_id(test_client, mocker, tmp_path):
    """
    Test /videos/minio endpoint with an empty video_id.
    """
    mock_config = {
        "videos_local_temp_dir": tmp_path,
        "metadata_local_temp_dir": tmp_path,
    }
    mock_video_request = {
        "bucket_name": "some-bucket",
        "video_id": "",
        "video_name": "some-video.mp4",
    }
    video_request_obj = VideoRequest.model_validate(mock_video_request)

    endpoint_module = "src.endpoints.video_processing.process_minio_video"
    mocker.patch(f"{endpoint_module}.read_config", return_value=mock_config)
    mocker.patch(f"{endpoint_module}.sanitize_model", return_value=video_request_obj)

    response = test_client.post("/videos/minio", json=mock_video_request)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["message"] == "Both bucket_name and video_id must be provided."


def test_process_minio_video_invalid_video_name(test_client, mocker, tmp_path):
    """
    Test /videos/minio endpoint with an invalid video_name.
    """
    mock_config = {
        "videos_local_temp_dir": tmp_path,
        "metadata_local_temp_dir": tmp_path,
    }
    mock_video_request = {
        "bucket_name": "some-bucket",
        "video_id": "abcdef-efgty-itbw",
        "video_name": "../invalid-video.mp4",
    }
    video_request_obj = VideoRequest.model_validate(mock_video_request)

    endpoint_module = "src.endpoints.video_processing.process_minio_video"
    mocker.patch(f"{endpoint_module}.read_config", return_value=mock_config)
    mocker.patch(f"{endpoint_module}.sanitize_model", return_value=video_request_obj)

    mock_minio_client = mocker.MagicMock()
    mock_minio_client.object_exists.return_value = True
    mock_minio_client.validate_object_name.return_value = False
    mocker.patch(f"{endpoint_module}.get_minio_client", return_value=mock_minio_client)

    response = test_client.post("/videos/minio", json=mock_video_request)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert (
        response.json()["message"]
        == "Invalid video name '../invalid-video.mp4' in directory 'abcdef-efgty-itbw'"
    )


def test_process_minio_video_invalid_tags_type(test_client, mocker, tmp_path):
    """
    Test /videos/minio endpoint with tags not being a list.
    """
    mock_video_request = {
        "bucket_name": "some-bucket",
        "video_id": "abcdef-efgty-itbw",
        "video_name": "some-video.mp4",
        "tags": "not-a-list",
    }

    response = test_client.post("/videos/minio", json=mock_video_request)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_process_minio_video_invalid_tags_content(test_client, mocker, tmp_path):
    """
    Test /videos/minio endpoint with tags list containing non-string elements.
    """
    mock_video_request = {
        "bucket_name": "some-bucket",
        "video_id": "abcdef-efgty-itbw",
        "video_name": "some-video.mp4",
        "tags": ["valid-tag", 123],
    }

    response = test_client.post("/videos/minio", json=mock_video_request)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


