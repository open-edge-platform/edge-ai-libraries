# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the optional FunASR Paraformer provider (Chinese/English ASR).

These assert the provider is genuinely opt-in: the module imports cleanly
without ``funasr``/``modelscope`` installed, and the download/instantiation
guards raise actionable errors. This protects existing Whisper/OpenVINO
consumers from being affected by the new provider.
"""
import sys
import types
import unittest


class ModelDownloadHelperTests(unittest.TestCase):
    def test_missing_modelscope_raises_actionable_error(self):
        from utils.model_download_helper import get_or_download_model_dir

        # modelscope is an optional (requirements-cjk.txt) dependency.
        if "modelscope" in sys.modules:
            self.skipTest("modelscope is installed; opt-in guard not exercised")
        with self.assertRaises(RuntimeError) as ctx:
            get_or_download_model_dir("iic/whatever", hub="ms")
        self.assertIn("modelscope", str(ctx.exception).lower())

    def test_rejects_unknown_hub(self):
        from utils.model_download_helper import get_or_download_model_dir

        with self.assertRaises(ValueError):
            get_or_download_model_dir("iic/whatever", hub="bogus")  # type: ignore[arg-type]


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

    def test_default_hub_is_modelscope(self):
        import components.asr.funasr.paraformer as pf

        self.assertEqual(pf._resolve_hub(), "ms")

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
