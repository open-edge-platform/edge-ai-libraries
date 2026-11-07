# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from utils import ensure_model, provision_models
from utils.local_models import (
    COMPLETION_FILE,
    FUNASR_MODEL_MAP,
    FUNASR_MODEL_REVISIONS,
    FUNASR_VAD_MODEL,
    get_local_model,
    model_directory,
)


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


class StandaloneDeploymentTests(unittest.TestCase):
    def test_compose_runs_a_single_self_provisioning_container(self):
        compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text())
        self.assertEqual(list(compose["services"]), ["audio-analyzer"])
        app = compose["services"]["audio-analyzer"]
        self.assertNotIn("depends_on", app)
        self.assertNotIn("AUDIO_ANALYZER_MODEL_DOWNLOAD_URL", app["environment"])
        self.assertNotIn("AUDIO_ANALYZER_MODEL_DIRECT_DOWNLOAD", app["environment"])
        self.assertIn("audio_analyzer_models:/app/audio_analyzer/models", app["volumes"])
        self.assertIn("HF_TOKEN", app["environment"])


class DirectDownloadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = tempfile.TemporaryDirectory()
        self.addCleanup(self.base.cleanup)

    async def test_huggingface_download_writes_snapshot_and_inventory(self):
        def fake_snapshot_download(**kwargs):
            Path(kwargs["local_dir"], "config.yaml").write_bytes(b"cfg")
            return kwargs["local_dir"]

        fake_hub = SimpleNamespace(snapshot_download=fake_snapshot_download)
        with patch.dict("sys.modules", {"huggingface_hub": fake_hub}):
            path = await provision_models.fetch_direct(
                "pyannote/example", download_path="diarization", required_files=["config.yaml"],
                files=["config.yaml"], hf_token="hf_x", models_base_path=self.base.name,
            )
        directory = model_directory("pyannote/example", "diarization", self.base.name)
        self.assertEqual(path, str(directory.resolve()))
        self.assertTrue((directory / COMPLETION_FILE).is_file())
        self.assertEqual(get_local_model(
            "pyannote/example", download_path="diarization", required_files=["config.yaml"],
            models_base_path=self.base.name,
        ), str(directory.resolve()))

    async def test_huggingface_download_forwards_revision_token_and_patterns(self):
        calls = []

        def fake_snapshot_download(**kwargs):
            calls.append(kwargs)
            Path(kwargs["local_dir"], "ggml-base.bin").write_bytes(b"w")

        with patch.dict("sys.modules", {"huggingface_hub": SimpleNamespace(snapshot_download=fake_snapshot_download)}):
            await provision_models.fetch_direct(
                "ggerganov/whisper.cpp", "abc", download_path="whisper-source",
                required_files=["ggml-base.bin"], files=["ggml-base.bin"], hf_token="hf_x",
                models_base_path=self.base.name,
            )
        self.assertEqual(calls[0]["repo_id"], "ggerganov/whisper.cpp")
        self.assertEqual(calls[0]["revision"], "abc")
        self.assertEqual(calls[0]["token"], "hf_x")
        self.assertEqual(calls[0]["allow_patterns"], ["ggml-base.bin"])

    async def test_modelscope_download_uses_pinned_revision(self):
        calls = []

        def fake_snapshot_download(model, revision=None, local_dir=None):
            calls.append((model, revision))
            for name in ("config.yaml", "model.pt"):
                Path(local_dir, name).write_bytes(b"w")

        modules = {
            "modelscope": SimpleNamespace(),
            "modelscope.hub": SimpleNamespace(),
            "modelscope.hub.snapshot_download": SimpleNamespace(snapshot_download=fake_snapshot_download),
        }
        with patch.dict("sys.modules", modules):
            await provision_models.fetch_direct(
                "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
            )
        self.assertEqual(calls, [("iic/example", "v2.0.4")])
        directory = model_directory("iic/example", "funasr", self.base.name, hub="modelscope")
        self.assertTrue((directory / COMPLETION_FILE).is_file())

    async def test_missing_modelscope_dependency_is_explained(self):
        with patch.dict("sys.modules", {"modelscope": None, "modelscope.hub": None, "modelscope.hub.snapshot_download": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-cjk.txt"):
                await provision_models.fetch_direct(
                    "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml"], models_base_path=self.base.name,
                )

    async def test_valid_snapshot_skips_download(self):
        directory = model_directory("iic/example", "funasr", self.base.name, hub="modelscope")
        directory.mkdir(parents=True)
        (directory / "config.yaml").write_bytes(b"cfg")
        provision_models.record_snapshot("iic/example", "v2.0.4", directory)
        with patch.object(provision_models, "download_from_hub") as download:
            await provision_models.fetch_direct(
                "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                required_files=["config.yaml"], models_base_path=self.base.name,
            )
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
