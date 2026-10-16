# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Download ModelScope snapshots into the shared model repository."""

import os
import re

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

        model_dir = os.path.join(output_dir, self.plugin_name, model_name.replace("/", "_"))
        os.makedirs(model_dir, exist_ok=True)
        kwargs.get("_model_download_dir", []).append(model_dir)
        downloaded_path = snapshot_download(
            model_name, revision=kwargs.get("revision"), local_dir=model_dir
        )
        if not os.path.isdir(downloaded_path) or not os.listdir(downloaded_path):
            raise RuntimeError(f"ModelScope snapshot is empty: {model_name}")
        return {
            "model_name": model_name,
            "source": self.plugin_name,
            "download_path": downloaded_path,
            "success": True,
        }
