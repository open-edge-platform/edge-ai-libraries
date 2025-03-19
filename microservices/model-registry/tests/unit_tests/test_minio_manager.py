# pylint: disable=import-error, unused-variable, unused-argument, redefined-outer-name
"""
This file provides functions for testing functions in the minio_manager.py file.
"""
import os
import pytest
from urllib3.response import HTTPResponse
import minio
from managers.minio_manager import MinioManager

@pytest.fixture
def mock_minio_client(mocker):
    """Returns a mocked minio client"""
    mock_client = mocker.Mock(spec=minio.Minio)
    mocker.patch("minio.Minio", return_value=mock_client)
    return mock_client

@pytest.fixture
def mock_minio_get_object(mock_minio_client, mocker):
    """Returns a mocked return value for the minio get_object method"""
    mock_get_object = mock_minio_client.get_object
    return mock_get_object

@pytest.mark.parametrize("g_object_params", [
    {"test_case": "non_existent_object", "object_name": "13214501", "expected_result": b""}
])
def test_get_object(g_object_params, mock_minio_get_object, mocker):
    """
    Tests get_object method.
    """
    # Mock get_object
    if g_object_params["test_case"] == "non_existent_object":
        data = b""
        resp = HTTPResponse(data, preload_content=False)
        mock_minio_get_object.return_value = resp

        mock_response_data = mocker.patch("urllib3.response.HTTPResponse.read")
        mock_response_data.return_value = data

    # Create MinioManager object and call get object
    minio_manager = MinioManager()
    # minio_manager._client = None # pylint: disable=protected-access
    object_bytes = minio_manager.get_object(g_object_params["object_name"])

    assert object_bytes == g_object_params["expected_result"]

def test_store_object(mocker):
    """
    Tests get_object method.
    """
    # Mock make_bucket
    mock_minio_make_bucket = mocker.patch("minio.Minio.make_bucket")

    # Mock fput_object
    mock_minio_make_bucket = mocker.patch("minio.Minio.fput_object")

    # Create MinioManager object and call get object
    minio_manager = MinioManager()
    minio_manager._client = None # pylint: disable=protected-access
    object_file_url = minio_manager.store_data(prefix_dir="prefix_dir",file_path="",file_name="file_name")

    assert object_file_url == "minio://test/prefix_dir/file_name"

def test_delete_object_raises_no_exception(mocker, mock_minio_client):
    """
    Tests that delete_object method raises no exception.
    """
    # Mock remove_object
    mock_minio_remove_object = mocker.patch("minio.Minio.remove_object")

    # Create MinioManager object and call get object
    minio_manager = MinioManager()
    is_object_deleted = minio_manager.delete_data(prefix_dir="prefix_dir", file_name="file_name")
    assert is_object_deleted is True

@pytest.mark.parametrize("d_object_params", [
    {"test_case": "S3Error", "error": minio.error.S3Error(message="", resource="MinIO", host_id="localhost", response=None, bucket_name=os.environ["MINIO_BUCKET_NAME"], code="", request_id=""), "expected_result": False},
    {"test_case": "InvalidResponseError", "error": minio.error.InvalidResponseError(body="This is an exception", content_type="text/plain", code=500), "expected_result": False}
])
def test_delete_object_raises_error(d_object_params, mock_minio_client):
    """
    Tests that delete_object method handles raised Errors properly.
    """
    minio_manager = MinioManager()
    minio_manager._minio_client = None # pylint: disable=protected-access
    mock_minio_client.remove_object.side_effect = d_object_params["error"]

    is_object_deleted = minio_manager.delete_data(prefix_dir="prefix_dir", file_name="file_name")

    assert is_object_deleted is d_object_params["expected_result"]
