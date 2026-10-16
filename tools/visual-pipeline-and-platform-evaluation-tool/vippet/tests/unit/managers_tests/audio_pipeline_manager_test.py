# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from managers.audio_pipeline_manager import (
    AudioPipelineManager,
    AudioPipelineOperation,
)


DEFAULT_TEXT = (
    "Welcome to Intel Performance Studio. This audio pipeline demonstrates clear "
    "text-to-speech synthesis, measures service latency, and produces a WAV file "
    "ready for playback on supported edge hardware."
)


class AudioPipelineManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.pipeline_dir = root / "audio"
        self.pipeline_dir.mkdir()
        images_dir = root / "images"
        images_dir.mkdir()
        (images_dir / "audio.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assets = MagicMock()
        self.assets.get_path.return_value = "/audio/input/auto/sample.wav"

    def write_pipeline(self, filename: str, config: dict) -> None:
        (self.pipeline_dir / filename).write_text(
            yaml.safe_dump(config), encoding="utf-8"
        )

    def stt_config(self) -> dict:
        return {
            "name": "Speech to Text",
            "definition": "Transcribe the managed default recording.",
            "type": "audio",
            "operation": "speech_to_text",
            "tags": ["Audio", "Speech Recognition"],
            "thumbnail": "images/audio.png",
            "required_models": ["Whisper Base"],
            "variants": [
                {"name": "CPU", "device": "CPU"},
                {"name": "GPU", "device": "GPU"},
                {"name": "NPU", "device": "NPU"},
            ],
            "defaults": {"audio": "sample.wav", "language": "en"},
        }

    def tts_config(self) -> dict:
        return {
            "name": "Text to Speech",
            "definition": "Generate WAV audio from the default text.",
            "type": "audio",
            "operation": "text_to_speech",
            "tags": ["Audio", "Speech Synthesis"],
            "thumbnail": "images/audio.png",
            "required_models": ["SpeechT5"],
            "variants": [
                {"name": "CPU", "device": "CPU"},
                {"name": "GPU", "device": "GPU"},
            ],
            "defaults": {"text": DEFAULT_TEXT, "voice": "Ryan"},
        }

    def test_loads_stt_and_tts_definitions(self) -> None:
        self.write_pipeline("speech-to-text.yaml", self.stt_config())
        self.write_pipeline("text-to-speech.yaml", self.tts_config())

        manager = AudioPipelineManager(self.pipeline_dir, self.assets)
        pipelines = manager.list_pipelines()

        self.assertEqual(
            [pipeline.id for pipeline in pipelines],
            ["speech-to-text", "text-to-speech"],
        )
        self.assertEqual(pipelines[0].type, "audio")
        self.assertEqual(pipelines[0].operation, AudioPipelineOperation.SPEECH_TO_TEXT)
        self.assertEqual(pipelines[0].defaults.audio, "sample.wav")
        self.assertEqual(
            [(variant.id, variant.device) for variant in pipelines[0].variants],
            [("cpu", "CPU"), ("gpu", "GPU"), ("npu", "NPU")],
        )
        self.assertEqual(pipelines[0].required_models, ["Whisper Base"])
        self.assertEqual(pipelines[1].defaults.text, DEFAULT_TEXT)
        self.assertEqual(pipelines[1].defaults.voice, "Ryan")
        self.assertEqual(
            [(variant.id, variant.device) for variant in pipelines[1].variants],
            [("cpu", "CPU"), ("gpu", "GPU")],
        )
        self.assertEqual(pipelines[1].required_models, ["SpeechT5"])
        self.assertEqual(
            manager.get_variant("speech-to-text", "npu"),
            pipelines[0].variants[2],
        )
        for pipeline in pipelines:
            assert pipeline.thumbnail is not None
            self.assertTrue(pipeline.thumbnail.startswith("data:image/png;base64,"))
        self.assertTrue(all(pipeline.available for pipeline in pipelines))

    def test_empty_directory_has_no_audio_pipelines(self) -> None:
        manager = AudioPipelineManager(self.pipeline_dir, self.assets)

        self.assertEqual(manager.list_pipelines(), [])

    def test_marks_stt_unavailable_when_default_audio_is_missing(self) -> None:
        self.assets.get_path.return_value = None
        self.write_pipeline("speech-to-text.yaml", self.stt_config())

        pipeline = AudioPipelineManager(self.pipeline_dir, self.assets).get_pipeline(
            "speech-to-text"
        )

        self.assertIsNotNone(pipeline)
        assert pipeline is not None
        self.assertFalse(pipeline.available)
        self.assertEqual(
            pipeline.unavailable_reason,
            "Default audio input is unavailable.",
        )

    def test_rejects_unknown_pipeline_type(self) -> None:
        config = self.stt_config()
        config["type"] = "voice"
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "type must be 'audio'"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_unknown_operation(self) -> None:
        config = self.stt_config()
        config["operation"] = "translate"
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "unsupported operation"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_unsafe_default_audio_filename(self) -> None:
        config = self.stt_config()
        config["defaults"]["audio"] = "../sample.wav"
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "safe WAV filename"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_tts_text_over_service_limit(self) -> None:
        config = self.tts_config()
        config["defaults"]["text"] = "x" * 201
        self.write_pipeline("text-to-speech.yaml", config)

        with self.assertRaisesRegex(ValueError, "between 1 and 200"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_unknown_fields(self) -> None:
        config = self.tts_config()
        config["endpoint"] = "http://untrusted.example"
        self.write_pipeline("text-to-speech.yaml", config)

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_empty_variants(self) -> None:
        config = self.stt_config()
        config["variants"] = []
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "at least one variant"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_duplicate_variant_ids(self) -> None:
        config = self.stt_config()
        config["variants"] = [
            {"name": "GPU", "device": "GPU"},
            {"name": "gpu", "device": "GPU"},
        ]
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "duplicate variant"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_unsupported_tts_variant_device(self) -> None:
        config = self.tts_config()
        config["variants"] = [{"name": "NPU", "device": "NPU"}]
        self.write_pipeline("text-to-speech.yaml", config)

        with self.assertRaisesRegex(ValueError, "unsupported device"):
            AudioPipelineManager(self.pipeline_dir, self.assets)

    def test_rejects_invalid_required_models(self) -> None:
        config = self.stt_config()
        config["required_models"] = ["Whisper Base", ""]
        self.write_pipeline("speech-to-text.yaml", config)

        with self.assertRaisesRegex(ValueError, "required models"):
            AudioPipelineManager(self.pipeline_dir, self.assets)


if __name__ == "__main__":
    unittest.main()
