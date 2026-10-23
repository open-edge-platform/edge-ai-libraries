# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import pytest

from src.api import main
from src.plugins import PLUGINS
from src.plugins.huggingface_plugin import HuggingFacePlugin


def test_openai_whisper_is_not_a_model_download_plugin():
    assert "openai-whisper" not in PLUGINS


def test_huggingface_can_fetch_only_one_whispercpp_file(tmp_path):
    with patch.object(HuggingFacePlugin, "_check_access"), \
         patch("src.plugins.huggingface_plugin.snapshot_download", return_value=str(tmp_path)) as snapshot:
        HuggingFacePlugin().download(
            "ggerganov/whisper.cpp", str(tmp_path),
            config={"files": ["ggml-base.bin"]},
        )
    assert snapshot.call_args.kwargs["allow_patterns"] == ["ggml-base.bin"]


def test_huggingface_rejects_filename_traversal(tmp_path):
    with pytest.raises(ValueError, match="plain filenames"):
        HuggingFacePlugin().download(
            "ggerganov/whisper.cpp", str(tmp_path),
            config={"files": ["../secret"]},
        )


async def test_startup_models_load_config_and_submit():
    config = object()
    with patch.object(main, "load_startup_models_config", return_value=config), \
         patch.object(main, "_submit_startup_models", new_callable=AsyncMock) as submit:
        async with main.lifespan(main.app):
            pass
    submit.assert_awaited_once_with(config)


async def test_startup_models_do_not_submit_when_config_is_unset():
    with patch.object(main, "load_startup_models_config", return_value=None) as load, \
         patch.object(main, "_submit_startup_models", new_callable=AsyncMock) as submit:
        async with main.lifespan(main.app):
            pass
    load.assert_called_once_with()
    submit.assert_not_awaited()
