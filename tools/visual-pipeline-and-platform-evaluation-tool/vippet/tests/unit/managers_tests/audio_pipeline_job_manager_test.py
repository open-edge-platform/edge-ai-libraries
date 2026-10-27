# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from managers.audio_pipeline_job_manager import (
    AudioPipelineRecordingInput,
    AudioPipelineSTTInput,
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
        self.addAsyncCleanup(self.manager.shutdown)

    async def test_completes_stt_job_with_transcript(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        job = await self.manager.start_job("speech-to-text")
        await self.manager.wait(job.id)
        completed = await self.manager.get_job(job.id)

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

        job = await self.manager.start_job("speech-to-text", "npu")
        await self.manager.wait(job.id)

        self.assertEqual(job.variant_id, "npu")
        self.assertEqual(job.variant_name, "NPU")
        self.assertEqual(job.device, "NPU")
        assert self.transcribe.await_args is not None
        self.assertEqual(self.transcribe.await_args.args[-1], "NPU")

    async def test_completes_stt_job_with_uploaded_input_and_cleans_it(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        observed: dict[str, object] = {}

        async def transcribe(
            audio_file, filename, content_type, language, device
        ) -> tuple[str, float]:
            observed["content"] = audio_file.read()
            observed["metadata"] = (filename, content_type, language, device)
            return "Uploaded transcript", 14.5

        self.manager.transcribe = transcribe

        job = await self.manager.start_job(
            "speech-to-text",
            "npu",
            stt_input=AudioPipelineSTTInput(
                file=io.BytesIO(b"uploaded audio"),
                filename="sample.mp3",
                content_type="audio/mpeg",
                language="pl",
            ),
        )
        await self.manager.wait(job.id)

        completed = await self.manager.get_job(job.id)
        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(completed.transcript, "Uploaded transcript")
        self.assertEqual(observed["content"], b"uploaded audio")
        self.assertEqual(
            observed["metadata"],
            ("sample.mp3", "audio/mpeg", "pl", "NPU"),
        )
        self.assertEqual(list(self.manager._input_directory.iterdir()), [])

    async def test_completes_stt_job_with_registered_recording(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        other_recording = Path(self.temp_dir.name) / "other.wav"
        other_recording.write_bytes(wav_bytes() + b"extra")
        self.assets.get_path.side_effect = lambda name: (
            str(other_recording) if name == "other.wav" else None
        )
        observed: dict[str, object] = {}

        async def transcribe(
            audio_file, filename, content_type, language, device
        ) -> tuple[str, float]:
            observed["content"] = audio_file.read()
            observed["metadata"] = (filename, content_type, language, device)
            return "Recording transcript", 9.5

        self.manager.transcribe = transcribe

        job = await self.manager.start_job(
            "speech-to-text",
            "npu",
            recording_input=AudioPipelineRecordingInput(
                filename="other.wav", language="de"
            ),
        )
        await self.manager.wait(job.id)

        completed = await self.manager.get_job(job.id)
        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(completed.transcript, "Recording transcript")
        self.assertEqual(observed["content"], other_recording.read_bytes())
        self.assertEqual(observed["metadata"], ("other.wav", "audio/wav", "de", "NPU"))

    async def test_rejects_unknown_recording_input(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        self.assets.get_path.return_value = None

        with self.assertRaisesRegex(ValueError, "Audio recording 'missing.wav'"):
            await self.manager.start_job(
                "speech-to-text",
                recording_input=AudioPipelineRecordingInput(
                    filename="missing.wav", language="en"
                ),
            )

        self.transcribe.assert_not_called()

    async def test_rejects_recording_input_for_tts_pipeline(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        with self.assertRaisesRegex(ValueError, "do not accept recording input"):
            await self.manager.start_job(
                "text-to-speech",
                recording_input=AudioPipelineRecordingInput(
                    filename="sample.wav", language="en"
                ),
            )

    async def test_completes_tts_job_with_atomic_wav_artifact(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        job = await self.manager.start_job("text-to-speech", "gpu")
        await self.manager.wait(job.id)
        completed = await self.manager.get_job(job.id)

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

        job = await self.manager.start_job(
            "text-to-speech",
            "gpu",
            input_text="Custom sentence",
            voice="Angus",
        )
        await self.manager.wait(job.id)
        completed = await self.manager.get_job(job.id)

        self.synthesize.assert_awaited_once_with(
            "Custom sentence",
            "Angus",
            "GPU",
        )
        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)
        self.assertEqual(completed.artifact_filename, f"{job.id}.wav")
        assert completed.artifact_path is not None
        self.assertEqual(Path(completed.artifact_path).read_bytes(), wav_bytes())

    async def test_rejects_tts_overrides_for_stt_job(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        with self.assertRaisesRegex(ValueError, "do not accept TTS overrides"):
            await self.manager.start_job(
                "speech-to-text",
                input_text="Custom sentence",
                voice="Ryan",
            )

    async def test_rejects_stt_input_for_tts_job(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        with self.assertRaisesRegex(ValueError, "do not accept STT input"):
            await self.manager.start_job(
                "text-to-speech",
                stt_input=AudioPipelineSTTInput(
                    file=io.BytesIO(b"audio"),
                    filename="sample.wav",
                    content_type="audio/wav",
                    language="en",
                ),
            )

    async def test_rejects_unknown_pipeline(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = None

        with self.assertRaisesRegex(ValueError, "not found"):
            await self.manager.start_job("missing")

    async def test_rejects_unknown_variant(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        with self.assertRaisesRegex(ValueError, "variant 'missing' not found"):
            await self.manager.start_job("speech-to-text", "missing")

    async def test_failure_uses_stable_public_message(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        async def fail(*_args, **_kwargs):
            raise RuntimeError("private upstream details")

        self.manager.transcribe = fail
        with self.assertLogs("audio_pipeline_jobs", level="ERROR") as logs:
            job = await self.manager.start_job("speech-to-text")
            await self.manager.wait(job.id)
        failed = await self.manager.get_job(job.id)

        assert failed is not None
        self.assertEqual(failed.status, AudioPipelineJobStatus.FAILED)
        self.assertEqual(failed.error, "Audio pipeline execution failed.")
        assert failed.error is not None
        self.assertNotIn("private", failed.error)
        self.assertNotIn("private upstream details", "\n".join(logs.output))

    async def test_lists_oldest_jobs_as_snapshots(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        first = await self.manager.start_job("speech-to-text")
        await self.manager.wait(first.id)
        second = await self.manager.start_job("speech-to-text", "npu")
        await self.manager.wait(second.id)

        jobs = await self.manager.list_jobs()
        self.assertEqual([job.id for job in jobs], [first.id, second.id])
        jobs[1].error = "external mutation"
        stored = await self.manager.get_job(second.id)
        assert stored is not None
        self.assertIsNone(stored.error)

    async def test_failed_uploaded_stt_job_cleans_staged_input(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )

        async def fail(*_args) -> tuple[str, float]:
            raise RuntimeError("private upstream details")

        self.manager.transcribe = fail
        job = await self.manager.start_job(
            "speech-to-text",
            stt_input=AudioPipelineSTTInput(
                file=io.BytesIO(b"uploaded audio"),
                filename="sample.wav",
                content_type="audio/wav",
                language="en",
            ),
        )
        await self.manager.wait(job.id)

        failed = await self.manager.get_job(job.id)
        assert failed is not None
        self.assertEqual(failed.status, AudioPipelineJobStatus.FAILED)
        self.assertEqual(list(self.manager._input_directory.iterdir()), [])

    async def test_shutdown_cleans_active_uploaded_stt_input(self) -> None:
        started = asyncio.Event()

        async def blocked_transcription(*_args) -> tuple[str, float]:
            started.set()
            await asyncio.Event().wait()
            return "unreachable", 0.0

        self.manager.transcribe = blocked_transcription
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job(
            "speech-to-text",
            stt_input=AudioPipelineSTTInput(
                file=io.BytesIO(b"uploaded audio"),
                filename="sample.wav",
                content_type="audio/wav",
                language="en",
            ),
        )
        await started.wait()

        await self.manager.shutdown()

        cancelled = await self.manager.get_job(job.id)
        assert cancelled is not None
        self.assertEqual(cancelled.status, AudioPipelineJobStatus.CANCELLED)
        self.assertFalse(self.manager._input_directory.exists())

    async def test_shutdown_cancels_active_jobs_and_cleans_tasks(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_transcription(*_args):
            started.set()
            await release.wait()
            return "unreachable", 0.0

        self.manager.transcribe = blocked_transcription
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job("speech-to-text")
        await started.wait()

        await self.manager.shutdown()

        cancelled = await self.manager.get_job(job.id)
        assert cancelled is not None
        self.assertEqual(cancelled.status, AudioPipelineJobStatus.CANCELLED)
        await self.manager.wait(job.id)
        self.assertEqual(self.manager._tasks, {})

    async def test_cancels_running_stt_job(self) -> None:
        started = asyncio.Event()
        interrupted = asyncio.Event()

        async def blocked_transcription(*_args):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                interrupted.set()
                raise
            return "unreachable", 0.0

        self.manager.transcribe = blocked_transcription
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job("speech-to-text")
        await started.wait()

        cancelled = await self.manager.cancel_job(job.id)

        self.assertEqual(cancelled.status, AudioPipelineJobStatus.CANCELLED)
        self.assertTrue(interrupted.is_set())
        stored = await self.manager.get_job(job.id)
        assert stored is not None
        self.assertEqual(stored.status, AudioPipelineJobStatus.CANCELLED)
        self.assertIsNone(stored.transcript)
        self.assertEqual(self.manager._tasks, {})

    async def test_cancels_running_tts_job_without_artifact(self) -> None:
        started = asyncio.Event()

        async def blocked_synthesis(*_args):
            started.set()
            await asyncio.Event().wait()
            return wav_bytes(), 0.0

        self.manager.synthesize = blocked_synthesis
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )
        job = await self.manager.start_job("text-to-speech", "gpu")
        await started.wait()

        cancelled = await self.manager.cancel_job(job.id)

        self.assertEqual(cancelled.status, AudioPipelineJobStatus.CANCELLED)
        self.assertIsNone(cancelled.artifact_path)
        self.assertFalse((Path(self.temp_dir.name) / f"{job.id}.wav").exists())
        self.assertEqual(list(Path(self.temp_dir.name).glob(".audio-job-*")), [])
        self.assertEqual(self.manager._tasks, {})

    async def test_cancelling_uploaded_stt_job_cleans_staged_input(self) -> None:
        started = asyncio.Event()

        async def blocked_transcription(*_args):
            started.set()
            await asyncio.Event().wait()
            return "unreachable", 0.0

        self.manager.transcribe = blocked_transcription
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job(
            "speech-to-text",
            stt_input=AudioPipelineSTTInput(
                file=io.BytesIO(b"uploaded audio"),
                filename="sample.wav",
                content_type="audio/wav",
                language="en",
            ),
        )
        await started.wait()

        await self.manager.cancel_job(job.id)

        self.assertEqual(list(self.manager._input_directory.iterdir()), [])

    async def test_cancels_queued_job_before_it_starts(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job(
            "speech-to-text",
            stt_input=AudioPipelineSTTInput(
                file=io.BytesIO(b"uploaded audio"),
                filename="sample.wav",
                content_type="audio/wav",
                language="en",
            ),
        )

        cancelled = await self.manager.cancel_job(job.id)

        self.assertEqual(cancelled.status, AudioPipelineJobStatus.CANCELLED)
        self.transcribe.assert_not_called()
        self.assertEqual(list(self.manager._input_directory.iterdir()), [])

    async def test_rejects_cancelling_unknown_or_finished_job(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job("speech-to-text")
        await self.manager.wait(job.id)

        with self.assertRaisesRegex(ValueError, "not found"):
            await self.manager.cancel_job("missing")
        with self.assertRaisesRegex(ValueError, "not running"):
            await self.manager.cancel_job(job.id)

        completed = await self.manager.get_job(job.id)
        assert completed is not None
        self.assertEqual(completed.status, AudioPipelineJobStatus.COMPLETED)

    async def test_rejects_transition_from_terminal_state(self) -> None:
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
        )
        job = await self.manager.start_job("speech-to-text")
        await self.manager.wait(job.id)

        with self.assertRaisesRegex(RuntimeError, "Invalid Audio job transition"):
            self.manager._transition_locked(
                self.manager._jobs[job.id],
                AudioPipelineJobStatus.RUNNING,
            )

    async def test_prunes_oldest_terminal_job_and_its_artifact(self) -> None:
        self.manager = AudioPipelineJobManager(
            self.pipeline_manager,
            self.assets,
            self.transcribe,
            self.synthesize,
            max_terminal_jobs=2,
        )
        self.addAsyncCleanup(self.manager.shutdown)
        self.pipeline_manager.get_pipeline.return_value = pipeline(
            AudioPipelineOperation.TEXT_TO_SPEECH
        )

        jobs = []
        artifact_paths = []
        for _ in range(3):
            job = await self.manager.start_job("text-to-speech")
            await self.manager.wait(job.id)
            completed = await self.manager.get_job(job.id)
            jobs.append(job)
            if completed is not None and completed.artifact_path is not None:
                artifact_paths.append(Path(completed.artifact_path))

        self.assertIsNone(await self.manager.get_job(jobs[0].id))
        self.assertIsNotNone(await self.manager.get_job(jobs[1].id))
        self.assertIsNotNone(await self.manager.get_job(jobs[2].id))
        self.assertFalse(artifact_paths[0].exists())
        self.assertTrue(artifact_paths[1].exists())

    async def test_retention_never_removes_active_job(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_transcription(*_args):
            started.set()
            await release.wait()
            return "Managed transcript", 12.5

        self.manager = AudioPipelineJobManager(
            self.pipeline_manager,
            self.assets,
            blocked_transcription,
            self.synthesize,
            max_terminal_jobs=1,
        )
        self.addAsyncCleanup(self.manager.shutdown)
        self.pipeline_manager.get_pipeline.side_effect = lambda pipeline_id: pipeline(
            AudioPipelineOperation.SPEECH_TO_TEXT
            if pipeline_id == "speech-to-text"
            else AudioPipelineOperation.TEXT_TO_SPEECH
        )

        active = await self.manager.start_job("speech-to-text")
        await started.wait()
        for _ in range(2):
            completed = await self.manager.start_job("text-to-speech")
            await self.manager.wait(completed.id)

        retained = await self.manager.get_job(active.id)
        assert retained is not None
        self.assertEqual(retained.status, AudioPipelineJobStatus.RUNNING)
        release.set()
        await self.manager.wait(active.id)

    async def test_artifact_cleanup_rejects_path_outside_output_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as external_directory:
            external_artifact = Path(external_directory) / "external.wav"
            external_artifact.write_bytes(wav_bytes())

            await self.manager._delete_artifacts([str(external_artifact)])

            self.assertTrue(external_artifact.exists())


if __name__ == "__main__":
    unittest.main()
