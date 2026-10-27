# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import json
import tempfile
import unittest
import wave
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.audio_jobs import (
    _reset_audio_pipeline_job_manager_for_tests,
    configure_audio_pipeline_job_manager_factory,
    get_audio_pipeline_job_manager,
    shutdown_audio_pipeline_job_manager,
)
from api.routes import voice
from managers.audio_pipeline_job_manager import (
    AudioPipelineJobStatus,
    AudioPipelineRecordingInput,
)


def wav_bytes(seconds: int = 1, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 16000 * seconds * channels)
    return buffer.getvalue()


class AudioJobManagerDependencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _reset_audio_pipeline_job_manager_for_tests()

    def tearDown(self) -> None:
        _reset_audio_pipeline_job_manager_for_tests()
        configure_audio_pipeline_job_manager_factory(
            voice._create_audio_pipeline_job_manager
        )

    async def test_audio_job_manager_dependency_is_shared(self) -> None:
        manager = MagicMock()
        factory = MagicMock(return_value=manager)
        configure_audio_pipeline_job_manager_factory(factory)

        self.assertIs(get_audio_pipeline_job_manager(), manager)
        self.assertIs(get_audio_pipeline_job_manager(), manager)
        factory.assert_called_once_with()

    async def test_audio_job_manager_dependency_shutdown(self) -> None:
        manager = MagicMock()
        manager.shutdown = AsyncMock()
        configure_audio_pipeline_job_manager_factory(lambda: manager)
        get_audio_pipeline_job_manager()

        await shutdown_audio_pipeline_job_manager()

        manager.shutdown.assert_awaited_once_with()


class VoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(voice.router, prefix="/voice")
        self.app = app
        self.requests: list[httpx.Request] = []
        self.upstream: httpx.Response | None = None
        self.failure: type[httpx.RequestError] | None = None
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        client_patch = patch.object(
            voice,
            "create_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.respond)),
        )
        client_patch.start()
        self.addCleanup(client_patch.stop)
        metrics_patch = patch.object(voice, "schedule_voice_metric")
        self.schedule_metric = metrics_patch.start()
        self.addCleanup(metrics_patch.stop)
        self.addCleanup(app.dependency_overrides.clear)

    def use_audio_jobs(self, jobs) -> None:
        self.app.dependency_overrides[get_audio_pipeline_job_manager] = lambda: jobs

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure:
            raise self.failure("private network detail", request=request)
        if self.upstream is not None:
            return self.upstream
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": "Hello world"})
        return httpx.Response(
            200, content=wav_bytes(), headers={"content-type": "audio/wav"}
        )

    def transcribe(
        self,
        content: bytes | None = None,
        device: str | None = None,
        filename: str = "sentence.wav",
        content_type: str = "audio/wav",
    ) -> httpx.Response:
        data = {"device": device} if device else None
        return self.client.post(
            "/voice/transcriptions",
            data=data,
            files={
                "file": (
                    filename,
                    wav_bytes() if content is None else content,
                    content_type,
                )
            },
        )

    def test_transcription_is_independent(self) -> None:
        for _ in range(2):
            response = self.transcribe()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"text": "Hello world"})
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(self.requests), 2)
        for request in self.requests:
            self.assertNotIn(b"session_id", request.content)
            self.assertNotIn(b"prompt", request.content)
            self.assertNotIn(b'name="device"', request.content)

    def test_forwards_selected_devices(self) -> None:
        transcription = self.transcribe(device="GPU")
        speech = self.client.post(
            "/voice/speech",
            json={"input": "Hello world", "voice": "Angus", "device": "NPU"},
        )

        self.assertEqual(transcription.status_code, 200)
        self.assertEqual(speech.status_code, 200)
        self.assertIn(b'name="device"', self.requests[0].content)
        self.assertIn(b"GPU", self.requests[0].content)
        self.assertEqual(
            json.loads(self.requests[1].content),
            {
                "input": "Hello world",
                "voice": "Angus",
                "response_format": "wav",
                "device": "NPU",
            },
        )

    def test_preserves_uploaded_audio_metadata(self) -> None:
        content = b"ID3\x04\x00\x00audio payload"

        response = self.transcribe(
            content,
            filename="sample.mp3",
            content_type="audio/mpeg",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.requests), 1)
        self.assertIn(b'filename="sample.mp3"', self.requests[0].content)
        self.assertIn(b"Content-Type: audio/mpeg", self.requests[0].content)
        self.assertIn(content, self.requests[0].content)

    def test_forwards_upload_larger_than_legacy_limit(self) -> None:
        content = b"x" * (10 * 1024 * 1024 + 1)

        response = self.transcribe(content, filename="large.mp3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.requests), 1)
        self.assertIn(content, self.requests[0].content)

    def test_rejects_unknown_devices(self) -> None:
        self.assertEqual(self.transcribe(device="AUTO").status_code, 422)
        self.assertEqual(
            self.client.post(
                "/voice/speech",
                json={"input": "Hello", "voice": "Ryan", "device": "AUTO"},
            ).status_code,
            422,
        )
        self.assertEqual(self.requests, [])

    def test_speech_returns_wav(self) -> None:
        response = self.client.post(
            "/voice/speech", json={"input": "Hello world", "voice": "Angus"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, wav_bytes())
        self.assertEqual(
            self.requests[0].content,
            b'{"input":"Hello world","voice":"Angus","response_format":"wav"}',
        )

    def test_accepts_supported_speech_voices(self) -> None:
        for voice_name in [
            "Ryan",
            "Miles",
            "Aaron",
            "Nora",
            "Elena",
            "Kabir",
            "Angus",
        ]:
            with self.subTest(voice=voice_name):
                response = self.client.post(
                    "/voice/speech", json={"input": "Hello", "voice": voice_name}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, wav_bytes())

    def test_rejects_invalid_speech_voice(self) -> None:
        for payload in [
            {"input": "Hello"},
            {"input": "Hello", "voice": ""},
            {"input": "Hello", "voice": "awb"},
            {"input": "Hello", "voice": "angus"},
            {"input": "Hello", "voice": "Unknown"},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/voice/speech", json=payload).status_code, 422
                )
        self.assertEqual(self.requests, [])

    def test_timings_belong_to_each_conversion(self) -> None:
        with patch.object(voice, "perf_counter", side_effect=[10, 10.25, 20, 20.75]):
            transcription = self.transcribe()
            speech = self.client.post(
                "/voice/speech", json={"input": "Hello", "voice": "Ryan"}
            )
        self.assertEqual(transcription.status_code, 200)
        self.assertEqual(speech.status_code, 200)
        self.assertEqual(
            transcription.headers["x-voice-service-duration-ms"], "250.000"
        )
        self.assertEqual(speech.headers["x-voice-service-duration-ms"], "750.000")
        self.assertEqual(transcription.json(), {"text": "Hello world"})
        self.assertEqual(speech.content, wav_bytes())
        self.assertEqual(len(self.requests), 2)

    def test_publishes_successful_conversion_metrics(self) -> None:
        with patch.object(voice, "perf_counter", side_effect=[10, 10.25, 20, 20.75]):
            transcription = self.transcribe(device="GPU")
            speech = self.client.post(
                "/voice/speech",
                json={"input": "Hello", "voice": "Angus", "device": "NPU"},
            )

        self.assertEqual(transcription.status_code, 200)
        self.assertEqual(speech.status_code, 200)
        self.assertEqual(
            self.schedule_metric.call_args_list,
            [
                call(
                    "voice_asr",
                    250.0,
                    {"device": "GPU", "language": "en"},
                ),
                call(
                    "voice_tts",
                    750.0,
                    {"device": "NPU", "voice": "Angus"},
                ),
            ],
        )

    def test_failed_conversion_has_no_success_timing(self) -> None:
        self.upstream = httpx.Response(500, text="private service detail")
        response = self.transcribe()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("x-voice-service-duration-ms", response.headers)
        self.schedule_metric.assert_not_called()

    def test_forwards_safe_audio_validation_errors(self) -> None:
        for detail in [
            "No filename provided",
            "Invalid file type",
            "File too large",
            "Uploaded file is empty",
            "Uploaded file is not a valid audio file",
        ]:
            with self.subTest(detail=detail):
                self.upstream = httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": detail,
                            "type": "invalid_request_error",
                            "param": None,
                            "code": "invalid_request",
                        }
                    },
                )

                response = self.transcribe()

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": detail})

    def test_sanitizes_unknown_audio_validation_errors(self) -> None:
        self.upstream = httpx.Response(
            400,
            json={
                "error": {
                    "message": "Audio file not found: /private/storage/session.wav",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_request",
                }
            },
        )

        response = self.transcribe()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "The speech service rejected the input."}
        )
        self.assertNotIn("private", response.text)

    def test_bounds_audio_validation_error_responses(self) -> None:
        self.upstream = httpx.Response(
            400,
            content=b"x" * (voice.MAX_ERROR_RESPONSE_BYTES + 1),
        )

        response = self.transcribe()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "The speech service rejected the input."}
        )

    def test_rejects_invalid_text(self) -> None:
        for text in ["", "   ", "a" * 5001]:
            with self.subTest(length=len(text)):
                self.assertEqual(
                    self.client.post(
                        "/voice/speech", json={"input": text, "voice": "Ryan"}
                    ).status_code,
                    422,
                )
        self.assertEqual(self.requests, [])

    def test_rejects_conversation_fields(self) -> None:
        self.assertEqual(
            self.client.post(
                "/voice/speech",
                json={"input": "Hello", "voice": "Ryan", "session_id": "previous"},
            ).status_code,
            422,
        )
        self.assertEqual(self.requests, [])

    def test_upstream_errors_are_sanitized(self) -> None:
        for upstream_status, expected_status in [
            (400, 400),
            (422, 400),
            (429, 503),
            (500, 502),
            (302, 502),
        ]:
            with self.subTest(upstream_status=upstream_status):
                self.upstream = httpx.Response(
                    upstream_status, text="private service detail"
                )
                response = self.client.post(
                    "/voice/speech", json={"input": "Hello", "voice": "Ryan"}
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private", response.text)

    def test_unavailable_service(self) -> None:
        for error, expected_status in [
            (httpx.ConnectError, 503),
            (httpx.ReadTimeout, 504),
        ]:
            with self.subTest(error=error):
                self.failure = error
                response = self.client.post(
                    "/voice/speech", json={"input": "Hello", "voice": "Ryan"}
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private", response.text)

    def test_rejects_invalid_upstream_payload(self) -> None:
        self.upstream = httpx.Response(200, json={"text": 123})
        responses = [
            self.transcribe(),
            self.client.post("/voice/speech", json={"input": "Hello", "voice": "Ryan"}),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("x-voice-service-duration-ms", response.headers)

    def test_rejects_oversized_upstream_response(self) -> None:
        self.upstream = httpx.Response(200, content=b"x" * (128 * 1024 + 1))
        self.assertEqual(self.transcribe().status_code, 502)

    def test_lists_audio_pipeline_catalog(self) -> None:
        catalog = SimpleNamespace(
            list_pipelines=lambda: [
                SimpleNamespace(
                    id="speech-to-text",
                    name="Speech to Text",
                    description="Transcribe managed audio.",
                    type="audio",
                    operation="speech_to_text",
                    tags=["Audio"],
                    thumbnail="data:image/png;base64,audio",
                    required_models=["Whisper Base"],
                    variants=[
                        SimpleNamespace(id="cpu", name="CPU", device="CPU"),
                        SimpleNamespace(id="gpu", name="GPU", device="GPU"),
                        SimpleNamespace(id="npu", name="NPU", device="NPU"),
                    ],
                    defaults=SimpleNamespace(
                        audio="sample_male.wav",
                        language="en",
                        text=None,
                        voice=None,
                    ),
                )
            ]
        )
        with patch.object(
            voice,
            "get_audio_pipeline_manager",
            return_value=catalog,
            create=True,
        ):
            response = self.client.get("/voice/pipelines")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], ["speech-to-text"])
        self.assertEqual(response.json()[0]["type"], "audio")
        self.assertNotIn("available", response.json()[0])
        self.assertEqual(response.json()[0]["thumbnail"], "data:image/png;base64,audio")
        self.assertEqual(response.json()[0]["required_models"], ["Whisper Base"])
        self.assertEqual(
            response.json()[0]["variants"],
            [
                {"id": "cpu", "name": "CPU", "device": "CPU"},
                {"id": "gpu", "name": "GPU", "device": "GPU"},
                {"id": "npu", "name": "NPU", "device": "NPU"},
            ],
        )
        self.assertEqual(response.json()[0]["defaults"]["language"], "en")

    def test_lists_empty_audio_pipeline_catalog(self) -> None:
        catalog = SimpleNamespace(list_pipelines=lambda: [])
        with patch.object(
            voice,
            "get_audio_pipeline_manager",
            return_value=catalog,
            create=True,
        ):
            response = self.client.get("/voice/pipelines")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_starts_and_reads_audio_pipeline_job(self) -> None:
        now = datetime.now(timezone.utc)
        job = SimpleNamespace(
            id="job-1",
            pipeline_id="speech-to-text",
            pipeline_name="Speech to Text",
            variant_id="cpu",
            variant_name="CPU",
            device="CPU",
            operation="speech_to_text",
            status=AudioPipelineJobStatus.QUEUED,
            created_at=now,
            modified_at=now,
            transcript=None,
            artifact_path=None,
            artifact_filename=None,
            service_round_trip_ms=None,
            error=None,
        )
        jobs = SimpleNamespace(
            start_job=AsyncMock(return_value=job),
            get_job=AsyncMock(
                side_effect=lambda job_id: job if job_id == "job-1" else None
            ),
        )
        self.use_audio_jobs(jobs)
        started = self.client.post("/voice/pipelines/speech-to-text/runs")
        status = self.client.get("/voice/jobs/job-1")

        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.json(), {"job_id": "job-1", "status": "QUEUED"})
        jobs.start_job.assert_awaited_once_with("speech-to-text", None)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["pipeline_id"], "speech-to-text")
        self.assertEqual(status.json()["variant_id"], "cpu")

    def test_starts_audio_pipeline_variant_job(self) -> None:
        job = SimpleNamespace(id="job-1", status=AudioPipelineJobStatus.QUEUED)
        jobs = SimpleNamespace(start_job=AsyncMock(return_value=job))
        self.use_audio_jobs(jobs)
        response = self.client.post("/voice/pipelines/speech-to-text/variants/gpu/runs")

        self.assertEqual(response.status_code, 202)
        jobs.start_job.assert_awaited_once_with("speech-to-text", "gpu")

    def test_starts_custom_tts_pipeline_job(self) -> None:
        job = SimpleNamespace(id="job-1", status=AudioPipelineJobStatus.QUEUED)
        jobs = SimpleNamespace(start_job=AsyncMock(return_value=job))
        self.use_audio_jobs(jobs)
        response = self.client.post(
            "/voice/pipelines/text-to-speech/variants/gpu/runs",
            json={"input": "Custom sentence", "voice": "Angus"},
        )

        self.assertEqual(response.status_code, 202)
        jobs.start_job.assert_awaited_once_with(
            "text-to-speech",
            "gpu",
            input_text="Custom sentence",
            voice="Angus",
        )

    def test_starts_managed_stt_upload_on_existing_variant_run(self) -> None:
        job = SimpleNamespace(id="job-1", status=AudioPipelineJobStatus.QUEUED)
        observed: dict[str, object] = {}

        async def start_job(pipeline_id, variant_id, *, stt_input):
            observed["pipeline"] = (pipeline_id, variant_id)
            observed["content"] = stt_input.file.read()
            observed["metadata"] = (
                stt_input.filename,
                stt_input.content_type,
                stt_input.language,
            )
            return job

        jobs = SimpleNamespace(start_job=AsyncMock(side_effect=start_job))
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/speech-to-text/variants/npu/runs",
            data={"language": "pl"},
            files={
                "file": (
                    "../folder\\sample.mp3",
                    b"uploaded audio",
                    "audio/mpeg",
                )
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": "job-1", "status": "QUEUED"})
        self.assertEqual(observed["pipeline"], ("speech-to-text", "npu"))
        self.assertEqual(observed["content"], b"uploaded audio")
        self.assertEqual(
            observed["metadata"],
            ("sample.mp3", "audio/mpeg", "pl"),
        )

    def test_normalizes_managed_stt_upload_media_type(self) -> None:
        job = SimpleNamespace(id="job-1", status=AudioPipelineJobStatus.QUEUED)
        observed: dict[str, object] = {}

        async def start_job(_pipeline_id, _variant_id, *, stt_input):
            observed["content_type"] = stt_input.content_type
            return job

        jobs = SimpleNamespace(start_job=AsyncMock(side_effect=start_job))
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            data={"language": "en"},
            files={
                "file": (
                    "sample.wav",
                    b"audio",
                    "not-a-media-type",
                )
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(observed["content_type"], "application/octet-stream")

    def test_rejects_invalid_managed_stt_multipart(self) -> None:
        jobs = SimpleNamespace(start_job=AsyncMock())
        self.use_audio_jobs(jobs)

        missing_file = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            data={"language": "en"},
            files={
                "ignored": (
                    "ignored.bin",
                    b"ignored",
                    "application/octet-stream",
                )
            },
        )
        invalid_language = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            data={"language": "english"},
            files={"file": ("sample.wav", b"audio", "audio/wav")},
        )

        self.assertEqual(missing_file.status_code, 422)
        self.assertEqual(invalid_language.status_code, 422)
        jobs.start_job.assert_not_called()

    def test_rejects_unsupported_managed_run_content_type(self) -> None:
        jobs = SimpleNamespace(start_job=AsyncMock())
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            content=b"audio",
            headers={"Content-Type": "audio/wav"},
        )

        self.assertEqual(response.status_code, 415)
        jobs.start_job.assert_not_called()

    def test_rejects_stt_upload_for_tts_pipeline(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError(
                    "Text-to-speech pipelines do not accept STT input."
                )
            )
        )
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/text-to-speech/runs",
            data={"language": "en"},
            files={"file": ("sample.wav", b"audio", "audio/wav")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "This Audio pipeline does not accept STT input."},
        )

    def test_rejects_invalid_custom_tts_pipeline_input(self) -> None:
        jobs = SimpleNamespace(start_job=AsyncMock())
        invalid_payloads = [
            {"input": "", "voice": "Ryan"},
            {"input": "x" * 201, "voice": "Ryan"},
            {"input": "Custom sentence", "voice": "Unknown"},
            {"input": "Custom sentence", "voice": "Ryan", "extra": True},
        ]
        self.use_audio_jobs(jobs)
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/voice/pipelines/text-to-speech/runs",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        jobs.start_job.assert_not_called()

    def test_rejects_tts_input_for_stt_pipeline(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError(
                    "Speech-to-text pipelines do not accept TTS overrides."
                )
            )
        )
        self.use_audio_jobs(jobs)
        response = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            json={"input": "Custom sentence", "voice": "Ryan"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "This Audio pipeline does not accept TTS input."},
        )

    def test_rejects_unknown_audio_pipeline_variant_run(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError(
                    "Audio pipeline 'speech-to-text' variant 'missing' not found."
                )
            )
        )
        self.use_audio_jobs(jobs)
        response = self.client.post(
            "/voice/pipelines/speech-to-text/variants/missing/runs"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Audio pipeline variant not found."}
        )

    def test_rejects_unknown_audio_pipeline_run(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError("Audio pipeline 'missing' not found.")
            )
        )
        self.use_audio_jobs(jobs)
        response = self.client.post("/voice/pipelines/missing/runs")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Audio pipeline not found."})

    def test_lists_audio_recordings(self) -> None:
        assets = SimpleNamespace(
            list_assets=MagicMock(
                return_value=[
                    SimpleNamespace(
                        filename="sample_male.wav",
                        path="/audio/sample_male.wav",
                        duration_seconds=33.5,
                    ),
                    SimpleNamespace(
                        filename="vippet info.wav",
                        path="/audio/vippet info.wav",
                        duration_seconds=15.0,
                    ),
                ]
            )
        )
        with patch.object(voice, "AudioAssetsManager", return_value=assets):
            response = self.client.get("/voice/recordings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "filename": "sample_male.wav",
                    "duration_seconds": 33.5,
                    "audio_url": "/api/v1/voice/recordings/sample_male.wav/audio",
                },
                {
                    "filename": "vippet info.wav",
                    "duration_seconds": 15.0,
                    "audio_url": "/api/v1/voice/recordings/vippet%20info.wav/audio",
                },
            ],
        )
        assets.list_assets.assert_called_once_with()

    def test_lists_empty_audio_recordings(self) -> None:
        assets = SimpleNamespace(list_assets=MagicMock(return_value=[]))
        with patch.object(voice, "AudioAssetsManager", return_value=assets):
            response = self.client.get("/voice/recordings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        assets.list_assets.assert_called_once_with()

    def test_serves_registered_recording_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            path.write_bytes(wav_bytes())
            assets = SimpleNamespace(
                get_asset=MagicMock(
                    return_value=SimpleNamespace(
                        filename="sample.wav", path=str(path), duration_seconds=0.1
                    )
                )
            )
            with patch.object(voice, "AudioAssetsManager", return_value=assets):
                response = self.client.get("/voice/recordings/sample.wav/audio")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, wav_bytes())
        assets.get_asset.assert_called_once_with("sample.wav")

    def test_rejects_unregistered_recording_audio(self) -> None:
        assets = SimpleNamespace(get_asset=MagicMock(return_value=None))
        with patch.object(voice, "AudioAssetsManager", return_value=assets):
            response = self.client.get("/voice/recordings/missing.wav/audio")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Audio recording not found."})
        assets.get_asset.assert_called_once_with("missing.wav")

    def test_starts_stt_job_with_registered_recording(self) -> None:
        job = SimpleNamespace(id="job-1", status=AudioPipelineJobStatus.QUEUED)
        jobs = SimpleNamespace(start_job=AsyncMock(return_value=job))
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/speech-to-text/variants/npu/runs",
            json={"recording": "sample.wav", "language": "pl"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": "job-1", "status": "QUEUED"})
        jobs.start_job.assert_awaited_once_with(
            "speech-to-text",
            "npu",
            recording_input=AudioPipelineRecordingInput(
                filename="sample.wav", language="pl"
            ),
        )

    def test_rejects_invalid_recording_run_request(self) -> None:
        jobs = SimpleNamespace(start_job=AsyncMock())
        self.use_audio_jobs(jobs)
        invalid_payloads = [
            {"recording": "", "language": "en"},
            {"recording": "sample.wav", "language": "english"},
            {"recording": "sample.wav"},
            {"language": "en"},
            {"recording": "sample.wav", "language": "en", "extra": True},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/voice/pipelines/speech-to-text/runs", json=payload
                )
                self.assertEqual(response.status_code, 422)

        jobs.start_job.assert_not_called()

    def test_rejects_unknown_recording_run(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError("Audio recording 'missing.wav' not found.")
            )
        )
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/speech-to-text/runs",
            json={"recording": "missing.wav", "language": "en"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Audio recording not found."})

    def test_rejects_recording_for_tts_pipeline(self) -> None:
        jobs = SimpleNamespace(
            start_job=AsyncMock(
                side_effect=ValueError(
                    "Text-to-speech pipelines do not accept recording input."
                )
            )
        )
        self.use_audio_jobs(jobs)

        response = self.client.post(
            "/voice/pipelines/text-to-speech/runs",
            json={"recording": "sample.wav", "language": "en"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "This Audio pipeline does not accept recording input."},
        )

    def test_downloads_completed_tts_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "job-1.wav"
            artifact.write_bytes(wav_bytes())
            job = SimpleNamespace(
                status="COMPLETED",
                artifact_path=str(artifact),
                artifact_filename="job-1.wav",
            )
            jobs = SimpleNamespace(get_job=AsyncMock(return_value=job))
            self.use_audio_jobs(jobs)
            response = self.client.get("/voice/jobs/job-1/artifact")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, wav_bytes())
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("speech.wav", response.headers["content-disposition"])


class ConcurrentVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_timing_includes_body_and_is_isolated_between_requests(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class TranscriptionStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                yield b'{"text":'
                await release.wait()
                yield b'"Hello world"}'

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("transcriptions"):
                return httpx.Response(200, stream=TranscriptionStream())
            return httpx.Response(
                200, content=wav_bytes(), headers={"content-type": "audio/wav"}
            )

        app = FastAPI()
        app.include_router(voice.router, prefix="/voice")
        with (
            patch.object(voice, "perf_counter", side_effect=[10, 20, 20.25, 21]),
            patch.object(
                voice,
                "create_client",
                lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
            ),
        ):
            async with (
                asyncio.timeout(5),
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client,
            ):
                pending = asyncio.create_task(
                    client.post(
                        "/voice/transcriptions",
                        files={"file": ("sentence.wav", wav_bytes(), "audio/wav")},
                    )
                )
                try:
                    await started.wait()
                    speech = await client.post(
                        "/voice/speech", json={"input": "Hello", "voice": "Ryan"}
                    )
                finally:
                    release.set()
                    transcription = await pending
        self.assertEqual(speech.status_code, 200)
        self.assertEqual(transcription.status_code, 200)
        self.assertEqual(speech.headers["x-voice-service-duration-ms"], "250.000")
        self.assertEqual(
            transcription.headers["x-voice-service-duration-ms"], "11000.000"
        )
        self.assertEqual(transcription.json(), {"text": "Hello world"})


class VoiceMetricPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_batch_payload(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(202, json={"accepted": 1})

        client_type = httpx.AsyncClient
        with patch.object(
            voice.httpx,
            "AsyncClient",
            lambda **_kwargs: client_type(transport=httpx.MockTransport(respond)),
        ):
            await voice.publish_voice_metric(
                "voice_asr",
                250.0,
                {"device": "GPU", "language": "en"},
            )

        self.assertEqual(len(requests), 1)
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "metrics": [
                    {
                        "name": "voice_asr",
                        "fields": {"service_round_trip_ms": 250.0},
                        "tags": {"device": "GPU", "language": "en"},
                    }
                ]
            },
        )

    async def test_metrics_manager_failure_is_non_fatal(self) -> None:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unavailable", request=request)

        client_type = httpx.AsyncClient
        with patch.object(
            voice.httpx,
            "AsyncClient",
            lambda **_kwargs: client_type(transport=httpx.MockTransport(fail)),
        ):
            await voice.publish_voice_metric(
                "voice_tts",
                750.0,
                {"device": "service-default", "voice": "Ryan"},
            )
