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
    assert settings.APP_NAME == "vlm-inference-microservice"
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
