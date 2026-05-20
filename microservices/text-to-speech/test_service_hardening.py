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
        self.assertEqual(
            response.json(),
            self._openai_error("bad voice", "invalid_request_error", code="invalid_request"),
        )

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
        self.assertEqual(
            response.json(),
            self._openai_error(
                "Speech synthesis is temporarily unavailable",
                "server_error",
                code="service_unavailable",
            ),
        )

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
        self.assertEqual(
            response.json(),
            self._openai_error("Speech synthesis failed", "server_error", code="internal_error"),
        )

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
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")
        self.assertEqual(response.json()["error"]["param"], "input")

    def test_generate_speech_rejects_whitespace_only_input(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={"model": "microsoft/speecht5_tts", "input": "   ", "response_format": "wav"},
                )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "Value error, Input text is required",
                "invalid_request_error",
                param="input",
                code="invalid_request",
            ),
        )

    def test_generate_speech_rejects_speecht5_instructions_before_synthesis(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={
                        "model": "microsoft/speecht5_tts",
                        "input": "hello",
                        "instructions": "Speak like a pirate",
                        "response_format": "wav",
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "SpeechT5 does not support free-form voice instructions.",
                "invalid_request_error",
                code="invalid_request",
            ),
        )
        mock_pipeline.assert_not_called()

    def test_generate_speech_rejects_speecht5_unsupported_voice_before_synthesis(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={
                        "model": "microsoft/speecht5_tts",
                        "input": "hello",
                        "voice": "NotRyan",
                        "response_format": "wav",
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "SpeechT5 currently supports only the configured voice 'Ryan'.",
                "invalid_request_error",
                code="invalid_request",
            ),
        )
        mock_pipeline.assert_not_called()

    def test_generate_speech_rejects_non_english_language(self):
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            mock_pipeline.return_value.synthesize.side_effect = ValueError("Only English is currently supported for speech synthesis.")
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={
                        "model": "qwen-tts",
                        "input": "hello",
                        "language": "Spanish",
                        "response_format": "wav",
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "Only English is currently supported for speech synthesis.",
                "invalid_request_error",
                code="invalid_request",
            ),
        )

    def test_generate_speech_rejects_qwen_voice_design_voice_before_synthesis(self):
        with patch.object(main.config.models.tts, "name", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"), patch.object(main.config.models.tts, "model_variant", "voice_design"), patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={
                        "model": "qwen-tts",
                        "input": "hello",
                        "voice": "Ryan",
                        "instructions": "Warm and calm",
                        "response_format": "wav",
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "Qwen voice_design does not accept the voice field. Describe the desired voice in instructions instead.",
                "invalid_request_error",
                code="invalid_request",
            ),
        )
        mock_pipeline.assert_not_called()

    def test_generate_speech_rejects_qwen_voice_design_without_instructions(self):
        with patch.object(main.config.models.tts, "name", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"), patch.object(main.config.models.tts, "model_variant", "voice_design"), patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.openai_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            with TestClient(main.app) as client:
                response = client.post(
                    "/v1/audio/speech",
                    json={
                        "model": "qwen-tts",
                        "input": "hello",
                        "response_format": "wav",
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            self._openai_error(
                "Qwen voice_design requires instructions describing the desired voice.",
                "invalid_request_error",
                code="invalid_request",
            ),
        )
        mock_pipeline.assert_not_called()

    def test_list_supported_voices_reports_english_only(self):
        model_info = {
            "model": "test-model",
            "supported_speakers": ["Ryan"],
            "supported_languages": ["English"],
            "default_language": "English",
        }
        with patch("main.ensure_model"), patch("main.preload_models"), patch("main.Pipeline") as warmup_pipeline, patch("api.custom_endpoints.Pipeline") as mock_pipeline:
            warmup_pipeline.return_value.synthesize.return_value = self._warmup_result()
            mock_pipeline.return_value.get_model_info.return_value = model_info
            with TestClient(main.app) as client:
                response = client.get("/v1/audio/voices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["supported_languages"], ["English"])


if __name__ == "__main__":
    unittest.main()