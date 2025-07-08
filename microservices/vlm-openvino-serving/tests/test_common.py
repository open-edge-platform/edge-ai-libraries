# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from unittest import mock

# Mock environment variables before importing anything from src.utils
mock.patch.dict(
    os.environ,
    {
        "http_proxy": "http://mock-proxy",
        "https_proxy": "https://mock-proxy",
        "no_proxy_env": "localhost,127.0.0.1",
        "VLM_MODEL_NAME": "mock_model",
        "VLM_COMPRESSION_WEIGHT_FORMAT": "int8",
        "VLM_DEVICE": "CPU",
        "SEED": "42",
    },
).start()

from src.utils.common import ErrorMessages, ModelNames, Settings, settings


def test_all_error_messages():
    assert ErrorMessages.REQUEST_ERROR == "Request error occurred"
    assert ErrorMessages.LOAD_IMAGE_ERROR == "Error occurred while loading image"
    assert (
        ErrorMessages.CHAT_COMPLETION_ERROR
        == "Error occurred in chat_completions endpoint"
    )
    assert ErrorMessages.GET_MODELS_ERROR == "Error occurred in get_models endpoint"
    assert ErrorMessages.GPU_OOM_ERROR_MESSAGE == "error code: -5"
    assert (
        ErrorMessages.UNSUPPORTED_VIDEO_INPUT
        == "Video input is not supported for this model."
    )
    assert (
        ErrorMessages.UNSUPPORTED_VIDEO_URL_INPUT
        == "Video URL input is not supported for this model."
    )
    assert (
        ErrorMessages.CONVERT_MODEL_ERROR == "Error occurred in convert_model function"
    )


def test_model_names():
    assert ModelNames.QWEN == "qwen2"


def test_all_model_names():
    assert ModelNames.PHI == "phi-3.5-vision"


def test_settings():
    assert settings.APP_NAME == "vlm-openvino-serving"
    assert settings.SEED == 42


def test_settings_initialization():
    with mock.patch.dict(
        os.environ,
        {
            "http_proxy": "http://mock-proxy",
            "https_proxy": "https://mock-proxy",
            "no_proxy_env": "localhost,127.0.0.1",
            "VLM_MODEL_NAME": "mock_model",
            "VLM_COMPRESSION_WEIGHT_FORMAT": "int8",
            "VLM_DEVICE": "CPU",
            "SEED": "42",
        },
    ):
        settings = Settings()
        assert settings.http_proxy == "http://mock-proxy"
        assert settings.https_proxy == "https://mock-proxy"
        assert settings.no_proxy_env == "localhost,127.0.0.1"
        assert settings.VLM_MODEL_NAME == "mock_model"
        assert settings.VLM_COMPRESSION_WEIGHT_FORMAT == "int8"
        assert settings.VLM_DEVICE == "CPU"
        assert settings.SEED == 42


def test_ov_config_default():
    """Test default OV_CONFIG behavior when not set"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
        },
        clear=True,
    ):
        settings = Settings()
        ov_config = settings.get_ov_config_dict()
        assert ov_config == {"PERFORMANCE_HINT": "LATENCY"}


def test_ov_config_valid_json():
    """Test OV_CONFIG with valid JSON"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "OV_CONFIG": '{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 4}',
        },
        clear=True,
    ):
        settings = Settings()
        ov_config = settings.get_ov_config_dict()
        assert ov_config == {"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 4}


def test_ov_config_invalid_json():
    """Test OV_CONFIG with invalid JSON falls back to default"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "OV_CONFIG": '{"PERFORMANCE_HINT": "THROUGHPUT",}',  # Invalid JSON
        },
        clear=True,
    ):
        settings = Settings()
        ov_config = settings.get_ov_config_dict()
        assert ov_config == {"PERFORMANCE_HINT": "LATENCY"}  # Falls back to default


def test_ov_config_empty_string():
    """Test OV_CONFIG with empty string"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "OV_CONFIG": "",
        },
        clear=True,
    ):
        settings = Settings()
        ov_config = settings.get_ov_config_dict()
        assert ov_config == {"PERFORMANCE_HINT": "LATENCY"}  # Falls back to default


def test_vlm_log_level_valid():
    """Test VLM_LOG_LEVEL with valid values"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "VLM_LOG_LEVEL": "debug",
        },
        clear=True,
    ):
        settings = Settings()
        assert settings.VLM_LOG_LEVEL == "debug"


def test_vlm_log_level_invalid():
    """Test VLM_LOG_LEVEL with invalid value falls back to default"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "VLM_LOG_LEVEL": "invalid_level",
        },
        clear=True,
    ):
        settings = Settings()
        assert settings.VLM_LOG_LEVEL == "info"  # Falls back to default


def test_vlm_log_level_default():
    """Test VLM_LOG_LEVEL defaults to info when not set"""
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
        },
        clear=True,
    ):
        settings = Settings()
        assert settings.VLM_LOG_LEVEL == "info"


def test_logging_configuration():
    """Test that logging is configured with the correct level based on VLM_LOG_LEVEL"""
    import logging
    with mock.patch.dict(
        os.environ,
        {
            "VLM_MODEL_NAME": "mock_model",
            "VLM_DEVICE": "CPU",
            "VLM_LOG_LEVEL": "debug",
        },
        clear=True,
    ):
        # We need to reload the module to test the logging configuration
        import importlib
        from src.utils import common
        importlib.reload(common)
        # Verify that the logging level was set correctly
        assert logging.getLogger().level == logging.DEBUG
