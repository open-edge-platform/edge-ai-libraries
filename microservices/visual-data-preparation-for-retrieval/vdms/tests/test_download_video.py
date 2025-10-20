# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
from http import HTTPStatus
from unittest.mock import MagicMock

from src.core.minio_client import MinioClient


def test_download(test_client, mocker):
    """Test successful download of a video from Minio."""

    # Mock Minio client functionality
    mock_minio = MagicMock()
    mock_stream = io.BytesIO(b"test video content")
    mock_minio.get_video_in_directory.return_value = "test-video-id/test-file.mp4"
    mock_minio.download_video_stream.return_value = mock_stream

    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)
    mocker.patch("src.main.StreamingResponse", return_value={})

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


def test_download_with_range_header(test_client, mocker):
    """Test video download with HTTP Range header."""

    # Mock Minio client functionality
    mock_minio = MagicMock()
    mock_stream = io.BytesIO(b"test video content")
    mock_minio.get_video_in_directory.return_value = "test-video-id/test-file.mp4"
    mock_minio.download_video_stream.return_value = mock_stream
    mock_minio.get_object_size.return_value = 1000

    mocker.patch("src.core.util.get_minio_client", return_value=mock_minio)
    mocker.patch("src.main.StreamingResponse", return_value={})

    # Test with range header
    headers = {"Range": "bytes=0-499"}
    response = test_client.get("/videos/download?video_id=test-video-id", headers=headers)
    assert response.status_code == HTTPStatus.PARTIAL_CONTENT
