# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""External sources downloader plugin.

Handles tarball-based hubs (``pipeline-zoo-models``, ``udf-timeseries``)
and OMZ downloads via a YAML-driven dispatch on ``kind``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.core.interfaces import DownloadTask, ModelDownloadPlugin
from src.utils.logging import logger


_CONFIG_DIR = Path(__file__).with_name("external_sources")
_PROFILE_FILE = _CONFIG_DIR / "sources.yaml"
_OMZ_VENV_BIN = Path(os.environ.get("OMZ_VENV", "/opt/.venv-omz")) / "bin"

# Fail fast: Python >= 3.12 required for tarfile.data_filter
if not hasattr(tarfile, "data_filter"):
    raise RuntimeError(
        "tarfile data_filter unavailable; Python >= 3.12 required"
    )


@lru_cache(maxsize=1)
def _load_profile() -> Dict[str, Dict[str, Any]]:
    """Read the static profile shipped with the plugin."""
    if not _PROFILE_FILE.is_file():
        logger.warning("external_sources_profile_missing", path=str(_PROFILE_FILE))
        return {}
    with open(_PROFILE_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources = data.get("sources", {})
    if not isinstance(sources, dict):
        logger.warning("external_sources_profile_invalid", path=str(_PROFILE_FILE))
        return {}
    return sources




class ExternalSourcesPlugin(ModelDownloadPlugin):
    """Combined downloader for external hubs (tarball + OMZ)."""

    @property
    def plugin_name(self) -> str:
        return "external-sources"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def supported_hubs(self) -> List[str]:
        return list(_load_profile().keys())

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        normalized = (hub or "").lower().replace("_", "-")
        return normalized in _load_profile()

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        raise NotImplementedError(
            "external-sources plugin does not support task-based downloading"
        )

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        raise NotImplementedError(
            "external-sources plugin does not support task-based downloading"
        )

    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """Download from an external hub (tarball or OMZ)."""
        hub = (kwargs.get("hub") or "").lower().replace("_", "-")
        if not hub:
            raise ValueError(
                "external-sources plugin requires 'hub' in download kwargs"
            )

        profile = _load_profile().get(hub)
        if profile is None:
            raise ValueError(f"Unsupported hub for external-sources plugin: {hub!r}")

        if not model_name or not model_name.strip():
            raise ValueError(f"Model name is required (hub={hub})")

        if "/" in model_name or ".." in model_name or model_name.startswith("."):
            raise ValueError(f"Invalid model name: {model_name!r}")

        target_dir = os.path.join(output_dir, hub, model_name)
        kind = profile.get("kind")

        try:
            if kind == "tarball":
                self._fetch_tarball(model_name, profile, target_dir)
            elif kind == "omz":
                self._fetch_omz(model_name, target_dir)
            else:
                raise ValueError(
                    f"Unknown 'kind' for hub {hub!r}: {kind!r} (check sources.yaml)"
                )

            host_path = target_dir
            if host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

            logger.info(
                "external_sources_download_succeeded",
                hub=hub,
                model_name=model_name,
                target=target_dir,
            )
            return {
                "model_name": model_name,
                "source": hub,
                "download_path": host_path,
                "success": True,
            }
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

    def _fetch_tarball(
        self, model_name: str, profile: Dict[str, Any], target_dir: str
    ) -> None:
        """Download and extract a tarball-based model (shared or per-model archive)."""
        if profile.get("archive_url_template"):
            # Per-model tarball: download and extract directly to target
            url = profile["archive_url_template"].format(model_name=model_name)
            os.makedirs(target_dir, exist_ok=True)
            self._download_and_extract_tarball(url, target_dir)
            logger.info(
                "external_sources_model_tarball_extracted",
                model_name=model_name,
                target=target_dir,
            )
        else:
            # Shared archive: download, extract to temp, copy requested subdir
            archive_url = profile.get("archive_url")
            if not archive_url:
                raise RuntimeError("Profile entry is missing 'archive_url'")

            model_subdir = profile.get("model_subdir", "{model_name}").format(
                model_name=model_name
            )
            if ".." in Path(model_subdir).parts:
                raise ValueError(f"model_subdir resolves outside archive: {model_subdir!r}")

            with tempfile.TemporaryDirectory(prefix="ext-archive-") as tmp_dir:
                extract_dir = os.path.join(tmp_dir, "extracted")
                os.makedirs(extract_dir)
                logger.info("external_sources_downloading_archive", url=archive_url)
                self._download_and_extract_tarball(archive_url, extract_dir)

                source_dir = os.path.join(extract_dir, model_subdir)
                if not os.path.isdir(source_dir):
                    raise FileNotFoundError(
                        f"Model {model_name!r} not found in archive at {source_dir}"
                    )

                os.makedirs(target_dir, exist_ok=True)
                shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
                logger.info(
                    "external_sources_tarball_copied",
                    model_name=model_name,
                    target=target_dir,
                )

    @staticmethod
    def _download_and_extract_tarball(url: str, target_dir: str) -> None:
        """Download a tarball from URL and extract it to target_dir."""
        with tempfile.TemporaryDirectory(prefix="ext-") as tmp_dir:
            archive_path = os.path.join(tmp_dir, "archive.tar.gz")
            urllib.request.urlretrieve(url, archive_path)  # noqa: S310
            with tarfile.open(archive_path, "r:*") as tar_ref:
                tar_ref.extractall(path=target_dir, filter="data")

    def _fetch_omz(self, model_name: str, target_dir: str) -> None:
        """Download and convert an OMZ model using omz_downloader/omz_converter."""
        omz_downloader = _OMZ_VENV_BIN / "omz_downloader"
        omz_converter = _OMZ_VENV_BIN / "omz_converter"

        if not omz_downloader.exists() or not omz_converter.exists():
            raise RuntimeError(
                f"OMZ tools not found in {_OMZ_VENV_BIN}; "
                "ensure OMZ venv is created (see entrypoint.sh)"
            )

        os.makedirs(os.path.dirname(target_dir), exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ext-omz-") as tmp_dir:
            # Download
            logger.info("external_sources_omz_downloading", model_name=model_name)
            self._run_omz_tool(
                [str(omz_downloader), "--name", model_name, "--output_dir", tmp_dir]
            )

            # Convert
            logger.info("external_sources_omz_converting", model_name=model_name)
            self._run_omz_tool(
                [
                    str(omz_converter),
                    "--name",
                    model_name,
                    "--download_dir",
                    tmp_dir,
                    "--output_dir",
                    tmp_dir,
                ]
            )

            # Move converted artefacts: omz_converter produces intel/ or public/ subdirs
            self._materialize_omz_artefacts(model_name, tmp_dir, target_dir)

    @staticmethod
    def _run_omz_tool(command: List[str]) -> None:
        """Run an OMZ CLI tool and raise on failure."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip() if result.stderr else "<empty>"
                raise RuntimeError(
                    f"OMZ tool failed (rc={result.returncode}): {' '.join(command)}\n"
                    f"stderr: {stderr}"
                )
            if result.stdout:
                logger.debug("omz_tool_output", output=result.stdout.strip())
        except FileNotFoundError as e:
            raise RuntimeError(f"OMZ tool not found: {command[0]}") from e

    @staticmethod
    def _materialize_omz_artefacts(
        model_name: str, tmp_dir: str, target_dir: str
    ) -> None:
        """Move converted OMZ artefacts from temp to target."""
        # omz_converter produces intel/ or public/ subdirs; find the model dir
        source_dir = None
        for category in ("intel", "public"):
            candidate = os.path.join(tmp_dir, category, model_name)
            if os.path.isdir(candidate):
                source_dir = candidate
                break

        if not source_dir:
            raise FileNotFoundError(
                f"OMZ converter produced no output for {model_name!r} "
                f"(looked in {tmp_dir}/intel and {tmp_dir}/public)"
            )

        os.makedirs(target_dir, exist_ok=True)
        for entry in os.listdir(source_dir):
            src = os.path.join(source_dir, entry)
            dst = os.path.join(target_dir, entry)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)

        logger.info(
            "external_sources_omz_materialized",
            model_name=model_name,
            target=target_dir,
        )

