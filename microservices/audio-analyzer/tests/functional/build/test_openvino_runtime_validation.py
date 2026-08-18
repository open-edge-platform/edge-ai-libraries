# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from types import ModuleType, SimpleNamespace

import pytest

from utils.openvino_runtime_validation import (
    validate_asr_runtime_configuration,
    validate_openvino_npu_runtime,
    validate_runtime_configuration,
)
from utils.openvino_runtime_validation import (
    resolve_diarization_torch_device,
    validate_diarization_device_configuration,
)


def _diar_cfg(
    *,
    diarization_enabled: bool = True,
    diarization_device: str = "CPU",
    asr_provider: str = "openvino",
    asr_device: str = "CPU",
):
    return SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(
                provider=asr_provider,
                device=asr_device,
                name="whisper-base",
                diarization=diarization_enabled,
            ),
            diarization=SimpleNamespace(
                provider="huggingface",
                device=diarization_device,
            ),
        ),
        sentiment=SimpleNamespace(enabled=False, provider="openvino", device="CPU"),
    )


def _cfg(asr_provider="openai", asr_device="CPU", asr_model_name="whisper-small", sentiment_enabled=False, sentiment_provider="openvino", sentiment_device="CPU"):
    return SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(provider=asr_provider, device=asr_device, name=asr_model_name),
        ),
        sentiment=SimpleNamespace(
            enabled=sentiment_enabled,
            provider=sentiment_provider,
            device=sentiment_device,
        ),
    )


def _install_fake_openvino(monkeypatch, available_devices, compile_error=None):
    fake_ov = ModuleType("openvino")
    fake_op = ModuleType("openvino.op")

    class FakeCore:
        def __init__(self):
            self.available_devices = list(available_devices)

        def compile_model(self, _model, _device):
            if compile_error is not None:
                raise RuntimeError(compile_error)
            return object()

    class FakeParameter:
        def __init__(self, *_args, **_kwargs):
            pass

        def output(self, *_args, **_kwargs):
            return "fake_output"

    class FakeResult:
        def __init__(self, *_args, **_kwargs):
            pass

    fake_ov.Core = FakeCore
    fake_ov.Model = lambda *args, **kwargs: (args, kwargs)
    fake_ov.Type = SimpleNamespace(f32="fake_f32")
    fake_ov.Shape = lambda dims: dims
    fake_op.Parameter = FakeParameter
    fake_op.Result = FakeResult
    fake_ov.op = fake_op

    monkeypatch.setitem(sys.modules, "openvino", fake_ov)
    monkeypatch.setitem(sys.modules, "openvino.op", fake_op)


def test_validate_npu_runtime_skips_when_npu_not_requested():
    validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="CPU"))


def test_validate_npu_runtime_reports_missing_openvino(monkeypatch):
    monkeypatch.setitem(sys.modules, "openvino", None)

    with pytest.raises(RuntimeError, match="OpenVINO runtime is not installed"):
        validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="NPU"))


def test_validate_npu_runtime_reports_missing_compiler_loader(monkeypatch):
    _install_fake_openvino(
        monkeypatch,
        available_devices=["NPU"],
        compile_error="Cannot load libopenvino_intel_npu_compiler_loader.so",
    )

    with pytest.raises(RuntimeError, match="libopenvino_intel_npu_compiler_loader.so"):
        validate_openvino_npu_runtime(_cfg(asr_provider="openvino", asr_device="NPU"))


def test_validate_asr_runtime_configuration_rejects_unknown_provider():
    with pytest.raises(RuntimeError, match="Invalid models.asr.provider"):
        validate_asr_runtime_configuration(_cfg(asr_provider="invalid", asr_device="CPU"))


def test_validate_asr_runtime_configuration_rejects_unknown_device():
    with pytest.raises(RuntimeError, match="Invalid models.asr.device"):
        validate_asr_runtime_configuration(_cfg(asr_provider="openvino", asr_device="VPU"))


def test_validate_asr_runtime_configuration_rejects_openai_gpu():
    with pytest.raises(RuntimeError, match="provider=openai"):
        validate_asr_runtime_configuration(_cfg(asr_provider="openai", asr_device="GPU"))


def test_validate_asr_runtime_configuration_rejects_openai_npu():
    with pytest.raises(RuntimeError, match="provider=openai"):
        validate_asr_runtime_configuration(_cfg(asr_provider="openai", asr_device="NPU"))


def test_validate_asr_runtime_configuration_rejects_whispercpp_gpu():
    with pytest.raises(RuntimeError, match="provider=whispercpp"):
        validate_asr_runtime_configuration(_cfg(asr_provider="whispercpp", asr_device="GPU"))


def test_validate_asr_runtime_configuration_rejects_whispercpp_npu():
    with pytest.raises(RuntimeError, match="provider=whispercpp"):
        validate_asr_runtime_configuration(_cfg(asr_provider="whispercpp", asr_device="NPU"))


def test_validate_asr_runtime_configuration_requires_openvino_visible_device(monkeypatch):
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])

    with pytest.raises(RuntimeError, match=r"available_devices=\['CPU', 'GPU'\]"):
        validate_asr_runtime_configuration(_cfg(asr_provider="openvino", asr_device="NPU"))


def test_validate_asr_runtime_configuration_accepts_openvino_gpu_when_available(monkeypatch):
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])

    validate_asr_runtime_configuration(_cfg(asr_provider="openvino", asr_device="GPU"))


def test_validate_asr_runtime_configuration_accepts_openvino_cpu_when_available(monkeypatch):
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])

    validate_asr_runtime_configuration(_cfg(asr_provider="openvino", asr_device="CPU"))


def test_validate_asr_runtime_configuration_accepts_openvino_npu_when_available(monkeypatch):
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])

    validate_asr_runtime_configuration(_cfg(asr_provider="openvino", asr_device="NPU", asr_model_name="whisper-medium"))


def test_validate_asr_runtime_configuration_rejects_whisper_large_npu(monkeypatch):
    """whisper-large+NPU is rejected at startup: confirmed ZE_RESULT_ERROR_UNINITIALIZED
    at pfnAppendGraphExecute on Intel Core Ultra NPU (arch 3720, OV 2026.1)."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])

    with pytest.raises(RuntimeError, match="not supported on this NPU hardware"):
        validate_asr_runtime_configuration(
            _cfg(asr_provider="openvino", asr_device="NPU", asr_model_name="whisper-large")
        )


def test_validate_asr_runtime_configuration_accepts_whisper_large_cpu(monkeypatch):
    """whisper-large+CPU must not be affected by the NPU-specific blocklist."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])

    validate_asr_runtime_configuration(
        _cfg(asr_provider="openvino", asr_device="CPU", asr_model_name="whisper-large")
    )


def test_validate_runtime_configuration_validates_sentiment_npu(monkeypatch):
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])

    validate_runtime_configuration(
        _cfg(
            asr_provider="openai",
            asr_device="CPU",
            sentiment_enabled=True,
            sentiment_provider="openvino",
            sentiment_device="NPU",
        )
    )


# ---------------------------------------------------------------------------
# resolve_diarization_torch_device
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# resolve_diarization_torch_device — new OV-based implementation
# ---------------------------------------------------------------------------

def test_resolve_diarization_torch_device_cpu_returns_cpu():
    """CPU device maps to 'CPU' (PyTorch CPU path)."""
    assert resolve_diarization_torch_device("CPU") == "CPU"
    assert resolve_diarization_torch_device("cpu") == "CPU"


def test_resolve_diarization_torch_device_gpu_returns_gpu():
    """GPU maps to 'GPU' (OpenVINO GPU path — no PyTorch GPU check needed)."""
    assert resolve_diarization_torch_device("GPU") == "GPU"
    assert resolve_diarization_torch_device("gpu") == "GPU"


def test_resolve_diarization_torch_device_npu_returns_npu():
    """NPU maps to 'NPU' (OpenVINO NPU path)."""
    assert resolve_diarization_torch_device("NPU") == "NPU"
    assert resolve_diarization_torch_device("npu") == "NPU"


def test_resolve_diarization_torch_device_invalid_name_raises():
    """An unrecognised config device name fails fast."""
    with pytest.raises(RuntimeError, match="Invalid diarization device"):
        resolve_diarization_torch_device("FPGA")


# ---------------------------------------------------------------------------
# validate_diarization_device_configuration — OV availability checks
# ---------------------------------------------------------------------------

def test_validate_diarization_device_skips_when_diarization_disabled():
    """validate_diarization_device_configuration is a no-op when diarization=false."""
    cfg = _diar_cfg(diarization_enabled=False, diarization_device="GPU")
    validate_diarization_device_configuration(cfg)  # must not raise


def test_validate_diarization_device_accepts_cpu_always():
    """CPU device is always accepted — no OV probe needed."""
    cfg = _diar_cfg(diarization_enabled=True, diarization_device="CPU")
    validate_diarization_device_configuration(cfg)  # must not raise


def test_validate_diarization_device_accepts_gpu_when_ov_sees_gpu(monkeypatch):
    """GPU diarization passes when OpenVINO enumerates GPU."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])
    cfg = _diar_cfg(diarization_enabled=True, diarization_device="GPU")
    validate_diarization_device_configuration(cfg)  # must not raise


def test_validate_diarization_device_rejects_gpu_when_ov_has_no_gpu(monkeypatch):
    """GPU diarization fails startup when OpenVINO does not enumerate GPU."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU"])
    cfg = _diar_cfg(diarization_enabled=True, diarization_device="GPU")
    with pytest.raises(RuntimeError, match="not visible in this runtime"):
        validate_diarization_device_configuration(cfg)


def test_validate_diarization_device_accepts_npu_when_ov_sees_npu(monkeypatch):
    """NPU diarization passes when OpenVINO enumerates NPU."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])
    cfg = _diar_cfg(diarization_enabled=True, diarization_device="NPU")
    validate_diarization_device_configuration(cfg)  # must not raise


def test_validate_diarization_device_rejects_npu_when_ov_has_no_npu(monkeypatch):
    """NPU diarization fails startup when OpenVINO does not enumerate NPU."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])
    cfg = _diar_cfg(diarization_enabled=True, diarization_device="NPU")
    with pytest.raises(RuntimeError, match="not visible in this runtime"):
        validate_diarization_device_configuration(cfg)


def test_validate_runtime_configuration_rejects_gpu_diarization_without_ov_gpu(monkeypatch):
    """End-to-end: validate_runtime_configuration propagates OV GPU diarization errors."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU"])
    cfg = _diar_cfg(
        diarization_enabled=True,
        diarization_device="GPU",
        asr_provider="openai",
        asr_device="CPU",
    )
    with pytest.raises(RuntimeError, match="not visible in this runtime"):
        validate_runtime_configuration(cfg)


def test_validate_runtime_configuration_accepts_npu_asr_with_cpu_diarization(monkeypatch):
    """openvino+NPU ASR paired with CPU diarization is a valid combination."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])
    cfg = _diar_cfg(
        diarization_enabled=True,
        diarization_device="CPU",
        asr_provider="openvino",
        asr_device="NPU",
    )
    validate_runtime_configuration(cfg)


def test_validate_runtime_configuration_accepts_npu_asr_with_npu_diarization(monkeypatch):
    """openvino+NPU ASR paired with NPU diarization is a valid combination."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "NPU"])
    cfg = _diar_cfg(
        diarization_enabled=True,
        diarization_device="NPU",
        asr_provider="openvino",
        asr_device="NPU",
    )
    validate_runtime_configuration(cfg)


def test_validate_runtime_configuration_accepts_gpu_asr_with_gpu_diarization(monkeypatch):
    """openvino+GPU ASR paired with GPU diarization is a valid combination."""
    _install_fake_openvino(monkeypatch, available_devices=["CPU", "GPU"])
    cfg = _diar_cfg(
        diarization_enabled=True,
        diarization_device="GPU",
        asr_provider="openvino",
        asr_device="GPU",
    )
    validate_runtime_configuration(cfg)
