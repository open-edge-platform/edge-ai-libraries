# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from huggingface_hub import snapshot_download
from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger
import os

class HuggingFacePlugin(ModelDownloadPlugin):
    """
    Plugin for downloading models from the HuggingFace Hub.
    """
    @property
    def plugin_name(self) -> str:
        return "huggingface"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "huggingface"
    

    def download(self, model_name: str, output_dir: str, **kwargs) -> dict:
        hf_token = kwargs.get("hf_token")
        revision = kwargs.get("revision")
        
        # Create hub-specific directory under the output directory
        hub_dir = os.path.join(output_dir, "huggingface")
        model_specific_path = os.path.join(hub_dir, model_name.replace("/", "_"))
        os.makedirs(model_specific_path, exist_ok=True)

        logger.info(f"Downloading HuggingFace model {model_name} to {model_specific_path}")
        model_downloaded_path = snapshot_download(
            repo_id=model_name,
            token=hf_token,
            local_dir=model_specific_path,
            revision=revision,
        )

        logger.info(f"Model {model_name} downloaded to {model_downloaded_path}")

        host_path = hub_dir
        if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

        return {
            "model_name": model_name,
            "source": "huggingface",
            "download_path": host_path,
            "success": True
        }

    def get_download_tasks(self, model_name: str, **kwargs):
        raise NotImplementedError("HuggingFace plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs):
        raise NotImplementedError("HuggingFace plugin does not support task-based downloading")

    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: list, **kwargs) -> dict:
        return {
            "model_name": model_name,
            "source": "huggingface",
            "download_path": output_dir,
            "success": True
        }