# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from unittest.mock import MagicMock


def test_getvideos_list(test_client, mocker):
    """Test successful retrieval of videos list from Minio."""

    # Mock MinioClient
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_video_directories.return_value = [
        ("video1", ["file1.mp4"]),
        ("video2", ["file2.mp4", "file3.mp4"]),
    ]

    mocker.patch("src.core.utils.common_utils.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.OK

    # Verify response content
    response_json = response.json()
    assert response_json["status"] == "success"
    assert response_json["bucket_name"] is not None
    assert "video_collections" in response_json
    assert len(response_json["video_collections"]) == 2
    assert "video1" in response_json["video_collections"]
    assert "video2" in response_json["video_collections"]
    assert response_json["video_collections"]["video1"] == ["file1.mp4"]
    assert len(response_json["video_collections"]["video2"]) == 2


def test_getvideos_minio_error(test_client, mocker):
    """Test when Minio client throws an error."""

    # Mock Minio client to raise an exception
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.side_effect = Exception("Minio error")

    mocker.patch("src.core.utils.common_utils.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_getvideos_empty_bucket(test_client, mocker):
    """Test when bucket exists but contains no videos."""

    # Mock MinioClient with empty list
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_video_directories.return_value = []

    mocker.patch("src.core.utils.common_utils.get_minio_client", return_value=mock_minio)

    # Test API endpoint
    response = test_client.get("/videos")
    assert response.status_code == HTTPStatus.OK

    # Verify response content shows empty video collections
    response_json = response.json()
    assert response_json["status"] == "success"
    assert "video_collections" in response_json
    assert len(response_json["video_collections"]) == 0


def test_getvideos_with_bucket_param(test_client, mocker):
    """Test listing videos with custom bucket parameter."""

    # Mock MinioClient
    mock_minio = MagicMock()
    mock_minio.ensure_bucket_exists.return_value = None
    mock_minio.list_video_directories.return_value = [("video1", ["file1.mp4"])]

    mocker.patch("src.core.utils.common_utils.get_minio_client", return_value=mock_minio)

    # Test API endpoint with custom bucket
    custom_bucket = "custom-bucket"
    response = test_client.get(f"/videos?bucket_name={custom_bucket}")
    assert response.status_code == HTTPStatus.OK

    # Verify bucket was passed correctly
    mock_minio.ensure_bucket_exists.assert_called_once_with(custom_bucket)
    mock_minio.list_video_directories.assert_called_once_with(custom_bucket)
