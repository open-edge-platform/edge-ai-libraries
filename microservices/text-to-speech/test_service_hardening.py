import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ServiceHardeningTests(unittest.TestCase):
    def setUp(self):
        self._cors_env = os.environ.get("TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS")
        os.environ["TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS"] = "http://127.0.0.1,http://localhost"

    def tearDown(self):
        if self._cors_env is None:
            os.environ.pop("TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS", None)
        else:
            os.environ["TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS"] = self._cors_env

    @staticmethod
    def _warmup_result():
        return {
            "audio": [0.0],
            "sampling_rate": 16000,
            "model": "test-model",
            "variant": "default",
            "speaker": "default",
            "language": "English",
            "instructions": None,
            "duration": 0.0,
        }

    def test_lifespan_warmup_uses_pipeline_without_persisting_output(self):
        async def _run_lifespan():
            with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as mock_pipeline:
                mock_pipeline.return_value.synthesize.return_value = self._warmup_result()
                async with main.lifespan(main.app):
                    pass

                mock_pipeline.assert_called_once_with(session_id="startup-warmup")
                mock_pipeline.return_value.synthesize.assert_called_once_with(
                    text="warmup",
                    speaker=main.config.models.tts.default_speaker,
                    language=main.config.models.tts.default_language,
                    persist_output=False,
                )

        asyncio.run(_run_lifespan())

    def test_generate_speech_returns_400_for_value_error(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            mock_pipeline.return_value.synthesize.side_effect = ValueError("bad voice")
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={"model": "qwen-tts", "input": "hello", "response_format": "wav"},
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "bad voice")

    def test_generate_speech_returns_503_for_runtime_error(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            mock_pipeline.return_value.synthesize.side_effect = RuntimeError("boom")
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={"model": "qwen-tts", "input": "hello", "response_format": "wav"},
                )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Speech synthesis is temporarily unavailable")

    def test_generate_speech_returns_500_for_unexpected_error(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            mock_pipeline.return_value.synthesize.side_effect = Exception("boom")
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={"model": "qwen-tts", "input": "hello", "response_format": "wav"},
                )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Speech synthesis failed")

    def test_generate_speech_rejects_oversized_input(self):
        oversized_text = "a" * 5001
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={"model": "qwen-tts", "input": oversized_text, "response_format": "wav"},
                )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()