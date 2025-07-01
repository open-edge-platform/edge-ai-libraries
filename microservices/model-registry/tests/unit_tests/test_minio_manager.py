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

def test_connect_to_obj_storage_https_and_http(mocker, monkeypatch):
    """Test connect_to_obj_storage for both HTTPS and HTTP modes."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    monkeypatch.setenv("MINIO_HOSTNAME", "localhost")
    monkeypatch.setenv("MINIO_SERVER_PORT", "9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("ENABLE_HTTPS_MODE", "True")
    monkeypatch.setenv("CA_CERT", "/tmp/fake.crt")

    # Patch get_bool to True for HTTPS
    mocker.patch("utils.app_utils.get_bool", return_value=True)
    mock_minio = mocker.patch("minio.Minio")
    mock_pool = mocker.patch("urllib3.PoolManager")
    manager = MinioManager()
    manager._minio_client = None
    manager.connect_to_obj_storage()
    assert mock_minio.called

    # Now test HTTP mode
    monkeypatch.setenv("ENABLE_HTTPS_MODE", "False")
    mocker.patch("utils.app_utils.get_bool", return_value=False)
    manager._minio_client = None
    manager.connect_to_obj_storage()
    assert mock_minio.called

def test_connect_to_obj_storage_exception(mocker, monkeypatch):
    """Test connect_to_obj_storage handles exceptions."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    monkeypatch.setenv("MINIO_HOSTNAME", "localhost")
    monkeypatch.setenv("MINIO_SERVER_PORT", "9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    mocker.patch("utils.app_utils.get_bool", side_effect=Exception("fail"))
    manager = MinioManager()
    manager._minio_client = None
    manager.connect_to_obj_storage()  # Should not raise

def test_store_data_with_file_object(mocker, monkeypatch):
    """Test store_data with file_object argument."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    manager = MinioManager()
    manager._minio_client = mocker.Mock()
    manager._minio_client.bucket_exists.return_value = True
    fake_file = mocker.Mock()
    fake_file.fileno.return_value = 1
    mocker.patch("os.fstat", return_value=mocker.Mock(st_size=123))
    manager._minio_client.put_object.return_value = None
    url = manager.store_data(prefix_dir="dir", file_name="file", file_object=fake_file)
    assert url == "minio://testbucket/dir/file"

def test_store_data_with_file_path(mocker, monkeypatch):
    """Test store_data with file_path argument."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    manager = MinioManager()
    manager._minio_client = mocker.Mock()
    manager._minio_client.bucket_exists.return_value = True
    manager._minio_client.fput_object.return_value = None
    url = manager.store_data(prefix_dir="dir", file_name="file", file_path="/tmp/file")
    assert url == "minio://testbucket/dir/file"

def test_store_data_bucket_creation(mocker, monkeypatch):
    """Test store_data creates bucket if not exists."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    manager = MinioManager()
    manager._minio_client = mocker.Mock()
    manager._minio_client.bucket_exists.return_value = False
    manager._minio_client.make_bucket.return_value = None
    manager._minio_client.fput_object.return_value = None
    url = manager.store_data(prefix_dir="dir", file_name="file", file_path="/tmp/file")
    assert url == "minio://testbucket/dir/file"
    assert manager._minio_client.make_bucket.called

def test_get_object_reads_bytes(mocker, monkeypatch):
    """Test get_object returns bytes from Minio."""
    monkeypatch.setenv("MINIO_BUCKET_NAME", "testbucket")
    manager = MinioManager()
    fake_response = mocker.Mock()
    fake_response.read.return_value = b"abc"
    fake_response.close.return_value = None
    fake_response.release_conn.return_value = None
    manager._minio_client = mocker.Mock()
    manager._minio_client.get_object.return_value = fake_response
    result = manager.get_object("object")
    assert result == b"abc"
    assert fake_response.close.called
    assert fake_response.release_conn.called