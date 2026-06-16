# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""External sources downloader plugin.

Handles tarball-based hubs (``pipeline-zoo-models``, ``udf-timeseries``)
via a YAML-driven dispatch on ``kind``. Profile is read from
``external_sources/sources.yaml``.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.interfaces import DownloadTask, ModelDownloadPlugin
from src.utils.logging import logger


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).with_name("external_sources")
_PROFILE_FILE = _CONFIG_DIR / "sources.yaml"


# ---------------------------------------------------------------------------
# Profile loading helper (module-private)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class ExternalSourcesPlugin(ModelDownloadPlugin):
    """Combined downloader for tarball-based external hubs."""

    # ``pipeline-zoo-models`` shares one cached extracted archive.
    _pzm_lock = threading.Lock()

    @property
    def plugin_name(self) -> str:
        return "external-sources"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    # ------------------------------------------------------------------
    # Plugin discovery / dispatch
    # ------------------------------------------------------------------

    def supported_hubs(self) -> List[str]:
        return list(_load_profile().keys())

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        normalized = (hub or "").lower().replace("_", "-")
        return normalized in _load_profile()

    # ------------------------------------------------------------------
    # Required (but unused) task-based API
    # ------------------------------------------------------------------

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        raise NotImplementedError(
            "external-sources plugin does not support task-based downloading"
        )

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        raise NotImplementedError(
            "external-sources plugin does not support task-based downloading"
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
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

        # Reject obvious path-injection attempts. Each branch may apply
        # additional, kind-specific validation below.
        if "/" in model_name or ".." in model_name or model_name.startswith("."):
            raise ValueError(f"Invalid model name: {model_name!r}")

        target_dir = os.path.join(output_dir, hub, model_name)
        kind = profile.get("kind")

        try:
            if kind == "tarball":
                self._fetch_tarball(model_name, profile, target_dir)
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

    # ------------------------------------------------------------------
    # Worker: tarball (pipeline-zoo-models, udf-timeseries, ...)
    # ------------------------------------------------------------------

    def _fetch_tarball(
        self, model_name: str, profile: Dict[str, Any], target_dir: str
    ) -> None:
        """Download an archive and place the model artefacts at ``target_dir``.

        Two sub-shapes are supported, controlled by the profile entry:

        * ``archive_url`` + ``model_subdir``: one big mirror tarball that
          contains many models; we cache the extracted tree and copy
          out the requested ``model_subdir``. Used for
          pipeline-zoo-models.

        * ``archive_url_template``: per-model tarball; the rendered URL
          is fetched, validated against ``allow_url_prefixes`` and
          extracted directly into ``target_dir``. Used for
          udf-timeseries.
        """
        if profile.get("archive_url_template") or profile.get("archive_url_template_env"):
            self._fetch_per_model_tarball(model_name, profile, target_dir)
        else:
            self._fetch_shared_archive_subdir(model_name, profile, target_dir)

    def _fetch_shared_archive_subdir(
        self, model_name: str, profile: Dict[str, Any], target_dir: str
    ) -> None:
        archive_url = self._env_or_default(
            profile.get("archive_url_env"), profile.get("archive_url")
        )
        if not archive_url:
            raise RuntimeError(
                "Profile entry is missing 'archive_url' (or its env override)"
            )
        cache_dir = Path(
            self._env_or_default(
                profile.get("cache_dir_env"),
                profile.get("cache_dir_default", "/tmp/model_download_external"),
            )
        )
        extracted_root = profile.get("extracted_root") or ""
        model_subdir_template = profile.get("model_subdir") or "{model_name}"

        with self._pzm_lock:
            extracted_dir = self._ensure_archive_extracted(
                archive_url=archive_url,
                cache_dir=cache_dir,
                extracted_root=extracted_root,
            )

        rel_subdir = model_subdir_template.format(model_name=model_name)
        # Block templates that would escape the extracted tree.
        if ".." in Path(rel_subdir).parts:
            raise ValueError(f"model_subdir resolves outside archive root: {rel_subdir!r}")
        source_dir = extracted_dir / rel_subdir
        if not source_dir.is_dir():
            raise FileNotFoundError(
                f"Model {model_name!r} not found in archive at {source_dir}"
            )

        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(str(source_dir), target_dir)
        logger.info(
            "external_sources_tarball_subdir_copied",
            model_name=model_name,
            source=str(source_dir),
            target=target_dir,
        )

    def _fetch_per_model_tarball(
        self, model_name: str, profile: Dict[str, Any], target_dir: str
    ) -> None:
        url_template = self._env_or_default(
            profile.get("archive_url_template_env"),
            profile.get("archive_url_template"),
        )
        if not url_template:
            raise RuntimeError("Profile entry is missing 'archive_url_template'")

        url = url_template.format(model_name=model_name)
        allow_prefixes = self._resolve_allow_prefixes(profile)
        if allow_prefixes and not any(url.startswith(p) for p in allow_prefixes):
            raise ValueError(
                f"Refusing to download from disallowed URL: {url!r}. "
                f"Allowed prefixes: {allow_prefixes}"
            )

        os.makedirs(target_dir, exist_ok=True)
        fd, archive_path = tempfile.mkstemp(prefix=f"ext-{model_name}-", suffix=".tar.gz")
        os.close(fd)
        try:
            logger.info(
                "external_sources_per_model_tarball_download_start",
                url=url,
                model_name=model_name,
            )
            urllib.request.urlretrieve(url, archive_path)  # noqa: S310

            if not hasattr(tarfile, "data_filter"):
                raise RuntimeError(
                    "tarfile data filter unavailable; Python >= 3.12 required"
                )
            with tarfile.open(archive_path, "r:*") as tar_ref:
                tar_ref.extractall(path=target_dir, filter="data")

            logger.info(
                "external_sources_per_model_tarball_extracted",
                model_name=model_name,
                target=target_dir,
            )
        finally:
            if os.path.exists(archive_path):
                os.remove(archive_path)

    @staticmethod
    def _resolve_allow_prefixes(profile: Dict[str, Any]) -> List[str]:
        env_key = profile.get("allow_url_prefixes_env")
        env_value = os.environ.get(env_key) if env_key else None
        if env_value:
            return [p.strip() for p in env_value.split(",") if p.strip()]
        prefixes = profile.get("allow_url_prefixes") or []
        return [str(p) for p in prefixes]

    @staticmethod
    def _env_or_default(env_key: Optional[str], default: Any) -> Any:
        if env_key:
            value = os.environ.get(env_key)
            if value:
                return value
        return default

    @staticmethod
    def _ensure_archive_extracted(
        archive_url: str,
        cache_dir: Path,
        extracted_root: str,
    ) -> Path:
        """Download and extract ``archive_url`` once; reuse on later calls."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        marker_dir = cache_dir / (extracted_root or "default")
        marker = marker_dir / ".download_complete"
        if marker.is_file():
            return marker_dir

        if marker_dir.exists():
            shutil.rmtree(marker_dir)

        fd, archive_path = tempfile.mkstemp(
            prefix="ext-shared-", suffix=".tar.gz", dir=str(cache_dir)
        )
        os.close(fd)
        try:
            logger.info("external_sources_archive_download_start", url=archive_url)
            urllib.request.urlretrieve(archive_url, archive_path)  # noqa: S310

            if not hasattr(tarfile, "data_filter"):
                raise RuntimeError(
                    "tarfile data filter unavailable; Python >= 3.12 required"
                )
            with tarfile.open(archive_path, "r:*") as tar_ref:
                tar_ref.extractall(path=cache_dir, filter="data")

            if not marker_dir.is_dir():
                raise RuntimeError(
                    f"Extracted archive directory not found: {marker_dir}"
                )
            marker.touch()
            logger.info("external_sources_archive_ready", path=str(marker_dir))
            return marker_dir
        finally:
            if os.path.exists(archive_path):
                os.remove(archive_path)
