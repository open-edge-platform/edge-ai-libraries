# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from src.core.interfaces import DownloadTask, ModelDownloadPlugin
from src.utils.logging import logger


PIPELINE_ZOO_ARCHIVE_URL = os.getenv(
    "PIPELINE_ZOO_ARCHIVE_URL",
    "https://github.com/dlstreamer/pipeline-zoo-models/archive/refs/heads/main.tar.gz",
)
PIPELINE_ZOO_CACHE_DIR = Path(
    os.getenv("PIPELINE_ZOO_CACHE_DIR", "/tmp/model_download_pipeline_zoo")
)
PIPELINE_ZOO_EXTRACTED_DIR = PIPELINE_ZOO_CACHE_DIR / "pipeline-zoo-models-main"
# Hidden marker written only after a successful, fully-extracted download.
PIPELINE_ZOO_COMPLETE_MARKER = ".download_complete"


class PipelineZooModelsPlugin(ModelDownloadPlugin):
    """Plugin for downloading models from dlstreamer/pipeline-zoo-models."""

    _repo_lock = threading.Lock()

    @property
    def plugin_name(self) -> str:
        return "pipeline-zoo-models"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """Return True for pipeline-zoo hubs; no model lookup."""
        hub_normalized = hub.lower().replace("_", "-")
        return hub_normalized in {"pipeline-zoo-models", "pipeline-zoo"}

    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """Download one or more pipeline-zoo models from the upstream archive."""
        logger.info(f"Starting pipeline-zoo download for model(s): {model_name}")

        # Keep the same destination convention as other plugins: output_dir/<hub>/<model>
        hub_dir = os.path.join(output_dir, "pipeline-zoo-models")
        os.makedirs(hub_dir, exist_ok=True)

        with self._repo_lock:
            repo_dir = self._ensure_repo_downloaded()

        if model_name.strip().lower() == "all":
            requested_models = self._list_models_in_repo(repo_dir)
        else:
            requested_models = self._parse_models(model_name)
        if not requested_models:
            raise ValueError("No pipeline-zoo model names were provided")

        missing_models: List[str] = []
        for model in requested_models:
            source_dir = repo_dir / "storage" / model
            target_dir = os.path.join(hub_dir, model)
            if not source_dir.is_dir():
                missing_models.append(model)
                continue

            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(str(source_dir), target_dir)
            logger.info(f"Installed pipeline-zoo model '{model}' to {target_dir}")

        if missing_models:
            raise RuntimeError(
                "Pipeline-zoo model(s) not found in repository storage: "
                + ", ".join(missing_models)
            )

        host_path = hub_dir
        if host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

        logger.info(f"Pipeline-zoo model(s) downloaded successfully: {model_name}")

        return {
            "model_name": model_name,
            "source": "pipeline-zoo-models",
            "download_path": host_path,
            "success": True,
        }

    @staticmethod
    def _list_models_in_repo(repo_dir: Path) -> List[str]:
        storage_dir = repo_dir / "storage"
        if not storage_dir.is_dir():
            raise RuntimeError(f"Pipeline-zoo storage directory not found at {storage_dir}")
        return sorted([entry.name for entry in storage_dir.iterdir() if entry.is_dir()])

    def _ensure_repo_downloaded(self) -> Path:
        marker = PIPELINE_ZOO_EXTRACTED_DIR / PIPELINE_ZOO_COMPLETE_MARKER
        if marker.is_file():
            logger.info("pipeline_zoo_repo_cache_available", path=str(PIPELINE_ZOO_EXTRACTED_DIR))
            return PIPELINE_ZOO_EXTRACTED_DIR

        # Purge any stale / partial cache from a previous interrupted download.
        if PIPELINE_ZOO_EXTRACTED_DIR.exists():
            logger.info("pipeline_zoo_repo_cache_stale_purging", path=str(PIPELINE_ZOO_EXTRACTED_DIR))
            shutil.rmtree(PIPELINE_ZOO_EXTRACTED_DIR)

        PIPELINE_ZOO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fd, archive_path = tempfile.mkstemp(prefix="pipeline-zoo-models-", suffix=".tar.gz")
        os.close(fd)

        try:
            logger.info("pipeline_zoo_repo_download_start", url=PIPELINE_ZOO_ARCHIVE_URL)
            urllib.request.urlretrieve(PIPELINE_ZOO_ARCHIVE_URL, archive_path)

            # ``filter="data"`` (Python >= 3.12) rejects absolute paths,
            # parent-directory traversal, symlinks/hardlinks escaping the
            # destination and special device files.
            if not hasattr(tarfile, "data_filter"):
                raise RuntimeError(
                    "tarfile data filter is unavailable; Python >= 3.12 is required "
                    "to safely extract the pipeline-zoo archive"
                )
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                tar_ref.extractall(path=PIPELINE_ZOO_CACHE_DIR, filter="data")

            if not PIPELINE_ZOO_EXTRACTED_DIR.is_dir():
                raise RuntimeError(
                    f"Extracted pipeline-zoo repository directory not found: {PIPELINE_ZOO_EXTRACTED_DIR}"
                )

            # # Write the marker last: its presence signals a complete, trusted cache.
            (PIPELINE_ZOO_EXTRACTED_DIR / PIPELINE_ZOO_COMPLETE_MARKER).touch()

            logger.info("pipeline_zoo_repo_download_done", path=str(PIPELINE_ZOO_EXTRACTED_DIR))
            return PIPELINE_ZOO_EXTRACTED_DIR
        finally:
            if os.path.exists(archive_path):
                os.remove(archive_path)

    def _parse_models(self, model_name: str) -> List[str]:
        """Parse comma-separated model names into a normalized list."""
        return [model.strip() for model in model_name.split(",") if model.strip()]

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        Pipeline-zoo does not support task-based downloading.
        """
        raise NotImplementedError("Pipeline-zoo plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        Pipeline-zoo does not support task-based downloading.
        """
        raise NotImplementedError("Pipeline-zoo plugin does not support task-based downloading")

    async def post_process(
        self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs
    ) -> Dict[str, Any]:
        """
        Post-process the downloaded files.
        For pipeline-zoo, this is handled by direct copy during download.
        """
        return {
            "model_name": model_name,
            "source": "pipeline-zoo-models",
            "download_path": output_dir,
            "success": True,
        }
