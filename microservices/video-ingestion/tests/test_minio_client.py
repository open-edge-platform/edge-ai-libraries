import pytest
from unittest.mock import MagicMock, patch
from minio.error import S3Error

# Import the module to test
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from minio_client import MinioClient


class TestMinioClient:
    """Test cases for MinioClient class."""

    @patch("minio_client.Minio")
    def test_get_client(self, mock_minio):
        """
        Confirms that get_client returns a singleton Minio client instance with the correct configuration.
        """
        # Setup
        mock_instance = MagicMock()
        mock_minio.return_value = mock_instance
        MinioClient.client = None  # Reset the singleton instance

        # Execute - First call
        client1 = MinioClient.get_client(
            minio_server="localhost:9000",
            access_key="test_key",
            secret_key="test_secret",
        )

        # Execute - Second call (should return the same instance)
        client2 = MinioClient.get_client(
            minio_server="localhost:9000",
            access_key="test_key",
            secret_key="test_secret",
        )

        # Verify
        assert client1 == client2 == mock_instance
        mock_minio.assert_called_once_with(
            "localhost:9000", "test_key", "test_secret", secure=False
        )

    @pytest.mark.parametrize(
        "file_type,expected_path,should_raise",
        [
            ("frame", "test_video/frame/chunk_2_frame_5.jpeg", False),
            ("metadata", "test_video/metadata/chunk_2_frame_5.json", False),
            ("invalid_type", "", True),
        ],
    )
    def test_get_destination_file(self, file_type, expected_path, should_raise):
        """
        Checks destination file path generation for valid types and raises exceptions for unsupported types.
        """
        if should_raise:
            with pytest.raises(Exception, match="File type not supported."):
                MinioClient.get_destination_file(
                    video_id="test_video", chunk_id=2, frame_id=5, file_type=file_type
                )
        else:
            result = MinioClient.get_destination_file(
                video_id="test_video", chunk_id=2, frame_id=5, file_type=file_type
            )
            assert result == expected_path

    def test_save_object(self, minio_client_mock, sample_image_bytes):
        """
        Validates saving objects to Minio with and without an explicit length, ensuring stream resets correctly.
        """
        # Setup
        bucket_name = "test_bucket"
        object_name = "test_object"
        data = sample_image_bytes
        expected_length = data.getbuffer().nbytes

        # Test with length provided
        MinioClient.save_object(
            client=minio_client_mock,
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=expected_length,
        )

        # Verify
        minio_client_mock.put_object.assert_called_with(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=expected_length,
            content_type="application/octet-stream",
        )
        
        # Test with length calculation (seek to end to test reset)
        minio_client_mock.reset_mock()
        data.seek(0, 2)  # Move to end
        
        MinioClient.save_object(
            client=minio_client_mock,
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
        )
        
        assert data.tell() == 0  # Verify position reset
        call_args = minio_client_mock.put_object.call_args[1]
        assert call_args["length"] == expected_length

    def test_save_object_s3_error(self, minio_client_mock, sample_image_bytes):
        """
        Verifies that S3Error exceptions are properly handled during put_object operations.
        """
        # Setup
        minio_client_mock.put_object.side_effect = S3Error(
            "Test error", "Test resource", "Test request", "Test host", "host_id", {}
        )

        # Execute and Verify
        with pytest.raises(Exception, match="Error ocurred during saving to bucket:"):
            MinioClient.save_object(
                client=minio_client_mock,
                bucket_name="test_bucket",
                object_name="test_object",
                data=sample_image_bytes,
            )
