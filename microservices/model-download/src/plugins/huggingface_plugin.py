# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import HfHubHTTPError
from src.core.interfaces import ListingAuthError, ModelDownloadPlugin, DownloadTask
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

    @property
    def supports_listing(self) -> bool:
        return True

    @property
    def listing_filter_fields(self) -> list[str]:
        return ["author", "owner", "organization", "search", "filter", "tags"]

    def list_models(self, filters=None, limit=50, offset=0, **kwargs) -> dict:
        """List models for an owner/organization on the HuggingFace Hub."""
        filters = filters or {}
        token = os.getenv("HF_TOKEN")

        author = filters.get("author") or filters.get("owner") or filters.get("organization")
        search = str(filters.get("search")) if filters.get("search") is not None else None
        model_filter = filters.get("filter")
        tags = filters.get("tags")
        if tags and not model_filter:
            model_filter = tags

        api = HfApi(token=token)
        fetch_limit = (limit + offset) if offset else limit

        try:
            results = api.list_models(
                author=author,
                search=search,
                filter=model_filter,
                sort="downloads",
                direction=-1,
                limit=fetch_limit,
                expand=["downloads", "likes", "lastModified", "pipeline_tag", "tags", "safetensors"],
            )
            models = list(results)
        except HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise ListingAuthError("HuggingFace credentials are missing or invalid.") from exc
            raise

        page = models[offset: offset + limit] if offset else models[:limit]
        items = [self._to_item(model) for model in page if getattr(model, "id", None)]
        return {"items": items, "total": None}

    @staticmethod
    def _to_item(model) -> dict:
        model_id = model.id
        owner = model_id.split("/")[0] if "/" in model_id else None
        last_modified = getattr(model, "last_modified", None)

        safetensors = getattr(model, "safetensors", None)
        params = getattr(safetensors, "parameters", None) if safetensors else None
        precisions = sorted(params.keys()) if params else []

        return {
            "name": model_id,
            "owner": owner,
            "precisions": precisions,
            "tags": list(getattr(model, "tags", []) or []),
            "model_type": getattr(model, "pipeline_tag", None),
            "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else last_modified,
            "metadata": {
                "downloads": getattr(model, "downloads", None),
                "likes": getattr(model, "likes", None),
                "library_name": getattr(model, "library_name", None),
            },
        }

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