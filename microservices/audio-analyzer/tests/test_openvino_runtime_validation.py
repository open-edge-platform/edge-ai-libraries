# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from types import ModuleType, SimpleNamespace

import pytest

from utils.openvino_runtime_validation import validate_openvino_npu_runtime


def _cfg(asr_provider="openai", asr_device="CPU", sentiment_enabled=False, sentiment_provider="openvino", sentiment_device="CPU"):
    return SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(provider=asr_provider, device=asr_device),
        ),
        sentiment=SimpleNamespace(
            enabled=sentiment_enabled,
            provider=sentiment_provider,
            device=sentiment_device,
        ),
    )


def test_validate_npu_runtime_skips_when_npu_not_requested():
    validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="CPU"))


def test_validate_npu_runtime_reports_missing_openvino(monkeypatch):
    monkeypatch.setitem(sys.modules, "openvino", None)

    with pytest.raises(RuntimeError, match="OpenVINO runtime is not installed"):
        validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="NPU"))


def test_validate_npu_runtime_reports_missing_compiler_loader(monkeypatch):
    fake_ov = ModuleType("openvino")
    fake_runtime = ModuleType("openvino.runtime")
    fake_opset8 = ModuleType("openvino.runtime.opset8")

    class FakeCore:
        def __init__(self):
            self.available_devices = ["NPU"]

        def compile_model(self, _model, _device):
            raise RuntimeError("Cannot load libopenvino_intel_npu_compiler_loader.so")

    fake_ov.Core = FakeCore
    fake_ov.Model = lambda *args, **kwargs: (args, kwargs)
    fake_opset8.parameter = lambda *args, **kwargs: ("parameter", args, kwargs)
    fake_opset8.result = lambda *args, **kwargs: ("result", args, kwargs)

    monkeypatch.setitem(sys.modules, "openvino", fake_ov)
    monkeypatch.setitem(sys.modules, "openvino.runtime", fake_runtime)
    monkeypatch.setitem(sys.modules, "openvino.runtime.opset8", fake_opset8)

    with pytest.raises(RuntimeError, match="libopenvino_intel_npu_compiler_loader.so"):
        validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="NPU"))
