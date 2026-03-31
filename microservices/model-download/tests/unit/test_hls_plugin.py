# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
from pathlib import Path
import pytest
from unittest.mock import patch

from src.plugins.hls_plugin import HlsPlugin


@pytest.fixture
def hls_plugin():
    return HlsPlugin()


def test_plugin_properties(hls_plugin):
    assert hls_plugin.plugin_name == "hls"
    assert hls_plugin.plugin_type == "downloader"


@pytest.mark.parametrize("model_type,expected", [
    ("3d-pose", True),
    ("rppg", True),
    ("ai-ecg", True),
    ("vision", False),
])
def test_can_handle_types(hls_plugin, model_type, expected):
    assert hls_plugin.can_handle("demo", "hls", type=model_type) is expected


def test_can_handle_wrong_hub(hls_plugin):
    assert hls_plugin.can_handle("demo", "huggingface", type="3d-pose") is False


@pytest.mark.asyncio
async def test_download_success(hls_plugin):
    with patch.object(HlsPlugin, "_run_script", return_value=0) as mock_run:
        result = await hls_plugin.download(
            model_name="human-pose-estimation-3d-0001",
            output_dir="/tmp",
            type="3d-pose"
        )

    mock_run.assert_called_once()
    assert result["success"] is True
    assert result["type"] == "3d-pose"
    assert result["source"] == "hls"
    assert result["download_path"].endswith("3d-pose")


@pytest.mark.asyncio
async def test_download_unsupported_type(hls_plugin):
    with pytest.raises(ValueError):
        await hls_plugin.download(
            model_name="foo",
            output_dir="/tmp",
            type="unsupported"
        )


def test_build_args_rppg_flags(hls_plugin):
    models_dir = Path("/tmp/models")

    args = hls_plugin._build_args("rppg", {}, models_dir)
    assert args == ["--models-dir", str(models_dir)]


@pytest.mark.asyncio
async def test_download_failure_propagates(hls_plugin):
    with patch.object(HlsPlugin, "_run_script", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            await hls_plugin.download(
                model_name="human-pose-estimation-3d-0001",
                output_dir="/tmp",
                type="3d-pose"
            )
