# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Fetch official OpenAI Whisper checkpoints without loading their pickle."""

import os

import whisper

from src.core.interfaces import ModelDownloadPlugin


class OpenAIWhisperPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "openai-whisper"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == self.plugin_name

    def download(self, model_name: str, output_dir: str, **kwargs) -> dict:
        if model_name not in {"tiny", "base", "small", "medium", "large-v3"}:
            raise ValueError(f"Unsupported OpenAI Whisper checkpoint: {model_name}")
        model_dir = os.path.join(output_dir, self.plugin_name, model_name)
        os.makedirs(model_dir, exist_ok=True)
        kwargs.get("_model_download_dir", []).append(model_dir)
        checkpoint = whisper._download(whisper._MODELS[model_name], model_dir, False)
        if not os.path.isfile(checkpoint):
            raise RuntimeError(f"Whisper checkpoint missing: {model_name}")
        return {
            "model_name": model_name,
            "source": self.plugin_name,
            "download_path": model_dir,
            "success": True,
        }
