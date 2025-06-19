#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import patch, MagicMock, mock_open
from mr_interface import MRHandler
import requests

@pytest.fixture
def config_fetch_true():
    return {
        "task": {
            "fetch_from_model_registry": True,
            "task_name": "test_model",
            "version": "1.0"
        }
    }

@pytest.fixture
def config_fetch_false():
    return {
        "task": {
            "fetch_from_model_registry": False,
            "task_name": "test_model",
            "version": "1.0"
        }
    }

@pytest.fixture
def fake_logger():
    class Logger:
        def __init__(self):
            self.errors = []
        def error(self, msg):
            self.errors.append(msg)
    return Logger()

def test_init_fetch_false_sets_flag(config_fetch_false, fake_logger, monkeypatch):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    handler = MRHandler(config_fetch_false, fake_logger)
    assert handler.fetch_from_model_registry is False

def test_init_fetch_true_success(monkeypatch, config_fetch_true, fake_logger):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    # Patch get_model_info to return a fake model list
    with patch.object(MRHandler, "get_model_info", return_value=[{"id": "abc"}]) as mock_info, \
         patch.object(MRHandler, "download_udf_model_by_id") as mock_download:
        handler = MRHandler(config_fetch_true, fake_logger)
        mock_info.assert_called_once_with("test_model", "1.0")
        mock_download.assert_called_once_with("test_model", "abc")
        assert handler.fetch_from_model_registry is True

def test_init_fetch_true_failure(monkeypatch, config_fetch_true, fake_logger):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    with patch.object(MRHandler, "get_model_info", return_value=None), \
         patch("os._exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            MRHandler(config_fetch_true, fake_logger)
        assert "Error: Invalid Model name/version" in fake_logger.errors[0]
        mock_exit.assert_called_once_with(1)

def test_get_model_info_success(monkeypatch, fake_logger):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    handler = MRHandler({"task": {}}, fake_logger)
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [{"id": "abc"}]
    with patch("requests.get", return_value=fake_response) as mock_get:
        result = handler.get_model_info("foo", "1.0")
        assert result == [{"id": "abc"}]
        mock_get.assert_called_once()

def test_get_model_info_failure_status(monkeypatch, fake_logger):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    handler = MRHandler({"task": {}}, fake_logger)
    fake_response = MagicMock()
    fake_response.status_code = 404
    with patch("requests.get", return_value=fake_response):
        result = handler.get_model_info("foo", "1.0")
        assert result is None
        assert "Failed to retrieve model info" in fake_logger.errors[0]

def test_get_model_info_logs_exception(monkeypatch, fake_logger):
    monkeypatch.setenv("MODEL_REGISTRY_URL", "http://fake-url")
    handler = MRHandler({"task": {}}, fake_logger)
    with patch("requests.get", side_effect=requests.exceptions.RequestException("boom")):
        result = handler.get_model_info("modelC", "3.0")
        assert result is None
        assert "An error occurred" in fake_logger.errors[0]
