# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import pytest

from src.api.models import ModelHub
from src.api import main
from src.plugins.huggingface_plugin import HuggingFacePlugin
from src.plugins.openai_whisper_plugin import OpenAIWhisperPlugin


def test_official_checkpoint_is_downloaded_without_loading(tmp_path):
    model_dir = tmp_path / "openai-whisper" / "base"
    checkpoint = model_dir / "base.pt"
    def download(url, root, in_memory):
        checkpoint.write_bytes(b"checkpoint")
        return str(checkpoint)

    with patch("src.plugins.openai_whisper_plugin.whisper._download", side_effect=download) as mock_download:
        dirs = []
        result = OpenAIWhisperPlugin().download("base", str(tmp_path), _model_download_dir=dirs)
    assert ModelHub("openai-whisper") is ModelHub.OPENAI_WHISPER
    assert result["source"] == "openai-whisper"
    assert dirs == [str(model_dir)]
    from src.plugins.openai_whisper_plugin import whisper
    mock_download.assert_called_once_with(whisper._MODELS["base"], str(model_dir), False)


def test_unknown_checkpoint_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        OpenAIWhisperPlugin().download("../other", str(tmp_path))


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


async def test_asr_only_profile_skips_text_gen_startup_models(monkeypatch):
    monkeypatch.setenv("STARTUP_MODELS_REQUIRED_PROFILE", "text-gen")
    monkeypatch.setenv("COMPOSE_PROFILES", "asr")
    with patch.object(main, "load_startup_models_config") as load:
        async with main.lifespan(main.app):
            pass
    load.assert_not_called()


async def test_combined_profiles_keep_text_gen_startup_models(monkeypatch):
    monkeypatch.setenv("STARTUP_MODELS_REQUIRED_PROFILE", "text-gen")
    monkeypatch.setenv("COMPOSE_PROFILES", "asr,text-gen")
    config = object()
    with patch.object(main, "load_startup_models_config", return_value=config), \
         patch.object(main, "_submit_startup_models", new_callable=AsyncMock) as submit:
        async with main.lifespan(main.app):
            pass
    submit.assert_awaited_once_with(config)
