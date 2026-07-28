# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from utils.config_loader import config


class VssModelsEndpointTests(unittest.TestCase):
    def test_get_models_returns_configured_model(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.get("/models")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["default_model"], config.models.asr.name)
        self.assertEqual(len(body["models"]), 1)
        self.assertEqual(body["models"][0]["model_id"], config.models.asr.name)


class VssTranscriptionEndpointTests(unittest.TestCase):
    def test_rejects_when_no_source_provided(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post("/transcriptions", data={})

        self.assertEqual(response.status_code, 400)

    def test_rejects_when_both_file_and_minio_provided(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                response = client.post(
                    "/transcriptions",
                    data={"minio_bucket": "b", "video_id": "v1", "video_name": "clip.mp4"},
                    files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                )

        self.assertEqual(response.status_code, 400)

    def test_file_upload_transcription_succeeds(self):
        fake_result = {"task": "transcribe", "language": "en", "duration": 12.3, "text": "hello world", "segments": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            saved_path = os.path.join(tmpdir, "clip.wav")
            with open(saved_path, "wb") as handle:
                handle.write(b"fake-audio")

            with patch("main.ensure_model"), patch("main.preload_models"), \
                 patch("api.custom_endpoints.save_audio_file", return_value=("clip.wav", saved_path)), \
                 patch("api.custom_endpoints.Pipeline") as mock_pipeline_cls:
                mock_pipeline_cls.return_value.transcribe.return_value = fake_result

                with TestClient(main.app) as client:
                    response = client.post(
                        "/transcriptions",
                        data={"include_timestamps": "true"},
                        files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                    )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["video_name"], "clip.wav")
        self.assertEqual(body["video_duration"], 12.3)
        self.assertIsNotNone(body["job_id"])
        self.assertIsNotNone(body["transcript_path"])

    def test_minio_source_not_configured_returns_503(self):
        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.custom_endpoints.MinioHandler.is_configured", return_value=False):
            with TestClient(main.app) as client:
                response = client.post(
                    "/transcriptions",
                    data={"minio_bucket": "b", "video_id": "v1", "video_name": "clip.mp4"},
                )

        self.assertEqual(response.status_code, 503)

    def test_minio_source_transcription_uploads_transcript(self):
        fake_result = {"task": "transcribe", "language": "en", "duration": 45.0, "text": "hi", "segments": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            downloaded_path = os.path.join(tmpdir, "clip.mp4")
            with open(downloaded_path, "wb") as handle:
                handle.write(b"fake-video")

            with patch("main.ensure_model"), patch("main.preload_models"), \
                 patch("api.custom_endpoints.MinioHandler.is_configured", return_value=True), \
                 patch("api.custom_endpoints.MinioHandler.get_video_from_minio",
                       new=AsyncMock(return_value=(downloaded_path, None))), \
                 patch("api.custom_endpoints.MinioHandler.save_transcript_to_minio",
                       return_value=(True, None)) as mock_upload, \
                 patch("api.custom_endpoints.Pipeline") as mock_pipeline_cls:
                mock_pipeline_cls.return_value.transcribe.return_value = fake_result

                with TestClient(main.app) as client:
                    response = client.post(
                        "/transcriptions",
                        data={"minio_bucket": "my-bucket", "video_id": "vid-1", "video_name": "clip.mp4"},
                    )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["transcript_path"], "minio://my-bucket/vid-1/clip.txt")
        self.assertEqual(body["video_duration"], 45.0)
        mock_upload.assert_called_once()

    def test_minio_source_not_found_returns_404(self):
        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.custom_endpoints.MinioHandler.is_configured", return_value=True), \
             patch("api.custom_endpoints.MinioHandler.get_video_from_minio",
                   new=AsyncMock(return_value=(None, "bucket not found"))):
            with TestClient(main.app) as client:
                response = client.post(
                    "/transcriptions",
                    data={"minio_bucket": "missing-bucket", "video_id": "vid-1", "video_name": "clip.mp4"},
                )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
