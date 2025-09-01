#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import os
import pytest
from unittest import mock
from mr_interface import MRHandler
import requests

@pytest.fixture
def mock_logger():
    logger = mock.Mock()
    logger.info = mock.Mock()
    logger.error = mock.Mock()
    logger.debug = mock.Mock()
    return logger

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://mock-registry")
    yield

def test_init_no_model_registry(monkeypatch, mock_logger):
    config = {"udfs": {"name": "test-model"}}
    handler = MRHandler(config, mock_logger)
    assert handler.base_url == "http://mock-registry"
    assert handler.fetch_from_model_registry is False
    assert handler.unique_id is None
    assert handler.config == config

def test_init_model_registry_disabled(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": False, "version": "1.0"}
    }
    handler = MRHandler(config, mock_logger)
    assert handler.fetch_from_model_registry is False
    assert handler.unique_id is None

def test_init_model_registry_enabled_success(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": True, "version": "1.0"}
    }
    fake_model_info = [{"id": "abc123"}]
    with mock.patch.object(MRHandler, "get_model_info", return_value=fake_model_info) as mock_get_info, \
         mock.patch.object(MRHandler, "download_udf_model_by_id") as mock_download:
        handler = MRHandler(config, mock_logger)
        mock_logger.info.assert_called_once()
        mock_get_info.assert_called_once_with("test-model", "1.0")
        mock_logger.debug.assert_called_once_with("Model id: %s", "abc123")
        mock_download.assert_called_once_with("abc123")
        assert handler.fetch_from_model_registry is True
        assert handler.unique_id is not None

def test_init_model_registry_enabled_no_data(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": True, "version": "1.0"}
    }
    with mock.patch.object(MRHandler, "get_model_info", return_value=[]) as mock_get_info, \
         mock.patch.object(MRHandler, "download_udf_model_by_id") as mock_download:
        handler = MRHandler(config, mock_logger)
        mock_logger.info.assert_called_once()
        mock_get_info.assert_called_once_with("test-model", "1.0")
        mock_logger.error.assert_called_once()
        mock_download.assert_not_called()
        assert handler.fetch_from_model_registry is True
        assert handler.unique_id is None

def test_init_model_registry_enabled_none_data(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": True, "version": "1.0"}
    }
    with mock.patch.object(MRHandler, "get_model_info", return_value=None) as mock_get_info, \
         mock.patch.object(MRHandler, "download_udf_model_by_id") as mock_download:
        handler = MRHandler(config, mock_logger)
        mock_logger.info.assert_called_once()
        mock_get_info.assert_called_once_with("test-model", "1.0")
        mock_logger.error.assert_called_once()
        mock_download.assert_not_called()
        assert handler.fetch_from_model_registry is True
        assert handler.unique_id is None

def test_init_sets_requests_ca_bundle_and_resets(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": True, "version": "1.0"}
    }
    fake_model_info = [{"id": "abc123"}]
    # Patch get_model_info and download_udf_model_by_id to avoid side effects
    with mock.patch.object(MRHandler, "get_model_info", return_value=fake_model_info), \
            mock.patch.object(MRHandler, "download_udf_model_by_id"):
        # Save original value
        orig_bundle = os.environ.get("REQUESTS_CA_BUNDLE")
        handler = MRHandler(config, mock_logger)
        # After __init__, REQUESTS_CA_BUNDLE should be reset to ""
        assert os.environ["REQUESTS_CA_BUNDLE"] == ""
        # Restore original value
        if orig_bundle is not None:
            os.environ["REQUESTS_CA_BUNDLE"] = orig_bundle
        else:
            del os.environ["REQUESTS_CA_BUNDLE"]

def test_init_sets_requests_ca_bundle_when_no_model_registry(monkeypatch, mock_logger):
    config = {"udfs": {"name": "test-model"}}
    orig_bundle = os.environ.get("REQUESTS_CA_BUNDLE")
    handler = MRHandler(config, mock_logger)
    assert os.environ["REQUESTS_CA_BUNDLE"] == ""
    if orig_bundle is not None:
        os.environ["REQUESTS_CA_BUNDLE"] = orig_bundle
    else:
        del os.environ["REQUESTS_CA_BUNDLE"]

def test_init_model_registry_enabled_exception_in_download(monkeypatch, mock_logger):
    config = {
        "udfs": {"name": "test-model"},
        "model_registry": {"enable": True, "version": "1.0"}
    }
    fake_model_info = [{"id": "abc123"}]
    with mock.patch.object(MRHandler, "get_model_info", return_value=fake_model_info), \
            mock.patch.object(MRHandler, "download_udf_model_by_id", side_effect=Exception("fail")):
        with pytest.raises(Exception):
            MRHandler(config, mock_logger)

def test_get_model_info_success(monkeypatch, mock_logger):
    config = {"udfs": {"name": "test-model"}}
    handler = MRHandler(config, mock_logger)
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": "abc123"}]
    with mock.patch("requests.get", return_value=mock_response) as mock_get:
        result = handler.get_model_info("test-model", "1.0")
        assert result == [{"id": "abc123"}]
        expected_url = "http://mock-registry/models?name=test-model&version=1.0"
        mock_get.assert_called_once_with(expected_url, timeout=10, verify=True)
        mock_logger.error.assert_not_called()

def test_get_model_info_non_200(monkeypatch, mock_logger):
    config = {"udfs": {"name": "test-model"}}
    handler = MRHandler(config, mock_logger)
    mock_response = mock.Mock()
    mock_response.status_code = 404
    with mock.patch("requests.get", return_value=mock_response):
        result = handler.get_model_info("test-model", "1.0")
        assert result is None
        mock_logger.error.assert_called_once_with("Failed to retrieve model info. Status code: %s", 404)

def test_get_model_info_request_exception(monkeypatch, mock_logger):
    config = {"udfs": {"name": "test-model"}}
    handler = MRHandler(config, mock_logger)
    with mock.patch("requests.get", side_effect=requests.exceptions.RequestException("fail")):
        result = handler.get_model_info("test-model", "1.0")
        assert result is None
        assert mock_logger.error.call_count == 1
        assert "An error occurred: %s" in str(mock_logger.error.call_args[0][0])

