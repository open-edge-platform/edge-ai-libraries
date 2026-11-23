# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import re
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

AUTO_AUDIO_DIR = os.path.normpath(os.environ.get("AUTO_AUDIO_DIR", "/audio/input/auto"))
OUTPUT_AUDIO_DIR = os.path.normpath(os.environ.get("OUTPUT_AUDIO_DIR", "/audio/output"))

logger = logging.getLogger("audio_assets")
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*\.wav$", re.IGNORECASE)

SAMPLE_AUDIO_RECORDINGS = (
    {
        "filename": "OSR_us_000_0010_8k.wav",
        "gender": "F",
        "format": "16b PCM",
        "sample_rate": "8 kHz",
        "description": "Harvard sentences",
        "url": "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0010_8k.wav",
    },
    {
        "filename": "OSR_us_000_0011_8k.wav",
        "gender": "F",
        "format": "16b PCM",
        "sample_rate": "8 kHz",
        "description": "Harvard sentences",
        "url": "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0011_8k.wav",
    },
    {
        "filename": "OSR_us_000_0012_8k.wav",
        "gender": "F",
        "format": "16b PCM",
        "sample_rate": "8 kHz",
        "description": "Harvard sentences",
        "url": "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0012_8k.wav",
    },
)
SAMPLE_AUDIO_FILENAMES = frozenset(
    recording["filename"] for recording in SAMPLE_AUDIO_RECORDINGS
)


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
        self._ensure_directories()

    @staticmethod
    def _ensure_directories() -> None:
        for directory in (AUTO_AUDIO_DIR, OUTPUT_AUDIO_DIR):
            try:
                os.makedirs(directory, mode=0o755, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(
                    f"Failed to create audio directory '{directory}': {exc}"
                ) from exc

    @staticmethod
    def _is_safe_filename(filename: str) -> bool:
        return (
            filename not in {".", ".."}
            and os.path.basename(filename) == filename
            and SAFE_FILENAME_PATTERN.fullmatch(filename) is not None
        )

    @staticmethod
    def _wav_duration(path: Path) -> float | None:
        """Return the WAV duration, or None when the file is not a usable WAV."""
        try:
            with wave.open(str(path), "rb") as audio:
                if (
                    audio.getnchannels() > 0
                    and audio.getsampwidth() > 0
                    and audio.getframerate() > 0
                    and audio.getnframes() > 0
                ):
                    return audio.getnframes() / audio.getframerate()
        except (OSError, EOFError, wave.Error):
            pass
        return None

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove temporary audio file")

    def list_assets(self) -> list[AudioAsset]:
        assets = (
            self.get_asset(recording["filename"])
            for recording in SAMPLE_AUDIO_RECORDINGS
        )
        return sorted(
            (asset for asset in assets if asset is not None),
            key=lambda asset: asset.filename.lower(),
        )

    def get_asset(self, filename: str) -> AudioAsset | None:
        if filename not in SAMPLE_AUDIO_FILENAMES or not self._is_safe_filename(
            filename
        ):
            return None
        path = Path(AUTO_AUDIO_DIR) / filename
        if path.is_symlink() or not path.is_file():
            return None
        duration = self._wav_duration(path)
        if duration is None:
            return None
        return AudioAsset(filename, str(path), duration)

    def save_sample_recording(self, filename: str, content: bytes) -> AudioAsset:
        """Atomically store a downloaded catalog sample in the managed input directory."""
        if filename not in SAMPLE_AUDIO_FILENAMES or not self._is_safe_filename(
            filename
        ):
            raise ValueError("Unknown sample audio recording")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".audio-sample-",
                suffix=".wav",
                dir=AUTO_AUDIO_DIR,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
            if self._wav_duration(temporary_path) is None:
                raise ValueError("Sample audio recording is not a valid WAV file")
            os.replace(temporary_path, Path(AUTO_AUDIO_DIR) / filename)
            temporary_path = None
        finally:
            if temporary_path is not None:
                self._remove_file(temporary_path)

        asset = self.get_asset(filename)
        if asset is None:
            raise OSError("Stored sample audio recording is unavailable")
        logger.info("Stored sample audio recording '%s'.", filename)
        return asset

    def get_path(self, filename: str) -> str | None:
        asset = self.get_asset(filename)
        return asset.path if asset is not None else None

    def get_output_directory(self) -> str:
        return OUTPUT_AUDIO_DIR
