# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import torch

from components.asr.diarization import ov_pyannote_diarizer as ovd


class _FakePort:
    def __init__(self, name: str, shape):
        self._name = name
        self.shape = shape

    def get_any_name(self) -> str:
        return self._name


class _FakeCompiledEmbedding:
    def __init__(self, static_frames: int | None = None, static_batch: int | None = 1):
        batch_dim = static_batch if static_batch is not None else -1
        frame_dim = static_frames if static_frames is not None else -1
        self.inputs = [
            _FakePort("fbank", [batch_dim, frame_dim, 4]),
            _FakePort("weights", [batch_dim, frame_dim]),
        ]

    def input(self, index: int):
        return self.inputs[index]

    def __call__(self, inputs):
        fbank = inputs["fbank"]
        weights = inputs["weights"]
        denom = np.clip(np.sum(weights, axis=1, keepdims=True), 1e-6, None)
        out = np.sum(fbank * weights[:, :, None], axis=1) / denom
        return {"embedding": out.astype(np.float32)}


class _ToyResNet(torch.nn.Module):
    def forward(self, fbank: torch.Tensor, weights: torch.Tensor | None = None):
        if weights is None:
            weights = torch.ones(
                (fbank.shape[0], fbank.shape[1]),
                dtype=fbank.dtype,
                device=fbank.device,
            )
        weighted = fbank * weights.unsqueeze(-1)
        denom = torch.clamp(weights.sum(dim=1, keepdim=True), min=1e-6)
        emb = weighted.sum(dim=1) / denom
        return torch.tensor(0.0, dtype=fbank.dtype, device=fbank.device), emb


class _ToyEmbeddingModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.resnet = _ToyResNet()

    def compute_fbank(self, waveforms: torch.Tensor) -> torch.Tensor:
        mono = waveforms.mean(dim=1)
        x = mono.unsqueeze(-1)
        return torch.cat([x, 0.5 * x, 2.0 * x, torch.sin(x)], dim=-1)


class _ToyFrontendModel:
    @staticmethod
    def compute_fbank(waveforms: torch.Tensor) -> torch.Tensor:
        mono = waveforms.mean(dim=1)
        x = mono.unsqueeze(-1)
        return torch.cat([x, x + 1.0, x + 2.0, x + 3.0], dim=-1)


@pytest.mark.parametrize("device", ["CPU", "GPU", "NPU"])
def test_ov_diarizer_accepts_supported_devices(device):
    diarizer = ovd.OVBackedPyannoteDiarizer.__new__(ovd.OVBackedPyannoteDiarizer)
    requested = str(device).strip().upper()
    assert requested in {"CPU", "GPU", "NPU"}


def test_ov_diarizer_rejects_unsupported_device():
    with pytest.raises(RuntimeError, match="Unsupported OpenVINO diarization device"):
        ovd.OVBackedPyannoteDiarizer(ov_device="TPU")


def test_embedding_wrapper_output_shape_and_parity():
    compiled = _FakeCompiledEmbedding(static_frames=None)
    spec = ovd._EmbeddingInputSpec(
        fbank_name="fbank",
        weights_name="weights",
        static_batch=None,
        static_frames=None,
    )
    wrapper = ovd._OVWeSpeakerEmbeddingModule(
        frontend_model=_ToyFrontendModel(),
        compiled_model=compiled,
        input_spec=spec,
        device_label="CPU",
    )

    waveforms = torch.randn(2, 1, 20, dtype=torch.float32)
    weights = torch.ones(2, 20, dtype=torch.float32)

    with torch.no_grad():
        ov_out = wrapper(waveforms, weights).numpy()
        fbank = _ToyFrontendModel.compute_fbank(waveforms).numpy()
        ref = compiled({"fbank": fbank, "weights": weights.numpy()})["embedding"]

    assert ov_out.shape == (2, 4)

    for idx in range(ov_out.shape[0]):
        ref_vec = ref[idx]
        ov_vec = ov_out[idx]
        cosine = float(np.dot(ref_vec, ov_vec) / (np.linalg.norm(ref_vec) * np.linalg.norm(ov_vec) + 1e-8))
        max_abs = float(np.max(np.abs(ref_vec - ov_vec)))
        assert cosine > 0.99999
        assert max_abs < 1e-6


def test_npu_static_shape_padding_and_cropping():
    compiled = _FakeCompiledEmbedding(static_frames=8)
    spec = ovd._EmbeddingInputSpec(
        fbank_name="fbank",
        weights_name="weights",
        static_batch=1,
        static_frames=8,
    )
    wrapper = ovd._OVWeSpeakerEmbeddingModule(
        frontend_model=_ToyFrontendModel(),
        compiled_model=compiled,
        input_spec=spec,
        device_label="NPU",
    )

    short_wave = torch.ones(1, 1, 5, dtype=torch.float32)
    long_wave = torch.ones(1, 1, 11, dtype=torch.float32)

    short_out = wrapper(short_wave)
    long_out = wrapper(long_wave)

    assert tuple(short_out.shape) == (1, 4)
    assert tuple(long_out.shape) == (1, 4)


def test_npu_static_batch_chunking_for_embedding_head():
    compiled = _FakeCompiledEmbedding(static_frames=8, static_batch=1)
    spec = ovd._EmbeddingInputSpec(
        fbank_name="fbank",
        weights_name="weights",
        static_batch=1,
        static_frames=8,
    )
    wrapper = ovd._OVWeSpeakerEmbeddingModule(
        frontend_model=_ToyFrontendModel(),
        compiled_model=compiled,
        input_spec=spec,
        device_label="NPU",
    )

    waveforms = torch.ones(3, 1, 8, dtype=torch.float32)
    out = wrapper(waveforms)

    assert tuple(out.shape) == (3, 4)


def test_embedding_head_openvino_conversion_cpu():
    pytest.importorskip("openvino")

    emb_model = _ToyEmbeddingModel()
    with tempfile.TemporaryDirectory() as tmp:
        compiled, spec = ovd._build_or_load_ov_embedding_head(
            emb_model,
            ov_device="CPU",
            model_dir=tmp,
            example_samples=32,
            is_npu=False,
        )

        assert compiled is not None
        assert spec.fbank_name
        assert spec.weights_name
        assert spec.static_batch is None
        # CPU/GPU export path is dynamic over frame count.
        assert spec.static_frames is None
        assert os.path.exists(os.path.join(tmp, "ov_embedding_head_cpu.xml"))


def test_embedding_head_openvino_conversion_npu_static_shape():
    pytest.importorskip("openvino")

    emb_model = _ToyEmbeddingModel()

    class _FakeCore:
        def read_model(self, *_args, **_kwargs):
            return object()

        def compile_model(self, _model, _device):
            return _FakeCompiledEmbedding(static_frames=16)

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "ov_embedding_head_npu.xml")
        with open(xml_path, "w", encoding="utf-8") as fh:
            fh.write("stub")

        with patch("openvino.Core", return_value=_FakeCore()):
            compiled, spec = ovd._build_or_load_ov_embedding_head(
                emb_model,
                ov_device="NPU",
                model_dir=tmp,
                example_samples=32,
                is_npu=True,
            )

    assert compiled is not None
    assert spec.static_batch == 1
    assert spec.static_frames == 16


def test_device_selection_no_silent_fallback():
    class _FakeInference:
        def __init__(self, model):
            self.model = model
            self.batch_size = 4

    class _FakeEmbeddingWrapper:
        def __init__(self, model):
            self.model_ = model

        def __call__(self, waveforms, masks=None):
            return self.model_(waveforms, masks)

    class _FakePipeline:
        def __init__(self, emb_model):
            self._inferences = {
                "_segmentation": _FakeInference(torch.nn.Identity()),
                "_embedding": _FakeInference(_FakeEmbeddingWrapper(emb_model)),
            }
            self._embedding = _FakeEmbeddingWrapper(emb_model)

    emb_model = _ToyEmbeddingModel()

    def _fake_super_init(self, device="cpu", hf_token=None):
        self.pipeline = _FakePipeline(emb_model)

    with patch.object(ovd.PyannoteDiarizer, "__init__", _fake_super_init):
        with patch.object(ovd, "_build_or_load_ov_model", return_value=_FakeCompiledEmbedding()):
            with patch.object(
                ovd,
                "_build_or_load_ov_embedding_head",
                return_value=(
                    _FakeCompiledEmbedding(),
                    ovd._EmbeddingInputSpec("fbank", "weights", None, None),
                ),
            ):
                d = ovd.OVBackedPyannoteDiarizer(ov_device="GPU")
                assert d._ov_device == "GPU"


def test_export_to_onnx_bytes_wraps_missing_onnx_dependency_error():
    model = torch.nn.Identity()
    example = torch.zeros(1, 1, 16, dtype=torch.float32)

    with patch.object(torch.onnx, "export", side_effect=ModuleNotFoundError("No module named 'onnx'")):
        with pytest.raises(RuntimeError, match="optional 'onnx' dependency is required") as exc_info:
            ovd._export_to_onnx_bytes(
                model,
                example_input=example,
                input_name="waveform",
                output_name="segmentation",
                dynamic_axes={"waveform": {0: "batch"}},
            )

    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)


def test_embedding_head_export_wraps_onnx_export_failure_with_actionable_error():
    emb_model = _ToyEmbeddingModel()

    fake_openvino = ModuleType("openvino")

    class _FakeCore:
        pass

    fake_openvino.Core = _FakeCore

    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(sys.modules, {"openvino": fake_openvino}):
            with patch.object(torch.onnx, "export", side_effect=RuntimeError("onnx export backend missing")):
                with pytest.raises(RuntimeError, match="OpenVINO diarization model export failed during ONNX export") as exc_info:
                    ovd._build_or_load_ov_embedding_head(
                        emb_model,
                        ov_device="CPU",
                        model_dir=tmp,
                        example_samples=32,
                        is_npu=False,
                    )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
