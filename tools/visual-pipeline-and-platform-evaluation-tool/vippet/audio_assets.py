# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import re
import shutil
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

AUTO_AUDIO_DIR = os.path.normpath(os.environ.get("AUTO_AUDIO_DIR", "/audio/input/auto"))
OUTPUT_AUDIO_DIR = os.path.normpath(os.environ.get("OUTPUT_AUDIO_DIR", "/audio/output"))
DEFAULT_AUDIO_RECORDINGS_FILE = os.environ.get(
    "DEFAULT_AUDIO_RECORDINGS_FILE",
    "/audio/default_recordings.yaml",
)
# Source directory for the `local:` manifest entries.
LOCAL_AUDIO_RECORDINGS_DIR = (
    Path(__file__).resolve().parent / "pipelines" / "recordings"
)

logger = logging.getLogger("audio_assets")
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*\.wav$", re.IGNORECASE)


@dataclass(frozen=True)
class AudioAsset:
    filename: str
    path: str
    duration_seconds: float = 0.0


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
            local = entry.get("local")
            filename = entry.get("filename")
            if not isinstance(local, str) or not isinstance(filename, str):
                logger.warning("Skipping invalid default audio recording entry")
                continue
            if not self._is_safe_filename(filename):
                logger.warning("Skipping default audio recording with unsafe filename")
                continue
            path = self._ensure_local_recording(local, filename)
            if path is not None:
                self._assets[filename] = AudioAsset(
                    filename, path, self._wav_duration(Path(path))
                )

    def _ensure_local_recording(self, local: str, filename: str) -> str | None:
        target = Path(AUTO_AUDIO_DIR) / filename
        if target.is_symlink():
            self._remove_file(target)
        if target.is_file() and self._is_valid_wav(target):
            return str(target)
        if target.exists():
            self._remove_file(target)

        if not self._is_safe_filename(local):
            logger.error("Local audio recording '%s' cannot be used", local)
            return None
        source = LOCAL_AUDIO_RECORDINGS_DIR / local
        if source.is_symlink() or not self._is_valid_wav(source):
            logger.error("Local audio recording '%s' is missing or not WAV", local)
            return None

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".audio-local-",
                suffix=".wav",
                dir=AUTO_AUDIO_DIR,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                with source.open("rb") as source_file:
                    shutil.copyfileobj(source_file, temporary_file)
            os.replace(temporary_path, target)
            temporary_path = None
            logger.info("Installed local audio recording '%s'.", filename)
            return str(target)
        except OSError as exc:
            logger.error(
                "Unable to install local audio '%s': %s",
                filename,
                type(exc).__name__,
            )
            return None
        finally:
            if temporary_path is not None:
                self._remove_file(temporary_path)

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
    def _wav_duration(path: Path) -> float:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove invalid audio file")

    def list_assets(self) -> list[AudioAsset]:
        return sorted(self._assets.values(), key=lambda asset: asset.filename.lower())

    def get_asset(self, filename: str) -> AudioAsset | None:
        if not self._is_safe_filename(filename):
            return None
        return self._assets.get(filename)

    def get_path(self, filename: str) -> str | None:
        asset = self.get_asset(filename)
        return asset.path if asset is not None else None

    def get_output_directory(self) -> str:
        return OUTPUT_AUDIO_DIR
