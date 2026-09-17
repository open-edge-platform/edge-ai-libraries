# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import unittest
import wave
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import voice


def wav_bytes(seconds: int = 1, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 16000 * seconds * channels)
    return buffer.getvalue()


class VoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(voice.router, prefix="/voice")
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

    def transcribe(self, content: bytes | None = None) -> httpx.Response:
        return self.client.post(
            "/voice/transcriptions",
            files={
                "file": (
                    "sentence.wav",
                    wav_bytes() if content is None else content,
                    "audio/wav",
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

    def test_rejects_invalid_audio(self) -> None:
        for content in [
            b"",
            b"not audio",
            wav_bytes(61),
            wav_bytes(channels=2),
            wav_bytes()[:-50],
        ]:
            with self.subTest(size=len(content)):
                self.assertEqual(self.transcribe(content).status_code, 400)
        self.assertEqual(self.requests, [])

    def test_rejects_oversized_upload(self) -> None:
        with patch.object(voice, "MAX_UPLOAD_BYTES", 128):
            self.assertEqual(self.transcribe().status_code, 413)
        self.assertEqual(self.requests, [])

    def test_speech_returns_wav(self) -> None:
        response = self.client.post("/voice/speech", json={"input": "Hello world"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, wav_bytes())
        self.assertEqual(
            self.requests[0].content, b'{"input":"Hello world","response_format":"wav"}'
        )

    def test_rejects_invalid_text(self) -> None:
        for text in ["", "   ", "a" * 5001]:
            with self.subTest(length=len(text)):
                self.assertEqual(
                    self.client.post("/voice/speech", json={"input": text}).status_code,
                    422,
                )
        self.assertEqual(self.requests, [])

    def test_rejects_conversation_fields(self) -> None:
        self.assertEqual(
            self.client.post(
                "/voice/speech", json={"input": "Hello", "session_id": "previous"}
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
                response = self.client.post("/voice/speech", json={"input": "Hello"})
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private", response.text)

    def test_unavailable_service(self) -> None:
        for error, expected_status in [
            (httpx.ConnectError, 503),
            (httpx.ReadTimeout, 504),
        ]:
            with self.subTest(error=error):
                self.failure = error
                response = self.client.post("/voice/speech", json={"input": "Hello"})
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("private", response.text)

    def test_rejects_invalid_upstream_payload(self) -> None:
        self.upstream = httpx.Response(200, json={"text": 123})
        self.assertEqual(self.transcribe().status_code, 502)
        self.assertEqual(
            self.client.post("/voice/speech", json={"input": "Hello"}).status_code, 502
        )

    def test_rejects_oversized_upstream_response(self) -> None:
        self.upstream = httpx.Response(200, content=b"x" * (128 * 1024 + 1))
        self.assertEqual(self.transcribe().status_code, 502)
