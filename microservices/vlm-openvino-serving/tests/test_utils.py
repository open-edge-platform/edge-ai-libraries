# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
from unittest import mock
from unittest.mock import patch

import aiohttp
import yaml

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

import base64
import tempfile
from pathlib import Path

import pytest
from src.utils.common import ErrorMessages, ModelNames
from src.utils.data_models import MessageContentVideoUrl
from src.utils import utils as utils_module
from src.utils.utils import load_images  # Add this import
from src.utils.utils import (
    convert_model,
    decode_and_save_video,
    get_device_property,
    get_devices,
    is_model_ready,
    load_model_config,
    setup_seed,
    validate_video_inputs,
)


def _resolve_cache_key(config_path: Path) -> str:
    return str(Path(config_path).expanduser().resolve(strict=False))


def _clear_model_config_cache(config_path: Path | None = None):
    cache = utils_module._MODEL_CONFIG_CACHE  # type: ignore[attr-defined]
    if config_path is None:
        cache.clear()
        return
    cache.pop(_resolve_cache_key(config_path), None)


@pytest.fixture(autouse=True)
def reset_model_config_cache():
    _clear_model_config_cache()
    yield
    _clear_model_config_cache()


def test_is_model_ready():
    model_dir = Path("tests/mock_model_dir")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "mock_openvino_model.xml").touch()

    with patch(
        "src.utils.utils._find_files_matching_pattern",
        return_value=["mock_openvino_model.xml"],
    ):
        assert is_model_ready(model_dir) is True

    (model_dir / "mock_openvino_model.xml").unlink()
    with patch("src.utils.utils._find_files_matching_pattern", return_value=[]):
        assert is_model_ready(model_dir) is False


def test_setup_seed():
    setup_seed(42)
    import random

    import numpy as np

    assert random.randint(0, 100) == 81
    assert np.random.randint(0, 100) == 51


def test_get_devices():
    devices = get_devices()
    assert isinstance(devices, list)
    assert len(devices) > 0


def test_get_device_property():
    devices = get_devices()
    if devices:
        device_props = get_device_property(devices[0])
        assert isinstance(device_props, dict)


def test_get_device_property_edge_cases():
    assert get_device_property("INVALID_DEVICE") == {}


def test_load_model_config():
    config_path = Path("tests/mock_config.yaml")
    config_path.write_text("mock_model:\n  param: value")
    config = load_model_config("mock_model", config_path)
    assert config == {"param": "value"}

    _clear_model_config_cache(config_path)
    config_path.unlink()
    config = load_model_config("mock_model", config_path)
    assert config == {}


def test_decode_and_save_video():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        valid_base64_video = (
            "data:video/mp4;base64," + base64.b64encode(b"mock_video_data").decode()
        )
        video_path = decode_and_save_video(valid_base64_video, tmp_path)
        assert Path(video_path.replace("file://", "")).exists()

        invalid_base64_video = "data:video/mp4;base64,invalid_data"
        with pytest.raises(ValueError):
            decode_and_save_video(invalid_base64_video, tmp_path)


def test_validate_video_inputs():
    content = MessageContentVideoUrl(
        type="video_url", video_url={"url": "http://example.com/video.mp4"}
    )
    model_name = "non_qwen_model"
    assert (
        validate_video_inputs(content, model_name)
        == ErrorMessages.UNSUPPORTED_VIDEO_URL_INPUT
    )

    model_name = ModelNames.QWEN
    assert validate_video_inputs(content, model_name) is None

    invalid_content = {"invalid_key": "invalid_value"}
    assert validate_video_inputs(invalid_content, model_name) is None


@mock.patch("src.utils.utils.AutoTokenizer.from_pretrained")
@mock.patch("src.utils.utils.OVModelForVisualCausalLM.from_pretrained")
@mock.patch("src.utils.utils.convert_tokenizer")
@mock.patch("src.utils.utils.ov.save_model")
@mock.patch("os.path.isdir", return_value=True)  # Mock directory existence
def test_convert_model(
    mock_isdir,
    mock_save_model,
    mock_convert_tokenizer,
    mock_from_pretrained,
    mock_auto_tokenizer,
):
    """
    Test the convert_model function to ensure it converts models correctly.
    """
    model_id = "test-model"
    cache_dir = "/tmp/test-cache"
    model_type = "vlm"
    weight_format = "int4"

    # Mock the behavior of the tokenizer and model
    mock_auto_tokenizer.return_value = mock.Mock()
    mock_from_pretrained.return_value = mock.Mock()

    try:
        convert_model(model_id, cache_dir, model_type, weight_format)
        assert os.path.isdir(
            cache_dir
        ), "Model conversion failed, cache directory not created."
    except Exception as e:
        assert False, f"convert_model raised an exception: {e}"


def test_load_images_invalid_base64(mocker):
    invalid_base64_image = "data:image/jpeg;base64,invalid_data"
    with pytest.raises(
        ValueError, match="Invalid input: Incorrect padding in base64 data"
    ):
        mocker.patch("aiohttp.ClientSession.get")  # Mock aiohttp session
        asyncio.run(load_images([invalid_base64_image]))


def test_load_images_http_error(mocker):
    mocker.patch(
        "aiohttp.ClientSession.get",
        side_effect=aiohttp.ClientError("Mocked HTTP error"),
    )
    with pytest.raises(RuntimeError, match="Request error occurred: Mocked HTTP error"):
        asyncio.run(load_images(["http://example.com/image.jpg"]))


def test_load_images_general_error(mocker):
    mocker.patch(
        "aiohttp.ClientSession.get", side_effect=Exception("Mocked general error")
    )
    with pytest.raises(
        RuntimeError, match="Error occurred while loading image: Mocked general error"
    ):
        asyncio.run(load_images(["http://example.com/image.jpg"]))


def test_get_device_property_invalid_device():
    assert get_device_property("INVALID_DEVICE") == {}


def test_load_model_config_yaml_error(mocker):
    mocker.patch("builtins.open", mocker.mock_open(read_data="invalid_yaml: ["))
    mocker.patch("yaml.safe_load", side_effect=yaml.YAMLError("Mocked YAML error"))
    with pytest.raises(RuntimeError, match="Error parsing YAML configuration"):
        load_model_config("mock_model")


def test_load_model_config_general_error(mocker):
    mocker.patch("builtins.open", side_effect=Exception("Mocked general error"))
    mocker.patch(
        "yaml.safe_load", side_effect=Exception("Mocked general error")
    )  # Ensure exception is raised
    with pytest.raises(
        RuntimeError, match="Error loading model configuration: Mocked general error"
    ):
        load_model_config("mock_model")


def test_decode_and_save_video_general_error(mocker):
    mocker.patch("base64.b64decode", side_effect=Exception("Mocked general error"))
    with pytest.raises(
        RuntimeError, match="Error decoding and saving video: Mocked general error"
    ):
        decode_and_save_video("data:video/mp4;base64,valid_data")
