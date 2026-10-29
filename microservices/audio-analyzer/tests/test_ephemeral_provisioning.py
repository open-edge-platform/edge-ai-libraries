# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from utils import ensure_model, provision_models
from utils.local_models import FUNASR_MODEL_MAP, FUNASR_MODEL_REVISIONS, FUNASR_VAD_MODEL


def configuration(provider="openvino", name="whisper-base", diarization=False):
    return SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(provider=provider, name=name, diarization=diarization, weight_format=None),
            diarization=SimpleNamespace(provider="huggingface", name="pyannote/pipeline"),
        ),
    )


class ProvisioningPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_openvino_downloads_source_only(self):
        fetch = AsyncMock()
        with patch.object(provision_models, "config", configuration()):
            await provision_models.provision_models(fetch)
        fetch.assert_awaited_once_with(
            "openai/whisper-base", download_path="whisper-source", required_files=["config.json"],
        )

    async def test_openai_does_not_request_shared_downloads(self):
        fetch = AsyncMock()
        with patch.object(provision_models, "config", configuration("openai")):
            await provision_models.provision_models(fetch)
        fetch.assert_not_awaited()

    async def test_whispercpp_selects_configured_quantization(self):
        cfg = configuration("whispercpp")
        cfg.models.asr.weight_format = "q5"
        fetch = AsyncMock()
        with patch.object(provision_models, "config", cfg):
            await provision_models.provision_models(fetch)
        fetch.assert_awaited_once_with(
            "ggerganov/whisper.cpp", download_path="whisper-source",
            files=["ggml-base-q5_1.bin"], required_files=["ggml-base-q5_1.bin"],
        )

    async def test_funasr_uses_pinned_models_and_custom_companions(self):
        cfg = configuration("funasr", "paraformer-en")
        cfg.models.asr.punc_model = "custom/punctuation"
        fetch = AsyncMock()
        with patch.object(provision_models, "config", cfg):
            await provision_models.provision_models(fetch)
        self.assertEqual(fetch.await_count, 3)
        self.assertEqual(fetch.await_args_list[0].args, (
            FUNASR_MODEL_MAP["paraformer-en"], "v2.0.4",
        ))
        self.assertEqual(fetch.await_args_list[1].args, (
            FUNASR_VAD_MODEL, FUNASR_MODEL_REVISIONS[FUNASR_VAD_MODEL],
        ))
        self.assertEqual(fetch.await_args_list[2].args, ("custom/punctuation", None))
        for call in fetch.await_args_list:
            self.assertEqual(call.kwargs, {
                "hub": "modelscope", "download_path": "funasr",
                "required_files": ["config.yaml", "model.pt"],
            })

    async def test_diarization_discovers_standalone_dependencies(self):
        with tempfile.TemporaryDirectory() as base:
            (Path(base) / "config.yaml").write_text(yaml.safe_dump({
                "pipeline": {"params": {"segmentation": "pyannote/segmentation", "embedding": "pyannote/embedding"}},
            }))
            fetch = AsyncMock(return_value=base)
            with patch.object(provision_models, "config", configuration("openai", diarization=True)), \
                 patch.object(provision_models, "_resolve_hf_token", return_value=None):
                await provision_models.provision_models(fetch)
            self.assertEqual([call.args[0] for call in fetch.await_args_list], [
                "pyannote/pipeline", "pyannote/segmentation", "pyannote/embedding",
            ])

    async def test_bundled_diarization_dependencies_are_checked(self):
        with tempfile.TemporaryDirectory() as base:
            (Path(base) / "config.yaml").write_text(yaml.safe_dump({
                "pipeline": {"params": {"segmentation": "$model/segmentation"}},
            }))
            fetch = AsyncMock(return_value=base)
            with patch.object(provision_models, "config", configuration("openai", diarization=True)), \
                 patch.object(provision_models, "_resolve_hf_token", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "dependency is missing"):
                    await provision_models.provision_models(fetch)
                (Path(base) / "segmentation").mkdir()
                with self.assertRaisesRegex(RuntimeError, "dependency is missing"):
                    await provision_models.provision_models(fetch)
                (Path(base) / "segmentation/pytorch_model.bin").write_bytes(b"weights")
                await provision_models.provision_models(fetch)

    async def test_failed_download_aborts_provisioning(self):
        fetch = AsyncMock(side_effect=RuntimeError("download failed"))
        with patch.object(provision_models, "config", configuration("funasr", "paraformer-zh")):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                await provision_models.provision_models(fetch)
        self.assertEqual(fetch.await_count, 1)

    async def test_unknown_provider_fails_visibly(self):
        with patch.object(provision_models, "config", configuration("unknown")):
            with self.assertRaisesRegex(ValueError, "Unsupported ASR provider"):
                await provision_models.provision_models(AsyncMock())


class DiarizationLocalConfigTests(unittest.TestCase):
    def test_local_config_preserves_snapshot_and_resolves_bundled_models(self):
        with tempfile.TemporaryDirectory() as base:
            directory = Path(base)
            bundled = directory / "segmentation"
            bundled.mkdir()
            weights = bundled / "pytorch_model.bin"
            weights.write_bytes(b"weights")
            original = yaml.safe_dump({"pipeline": {"params": {"segmentation": "$model/segmentation"}}})
            (directory / "config.yaml").write_text(original)
            ensure_model._cache_diarization_dependencies_locally(base)
            self.assertEqual((directory / "config.yaml").read_text(), original)
            local = yaml.safe_load((directory / "config.local.yaml").read_text())
            self.assertEqual(local["pipeline"]["params"]["segmentation"], str(weights))


class EphemeralDeploymentTests(unittest.TestCase):
    def test_compose_waits_for_successful_exit_and_retains_models(self):
        compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text())
        app = compose["services"]["audio-analyzer"]
        job = compose["services"]["model-downloader"]
        self.assertEqual(app["depends_on"]["model-downloader"]["condition"], "service_completed_successfully")
        self.assertEqual(job["restart"], "no")
        self.assertTrue(job["healthcheck"]["disable"])
        self.assertIn("--ephemeral", job["command"])
        self.assertEqual(job["command"][1], "huggingface,modelscope")
        self.assertEqual(job["environment"]["ENABLED_PLUGINS"], "huggingface,modelscope")
        self.assertNotIn("AUDIO_ANALYZER_MODEL_DOWNLOAD_URL", app["environment"])
        self.assertIn("audio_analyzer_models:/opt/models", job["volumes"])
        self.assertIn("audio_analyzer_models:/app/audio_analyzer/models", app["volumes"])
        self.assertNotIn("ports", job)

    def test_downloader_normalizes_proxy_variable_case(self):
        compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text())
        environment = compose["services"]["model-downloader"]["environment"]
        for lower, upper in (
            ("http_proxy", "HTTP_PROXY"),
            ("https_proxy", "HTTPS_PROXY"),
            ("no_proxy", "NO_PROXY"),
        ):
            with self.subTest(variable=lower):
                expected = "${" + lower + ":-${" + upper + ":-}}"
                self.assertEqual(environment[lower], expected)
                self.assertEqual(environment[upper], expected)

if __name__ == "__main__":
    unittest.main()
