# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import os
import tempfile
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

import httpx

import audio_service_client as speech_client
from audio_assets import AudioAssetsManager
from audio_errors import (
    AudioRecordingNotFoundError,
    SampleAudioDownloadError,
    SampleAudioDownloadTimeoutError,
    SampleAudioStorageError,
)

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


class AudioAssetsManagerTests(unittest.IsolatedAsyncioTestCase):
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

    def test_initializes_once_across_threads(self) -> None:
        start = Barrier(8)

        def create() -> AudioAssetsManager:
            start.wait(timeout=5)
            return AudioAssetsManager()

        with patch.object(
            AudioAssetsManager,
            "_ensure_directories",
            side_effect=lambda: Event().wait(0.02),
        ) as initialize:
            with ThreadPoolExecutor(max_workers=8) as executor:
                managers = list(executor.map(lambda _: create(), range(8)))

        self.assertTrue(all(manager is managers[0] for manager in managers))
        initialize.assert_called_once_with()

    def test_retries_initialization_after_failure(self) -> None:
        with patch.object(
            AudioAssetsManager,
            "_ensure_directories",
            side_effect=[RuntimeError("not writable"), None],
        ) as initialize:
            with self.assertRaises(RuntimeError):
                AudioAssetsManager()
            manager = AudioAssetsManager()
            self.assertIs(manager, AudioAssetsManager())

        self.assertEqual(initialize.call_count, 2)

    async def test_downloads_only_the_catalog_url_and_installs_wav(self) -> None:
        manager = self.create_manager()
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200, content=wav_bytes(), headers={"content-type": "audio/wav"}
            )

        with patch.object(
            speech_client,
            "create_sample_audio_client",
            side_effect=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(respond)
            ),
        ):
            recording = await manager.download_sample_recording(FIRST)

        self.assertEqual(recording["filename"], FIRST)
        self.assertEqual(requests[0].url, recording["url"])
        self.assertEqual((self.auto_dir / FIRST).read_bytes(), wav_bytes())

    async def test_skips_downloading_an_existing_valid_sample(self) -> None:
        manager = self.create_manager()
        manager.save_sample_recording(FIRST, wav_bytes())
        with patch.object(speech_client, "create_sample_audio_client") as factory:
            recording = await manager.download_sample_recording(FIRST)

        self.assertEqual(recording["filename"], FIRST)
        factory.assert_not_called()

    async def test_rejects_unknown_samples_before_network_access(self) -> None:
        manager = self.create_manager()
        with patch.object(speech_client, "create_sample_audio_client") as factory:
            for filename in (
                "other.wav",
                "../" + FIRST,
                "https://example.com/audio.wav",
            ):
                with (
                    self.subTest(filename=filename),
                    self.assertRaises(AudioRecordingNotFoundError),
                ):
                    await manager.download_sample_recording(filename)
        factory.assert_not_called()

    async def test_rejects_invalid_sample_responses_before_writing(self) -> None:
        manager = self.create_manager()
        responses = [
            httpx.Response(302, headers={"location": "https://example.com"}),
            httpx.Response(500),
            httpx.Response(
                200, content=wav_bytes(), headers={"content-type": "text/html"}
            ),
            httpx.Response(
                200, content=b"not a WAV", headers={"content-type": "audio/wav"}
            ),
            httpx.Response(
                200,
                content=wav_bytes(),
                headers={"content-type": "audio/wav", "content-length": "invalid"},
            ),
            httpx.Response(
                200,
                content=wav_bytes(),
                headers={"content-type": "audio/wav", "content-length": "-1"},
            ),
            httpx.Response(
                200,
                content=wav_bytes(),
                headers={
                    "content-type": "audio/wav",
                    "content-length": str(speech_client.MAX_SAMPLE_AUDIO_BYTES + 1),
                },
            ),
            httpx.Response(
                200,
                stream=httpx.ByteStream(
                    b"x" * (speech_client.MAX_SAMPLE_AUDIO_BYTES + 1)
                ),
                headers={"content-type": "audio/wav"},
            ),
        ]
        for response in responses:
            with self.subTest(status=response.status_code, headers=response.headers):

                def respond(request: httpx.Request) -> httpx.Response:
                    return response

                with patch.object(
                    speech_client,
                    "create_sample_audio_client",
                    side_effect=lambda: httpx.AsyncClient(
                        transport=httpx.MockTransport(respond)
                    ),
                ):
                    with self.assertRaises(SampleAudioDownloadError):
                        await manager.download_sample_recording(FIRST)
                self.assertEqual(list(self.auto_dir.iterdir()), [])

    async def test_timeout_and_network_errors_are_sanitized(self) -> None:
        manager = self.create_manager()
        for failure, expected in (
            (httpx.ReadTimeout, SampleAudioDownloadTimeoutError),
            (httpx.ConnectError, SampleAudioDownloadError),
        ):
            with self.subTest(failure=failure):

                def respond(request: httpx.Request) -> httpx.Response:
                    raise failure("private upstream detail", request=request)

                with patch.object(
                    speech_client,
                    "create_sample_audio_client",
                    side_effect=lambda: httpx.AsyncClient(
                        transport=httpx.MockTransport(respond)
                    ),
                ):
                    with self.assertRaises(expected) as raised:
                        await manager.download_sample_recording(FIRST)
                self.assertNotIn("private", str(raised.exception))
                self.assertEqual(list(self.auto_dir.iterdir()), [])

    async def test_storage_errors_are_sanitized(self) -> None:
        manager = self.create_manager()
        with (
            patch("audio_assets.fetch_sample_audio", return_value=wav_bytes()),
            patch.object(
                manager, "save_sample_recording", side_effect=OSError("private path")
            ),
        ):
            with self.assertRaisesRegex(
                SampleAudioStorageError, "^Unable to store audio sample\\.$"
            ):
                await manager.download_sample_recording(FIRST)

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
