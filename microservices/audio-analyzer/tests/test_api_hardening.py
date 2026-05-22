import io
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

import main
from utils.audio_util import save_audio_file


class ApiHardeningTests(unittest.TestCase):
    @staticmethod
    def _openai_error(message, error_type, *, param=None, code=None):
        return {
            "error": {
                "message": message,
                "type": error_type,
                "param": param,
                "code": code,
            }
        }

    def test_openai_transcription_rejects_prompt(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/transcriptions",
                    data={
                        "model": "whisper-1",
                        "prompt": "bias this result",
                        "temperature": "0.0",
                        "response_format": "json",
                    },
                    files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "prompt is not currently supported",
                "invalid_request_error",
                code="invalid_request",
            ),
        )

    def test_openai_transcription_rejects_invalid_temperature(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/transcriptions",
                    data={
                        "model": "whisper-1",
                        "temperature": "2.0",
                        "response_format": "json",
                    },
                    files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "temperature must be between 0.0 and 1.0",
                "invalid_request_error",
                code="invalid_request",
            ),
        )

    def test_stream_endpoint_rejects_invalid_temperature(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/transcriptions/stream",
                    data={"temperature": "-0.5"},
                    files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "temperature must be between 0.0 and 1.0",
                "invalid_request_error",
                code="invalid_request",
            ),
        )

    def test_openai_transcription_missing_file_uses_validation_error_envelope(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/transcriptions",
                    data={
                        "model": "whisper-1",
                        "temperature": "0.0",
                        "response_format": "json",
                    },
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")
        self.assertEqual(response.json()["error"]["param"], "file")


class AudioUploadValidationTests(unittest.TestCase):
    class DummyUploadFile:
        def __init__(self, filename: str, content: bytes):
            self.filename = filename
            self.file = io.BytesIO(content)

    def test_save_audio_file_rejects_empty_upload(self):
        upload = self.DummyUploadFile("clip.wav", b"")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("utils.audio_util.get_audio_upload_dir", return_value=temp_dir):
                with self.assertRaises(HTTPException) as exc:
                    save_audio_file(upload)

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "Uploaded file is empty")

    def test_save_audio_file_rejects_non_audio_payload(self):
        upload = self.DummyUploadFile("clip.wav", b"not-really-audio")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("utils.audio_util.get_audio_upload_dir", return_value=temp_dir), patch(
                "utils.audio_util._audio_stream_exists", return_value=False
            ):
                with self.assertRaises(HTTPException) as exc:
                    save_audio_file(upload)

                self.assertEqual(os.listdir(temp_dir), [])

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "Uploaded file is not a valid audio file")


if __name__ == "__main__":
    unittest.main()