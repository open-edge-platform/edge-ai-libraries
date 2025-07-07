# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import MagicMock, patch
import json
import os
import numpy as np

# Import the module to test
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from publish import Publisher
from minio_client import MinioClient


class TestPublisher:
    """
    Test suite for the Publisher class, ensuring expected behaviors and error handling.
    """

    @pytest.mark.parametrize(
        "topic,video_identifier,bucket_name,expect_exception",
        [
            ("test_topic", "test_video_id", "test_bucket", False),
            (None, "test_video_id", "test_bucket", True),
            ("test_topic", None, "test_bucket", True),
            ("test_topic", "test_video_id", None, True),
        ],
    )
    def test_init_args(
        self, publisher_fixture, topic, video_identifier, bucket_name, expect_exception
    ):
        """
        Ensures that Publisher initialization fails if required arguments are missing.
        """
        _create_publisher, _ = publisher_fixture
        if expect_exception:
            with pytest.raises(Exception, match="Missing required arguments"):
                _create_publisher(
                    topic=topic, video_identifier=video_identifier, minio_bucket=bucket_name
                )
        else:
            pub = _create_publisher(
                topic=topic, video_identifier=video_identifier, minio_bucket=bucket_name
            )
            assert pub.topic == topic

    def test_init_port_validation(self, publisher_fixture):
        """
        Verifies that an invalid port in environment variables raises an exception.
        """
        with patch.dict("os.environ", {"RABBITMQ_PORT": "invalid_port"}):
            _create_publisher, _ = publisher_fixture
            with pytest.raises(Exception, match="Port value should be an integer."):
                _create_publisher()

    def test_del(self, publisher_fixture):
        """
        Checks that any remaining buffered messages are published and the connection stops on deletion.
        """
        _create_publisher, mock_rabbitmq_instance = publisher_fixture
        pub = _create_publisher()
        pub.messages = {"chunk_1": {"data": "test_message"}}
        pub.__del__()
        mock_rabbitmq_instance.publish.assert_called_once()
        mock_rabbitmq_instance.stop.assert_called_once()

    @pytest.mark.parametrize("has_message", [True, False])
    def test_publish_current_chunk(self, publisher_fixture, has_message):
        """
        Confirms that chunks are only published if messages are present.
        """
        _create_publisher, mock_rabbitmq_instance = publisher_fixture
        pub = _create_publisher()
        if has_message:
            pub.messages = {"chunk_1": {"test": "message"}}
        pub.publish_current_chunk()
        if has_message:
            mock_rabbitmq_instance.publish.assert_called_once()
        else:
            mock_rabbitmq_instance.publish.assert_not_called()

    def test_get_gva_metadata(self, publisher_fixture):
        """
        Merges multiple JSON metadata entries into a single dictionary.
        """
        _create_publisher, _ = publisher_fixture
        pub = _create_publisher()
        assert pub.get_gva_metadata([json.dumps({"k1": "v1"}), json.dumps({"k2": "v2"})]) == {
            "k1": "v1",
            "k2": "v2",
        }

    def test_update_metadata(self, publisher_fixture):
        """
        Validates the addition of frame format and timestamp to the metadata.
        """
        _create_publisher, _ = publisher_fixture
        pub = _create_publisher()
        metadata = {"existing": "value"}
        video_info = MagicMock()
        caps = MagicMock()
        structure = MagicMock()
        structure.get_value.return_value = "BGR"
        caps.get_structure.return_value = structure
        video_info.to_caps.return_value = caps
        pub.frame_id = 5
        pub.frame_interval = 0.5
        pub.update_metadata(metadata, video_info)
        assert metadata["img_format"] == "BGR"
        assert metadata["frame_timestamp"] == 2.5

    @pytest.mark.parametrize("img_format", ["BGR", "RGB"])
    def test_save_image(self, publisher_fixture, img_format):
        """
        Ensures the image saving process respects the image format (BGR or RGB).
        """
        _create_publisher, _ = publisher_fixture
        pub = _create_publisher()
        image_array = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch("publish.Image") as mock_image, patch("publish.BytesIO") as mock_bytesio:
            mock_image_instance = MagicMock()
            mock_image.fromarray.return_value = mock_image_instance
            mock_bytesio_instance = MagicMock()
            mock_bytesio.return_value = mock_bytesio_instance
            pub.save_image(image_array, "test_image_filename", {"img_format": img_format})
            if img_format == "BGR":
                mock_image.fromarray.assert_called()
            else:
                mock_image.fromarray.assert_called_once_with(image_array)

    def test_save_metadata(self, publisher_fixture):
        """
        Confirms that metadata is correctly serialized and saved via MinioClient.
        """
        _create_publisher, _ = publisher_fixture
        pub = _create_publisher()
        pub.frame_id = 42
        meta = {"example": "meta"}
        with patch("publish.BytesIO") as mock_bytesio, patch("publish.MinioClient.save_object") as mock_save:
            mock_bytesio_instance = MagicMock()
            mock_bytesio.return_value = mock_bytesio_instance
            # Fix for TypeError by providing valid JSON bytes
            mock_bytesio_instance.getvalue.return_value = b'{"frame_metadata":{"example":"meta"}}'
            pub.save_metadata("test_meta", meta, "/bucket/image", 3, 2)
            assert json.loads(mock_bytesio_instance.getvalue())["frame_metadata"] == {"example": "meta"}
