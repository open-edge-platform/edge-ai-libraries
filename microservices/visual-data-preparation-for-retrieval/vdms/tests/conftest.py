# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.minio_client import MinioClient
from src.main import app

# application packages
from src.main import app


@pytest.fixture(scope="function")
def video_file(tmp_path):
    content = b"$binary content$"
    file = tmp_path / "sample-video.mp4"
    file.write_bytes(content)
    yield {"file": ("sample-video.mp4", open(file, "rb"), "video/mp4")}


@pytest.fixture(scope="function")
def invalid_video_file(tmp_path):
    content = b"$binary content$"
    file = tmp_path / "sample-video.txt"
    file.write_bytes(content)
    yield {"file": ("sample-video.txt", open(file, "rb"), "aplication/octet-stream")}


@pytest.fixture(scope="module")
def test_client():
    """A fixture to help send HTTP REST requests to API endpoints."""

    client = TestClient(app)
    yield client


@pytest.fixture
def mock_minio_client():
    """Fixture to provide a mocked MinioClient for tests."""

    mock_client = MagicMock(spec=MinioClient)

    # Setup common mock methods
    mock_client.ensure_bucket_exists.return_value = None
    mock_client.list_video_directories.return_value = [
        ("video1", ["file1.mp4"]),
        ("video2", ["file2.mp4", "file3.mp4"]),
    ]
    mock_client.get_video_in_directory.return_value = "video1/file1.mp4"

    # Create a mock binary stream
    mock_stream = io.BytesIO(b"test video content")
    mock_client.download_video_stream.return_value = mock_stream
    mock_client.get_object_size.return_value = 1000

    # Handle client directly for some operations
    mock_client.client = MagicMock()
    mock_client.client.put_object.return_value = None
    mock_client.client.make_bucket.return_value = None
    mock_client.client.bucket_exists.return_value = True

    return mock_client
