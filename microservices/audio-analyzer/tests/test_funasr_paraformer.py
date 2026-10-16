# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the optional FunASR Paraformer provider (Chinese/English ASR).

These assert the provider is genuinely opt-in: the module imports cleanly
without ``funasr`` installed, and the instantiation guards raise actionable
errors. This protects existing Whisper/OpenVINO consumers.
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


JOB_ID = "e8f1892a-8c08-401f-a37a-d48957f206c1"


class ModelDownloadClientTests(unittest.TestCase):
    def test_requests_modelscope_and_loads_shared_snapshot(self):
        from utils.model_download_client import get_model_from_service

        with tempfile.TemporaryDirectory() as base:
            model_dir = Path(base) / "funasr" / "modelscope" / "iic_example"
            model_dir.mkdir(parents=True)
            (model_dir / "configuration.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": "http://model-downloader:8000"}), \
                 patch("utils.model_download_client.config.models.asr.models_base_path", base), \
                 patch("utils.model_download_client._request_json", side_effect=[
                     {"job_ids": [JOB_ID]},
                     {"status": "completed", "result": {"source": "modelscope", "model_name": "iic/example"}},
                 ]) as request:
                self.assertEqual(get_model_from_service("iic/example", "v2.0.4"), str(model_dir))
            self.assertIn("download_path=funasr", request.call_args_list[0].args[0])
            self.assertEqual(
                request.call_args_list[0].args[1],
                {"models": [{"name": "iic/example", "hub": "modelscope", "revision": "v2.0.4"}]},
            )

    def test_fails_without_service_or_shared_snapshot(self):
        from utils.model_download_client import get_model_from_service

        with patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "AUDIO_ANALYZER_MODEL_DOWNLOAD_URL"):
                get_model_from_service("iic/example", "v2.0.4")
        with tempfile.TemporaryDirectory() as base, \
             patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": "http://model-downloader:8000"}), \
             patch("utils.model_download_client.config.models.asr.models_base_path", base), \
             patch("utils.model_download_client._request_json", side_effect=[
                 {"job_ids": [JOB_ID]},
                 {"status": "completed", "result": {"source": "modelscope", "model_name": "iic/example"}},
             ]):
            with self.assertRaisesRegex(RuntimeError, "shared models volume"):
                get_model_from_service("iic/example", "v2.0.4")

    def test_rejects_bad_model_id_and_failed_job(self):
        from utils.model_download_client import get_model_from_service

        with self.assertRaises(ValueError):
            get_model_from_service("../escape", "v2.0.4")
        with patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": "http://model-downloader:8000"}), \
             patch("utils.model_download_client._request_json", side_effect=[
                 {"job_ids": [JOB_ID]}, {"status": "failed", "error": "not found"}
             ]):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                get_model_from_service("iic/example", "v2.0.4")


class ParaformerProviderTests(unittest.TestCase):
    def test_module_imports_without_funasr(self):
        # The whole point of the lazy import: this must not require funasr.
        import components.asr.funasr.paraformer as pf

        self.assertEqual(
            set(pf.FUNASR_MODEL_MAP),
            {"paraformer-zh", "paraformer-en", "paraformer-online"},
        )
        self.assertEqual(pf._MODEL_LANGUAGE["paraformer-zh"], "zh")
        self.assertEqual(pf._MODEL_LANGUAGE["paraformer-en"], "en")

    def test_uses_model_download_service_for_all_three_snapshots(self):
        import components.asr.funasr.paraformer as pf

        fake_funasr = types.ModuleType("funasr")
        fake_funasr.AutoModel = MagicMock()
        with patch.dict(sys.modules, {"funasr": fake_funasr}), \
             patch.object(pf, "get_model_from_service", side_effect=["asr", "vad", "punc"]) as download:
            pf.Paraformer("paraformer-zh")
        self.assertEqual(download.call_count, 3)
        self.assertEqual(download.call_args_list[0].args, (pf.FUNASR_MODEL_MAP["paraformer-zh"], "v2.0.4"))
        self.assertEqual(download.call_args_list[1].args, (pf.VAD_MODEL, "v2.0.4"))
        self.assertEqual(download.call_args_list[2].args, (pf.PUNC_MODEL, "v2.0.4"))
        fake_funasr.AutoModel.assert_called_once()

    def test_invalid_model_name_raises_value_error(self):
        import components.asr.funasr.paraformer as pf

        with self.assertRaises(ValueError):
            pf.Paraformer("not-a-real-model")

    def test_valid_model_without_funasr_raises_runtime_error(self):
        import components.asr.funasr.paraformer as pf

        if "funasr" in sys.modules:
            self.skipTest("funasr is installed; opt-in guard not exercised")
        with self.assertRaises(RuntimeError) as ctx:
            pf.Paraformer("paraformer-zh")
        self.assertIn("requirements-cjk.txt", str(ctx.exception))


class ResolveBackendRoutingTests(unittest.TestCase):
    """Verify _resolve_backend routes funasr correctly without breaking others."""

    @staticmethod
    def _import_asr_component():
        # Stub the heavy Whisper provider modules imported at asr_component top.
        def _stub(modname, clsname="Whisper"):
            module = types.ModuleType(modname)
            setattr(module, clsname, type(clsname, (), {}))
            sys.modules[modname] = module

        _stub("components.asr.openai.whisper")
        _stub("components.asr.openvino.whisper")
        _stub("components.asr.openvino_genai.whisper")
        _stub("components.asr.whispercpp.whisper", "WhisperCpp")

        from components.asr_component import ASRComponent

        return ASRComponent

    def test_funasr_routes_to_paraformer_on_cpu(self):
        ASRComponent = self._import_asr_component()
        cls, _key, device = ASRComponent._resolve_backend("funasr", "paraformer-zh", "CPU")
        self.assertEqual(cls.__name__, "Paraformer")
        self.assertEqual(device, "cpu")

    def test_existing_whisper_routing_unchanged(self):
        ASRComponent = self._import_asr_component()
        _cls, _key, device = ASRComponent._resolve_backend("openvino", "whisper-base", "GPU")
        self.assertEqual(device, "GPU")

    def test_unsupported_combination_raises(self):
        ASRComponent = self._import_asr_component()
        with self.assertRaises(ValueError):
            ASRComponent._resolve_backend("funasr", "whisper-base", "CPU")


if __name__ == "__main__":
    unittest.main()
