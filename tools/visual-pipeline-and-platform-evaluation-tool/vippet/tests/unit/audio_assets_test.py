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


class AudioAssetsManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.auto_dir = root / "input" / "auto"
        self.output_dir = root / "output"
        self.manifest = root / "default_recordings.yaml"
        self.local_dir = root / "local"
        AudioAssetsManager._instance = None
        self.addCleanup(setattr, AudioAssetsManager, "_instance", None)

    def write_manifest(self, entries: list[dict[str, str]]) -> None:
        self.manifest.write_text(yaml.safe_dump(entries), encoding="utf-8")

    def create_manager(self) -> AudioAssetsManager:
        patches = (
            patch("audio_assets.AUTO_AUDIO_DIR", str(self.auto_dir)),
            patch("audio_assets.OUTPUT_AUDIO_DIR", str(self.output_dir)),
            patch("audio_assets.DEFAULT_AUDIO_RECORDINGS_FILE", str(self.manifest)),
            patch("audio_assets.LOCAL_AUDIO_RECORDINGS_DIR", self.local_dir),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        return AudioAssetsManager()

    def test_copies_local_recording_and_registers_it(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "source.wav").write_bytes(wav_bytes())
        self.write_manifest([{"local": "source.wav", "filename": "local.wav"}])

        manager = self.create_manager()

        installed = self.auto_dir / "local.wav"
        self.assertEqual(manager.get_path("local.wav"), str(installed))
        self.assertEqual(installed.read_bytes(), wav_bytes())

    def test_keeps_existing_valid_copy_of_local_recording(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "local.wav").write_bytes(wav_bytes())
        self.auto_dir.mkdir(parents=True)
        existing = self.auto_dir / "local.wav"
        other = io.BytesIO()
        with wave.open(other, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x01\x00" * 10)
        existing.write_bytes(other.getvalue())
        self.write_manifest([{"local": "local.wav", "filename": "local.wav"}])

        manager = self.create_manager()

        self.assertEqual(existing.read_bytes(), other.getvalue())
        self.assertEqual(manager.get_path("local.wav"), str(existing))

    def test_replaces_invalid_copy_of_local_recording(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "local.wav").write_bytes(wav_bytes())
        self.auto_dir.mkdir(parents=True)
        (self.auto_dir / "local.wav").write_bytes(b"corrupt")
        self.write_manifest([{"local": "local.wav", "filename": "local.wav"}])

        manager = self.create_manager()

        installed = self.auto_dir / "local.wav"
        self.assertEqual(installed.read_bytes(), wav_bytes())
        self.assertEqual(manager.get_path("local.wav"), str(installed))

    def test_replaces_symlinked_copy_of_local_recording(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "local.wav").write_bytes(wav_bytes())
        self.auto_dir.mkdir(parents=True)
        external = Path(self.temp_dir.name) / "external.wav"
        external.write_bytes(wav_bytes())
        managed = self.auto_dir / "local.wav"
        managed.symlink_to(external)
        self.write_manifest([{"local": "local.wav", "filename": "local.wav"}])

        manager = self.create_manager()

        self.assertFalse(managed.is_symlink())
        self.assertEqual(manager.get_path("local.wav"), str(managed))

    def test_skips_unusable_local_recordings(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "broken.wav").write_bytes(b"not a wav")
        external = Path(self.temp_dir.name) / "external.wav"
        external.write_bytes(wav_bytes())
        (self.local_dir / "link.wav").symlink_to(external)
        self.write_manifest(
            [
                {"local": "broken.wav", "filename": "broken.wav"},
                {"local": "link.wav", "filename": "link.wav"},
                {"local": "missing.wav", "filename": "missing.wav"},
                {"local": "../external.wav", "filename": "escape.wav"},
            ]
        )

        manager = self.create_manager()

        for name in ("broken.wav", "link.wav", "missing.wav", "escape.wav"):
            self.assertIsNone(manager.get_path(name))
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_rejects_unsafe_manifest_filename(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "sample.wav").write_bytes(wav_bytes())
        self.write_manifest([{"local": "sample.wav", "filename": "../sample.wav"}])

        manager = self.create_manager()

        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertFalse((Path(self.temp_dir.name) / "sample.wav").exists())

    def test_ignores_entries_without_a_local_source(self) -> None:
        self.write_manifest(
            [{"url": "https://example.com/sample.wav", "filename": "sample.wav"}]
        )

        manager = self.create_manager()

        self.assertIsNone(manager.get_path("sample.wav"))
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_lists_registered_recordings_with_durations(self) -> None:
        self.local_dir.mkdir()
        (self.local_dir / "b.wav").write_bytes(wav_bytes())
        (self.local_dir / "a.wav").write_bytes(wav_bytes())
        self.write_manifest(
            [
                {"local": "b.wav", "filename": "b.wav"},
                {"local": "a.wav", "filename": "a.wav"},
            ]
        )

        manager = self.create_manager()

        assets = manager.list_assets()
        self.assertEqual([asset.filename for asset in assets], ["a.wav", "b.wav"])
        self.assertAlmostEqual(assets[0].duration_seconds, 0.1)
        self.assertEqual(assets[0].path, str(self.auto_dir / "a.wav"))

    def test_lists_nothing_when_no_recording_is_registered(self) -> None:
        self.write_manifest([])

        self.assertEqual(self.create_manager().list_assets(), [])

    def test_get_path_accepts_only_registered_logical_names(self) -> None:
        self.write_manifest([])
        manager = self.create_manager()

        self.assertIsNone(manager.get_path("../sample.wav"))
        self.assertIsNone(manager.get_path(os.path.abspath("sample.wav")))


if __name__ == "__main__":
    unittest.main()
