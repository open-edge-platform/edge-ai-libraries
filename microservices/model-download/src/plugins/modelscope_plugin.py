# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Download ModelScope snapshots into the shared model repository."""

import re
from pathlib import Path

from modelscope.hub.snapshot_download import snapshot_download

from src.core.interfaces import ModelDownloadPlugin


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class ModelScopePlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "modelscope"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == self.plugin_name

    def download(self, model_name: str, output_dir: str, **kwargs) -> dict:
        if not _MODEL_ID.fullmatch(model_name) or ".." in model_name.split("/"):
            raise ValueError("ModelScope model name must be an owner/model identifier")

        base = Path(output_dir).resolve()
        model_dir = base / self.plugin_name / model_name.replace("/", "_")
        if model_dir.is_symlink() or not model_dir.resolve().is_relative_to(base):
            raise ValueError("ModelScope snapshot must remain inside the output directory")
        model_dir.mkdir(parents=True, exist_ok=True)
        kwargs.get("_model_download_dir", []).append(str(model_dir))
        downloaded_path = Path(snapshot_download(
            model_name, revision=kwargs.get("revision"), local_dir=str(model_dir),
        ))
        if downloaded_path.resolve() != model_dir.resolve():
            raise RuntimeError("ModelScope returned an unexpected snapshot directory")
        if not downloaded_path.is_dir() or not any(downloaded_path.iterdir()):
            raise RuntimeError(f"ModelScope snapshot is empty: {model_name}")
        return {
            "model_name": model_name,
            "source": self.plugin_name,
            "download_path": str(downloaded_path),
            "success": True,
        }
