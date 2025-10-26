# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
from http import HTTPStatus
from unittest.mock import MagicMock

from src.common import settings
from src.core.util import get_video_from_minio

def test_download(test_client, mocker):
    """Test successful download of a video from Minio."""

    # Mock Minio client functionality
    mock_minio = MagicMock()

    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)
    mocker.patch("src.endpoints.video_management.download_video.StreamingResponse", return_value={})

    response = test_client.get("/videos/download?video_id=test-video-id")
    assert response.status_code == HTTPStatus.OK
    

def test_download_video_not_found(test_client, mocker):
    """Test when video is not found in Minio."""

    # Mock Minio client with no video found
    mock_minio = MagicMock()
    mock_minio.get_video_in_directory.return_value = None
    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)

    response = test_client.get("/videos/download?video_id=non-existent-id")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_download_minio_error(test_client, mocker):
    """Test when Minio service throws an error."""

    # Mock Minio client to throw an exception
    mock_minio = MagicMock()
    mock_minio.get_video_in_directory.side_effect = Exception("Minio error")
    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)

    response = test_client.get("/videos/download?video_id=test-video-id")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_minio_util_func_call(test_client, mocker):
    """Test calls to utility functions while downloading video."""

    mocker_tuple = (io.BytesIO(b"test video content"), "filename")

    mock_util = mocker.patch("src.endpoints.video_management.download_video.get_video_from_minio")
    mock_util.return_value = mocker_tuple
    mock_streaming = mocker.patch("src.endpoints.video_management.download_video.StreamingResponse")
    mock_streaming.return_value = {}

    response = test_client.get("/videos/download?video_id=test-video-id")

    mock_util.assert_called_once_with(
        settings.DEFAULT_BUCKET_NAME,
        "test-video-id",
        None,
    )
    mock_streaming.assert_called_once()
    assert response.status_code == HTTPStatus.OK


def test_get_video_from_minio_calls(test_client, mocker):
    """Test calls to get_video_from_minio function while downloading video."""

    file_name = "filename"
    byte_obj = io.BytesIO(b"test video content")
    bucket_name = "test-bucket"
    video_id = "test-video-id"
    minio_object_name = f"{video_id}/{file_name}"

    mock_minio = MagicMock()
    mock_minio.get_video_in_directory.return_value = minio_object_name
    mock_minio.download_video_stream.return_value = byte_obj

    mock_minio_client = mocker.patch("src.core.util.get_minio_client")
    mock_minio_client.return_value = mock_minio

    assert get_video_from_minio(bucket_name, video_id) == (byte_obj, file_name)
    mock_minio_client.assert_called_once()
    mock_minio.get_video_in_directory.assert_called_once_with(bucket_name, video_id)
    mock_minio.download_video_stream.assert_called_once_with(bucket_name, minio_object_name)
