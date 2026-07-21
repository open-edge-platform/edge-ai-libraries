# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""External sources downloader plugin.

Handles tarball-based hubs (``pipeline-zoo-models``, ``remote-url``) and OMZ
downloads via a YAML-driven dispatch on ``kind``. The ``remote-url`` hub takes
an archive URL from the request (``config.url``) and validates it against an
allowlist before downloading.
"""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.interfaces import DownloadTask, ListingNotSupportedError, ModelDownloadPlugin
from src.utils.logging import logger


_CONFIG_DIR = Path(__file__).with_name("external_sources")
_PROFILE_FILE = _CONFIG_DIR / "sources.yaml"
_OMZ_RULES_FILE = _CONFIG_DIR / "omz_rules.yaml"
_OMZ_VENV_BIN = Path(os.environ.get("OMZ_VENV", "/opt/.venv-omz")) / "bin"
_CACHE_ROOT = Path(os.environ.get("EXTERNAL_SOURCES_CACHE_DIR", "/tmp/model_download_external_sources"))
_COMPLETE_MARKER = ".download_complete"

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


@lru_cache(maxsize=1)
def _load_omz_rules() -> Dict[str, Dict[str, Any]]:
    """Read static OMZ post-processing rules shipped with the plugin."""
    if not _OMZ_RULES_FILE.is_file():
        logger.warning("OMZ rules file missing", path=str(_OMZ_RULES_FILE))
        return {}

    with open(_OMZ_RULES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        logger.warning("OMZ rules file is invalid", path=str(_OMZ_RULES_FILE))
        return {}

    return rules




class ExternalSourcesPlugin(ModelDownloadPlugin):
    """Combined downloader for external hubs (tarball + OMZ)."""

    _archive_lock = threading.Lock()

    @property
    def plugin_name(self) -> str:
        return "external-sources"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def plugin_supported_hubs(self) -> List[str]:
        """Return all hub names this plugin serves."""
        return list(_load_profile().keys())

    def hub_description(self, hub: str) -> Optional[str]:
        """Return the user-facing description for a single hub, if defined.

        This is displayed in the /plugins endpoint under the hub's entry so
        users understand what each hub does. Descriptions are defined in
        sources.yaml per hub.
        """
        profile = _load_profile().get((hub or "").lower().replace("_", "-"))
        return profile.get("description") if profile else None

    def hub_capabilities(self, hub: str) -> Dict[str, Any]:
        """Return per-hub listing capabilities from the profile.

        Only some hubs support listing (e.g. ``pipeline-zoo-models``); the
        rest report no listing support so the /plugins endpoint shows accurate
        capabilities for each hub. For multi-hub plugins, this allows different
        hubs to have different capabilities.
        """
        profile = _load_profile().get((hub or "").lower().replace("_", "-")) or {}
        return {
            "supports_listing": bool(profile.get("supports_listing", False)),
            "listing_filter_fields": list(profile.get("listing_filter_fields") or []),
        }

    @property
    def supports_listing(self) -> bool:
        return True

    @property
    def listing_filter_fields(self) -> List[str]:
        return ["search"]

    def list_models(self, filters=None, limit=50, offset=0, **kwargs) -> Dict[str, Any]:
        """List models for external hubs that have a discoverable catalog."""
        hub = (kwargs.get("hub") or "").lower().replace("_", "-")
        if hub != "pipeline-zoo-models":
            raise ListingNotSupportedError(
                f"Hub '{hub}' does not support listing models"
            )

        self._validate_listing_filters(filters)

        profile = _load_profile().get(hub)
        if profile is None:
            raise ListingNotSupportedError(
                f"Hub '{hub}' does not support listing models"
            )

        extract_dir = self._ensure_shared_archive_extracted(hub, profile)
        extracted_root = profile.get("shared_archive_root")
        source_base = Path(extract_dir) / extracted_root if extracted_root else Path(extract_dir)
        model_subpath = profile.get("shared_model_subpath", "{model_name}")
        prefix = model_subpath.split("{model_name}", 1)[0].strip("/")
        model_root = source_base / prefix if prefix else source_base
        if not model_root.is_dir():
            raise RuntimeError(f"Pipeline-zoo model directory not found at {model_root}")

        names = sorted(path.name for path in model_root.iterdir() if path.is_dir())
        search_term = str((filters or {}).get("search", "")).lower()
        if search_term:
            names = [name for name in names if search_term in name.lower()]

        total = len(names)
        page = names[offset: offset + limit]
        items = [
            {
                "name": name,
                "owner": "dlstreamer",
            }
            for name in page
        ]
        return {"items": items, "total": total}

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


        kind = profile.get("kind")

        # For pipeline-zoo (`all`/comma) and OMZ (comma) multi-model requests, each
        # model lands under its own folder with the hub directory as parent.
        is_multi = (
            hub == "pipeline-zoo-models"
            and (model_name.strip().lower() == "all" or "," in model_name)
        ) or (
            hub == "omz" and "," in model_name
        )
        target_dir = os.path.join(output_dir, hub) if is_multi else os.path.join(output_dir, hub, model_name)

        # The 'remote-url' hub takes the archive URL from the request and validates
        # it against the allowlist before download.
        runtime_url: Optional[str] = None
        if hub == "remote-url":
            config = kwargs.get("config") or {}
            raw_url = config.get("url") if isinstance(config, dict) else None
            if not raw_url or not str(raw_url).strip():
                raise ValueError("hub 'remote-url' requires 'url' in the request config")
            runtime_url = str(raw_url).strip().replace("{name}", model_name)
            self._validate_runtime_url(runtime_url, self._resolve_allowlist(profile))

        try:
            if kind == "omz":
                self._fetch_omz(hub, model_name, target_dir)
            elif kind == "tarball":
                self._fetch_tarball(hub, model_name, profile, target_dir, runtime_url=runtime_url)
            else:
                raise ValueError(f"Unknown 'kind' for hub {hub!r}: {kind!r} (check sources.yaml)")

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
        self,
        hub: str,
        model_name: str,
        profile: Dict[str, Any],
        target_dir: str,
        runtime_url: Optional[str] = None,
    ) -> None:
        """Download and extract a tarball-based model.

        ``runtime_url`` (the ``url`` hub) downloads a per-request archive;
        otherwise a shared archive declared in the profile is used.
        """
        if runtime_url is not None:
            # Runtime URL: an already-validated per-model archive.
            os.makedirs(target_dir, exist_ok=True)
            logger.info(
                "external_sources_downloading_archive",
                hub=hub,
                model_name=model_name,
                url=runtime_url,
            )
            self._download_and_extract_tarball(runtime_url, target_dir)
            logger.info(
                "external_sources_runtime_url_tarball_extracted",
                model_name=model_name,
                target=target_dir,
            )
            return

        # Shared archive: use persistent extracted cache to avoid downloading full tar on each request
        extract_dir = self._ensure_shared_archive_extracted(hub, profile)

        extracted_root = profile.get("shared_archive_root")
        source_base = os.path.join(extract_dir, extracted_root) if extracted_root else extract_dir

        model_subdir_template = profile.get("shared_model_subpath", "{model_name}")
        model_names = self._resolve_tarball_model_names(model_name, source_base, model_subdir_template)

        for resolved_name in model_names:
            model_subdir = model_subdir_template.format(model_name=resolved_name)
            if ".." in Path(model_subdir).parts:
                raise ValueError(f"model_subdir resolves outside archive: {model_subdir!r}")

            source_dir = os.path.join(source_base, model_subdir)
            if not os.path.isdir(source_dir):
                raise FileNotFoundError(
                    f"Model {resolved_name!r} not found in archive at {source_dir}"
                )

            # pipeline-zoo multi-model requests place each model under its own folder.
            destination = (
                os.path.join(target_dir, resolved_name)
                if hub == "pipeline-zoo-models"
                and (model_name.strip().lower() == "all" or "," in model_name)
                else target_dir
            )

            os.makedirs(destination, exist_ok=True)
            shutil.copytree(source_dir, destination, dirs_exist_ok=True)
            logger.info(
                "external_sources_shared_tarball_copied",
                model_name=resolved_name,
                target=destination,
            )

    def _resolve_tarball_model_names(
        self,
        model_name: str,
        source_base: str,
        model_subdir_template: str,
    ) -> List[str]:
        """Resolve target model names for shared tarball downloads.

        Supports:
        - `all`: every model under the shared model root
        - comma-separated model names: `a,b,c`
        - single model name
        """
        normalized = (model_name or "").strip().lower()

        if normalized == "all":
            prefix = model_subdir_template.split("{model_name}", 1)[0].strip("/")
            model_root = Path(source_base) / prefix if prefix else Path(source_base)
            if not model_root.is_dir():
                raise RuntimeError(f"Pipeline-zoo model directory not found at {model_root}")
            names = sorted(path.name for path in model_root.iterdir() if path.is_dir())
            if not names:
                raise FileNotFoundError(f"No models found in archive at {model_root}")
            return names

        if "," in model_name:
            return self._parse_comma_names(model_name)

        return [model_name]

    @staticmethod
    def _parse_comma_names(model_name: str) -> List[str]:
        """Split, validate, and deduplicate a comma-separated model name string."""
        names: List[str] = []
        for raw in model_name.split(","):
            name = raw.strip()
            if not name:
                continue
            if "/" in name or ".." in name or name.startswith("."):
                raise ValueError(f"Invalid model name: {name!r}")
            if name not in names:
                names.append(name)
        if not names:
            raise ValueError("Model name is required")
        return names

    @staticmethod
    def _resolve_allowlist(profile: Dict[str, Any]) -> List[str]:
        """Resolve the runtime-URL allowlist of ``host + path`` prefixes.

        ``EXTERNAL_SOURCES_URL_ALLOWLIST`` (comma-separated), env when non-empty,
        overrides the profile's ``allowed_prefixes``; otherwise the profile
        default is used.
        """
        env_value = os.environ.get("EXTERNAL_SOURCES_URL_ALLOWLIST")
        if env_value is not None and env_value.strip():
            # A non-empty env value overrides the profile default.
            return [p.strip() for p in env_value.split(",") if p.strip()]
        return [
            str(p).strip()
            for p in (profile.get("allowed_prefixes") or [])
            if str(p).strip()
        ]

    @staticmethod
    def _validate_runtime_url(url: str, allowlist: List[str]) -> None:
        """Validate a user-supplied archive URL against the allowlist.

        Enforces ``https``, rejects embedded credentials, and requires the
        parsed ``host + path`` to start with an allowed prefix. Raises
        ``ValueError`` on any violation.
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(f"Runtime URL must use https scheme: {url!r}")
        if not parsed.hostname:
            raise ValueError(f"Runtime URL has no host: {url!r}")
        if parsed.username or parsed.password:
            raise ValueError("Runtime URL must not contain embedded credentials")
        if not allowlist:
            raise ValueError(
                "No URL allowlist configured; runtime URL downloads are disabled. "
                "Set EXTERNAL_SOURCES_URL_ALLOWLIST or sources.yaml allowed_prefixes."
            )

        host_path = f"{parsed.hostname}{parsed.path}"
        if not any(host_path.startswith(prefix) for prefix in allowlist):
            raise ValueError(
                f"Runtime URL host/path not in allowlist: {parsed.hostname}{parsed.path}"
            )


    def _ensure_shared_archive_extracted(self, hub: str, profile: Dict[str, Any]) -> str:
        """Ensure the shared archive for a hub is downloaded and extracted once."""
        archive_url = profile.get("shared_archive_url")
        if not archive_url:
            raise RuntimeError(
                "Profile entry is missing shared archive URL "
                "(expected 'shared_archive_url')"
            )

        cache_dir = _CACHE_ROOT / hub
        extract_dir = cache_dir / "extracted"
        marker = extract_dir / _COMPLETE_MARKER

        if marker.is_file():
            return str(extract_dir)

        with self._archive_lock:
            if marker.is_file():
                return str(extract_dir)

            # Marker missing means cache is not trusted; remove any partial extract.
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            extract_dir.mkdir(parents=True, exist_ok=True)
            logger.info("external_sources_downloading_archive", hub=hub, url=archive_url)
            self._download_and_extract_tarball(archive_url, str(extract_dir))
            marker.touch()

        return str(extract_dir)

    @staticmethod
    def _download_and_extract_tarball(url: str, target_dir: str) -> None:
        """Download a tarball from URL and extract it to target_dir."""
        with tempfile.TemporaryDirectory(prefix="ext-") as tmp_dir:
            archive_path = os.path.join(tmp_dir, "archive.tar.gz")
            try:
                urllib.request.urlretrieve(url, archive_path)  # noqa: S310
            except urllib.error.HTTPError as e:
                msg = (
                    f"Failed to download archive from {url!r}: "
                    f"HTTP {e.code} {e.reason}. Verify the model name and "
                    "that the archive exists at the resolved URL."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            except urllib.error.URLError as e:
                msg = (
                    f"Failed to reach archive URL {url!r}: {e.reason}. "
                    "Check network connectivity and that the host is reachable."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            try:
                with tarfile.open(archive_path, "r:*") as tar_ref:
                    tar_ref.extractall(path=target_dir, filter="data")
            except tarfile.TarError as e:
                msg = f"Downloaded file from {url!r} is not a valid tar archive: {e}"
                logger.error(msg)
                raise RuntimeError(msg)


    def _fetch_omz(self, hub: str, model_name: str, target_dir: str) -> None:
        """Download and convert an OMZ model using omz_downloader/omz_converter."""
        if "," in model_name:
            for name in self._parse_comma_names(model_name):
                self._fetch_omz(hub, name, os.path.join(target_dir, name))
            return

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
            logger.info(
                "external_sources_downloading_archive",
                hub=hub,
                model_name=model_name,
            )
            download_cmd = [
                str(omz_downloader),
                "--name",
                model_name,
                "--output_dir",
                tmp_dir,
            ]
            self._run_omz_tool(download_cmd)

            # Convert
            logger.info("external_sources_omz_converting", hub=hub, model_name=model_name)
            convert_cmd = [
                str(omz_converter),
                "--name",
                model_name,
                "--download_dir",
                tmp_dir,
                "--output_dir",
                tmp_dir,
            ]

            mo_executable = self._resolve_mo_executable()
            if mo_executable:
                convert_cmd.extend(["--mo", mo_executable])

            self._run_omz_tool(convert_cmd)

            # Move converted artefacts: omz_converter produces intel/ or public/ subdirs
            self._materialize_omz_artefacts(model_name, tmp_dir, target_dir)

        self._apply_omz_post_processing(model_name, target_dir)

    def _apply_omz_post_processing(self, model_name: str, target_dir: str) -> None:
        """Apply optional model-specific OMZ post-processing from rules."""
        rule = _load_omz_rules().get(model_name)
        if not rule:
            logger.info(
                "OMZ model has no specific post-processing rule; skipping post-processing",
                model_name=model_name,
            )
            return

        # If model is in rules, model_proc_src is required
        model_proc_src = rule.get("model_proc_src")
        if not model_proc_src:
            raise ValueError(
                f"OMZ rule for {model_name!r} is missing required 'model_proc_src'"
            )

        model_proc_dst = rule.get("model_proc_dst")
        if not model_proc_dst:
            raise ValueError(
                f"OMZ rule for {model_name!r} is missing required 'model_proc_dst'"
            )

        labels_src = rule.get("labels_src")
        inject_labels = bool(rule.get("inject_labels", False))

        # Copy model_proc file (always, since model_proc_src is required)
        self._copy_model_proc(
            model_name=model_name,
            target_dir=target_dir,
            model_proc_src=model_proc_src,
            model_proc_dst=model_proc_dst,
        )

        # Inject labels only if both present and explicitly enabled
        if labels_src and inject_labels:
            self._inject_labels_into_model_proc(
                model_name=model_name,
                labels_path=labels_src,
                json_path=os.path.join(target_dir, model_proc_dst),
            )

        logger.info("OMZ post-processing applied", model_name=model_name, target=target_dir)

    @staticmethod
    def _is_remote_source(src: str) -> bool:
        """Return True if the source is an http(s) URL rather than a local path."""
        return src.startswith("http://") or src.startswith("https://")

    @staticmethod
    def _copy_model_proc(
        model_name: str,
        target_dir: str,
        model_proc_src: str,
        model_proc_dst: str,
    ) -> None:
        """Materialize the model_proc JSON file into the model target directory.

        ``model_proc_src`` may be a local path (DL Streamer image) or an http(s)
        URL (DL Streamer repository).
        """
        destination = os.path.join(target_dir, model_proc_dst)

        if ExternalSourcesPlugin._is_remote_source(model_proc_src):
            urllib.request.urlretrieve(model_proc_src, destination)  # noqa: S310
        else:
            if not os.path.isfile(model_proc_src):
                raise FileNotFoundError(
                    f"OMZ model_proc source not found for {model_name!r}: {model_proc_src}"
                )
            shutil.copyfile(model_proc_src, destination)

        logger.info(
            "Copied OMZ model-proc file",
            model_name=model_name,
            source=model_proc_src,
            destination=destination,
        )

    @staticmethod
    def _inject_labels_into_model_proc(
        model_name: str,
        labels_path: str,
        json_path: str,
    ) -> None:
        """Inject labels into output_postproc[0].labels in model_proc JSON."""
        if ExternalSourcesPlugin._is_remote_source(labels_path):
            with urllib.request.urlopen(labels_path) as response:  # noqa: S310
                labels_text = response.read().decode("utf-8")
            label_lines = labels_text.splitlines()
        else:
            if not os.path.isfile(labels_path):
                raise FileNotFoundError(
                    f"OMZ labels source not found for {model_name!r}: {labels_path}"
                )
            with open(labels_path, "r", encoding="utf-8") as f:
                label_lines = f.readlines()

        if not os.path.isfile(json_path):
            raise FileNotFoundError(
                f"OMZ model_proc JSON not found for {model_name!r}: {json_path}"
            )

        labels: List[str] = []
        for line_number, raw_line in enumerate(label_lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 1 and parts[0].isdigit():
                raise ValueError(
                    f"OMZ labels file has ID without label for {model_name!r} at "
                    f"line {line_number}: {line!r}"
                )
            labels.append(parts[1] if len(parts) == 2 else parts[0])

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        postproc = data.get("output_postproc")
        if not isinstance(postproc, list) or not postproc:
            raise ValueError(
                f"model_proc file lacks non-empty output_postproc for {model_name!r}: {json_path}"
            )

        if not isinstance(postproc[0], dict):
            raise ValueError(
                f"model_proc output_postproc[0] must be an object for {model_name!r}: {json_path}"
            )

        # inject labels under output_postproc[0].labels
        postproc[0]["labels"] = labels

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        logger.info(
            "Injected labels into OMZ model-proc",
            model_name=model_name,
            labels_count=len(labels),
            json_path=json_path,
        )

    @staticmethod
    def _run_omz_tool(command: List[str]) -> None:
        """Run an OMZ CLI tool and raise on failure."""
        try:
            env = os.environ.copy()
            omz_bin_dir = str(_OMZ_VENV_BIN)
            if os.path.isdir(omz_bin_dir):
                env["PATH"] = omz_bin_dir + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            if result.returncode != 0:
                stdout = result.stdout.strip() if result.stdout else "<empty>"
                stderr = result.stderr.strip() if result.stderr else "<empty>"
                details = f"stderr: {stderr}"
                if stdout and stdout != "<empty>":
                    details += f"\nstdout: {stdout}"
                raise RuntimeError(
                    f"OMZ tool failed (rc={result.returncode}): {' '.join(command)}\n"
                    f"{details}"
                )
            if result.stdout:
                logger.debug("omz_tool_output", output=result.stdout.strip())
        except FileNotFoundError as e:
            raise RuntimeError(f"OMZ tool not found: {command[0]}") from e

    @staticmethod
    def _resolve_mo_executable() -> Optional[str]:
        """Resolve a Model Optimizer executable path for omz_converter."""
        path = os.environ.get("PATH", "")
        omz_bin_dir = str(_OMZ_VENV_BIN)
        search_path = omz_bin_dir + os.pathsep + path if omz_bin_dir else path

        for candidate in ("mo", "mo.py"):
            mo_path = shutil.which(candidate, path=search_path)
            if mo_path:
                return mo_path

        return None

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

