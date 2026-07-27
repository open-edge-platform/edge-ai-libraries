# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import HfHubHTTPError, GatedRepoError, RepositoryNotFoundError
from src.core.interfaces import ListingAuthError, ModelDownloadPlugin, DownloadTask, PluginConfigKey
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

    def config_keys(self) -> list:
        return [
            PluginConfigKey(
                name="HF_TOKEN",
                description=(
                    "HuggingFace access token. Required only for gated or private "
                    "models; public models work without authentication."
                ),
                sensitive=True,
            ),
        ]

    @property
    def supports_listing(self) -> bool:
        return True

    @property
    def listing_filter_fields(self) -> list[str]:
        return ["author", "search", "tags"]

    def list_models(self, filters=None, limit=50, offset=0, **kwargs) -> dict:
        """List models for an author (user, owner, or organization) on the HuggingFace Hub."""
        filters = filters or {}
        self._validate_listing_filters(filters)
        # Per-request override wins; env HF_TOKEN is the fallback (already applied
        # by resolve_config when a resolved_config is supplied).
        resolved_config = kwargs.get("resolved_config") or {}
        token = resolved_config.get("HF_TOKEN") or os.getenv("HF_TOKEN")

        # HuggingFace exposes the repo namespace (a user, owner, or organization) as `author`.
        author = filters.get("author")
        search = str(filters.get("search")) if filters.get("search") is not None else None
        # `tags` maps to HuggingFace's `filter` parameter (library, language, task, license, ...).
        model_filter = filters.get("tags")

        api = HfApi(token=token)
        # Fetch one extra item so the API can tell whether another page exists.
        fetch_limit = offset + limit + 1

        try:
            results = api.list_models(
                author=author,
                search=search,
                filter=model_filter,
                sort="downloads",
                direction=-1,
                limit=fetch_limit,
                expand=["downloads", "likes", "lastModified", "pipeline_tag", "tags", "safetensors", "gated"],
            )
            models = list(results)
        except HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise ListingAuthError("HuggingFace credentials are missing or invalid.") from exc
            raise

        page_end = offset + limit + 1
        page = models[offset:page_end]
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

        tags = list(getattr(model, "tags", []) or [])
        # HuggingFace encodes the license as a "license:<id>" tag (e.g. "license:apache-2.0").
        license_id = next(
            (tag.split("license:", 1)[1] for tag in tags if tag.startswith("license:")),
            None,
        )

        # `gated` is False for open models, or "auto"/"manual" for gated models.
        # Gated models require accepting the license/terms and a valid HF token.
        gated = getattr(model, "gated", None)
        requires_token = bool(gated) and gated is not False

        return {
            "name": model_id,
            "owner": owner,
            "precisions": precisions,
            "tags": tags,
            "model_type": getattr(model, "pipeline_tag", None),
            "license": license_id,
            "gated": gated,
            "requires_token": requires_token,
            "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else last_modified,
            "metadata": {
                "downloads": getattr(model, "downloads", None),
                "likes": getattr(model, "likes", None),
                "library_name": getattr(model, "library_name", None),
            },
        }

    @staticmethod
    def _check_access(model_name: str, token) -> None:
        """Raise a clear error if the repo is gated/private and not accessible.

        HuggingFace's snapshot_download can mask a gated or unauthorized repo as a
        misleading "check your internet connection" error. Checking access first
        surfaces the real cause. Non-access errors (e.g. transient 5xx or network
        issues) are ignored here so the actual download can surface them.
        """
        api = HfApi(token=token)
        try:
            api.auth_check(model_name)
        except GatedRepoError as exc:
            raise ValueError(
                f"'{model_name}' is a gated model. Provide an HF_TOKEN that has been "
                f"granted access to this repository."
            ) from exc
        except RepositoryNotFoundError as exc:
            raise ValueError(
                f"'{model_name}' was not found or is private. If it is gated or private, "
                f"provide an HF_TOKEN with access to this repository."
            ) from exc
        except HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise ValueError(
                    f"Access to '{model_name}' is unauthorized. Provide an HF_TOKEN with "
                    f"access to this repository."
                ) from exc
            return
        except Exception:
            # Network or other unexpected error: let the download attempt surface it.
            return

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        return hub.lower() == "huggingface"

    def download(self, model_name: str, output_dir: str, **kwargs) -> dict:
        # Per-request override wins; env HF_TOKEN is the fallback (applied by
        # resolve_config). Fall back to the legacy hf_token kwarg for compatibility.
        resolved_config = kwargs.get("resolved_config") or {}
        hf_token = resolved_config.get("HF_TOKEN") or kwargs.get("hf_token")
        revision = kwargs.get("revision")
        
        # Create hub-specific directory under the output directory
        hub_dir = os.path.join(output_dir, "huggingface")
        model_specific_path = os.path.join(hub_dir, model_name.replace("/", "_"))
        os.makedirs(model_specific_path, exist_ok=True)

        logger.info(f"Downloading HuggingFace model {model_name} to {model_specific_path}")
        # Verify access up-front: a gated/unauthorized repo otherwise surfaces as a
        # misleading "check your internet connection" error from snapshot_download.
        self._check_access(model_name, hf_token)
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