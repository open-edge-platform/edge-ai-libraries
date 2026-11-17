# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import main
from api.middleware import InitializationMiddleware
from api.routes import health
from audio_assets import AudioAssetsManager
from internal_types import InternalAppStatus
from managers import audio_pipeline_manager
from managers.app_state_manager import AppStateManager
from managers.pipeline_manager import PipelineManager


class VoiceInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.pipeline_dir = root / "pipelines"
        self.pipeline_dir.mkdir()
        self.audio_path = self.pipeline_dir / "speech-to-text.yaml"
        self.audio_path.write_text(
            yaml.safe_dump(
                {
                    "name": "Speech to Text",
                    "type": "audio",
                    "operation": "speech_to_text",
                    "required_models": ["Whisper Base"],
                    "variants": [{"name": "CPU", "device": "CPU"}],
                    "defaults": {"audio": "sample.wav", "language": "en"},
                }
            ),
            encoding="utf-8",
        )
        for pipeline_type in ("vision", "time_series"):
            (self.pipeline_dir / f"{pipeline_type}.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": pipeline_type,
                        "type": pipeline_type,
                        "variants": [
                            {
                                "name": "CPU",
                                "pipeline_description": "videotestsrc ! fakesink",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        manifest = root / "recordings.yaml"
        manifest.write_text("[]", encoding="utf-8")
        for target in (
            "get_cpu_topology",
            "_release_pipeline_execution",
            "VideosManager",
            "ImagesManager",
            "PipelineTemplateManager",
            "ModelManager",
        ):
            self.enterContext(patch.object(main, target))
        self.enterContext(patch.object(AppStateManager, "_instance", None))
        self.enterContext(patch.object(PipelineManager, "_instance", None))
        self.enterContext(patch.object(AudioAssetsManager, "_instance", None))
        self.enterContext(
            patch("managers.pipeline_manager.is_variant_supported", return_value=True)
        )
        self.enterContext(
            patch.object(audio_pipeline_manager, "_default_manager", None)
        )
        self.enterContext(patch("audio_assets.AUTO_AUDIO_DIR", str(root / "input")))
        self.enterContext(patch("audio_assets.OUTPUT_AUDIO_DIR", str(root / "output")))
        self.enterContext(
            patch("audio_assets.DEFAULT_AUDIO_RECORDINGS_FILE", str(manifest))
        )
        self.enterContext(
            patch(
                "managers.pipeline_manager.PipelineLoader.list",
                side_effect=lambda: sorted(self.pipeline_dir.glob("*.yaml")),
            )
        )
        self.enterContext(
            patch(
                "managers.pipeline_manager.PipelineLoader.get_pipelines_directory",
                return_value=str(self.pipeline_dir),
            )
        )
        self.enterContext(
            patch.object(
                main,
                "get_audio_pipeline_manager",
                side_effect=lambda: self._load_audio_manager(),
            )
        )
        self.app = FastAPI()
        self.app.add_middleware(InitializationMiddleware)
        self.app.include_router(health.router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def _load_audio_manager(self) -> audio_pipeline_manager.AudioPipelineManager:
        manager = audio_pipeline_manager.AudioPipelineManager(self.pipeline_dir)
        audio_pipeline_manager._default_manager = manager
        return manager

    def assert_backend_ready(self) -> None:
        self.assertEqual(AppStateManager().status, InternalAppStatus.READY)
        self.assertTrue(self.client.get("/health").json()["healthy"])
        self.assertTrue(self.client.get("/status").json()["ready"])
        with patch(
            "api.routes.pipelines._is_timeseries_service_available", return_value=True
        ):
            response = self.client.get("/pipelines")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["name"] for item in response.json()}, {"vision", "time_series"}
        )
        with (
            patch("api.routes.timeseries._read_ingestion_snapshot", return_value=[]),
            patch("api.routes.timeseries._fetch_kapacitor_analytics", return_value=[]),
        ):
            self.assertEqual(self.client.get("/timeseries/data").status_code, 200)

    def assert_voice_unavailable(self) -> None:
        self.assertFalse(self.app.state.voice_available)
        with patch("api.dependencies.audio_jobs._factory") as factory:
            for method, path in (
                ("GET", "/voice/pipelines"),
                ("GET", "/voice/recordings"),
                ("GET", "/voice/recordings/sample.wav/audio"),
                ("POST", "/voice/pipelines/speech-to-text/variants/cpu/runs"),
                ("GET", "/voice/jobs/missing/artifact"),
                ("GET", "/jobs/audio/status"),
                ("GET", "/jobs/audio/missing/status"),
                ("DELETE", "/jobs/audio/missing"),
            ):
                with self.subTest(method=method, path=path):
                    response = self.client.request(method, path)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn("Voice is unavailable", response.json()["detail"])
            factory.assert_not_called()

    def assert_failed_voice_startup(self) -> None:
        with self.assertLogs(level="ERROR") as logs:
            main._initialize_in_background(self.app)
        self.assertIn("Voice initialization failed", "\n".join(logs.output))
        self.assert_backend_ready()
        self.assert_voice_unavailable()

    def test_unknown_type_is_ignored_and_backend_starts(self) -> None:
        (self.pipeline_dir / "unknown.yaml").write_text(
            "type: future_type\nvariants: invalid\n", encoding="utf-8"
        )

        main._initialize_in_background(self.app)

        self.assert_backend_ready()
        self.assertTrue(self.app.state.voice_available)
        response = self.client.get("/voice/pipelines")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], ["speech-to-text"])
        self.assertEqual(self.client.get("/voice/recordings").status_code, 200)

    def test_invalid_audio_definition_disables_only_voice(self) -> None:
        self.audio_path.write_text("type: audio\nname: Broken\n", encoding="utf-8")

        self.assert_failed_voice_startup()

    def test_invalid_yaml_syntax_disables_only_voice(self) -> None:
        self.audio_path.write_text("type: audio\nvariants: [", encoding="utf-8")

        self.assert_failed_voice_startup()

    def test_non_utf8_audio_yaml_disables_only_voice(self) -> None:
        self.audio_path.write_bytes(b"type: audio\nname: Invalid \xff\n")

        self.assert_failed_voice_startup()

    def test_empty_yaml_disables_only_voice(self) -> None:
        self.audio_path.write_text("", encoding="utf-8")

        self.assert_failed_voice_startup()

    def test_unwritable_audio_output_disables_only_voice(self) -> None:
        with patch("audio_assets.tempfile.TemporaryFile", side_effect=PermissionError):
            self.assert_failed_voice_startup()
        self.assertFalse(hasattr(AudioAssetsManager._instance, "_initialized"))

    def test_vision_initialization_failure_remains_fatal(self) -> None:
        with (
            patch.object(
                main, "PipelineManager", side_effect=RuntimeError("vision failure")
            ),
            self.assertLogs(level="ERROR"),
        ):
            main._initialize_in_background(self.app)

        self.assertEqual(AppStateManager().status, InternalAppStatus.SHUTDOWN)
