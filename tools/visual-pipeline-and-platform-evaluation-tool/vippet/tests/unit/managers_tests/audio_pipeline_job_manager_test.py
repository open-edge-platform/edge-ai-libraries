# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from managers.audio_pipeline_job_manager import (
    AudioPipelineJobManager,
    AudioPipelineJobStatus,
)
from managers.audio_pipeline_manager import (
    AudioPipeline,
    AudioPipelineDefaults,
    AudioPipelineOperation,
    AudioPipelineVariant,
)


def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


def pipeline(
    operation: AudioPipelineOperation,
    *,
    available: bool = True,
) -> AudioPipeline:
    is_stt = operation is AudioPipelineOperation.SPEECH_TO_TEXT
    return AudioPipeline(
        id="speech-to-text" if is_stt else "text-to-speech",
        name="Speech to Text" if is_stt else "Text to Speech",
        description="Audio pipeline",
        type="audio",
        operation=operation,
        tags=["Audio"],
        thumbnail=None,
        required_models=["Whisper Base" if is_stt else "SpeechT5"],
        variants=[
            AudioPipelineVariant(id="cpu", name="CPU", device="CPU"),
            AudioPipelineVariant(
                id="npu" if is_stt else "gpu",
                name="NPU" if is_stt else "GPU",
                device="NPU" if is_stt else "GPU",
            ),
        ],
        defaults=AudioPipelineDefaults(
            audio="sample.wav" if is_stt else None,
            language="en" if is_stt else None,
            text=None if is_stt else "Hello world",
            voice=None if is_stt else "Ryan",
        ),
        available=available,
        unavailable_reason=None if available else "Default audio input is unavailable.",
    )


class AudioPipelineJobManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.audio_file = Path(self.temp_dir.name) / "sample.wav"
        self.audio_file.write_bytes(wav_bytes())
        self.pipeline_manager = MagicMock()
        self.assets = MagicMock()
        self.assets.get_path.return_value = str(self.audio_file)
        self.assets.get_output_directory.return_value = self.temp_dir.name

        self.transcribe = AsyncMock(return_value=("Managed transcript", 12.5))
        self.synthesize = AsyncMock(return_value=(wav_bytes(), 18.75))

        self.manager = AudioPipelineJobManager(
            self.pipeline_manager,
            self.assets,
            self.transcribe,
            self.synthesize,
        )

    async def test_completes_stt_job_with_transcript(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        job = self.manager.start_job("speech-to-text")
        await self.manager.wait(job.id)
        completed = self.manager.get_job(job.id)

        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(completed.transcript, "Managed transcript")
        self.assertEqual(completed.service_round_trip_ms, 12.5)
        self.assertEqual(completed.variant_id, "cpu")
        self.assertEqual(completed.device, "CPU")
        assert self.transcribe.await_args is not None
        self.assertEqual(self.transcribe.await_args.args[-1], "CPU")
        self.assertIsNone(completed.artifact_path)

    async def test_runs_explicit_stt_variant_on_its_device(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        job = self.manager.start_job("speech-to-text", "npu")
        await self.manager.wait(job.id)

        self.assertEqual(job.variant_id, "npu")
        self.assertEqual(job.variant_name, "NPU")
        self.assertEqual(job.device, "NPU")
        assert self.transcribe.await_args is not None
        self.assertEqual(self.transcribe.await_args.args[-1], "NPU")

    async def test_completes_tts_job_with_atomic_wav_artifact(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        job = self.manager.start_job("text-to-speech", "gpu")
        await self.manager.wait(job.id)
        completed = self.manager.get_job(job.id)

        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(completed.service_round_trip_ms, 18.75)
        self.assertEqual(completed.variant_id, "gpu")
        self.assertEqual(completed.device, "GPU")
        assert self.synthesize.await_args is not None
        self.assertEqual(self.synthesize.await_args.args[-1], "GPU")
        self.assertEqual(completed.artifact_filename, f"{job.id}.wav")
        assert completed.artifact_path is not None
        self.assertEqual(Path(completed.artifact_path).read_bytes(), wav_bytes())
        self.assertEqual(list(Path(self.temp_dir.name).glob(".audio-job-*")), [])

    async def test_completes_custom_tts_job_with_persisted_artifact(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        job = self.manager.start_job(
            "text-to-speech",
            "gpu",
            input_text="Custom sentence",
            voice="Angus",
        )
        await self.manager.wait(job.id)

        self.synthesize.assert_awaited_once_with(
            "Custom sentence",
            "Angus",
            "GPU",
        )
        self.assertEqual(job.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(job.artifact_filename, f"{job.id}.wav")
        assert job.artifact_path is not None
        self.assertEqual(Path(job.artifact_path).read_bytes(), wav_bytes())

    async def test_rejects_tts_overrides_for_stt_job(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        with self.assertRaisesRegex(ValueError, "do not accept TTS overrides"):
            self.manager.start_job(
                "speech-to-text",
                input_text="Custom sentence",
                voice="Ryan",
            )

    async def test_rejects_unknown_pipeline(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = None

        with self.assertRaisesRegex(ValueError, "not found"):
            self.manager.start_job("missing")

    async def test_rejects_unavailable_pipeline(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT,
            available=False,
        )

        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.manager.start_job("speech-to-text")

    async def test_rejects_unknown_variant(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        with self.assertRaisesRegex(ValueError, "variant 'missing' not found"):
            self.manager.start_job("speech-to-text", "missing")

    async def test_failure_uses_stable_public_message(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        async def fail(*_args, **_kwargs):
            raise RuntimeError("private upstream details")

        self.manager.transcribe = fail
        job = self.manager.start_job("speech-to-text")
        await self.manager.wait(job.id)
        failed = self.manager.get_job(job.id)

        assert failed is not None
        self.assertEqual(failed.status, AudioPipelineJobStatus.FAILED)
        self.assertEqual(failed.error, "Audio pipeline execution failed.")
        assert failed.error is not None
        self.assertNotIn("private", failed.error)


if __name__ == "__main__":
    unittest.main()
