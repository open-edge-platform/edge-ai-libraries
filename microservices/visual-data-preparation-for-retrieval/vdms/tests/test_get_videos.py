# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from unittest.mock import MagicMock

from src.common import settings


def test_getvideos_list(test_client, mocker):
    """Test successful retrieval of videos list from Minio."""

    # Mock MinioClient
    mock_video_info = {
        "video_id": "test_video_id",
        "video_name": "test_video.mp4",
        "video_path": "test_video_path",
        "creation_ts": "test_creation_time",
    }
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_all_videos.return_value = [mock_video_info]

    mock_minio_client = mocker.patch("src.endpoints.video_management.list_videos.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.OK

    mock_minio_client.assert_called_once()
    mock_minio.ensure_bucket_exists.assert_called_once_with(settings.DEFAULT_BUCKET_NAME)
    mock_minio.list_all_videos.assert_called_once_with(bucket_name=settings.DEFAULT_BUCKET_NAME)

    # Verify response content
    response_json = response.json()
    assert response_json["status"] == "success"
    assert response_json["bucket_name"] is not None
    assert "videos" in response_json
    assert type(response_json["videos"]) is list
    assert len(response_json["videos"]) == 1
    assert response_json["videos"][0]["video_id"] == "test_video_id"
    assert response_json["videos"][0]["video_name"] == "test_video.mp4"
    assert response_json["videos"][0]["video_path"] == "test_video_path"
    assert response_json["videos"][0]["creation_ts"] == "test_creation_time"


def test_getvideos_minio_error(test_client, mocker):
    """Test when Minio client throws an error."""

    # Mock Minio client to raise an exception
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.side_effect = Exception("Minio error")

    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_getvideos_empty_bucket(test_client, mocker):
    """Test when bucket exists but contains no videos."""

    # Mock MinioClient with empty list
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_all_videos.return_value = []

    mock_minio_client = mocker.patch("src.endpoints.video_management.list_videos.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.OK

    mock_minio_client.assert_called_once()
    mock_minio.ensure_bucket_exists.assert_called_once_with(settings.DEFAULT_BUCKET_NAME)
    mock_minio.list_all_videos.assert_called_once_with(bucket_name=settings.DEFAULT_BUCKET_NAME)

    # Verify response content shows empty video collections
    response_json = response.json()
    assert response_json["status"] == "success"
    assert "videos" in response_json
    assert len(response_json["videos"]) == 0


def test_getvideos_with_bucket_param(test_client, mocker):
    """Test listing videos with custom bucket parameter."""

    # Mock MinioClient
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_all_videos.return_value = []

    mocker.patch("src.endpoints.video_management.list_videos.get_minio_client", return_value=mock_minio)

    # Test API endpoint with custom bucket
    custom_bucket = "custom-bucket"
    response = test_client.get(f"/videos?bucket_name={custom_bucket}")
    assert response.status_code == HTTPStatus.OK

    # Verify bucket was passed correctly
    mock_minio.ensure_bucket_exists.assert_called_once_with(custom_bucket)
    mock_minio.list_all_videos.assert_called_once_with(bucket_name=custom_bucket)
