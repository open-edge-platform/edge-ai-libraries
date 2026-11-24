# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from audio_assets import AudioAssetsManager

FIRST = "OSR_us_000_0010_8k.wav"
SECOND = "OSR_us_000_0011_8k.wav"


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
        AudioAssetsManager._instance = None
        self.addCleanup(setattr, AudioAssetsManager, "_instance", None)

    def create_manager(self) -> AudioAssetsManager:
        patches = (
            patch("audio_assets.AUTO_AUDIO_DIR", str(self.auto_dir)),
            patch("audio_assets.OUTPUT_AUDIO_DIR", str(self.output_dir)),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        return AudioAssetsManager()

    def test_starts_with_no_recordings(self) -> None:
        manager = self.create_manager()

        self.assertTrue(self.auto_dir.is_dir())
        self.assertEqual(manager.list_assets(), [])
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_saves_and_lists_downloaded_sample(self) -> None:
        manager = self.create_manager()

        asset = manager.save_sample_recording(FIRST, wav_bytes())

        stored = self.auto_dir / FIRST
        self.assertEqual(asset.path, str(stored))
        self.assertAlmostEqual(asset.duration_seconds, 0.1)
        self.assertEqual(stored.read_bytes(), wav_bytes())
        self.assertEqual(manager.get_path(FIRST), str(stored))
        self.assertEqual([item.filename for item in manager.list_assets()], [FIRST])

    def test_lists_existing_downloaded_samples_sorted(self) -> None:
        self.auto_dir.mkdir(parents=True)
        (self.auto_dir / SECOND).write_bytes(wav_bytes())
        (self.auto_dir / FIRST).write_bytes(wav_bytes())

        assets = self.create_manager().list_assets()

        self.assertEqual([asset.filename for asset in assets], [FIRST, SECOND])

    def test_ignores_files_outside_the_sample_catalog(self) -> None:
        self.auto_dir.mkdir(parents=True)
        (self.auto_dir / "sample_male.wav").write_bytes(wav_bytes())

        manager = self.create_manager()

        self.assertEqual(manager.list_assets(), [])
        self.assertIsNone(manager.get_path("sample_male.wav"))

    def test_ignores_invalid_or_symlinked_samples(self) -> None:
        self.auto_dir.mkdir(parents=True)
        (self.auto_dir / FIRST).write_bytes(b"corrupt")
        external = Path(self.temp_dir.name) / "external.wav"
        external.write_bytes(wav_bytes())
        (self.auto_dir / SECOND).symlink_to(external)

        manager = self.create_manager()

        self.assertIsNone(manager.get_path(FIRST))
        self.assertIsNone(manager.get_path(SECOND))
        self.assertEqual(manager.list_assets(), [])

    def test_save_replaces_symlinked_sample(self) -> None:
        self.auto_dir.mkdir(parents=True)
        external = Path(self.temp_dir.name) / "external.wav"
        external.write_bytes(b"external")
        managed = self.auto_dir / FIRST
        managed.symlink_to(external)

        self.create_manager().save_sample_recording(FIRST, wav_bytes())

        self.assertFalse(managed.is_symlink())
        self.assertEqual(external.read_bytes(), b"external")

    def test_save_rejects_unknown_filename(self) -> None:
        manager = self.create_manager()

        for name in ("other.wav", "../" + FIRST):
            with self.assertRaises(ValueError):
                manager.save_sample_recording(name, wav_bytes())
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_save_rejects_invalid_wav_without_leaving_files(self) -> None:
        manager = self.create_manager()

        with self.assertRaises(ValueError):
            manager.save_sample_recording(FIRST, b"not a wav")
        self.assertEqual(list(self.auto_dir.iterdir()), [])

    def test_get_path_accepts_only_catalog_names(self) -> None:
        manager = self.create_manager()

        self.assertIsNone(manager.get_path("../" + FIRST))
        self.assertIsNone(manager.get_path(os.path.abspath(FIRST)))


if __name__ == "__main__":
    unittest.main()
