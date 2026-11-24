# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Write the zip archive of a pipeline exported as an app.

The archive holds one directory, named after the app, with the compose file,
helper scripts, launch strings (``pipelines.json``), a manifest and the bundled
model and video files under ``assets/``. ``assets/models`` and
``assets/videos`` mirror the container paths under ``/models`` and
``/videos`` that the launch strings reference.
"""

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app_export.pipelines import MODELS_ROOT, VIDEOS_ROOT, AppPipelines
from app_version import VIPPET_REVISION, VIPPET_VERSION
from utils import slugify_text

# Same pipeline server image as `make run-prebuilt` (PREBUILT_DLSPS2_IMAGE in the
# Makefile) and the same media server as compose.yml.
DLSPS2_IMAGE = "intel/dlstreamer-pipeline-server:2026.3.0-ubuntu26-2.0-rc2"
MEDIAMTX_IMAGE = "bluenviron/mediamtx:1.21.3"

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_FILES = (
    "start_app.sh",
    "run.sh",
    "stop.sh",
    "status.sh",
    "stop_app.sh",
    "scripts/common.sh",
)
_EXECUTABLES = frozenset(
    {"start_app.sh", "run.sh", "stop.sh", "status.sh", "stop_app.sh"}
)
# Already compressed; deflating them only costs time.
_STORED_SUFFIXES = frozenset({".bin", ".avi", ".ts", ".mp4", ".mkv", ".mov"})
_CHUNK_SIZE = 1024 * 1024
_TOKEN = re.compile(r"@([A-Z0-9_]+)@")

_DEVICE_COMPOSE = {
    "GPU": ["/dev/dri:/dev/dri"],
    "NPU": ["/dev/dri:/dev/dri", "/dev/accel:/dev/accel"],
}
_DEVICE_REQUIREMENTS = {
    "GPU": "- An Intel GPU (`/dev/dri/renderD*`).",
    "NPU": "- An Intel NPU with its driver (`/dev/accel/accel0`), and an Intel GPU for "
    "video decoding.",
}


@dataclass(frozen=True)
class AppSource:
    """
    The pipeline variant an app was exported from.

    Attributes:
        pipeline_id: ViPPET pipeline id.
        pipeline_name: Pipeline name shown in ViPPET.
        variant_id: ViPPET variant id.
        variant_name: Variant name shown in ViPPET.
        launch_string: The variant's pipeline description, as ViPPET resolves it.
    """

    pipeline_id: str
    pipeline_name: str
    variant_id: str
    variant_name: str
    launch_string: str


def app_name(source: AppSource) -> str:
    """
    Return the app name: archive root directory and Compose project name.

    Args:
        source: The exported pipeline variant.

    Returns:
        str: Lowercase slug such as "defect-detection-cpu-app".
    """
    slug = slugify_text(f"{source.pipeline_name}-{source.variant_name}", 60)
    return f"{slug or 'pipeline'}-app"


def write_app_archive(
    dest: BinaryIO,
    source: AppSource,
    app: AppPipelines,
    roots: dict[str, str] | None = None,
) -> None:
    """
    Write the app archive to a binary file object.

    Args:
        dest: Seekable binary file object the zip is written to.
        source: The exported pipeline variant.
        app: Launch strings and referenced files from ``build_app_pipelines``.
        roots: Local directory of each container root (``MODELS_ROOT``,
            ``VIDEOS_ROOT``). Defaults to the same paths, as mounted in the
            ViPPET container.

    Raises:
        ValueError: If a referenced file is missing or resolves outside its root.
    """
    roots = roots or {MODELS_ROOT: MODELS_ROOT, VIDEOS_ROOT: VIDEOS_ROOT}
    name = app_name(source)
    assets = _collect_assets(app, roots)
    timestamp = datetime.now(timezone.utc)
    # Zip stores local time without a zone.
    date_time = timestamp.astimezone().timetuple()[:6]

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        directory = zipfile.ZipInfo(f"{name}/output/", date_time)
        directory.external_attr = (0o40755 << 16) | 0x10
        archive.writestr(directory, b"")

        checksums: list[dict[str, str | int]] = []
        for local_path, archive_path in assets:
            info = zipfile.ZipInfo(f"{name}/{archive_path}", date_time)
            info.external_attr = 0o100644 << 16
            if Path(archive_path).suffix.lower() in _STORED_SUFFIXES:
                info.compress_type = zipfile.ZIP_STORED
            else:
                info.compress_type = zipfile.ZIP_DEFLATED
            digest = hashlib.sha256()
            size = 0
            with (
                open(local_path, "rb") as src,
                archive.open(info, "w", force_zip64=True) as out,
            ):
                while chunk := src.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            checksums.append(
                {"path": archive_path, "size": size, "sha256": digest.hexdigest()}
            )

        values = {
            "NAME": name,
            "PIPELINE_NAME": source.pipeline_name,
            "VARIANT_NAME": source.variant_name,
            "DEVICES": ", ".join(app.devices),
            "VIPPET_VERSION": VIPPET_VERSION,
            "EXPORTED_AT": timestamp.strftime("%Y-%m-%d %H:%M UTC"),
            "DLSPS2_IMAGE": DLSPS2_IMAGE,
            "MEDIAMTX_IMAGE": MEDIAMTX_IMAGE,
            "DEVICES_BLOCK": _devices_block(app.devices),
            "DEVICE_REQUIREMENTS": "\n".join(
                _DEVICE_REQUIREMENTS[device]
                for device in app.devices
                if device in _DEVICE_REQUIREMENTS
            ),
            "ASSETS": "\n".join(
                f"- `{entry['path']}` ({_size(int(entry['size']))})"
                for entry in checksums
            ),
        }
        manifest = {
            "generator": "ViPPET Export as app",
            "vippet_version": VIPPET_VERSION,
            "vippet_revision": VIPPET_REVISION,
            "exported_at": timestamp.isoformat(timespec="seconds"),
            "pipeline": {"id": source.pipeline_id, "name": source.pipeline_name},
            "variant": {"id": source.variant_id, "name": source.variant_name},
            "devices": app.devices,
            "source_launch_string": source.launch_string,
            "dlsps2_image": DLSPS2_IMAGE,
            "assets": checksums,
        }

        texts = {
            "compose.yml": _render("compose.yml.tmpl", values),
            "README.md": _render("README.md.tmpl", values),
            "pipelines.json": json.dumps(app.launch_strings, indent=2) + "\n",
            "manifest.json": json.dumps(manifest, indent=2) + "\n",
        }
        for path in _STATIC_FILES:
            texts[path] = (_TEMPLATES_DIR / path).read_text(encoding="utf-8")

        for path, text in texts.items():
            info = zipfile.ZipInfo(f"{name}/{path}", date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o100755 if path in _EXECUTABLES else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, text)


def _collect_assets(app: AppPipelines, roots: dict[str, str]) -> list[tuple[str, str]]:
    """
    Return (local path, archive path) of every file to bundle.

    A model's whole directory is bundled (weights, labels and configs next to
    the ``.xml``); other referenced files are bundled alone.
    """
    container_paths: set[str] = set(app.other_model_files) | set(app.video_files)
    for model_file in app.model_files:
        directory = os.path.dirname(model_file)
        local_directory = _local_path(directory, roots)
        if not os.path.isdir(local_directory):
            raise ValueError(f"Model directory {directory} is missing.")
        for entry in os.scandir(local_directory):
            if entry.is_file():
                container_paths.add(f"{directory}/{entry.name}")

    assets: list[tuple[str, str]] = []
    for container_path in sorted(container_paths):
        local_path = _local_path(container_path, roots)
        if not os.path.isfile(local_path):
            raise ValueError(f"File {container_path} is missing.")
        archive_path = "assets/" + container_path.lstrip("/")
        assets.append((local_path, archive_path))
    return assets


def _local_path(container_path: str, roots: dict[str, str]) -> str:
    """Map a container path to the local file system, refusing anything outside its root."""
    for container_root, local_root in roots.items():
        if container_path.startswith(f"{container_root}/"):
            relative = container_path[len(container_root) + 1 :]
            real_root = os.path.realpath(local_root)
            real_path = os.path.realpath(os.path.join(real_root, relative))
            if not real_path.startswith(f"{real_root}{os.sep}"):
                raise ValueError(f"{container_path} resolves outside {container_root}.")
            return real_path
    raise ValueError(f"{container_path} is not under {', '.join(roots)}.")


def _devices_block(devices: list[str]) -> str:
    """Return the compose device and group lines of the pipeline server, empty for CPU only."""
    mounts: list[str] = []
    for device in devices:
        for mount in _DEVICE_COMPOSE.get(device, []):
            if mount not in mounts:
                mounts.append(mount)
    if not mounts:
        return ""
    lines = ["    devices:"]
    lines += [f"      - {mount}" for mount in mounts]
    lines += [
        "    group_add:",
        "      # Group that owns /dev/dri/renderD*, written to .env by start_app.sh.",
        '      - "${RENDER_GID:-video}"',
    ]
    return "\n".join(lines)


def _render(template: str, values: dict[str, str]) -> str:
    """Replace @TOKEN@ markers of a template; a marker alone on a line that renders empty is dropped."""
    text = (_TEMPLATES_DIR / template).read_text(encoding="utf-8")

    def _value(match: re.Match[str]) -> str:
        return values[match.group(1)]

    lines: list[str] = []
    for line in text.splitlines():
        rendered = _TOKEN.sub(_value, line)
        if rendered.strip() or not _TOKEN.fullmatch(line.strip()):
            lines.append(rendered)
    return "\n".join(lines) + "\n"


def _size(size: int) -> str:
    """Return a human-readable file size."""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.1f} KB"
