# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import yaml

from audio_assets import AudioAssetsManager


def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(
        self, content: bytes, final_url: str = "https://example.com/sample.wav"
    ):
        super().__init__(content)
        self.final_url = final_url

    def geturl(self) -> str:
        return self.final_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AudioAssetsManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.auto_dir = root / "input" / "auto"
        self.output_dir = root / "output"
        self.manifest = root / "default_recordings.yaml"
        AudioAssetsManager._instance = None
        self.addCleanup(setattr, AudioAssetsManager, "_instance", None)

    def write_manifest(self, entries: list[dict[str, str]]) -> None:
        self.manifest.write_text(yaml.safe_dump(entries), encoding="utf-8")

    def create_manager(self) -> AudioAssetsManager:
        patches = (
            patch("audio_assets.AUTO_AUDIO_DIR", str(self.auto_dir)),
            patch("audio_assets.OUTPUT_AUDIO_DIR", str(self.output_dir)),
            patch("audio_assets.DEFAULT_AUDIO_RECORDINGS_FILE", str(self.manifest)),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        return AudioAssetsManager()

    def test_downloads_and_registers_valid_wav(self) -> None:
        self.write_manifest(
            [
                {
                    "url": "https://example.com/sample.wav",
                    "filename": "sample.wav",
                }
            ]
        )

        with patch(
            "audio_assets.urllib.request.urlopen",
            return_value=FakeResponse(wav_bytes()),
        ):
            manager = self.create_manager()

        expected = self.auto_dir / "sample.wav"
        self.assertEqual(manager.get_path("sample.wav"), str(expected))
        self.assertEqual(expected.read_bytes(), wav_bytes())

    def test_successful_download_logs_start_size_and_duration(self) -> None:
        self.write_manifest(
            [
                {
                    "url": "https://example.com/sample.wav?source=manifest",
                    "filename": "sample.wav",
                }
            ]
        )

        with (
            patch(
                "audio_assets.urllib.request.urlopen",
                return_value=FakeResponse(wav_bytes()),
            ),
            patch(
                "audio_assets.time.perf_counter", side_effect=[10.0, 13.2]
            ) as perf_counter,
            self.assertLogs("audio_assets", level="INFO") as logs,
        ):
            self.create_manager()

        self.assertEqual(perf_counter.call_count, 2)
        self.assertEqual(
            logs.output,
            [
                "INFO:audio_assets:Downloading 'sample.wav' from "
                "https://example.com/sample.wav?source=manifest...",
                "INFO:audio_assets:Downloaded 'sample.wav' (0.0 MB) in 3.2 seconds.",
            ],
        )

    def test_reuses_existing_valid_wav(self) -> None:
        self.auto_dir.mkdir(parents=True)
        existing = self.auto_dir / "sample.wav"
        existing.write_bytes(wav_bytes())
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        with patch("audio_assets.urllib.request.urlopen") as urlopen:
            manager = self.create_manager()

        urlopen.assert_not_called()
        self.assertEqual(manager.get_path("sample.wav"), str(existing))

    def test_rejects_unsafe_manifest_filename(self) -> None:
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "../sample.wav"}]
        )

        with patch("audio_assets.urllib.request.urlopen") as urlopen:
            manager = self.create_manager()

        urlopen.assert_not_called()
        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertFalse((Path(self.temp_dir.name) / "sample.wav").exists())

    def test_invalid_download_is_removed(self) -> None:
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        with patch(
            "audio_assets.urllib.request.urlopen",
            return_value=FakeResponse(b"not a wav"),
        ):
            manager = self.create_manager()

        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_oversized_download_is_removed(self) -> None:
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        with (
            patch("audio_assets.MAX_AUDIO_DOWNLOAD_BYTES", 100),
            patch(
                "audio_assets.urllib.request.urlopen",
                return_value=FakeResponse(wav_bytes()),
            ),
        ):
            manager = self.create_manager()

        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_rejects_redirect_to_non_https_url(self) -> None:
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        with patch(
            "audio_assets.urllib.request.urlopen",
            return_value=FakeResponse(
                wav_bytes(),
                final_url="http://example.com/sample.wav",
            ),
        ):
            manager = self.create_manager()

        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_does_not_reuse_symlinked_recording(self) -> None:
        self.auto_dir.mkdir(parents=True)
        external = Path(self.temp_dir.name) / "external.wav"
        external.write_bytes(wav_bytes())
        managed = self.auto_dir / "sample.wav"
        managed.symlink_to(external)
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        with patch(
            "audio_assets.urllib.request.urlopen",
            return_value=FakeResponse(wav_bytes()),
        ) as urlopen:
            manager = self.create_manager()

        urlopen.assert_called_once()
        self.assertFalse(managed.is_symlink())
        self.assertEqual(manager.get_path("sample.wav"), str(managed))

    def test_get_path_accepts_only_registered_logical_names(self) -> None:
        self.write_manifest([])
        manager = self.create_manager()

        self.assertIsNone(manager.get_path("../sample.wav"))
        self.assertIsNone(manager.get_path(os.path.abspath("sample.wav")))


if __name__ == "__main__":
    unittest.main()
