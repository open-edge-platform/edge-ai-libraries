"""
This file contains test cases for functions defined in the app_utils.py file.
"""
# import os
import re
import pytest
from fastapi import HTTPException, status
from fastapi.responses import Response
from utils.app_utils import (
    get_version_info, get_bool, check_required_env_vars,
    validate_id, ResourceType, validate_resource_id, get_exception_response
)

@pytest.mark.parametrize("is_file", [True, False, True],
                         ids=["success", "file_not_found", "invalid_file_contents"])
def test_get_version_info(is_file, mocker, request):
    """
    Test get_version_info when the version is successfully returned,
    or when it raises either a FileNotFoundError or ValueError exception
    """
    mocker.patch('utils.app_utils.os.path.isfile', return_value=is_file)

    if request.node.callspec.id == "file_not_found":
        mocker.patch('utils.app_utils.open', side_effect=FileNotFoundError)
        with pytest.raises(FileNotFoundError):
            get_version_info()

    else:
        mocker.patch('utils.app_utils.open')

        if request.node.callspec.id == "success":
            # Create a mocked match object
            mock_match = mocker.Mock(spec=re.Match)
            mock_match.group.return_value = '1.2.3'
            mock_match.regs = [(0, 5)]

            mocker.patch('utils.app_utils.re.match', return_value=mock_match)

            assert get_version_info() == '1.2.3'

        elif request.node.callspec.id == "invalid_file_contents":
            mocker.patch('utils.app_utils.re.match', return_value=None)

            with pytest.raises(ValueError):
                get_version_info()


@pytest.mark.parametrize("gb_params", [{"string": "true", "var_name": "test_var_1", "expected_result": True},
                                       {"string": "NO", "var_name": None, "expected_result": False},
                                       {"string": "NONE", "var_name": "test_var_2", "expected_result": None},
                                       {"string": "abcdef", "var_name": "", "expected_result": None}])
def test_get_bool(gb_params):
    """
    Test get_bool when the string is successfully converted to a boolean,
    or when it raises a ValueError exception
    """

    string = gb_params["string"]
    if string in ("NONE", "abcdef"):
        with pytest.raises(ValueError):
            get_bool(gb_params["string"], gb_params["var_name"])
    else:
        val = get_bool(gb_params["string"])
        assert gb_params["expected_result"] == val


def test_check_required_env_vars_all_present(monkeypatch):
    """Test check_required_env_vars when all required env vars are present."""
    required_vars = [
        "MLFLOW_S3_ENDPOINT_URL", "MINIO_HOSTNAME", "MINIO_SERVER_PORT",
        "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET_NAME", "SERVER_PORT"
    ]
    for var in required_vars:
        monkeypatch.setenv(var, "dummy")
    monkeypatch.setenv("ENABLE_HTTPS_MODE", "False")
    is_set, missing = check_required_env_vars()
    assert is_set is True
    assert missing == []

def test_check_required_env_vars_missing(monkeypatch):
    """Test check_required_env_vars when some env vars are missing."""
    monkeypatch.delenv("MLFLOW_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("ENABLE_HTTPS_MODE", "False")
    is_set, missing = check_required_env_vars()
    assert is_set is False
    assert "MLFLOW_S3_ENDPOINT_URL" in missing

def test_check_required_env_vars_https(monkeypatch):
    """Test check_required_env_vars with HTTPS mode enabled."""
    required_vars = [
        "MLFLOW_S3_ENDPOINT_URL", "MINIO_HOSTNAME", "MINIO_SERVER_PORT",
        "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET_NAME", "SERVER_PORT",
        "SERVER_CERT", "CA_CERT", "SERVER_PRIVATE_KEY"
    ]
    for var in required_vars:
        monkeypatch.setenv(var, "dummy")
    monkeypatch.setenv("ENABLE_HTTPS_MODE", "True")
    is_set, missing = check_required_env_vars()
    assert is_set is True
    assert missing == []

def test_validate_id_valid():
    """Test validate_id with valid id."""
    valid_id = "abcDEF1234567890"
    assert validate_id(valid_id, ResourceType.MODEL) == valid_id

def test_validate_id_invalid():
    """Test validate_id with invalid id."""
    invalid_id = "short"
    with pytest.raises(HTTPException) as exc:
        validate_id(invalid_id, ResourceType.PROJECT)
    assert exc.value.status_code == 400

def test_validate_resource_id_model():
    """Test validate_resource_id for model."""
    dep = validate_resource_id(ResourceType.MODEL)
    valid_id = "abcDEF1234567890"
    assert dep(valid_id) == valid_id

def test_validate_resource_id_project():
    """Test validate_resource_id for project."""
    dep = validate_resource_id(ResourceType.PROJECT)
    valid_id = "abcDEF1234567890"
    assert dep(valid_id) == valid_id

def test_get_exception_response_http_exception():
    """Test get_exception_response with HTTPException."""
    exc = HTTPException(status_code=400, detail="Bad request")
    resp = get_exception_response("GET /test", exc)
    assert isinstance(resp, Response)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "Bad request" in resp.body.decode()

def test_get_exception_response_other_exception():
    """Test get_exception_response with generic Exception."""
    exc = ValueError("Some error")
    resp = get_exception_response("POST /test", exc)
    assert isinstance(resp, Response)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "ValueError" in resp.body.decode()
    assert "Some error" in resp.body.decode()

def test_get_exception_response_unbound_local_error():
    """Test get_exception_response with UnboundLocalError."""
    exc = UnboundLocalError("Unbound error")
    resp = get_exception_response("PUT /test", exc)
    assert isinstance(resp, Response)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "ConnectionError" in resp.body.decode()
    assert "Unbound error" in resp.body.decode()

def test_get_exception_response_component_error():
    """Test get_exception_response with error class containing component name."""
    class MinioError(Exception):
        """Custom exception to simulate a Minio error."""
        # pass
    exc = MinioError("minio failed")
    resp = get_exception_response("GET /minio", exc)
    assert isinstance(resp, Response)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "minio failed" in resp.body.decode()
