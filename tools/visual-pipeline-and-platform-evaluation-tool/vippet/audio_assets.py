# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

AUTO_AUDIO_DIR = os.path.normpath(os.environ.get("AUTO_AUDIO_DIR", "/audio/input/auto"))
OUTPUT_AUDIO_DIR = os.path.normpath(os.environ.get("OUTPUT_AUDIO_DIR", "/audio/output"))
DEFAULT_AUDIO_RECORDINGS_FILE = os.environ.get(
    "DEFAULT_AUDIO_RECORDINGS_FILE",
    "/audio/default_recordings.yaml",
)

logger = logging.getLogger("audio_assets")
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*\.wav$", re.IGNORECASE)
MAX_AUDIO_DOWNLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class AudioAsset:
    filename: str
    path: str


class AudioAssetsManager:
    _instance: "AudioAssetsManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "AudioAssetsManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._assets: dict[str, AudioAsset] = {}
        self._ensure_directories()
        self._load_default_recordings()

    @staticmethod
    def _ensure_directories() -> None:
        for directory in (AUTO_AUDIO_DIR, OUTPUT_AUDIO_DIR):
            try:
                os.makedirs(directory, mode=0o755, exist_ok=True)
                os.chmod(directory, 0o755)
            except OSError as exc:
                raise RuntimeError(
                    f"Failed to create audio directory '{directory}': {exc}"
                ) from exc

    def _load_default_recordings(self) -> None:
        manifest = self._read_manifest()
        for entry in manifest:
            url = entry.get("url")
            filename = entry.get("filename")
            if not isinstance(url, str) or not isinstance(filename, str):
                logger.warning("Skipping invalid default audio recording entry")
                continue
            if not self._is_safe_filename(filename):
                logger.warning("Skipping default audio recording with unsafe filename")
                continue
            if urlparse(url).scheme != "https":
                logger.warning("Skipping default audio recording with non-HTTPS URL")
                continue
            path = self._ensure_recording(url, filename)
            if path is not None:
                self._assets[filename] = AudioAsset(filename, path)

    def _read_manifest(self) -> list[dict[str, Any]]:
        try:
            with open(DEFAULT_AUDIO_RECORDINGS_FILE, encoding="utf-8") as manifest_file:
                manifest = yaml.safe_load(manifest_file)
        except FileNotFoundError:
            logger.error(
                "Default audio recordings file '%s' not found",
                DEFAULT_AUDIO_RECORDINGS_FILE,
            )
            return []
        except (OSError, yaml.YAMLError) as exc:
            logger.error(
                "Unable to read default audio recordings: %s", type(exc).__name__
            )
            return []
        if not isinstance(manifest, list):
            logger.error("Default audio recordings manifest must contain a list")
            return []
        return [entry for entry in manifest if isinstance(entry, dict)]

    def _ensure_recording(self, url: str, filename: str) -> str | None:
        target = Path(AUTO_AUDIO_DIR) / filename
        if target.is_symlink():
            self._remove_file(target)
        if target.is_file() and self._is_valid_wav(target):
            return str(target)
        if target.exists():
            self._remove_file(target)

        temporary_path: Path | None = None
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "ViPPET/1.0"},
            )
            logger.info("Downloading '%s' from %s...", filename, url)
            started_at = time.perf_counter()
            with (
                urllib.request.urlopen(request, timeout=600) as response,
                tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=".audio-download-",
                    suffix=".wav",
                    dir=AUTO_AUDIO_DIR,
                    delete=False,
                ) as temporary_file,
            ):
                temporary_path = Path(temporary_file.name)
                if getattr(response, "status", 200) != 200:
                    logger.error(
                        "Unable to download default audio '%s': HTTP %s",
                        filename,
                        response.status,
                    )
                    return None
                final_url = response.geturl()
                if (
                    not isinstance(final_url, str)
                    or urlparse(final_url).scheme != "https"
                ):
                    logger.error(
                        "Default audio '%s' redirected to a non-HTTPS URL", filename
                    )
                    return None
                headers = getattr(response, "headers", None)
                content_length = (
                    headers.get("Content-Length") if headers is not None else None
                )
                if (
                    isinstance(content_length, str)
                    and content_length.isdigit()
                    and int(content_length) > MAX_AUDIO_DOWNLOAD_BYTES
                ):
                    logger.error("Default audio '%s' exceeds the size limit", filename)
                    return None
                downloaded_bytes = 0
                while chunk := response.read(8192):
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > MAX_AUDIO_DOWNLOAD_BYTES:
                        logger.error(
                            "Default audio '%s' exceeds the size limit", filename
                        )
                        return None
                    temporary_file.write(chunk)
            if not self._is_valid_wav(temporary_path):
                logger.error("Downloaded default audio '%s' is not valid WAV", filename)
                return None
            os.replace(temporary_path, target)
            temporary_path = None
            elapsed_seconds = time.perf_counter() - started_at
            file_size = target.stat().st_size if target.is_file() else 0
            logger.info(
                "Downloaded '%s' (%.1f MB) in %.1f seconds.",
                filename,
                file_size / (1024 * 1024),
                elapsed_seconds,
            )
            return str(target)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            logger.error(
                "Unable to download default audio '%s': %s",
                filename,
                type(exc).__name__,
            )
            return None
        finally:
            if temporary_path is not None:
                self._remove_file(temporary_path)

    @staticmethod
    def _is_safe_filename(filename: str) -> bool:
        return (
            filename not in {".", ".."}
            and os.path.basename(filename) == filename
            and SAFE_FILENAME_PATTERN.fullmatch(filename) is not None
        )

    @staticmethod
    def _is_valid_wav(path: Path) -> bool:
        try:
            with wave.open(str(path), "rb") as audio:
                return (
                    audio.getnchannels() > 0
                    and audio.getsampwidth() > 0
                    and audio.getframerate() > 0
                    and audio.getnframes() > 0
                )
        except (OSError, EOFError, wave.Error):
            return False

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove invalid audio file")

    def get_asset(self, filename: str) -> AudioAsset | None:
        if not self._is_safe_filename(filename):
            return None
        return self._assets.get(filename)

    def get_path(self, filename: str) -> str | None:
        asset = self.get_asset(filename)
        return asset.path if asset is not None else None

    def get_output_directory(self) -> str:
        return OUTPUT_AUDIO_DIR
