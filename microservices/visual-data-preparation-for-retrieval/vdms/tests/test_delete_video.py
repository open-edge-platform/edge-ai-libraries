# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from unittest.mock import MagicMock

from minio.error import S3Error


def test_delete_video_not_implemented(test_client):
    """Test that DELETE endpoint returns Not Implemented status.

    The DELETE endpoint has been removed in the new implementation that
    interacts directly with Minio. This test ensures that any attempts
    to call the old endpoint receive a 404 Not Found response.
    """
    response = test_client.delete("/videos/file1.mp4")
    assert response.status_code == HTTPStatus.NOT_FOUND
