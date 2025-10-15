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
        model_specific_path = os.path.join(output_dir, model_name.replace("/", "_"))
        os.makedirs(model_specific_path, exist_ok=True)

        logger.info(f"Downloading HuggingFace model {model_name} to {model_specific_path}")
        model_downloaded_path = snapshot_download(
            repo_id=model_name,
            token=hf_token,
            local_dir=model_specific_path,
            revision=revision,
        )

        return {
            "model_name": model_name,
            "source": "huggingface",
            "download_path": model_downloaded_path,
            "success": True
        }

    def get_download_tasks(self, model_name: str, **kwargs):
        raise NotImplementedError("HuggingFace plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs):
        raise NotImplementedError("HuggingFace plugin does not support task-based downloading")

    def post_process(self, model_name: str, output_dir: str, downloaded_paths: list, **kwargs) -> dict:
        return {
            "model_name": model_name,
            "source": "huggingface",
            "download_path": output_dir,
            "success": True
        }