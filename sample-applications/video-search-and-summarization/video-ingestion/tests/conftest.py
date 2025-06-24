# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO
import numpy as np
from PIL import Image
import os
import sys

# Add the src directory to the path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


@pytest.fixture
def minio_client_mock():
    """Mocked MinioClient instance."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_image_bytes():
    """Create a sample image in BytesIO object."""
    img = Image.new("RGB", (10, 10), color="red")
    img_bytes = BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    return img_bytes


@pytest.fixture
def publisher_fixture():
    with patch.dict(
        "os.environ",
        {
            "RABBITMQ_HOST": "test_host",
            "RABBITMQ_PORT": "1883",
            "MINIO_SERVER": "test_server:9000",
            "RABBITMQ_DEFAULT_USER": "test_user",
            "RABBITMQ_DEFAULT_PASS": "test_pass",
            "MINIO_ROOT_USER": "test_minio_user",
            "MINIO_ROOT_PASSWORD": "test_minio_pass",
        },
    ), patch("publish.RabbitMQMQTTClient") as mock_rabbitmq_client, patch("publish.MinioClient") as mock_minio_client:
        mock_rabbitmq_instance = MagicMock()
        mock_rabbitmq_instance.is_connected.return_value = True
        mock_rabbitmq_client.return_value = mock_rabbitmq_instance
        mock_minio_instance = MagicMock()
        mock_minio_client.get_client.return_value = mock_minio_instance

        def _create_publisher(**kwargs):
            from publish import Publisher
            return Publisher(
                kwargs.get("frames_per_chunk", 10),
                kwargs.get("chunk_duration", 5),
                topic=kwargs.get("topic", "test_topic"),
                video_identifier=kwargs.get("video_identifier", "test_video_id"),
                minio_bucket=kwargs.get("minio_bucket", "test_bucket"),
            )
        yield _create_publisher, mock_rabbitmq_instance
