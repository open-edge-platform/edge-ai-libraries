# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the optional FunASR Paraformer provider (Chinese/English ASR).

These assert the provider is genuinely opt-in: the module imports cleanly
without ``funasr`` installed, and the instantiation guards raise actionable
errors. This protects existing Whisper/OpenVINO consumers.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class ParaformerProviderTests(unittest.TestCase):
    def test_transcription_requests_token_and_sentence_timestamps(self):
        import components.asr.funasr.paraformer as pf

        provider = object.__new__(pf.Paraformer)
        provider.language = "zh"
        provider.model = MagicMock()
        provider.model.generate.return_value = [{
            "text": "test",
            "sentence_info": [{"start": 100, "end": 900, "text": "test"}],
        }]
        result = provider.transcribe("recording.wav")
        provider.model.generate.assert_called_once_with(
            input="recording.wav", pred_timestamp=True,
            sentence_timestamp=True, batch_size_s=300,
        )
        self.assertEqual(result["segments"], [{"start": 0.1, "end": 0.9, "text": "test"}])

    def test_transcription_errors_are_not_returned_as_empty_success(self):
        import components.asr.funasr.paraformer as pf

        provider = object.__new__(pf.Paraformer)
        provider.language = "zh"
        provider.model = MagicMock()
        provider.model.generate.side_effect = KeyError("timestamp")
        with self.assertRaises(KeyError):
            provider.transcribe("recording.wav")

    def test_module_imports_without_funasr(self):
        # The whole point of the lazy import: this must not require funasr.
        import components.asr.funasr.paraformer as pf

        self.assertEqual(
            set(pf.FUNASR_MODEL_MAP),
            {"paraformer-zh", "paraformer-en", "paraformer-online"},
        )
        self.assertEqual(pf._MODEL_LANGUAGE["paraformer-zh"], "zh")
        self.assertEqual(pf._MODEL_LANGUAGE["paraformer-en"], "en")

    def test_loads_all_three_provisioned_snapshots_locally(self):
        import components.asr.funasr.paraformer as pf

        fake_funasr = types.ModuleType("funasr")
        fake_funasr.AutoModel = MagicMock()
        with patch.dict(sys.modules, {"funasr": fake_funasr}), \
             patch.object(pf, "get_local_model", side_effect=["asr", "vad", "punc"]) as download:
            pf.Paraformer("paraformer-zh")
        self.assertEqual(download.call_count, 3)
        self.assertEqual(download.call_args_list[0].args, (pf.FUNASR_MODEL_MAP["paraformer-zh"], "v2.0.4"))
        self.assertEqual(download.call_args_list[1].args, (pf.FUNASR_VAD_MODEL, "v2.0.4"))
        self.assertEqual(download.call_args_list[2].args, (pf.FUNASR_PUNC_MODEL, "v2.0.4"))
        for call in download.call_args_list:
            self.assertEqual(call.kwargs, {
                "hub": "modelscope", "required_files": ["config.yaml", "model.pt"],
            })
        fake_funasr.AutoModel.assert_called_once_with(
            model="asr", vad_model="vad", punc_model="punc",
            device="cpu", disable_update=True,
        )

    def test_revision_override_only_changes_asr_snapshot(self):
        import components.asr.funasr.paraformer as pf

        fake_funasr = types.ModuleType("funasr")
        fake_funasr.AutoModel = MagicMock()
        with patch.dict(sys.modules, {"funasr": fake_funasr}), \
             patch.object(pf, "get_local_model", return_value="local") as download:
            pf.Paraformer("paraformer-zh", revision="custom-commit")
        self.assertEqual(download.call_args_list[0].args[1], "custom-commit")
        self.assertEqual(download.call_args_list[1].args[1], pf._MODEL_REVISIONS[pf.VAD_MODEL])
        self.assertEqual(download.call_args_list[2].args[1], pf._MODEL_REVISIONS[pf.PUNC_MODEL])

    def test_custom_companions_do_not_inherit_default_repository_revisions(self):
        import components.asr.funasr.paraformer as pf

        fake_funasr = types.ModuleType("funasr")
        fake_funasr.AutoModel = MagicMock()
        with patch.dict(sys.modules, {"funasr": fake_funasr}), \
             patch.object(pf, "VAD_MODEL", "custom/vad"), \
             patch.object(pf, "PUNC_MODEL", "custom/punc"), \
             patch.object(pf, "get_local_model", return_value="local") as download:
            pf.Paraformer("paraformer-zh")
        self.assertEqual(download.call_args_list[1].args, ("custom/vad", None))
        self.assertEqual(download.call_args_list[2].args, ("custom/punc", None))

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
