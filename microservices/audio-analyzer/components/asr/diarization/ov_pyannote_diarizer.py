# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import torch

from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer
from utils.ensure_model import get_diarization_model_path

if TYPE_CHECKING:
    import openvino as ov

logger = logging.getLogger(__name__)

_SEG_CHUNK_DURATION_SEC: float = 10.0
_SEG_SAMPLE_RATE: int = 16_000
_SEG_CHUNK_SAMPLES: int = int(_SEG_CHUNK_DURATION_SEC * _SEG_SAMPLE_RATE)
_EMB_EXAMPLE_SAMPLES: int = 48_000


@dataclass
class _EmbeddingInputSpec:
    fbank_name: str
    weights_name: str
    static_batch: int | None
    static_frames: int | None


class _OVModelModule(torch.nn.Module):
    """Torch module shim that delegates forward() to an OV compiled model."""

    def __init__(self, compiled_model, device_label: str) -> None:
        super().__init__()
        self._compiled = compiled_model
        self._device_label = device_label
        self._static_samples = self._extract_static_samples(compiled_model)

    @staticmethod
    def _extract_static_samples(compiled_model) -> int | None:
        try:
            input_shape = list(compiled_model.input(0).shape)
            if len(input_shape) == 3 and all(int(dim) > 0 for dim in input_shape):
                return int(input_shape[2])
        except Exception:
            return None
        return None

    def _adapt_samples_for_static_shape(self, np_input: np.ndarray) -> np.ndarray:
        if self._static_samples is None:
            return np_input
        current = int(np_input.shape[2])
        if current == self._static_samples:
            return np_input
        if current > self._static_samples:
            return np_input[:, :, : self._static_samples]
        pad = self._static_samples - current
        return np.pad(np_input, ((0, 0), (0, 0), (0, pad)), mode="constant")

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        np_input = waveform.detach().cpu().numpy().astype(np.float32, copy=False)
        np_input = self._adapt_samples_for_static_shape(np_input)
        result = self._compiled([np_input])
        output = next(iter(result.values()))
        return torch.from_numpy(output)

    def to(self, *args, **kwargs):  # type: ignore[override]
        return self

    def eval(self):  # pragma: no cover
        return self

    def train(self, mode: bool = True):  # pragma: no cover
        return self

    def parameters(self, recurse: bool = True):  # pragma: no cover
        return iter(())

    def __repr__(self) -> str:  # pragma: no cover
        return f"_OVModelModule(device={self._device_label!r})"


class _WeSpeakerEmbeddingHead(torch.nn.Module):
    """Exportable neural embedding head (post-fbank frontend)."""

    def __init__(self, emb_model: torch.nn.Module) -> None:
        super().__init__()
        self._resnet = emb_model.resnet

    def forward(self, fbank: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
        return self._resnet(fbank, weights=weights)[1]


class _OVWeSpeakerEmbeddingModule(torch.nn.Module):
    """Keep pyannote's exact fbank frontend and run only head via OV."""

    def __init__(
        self,
        *,
        frontend_model: torch.nn.Module,
        compiled_model,
        input_spec: _EmbeddingInputSpec,
        device_label: str,
    ) -> None:
        super().__init__()
        self._frontend_model = frontend_model
        self._compiled = compiled_model
        self._input_spec = input_spec
        self._device_label = device_label

    @staticmethod
    def _default_weights(fbank: torch.Tensor) -> torch.Tensor:
        return torch.ones(
            (fbank.shape[0], fbank.shape[1]),
            dtype=fbank.dtype,
            device=fbank.device,
        )

    def _adapt_frames(
        self,
        fbank_np: np.ndarray,
        weights_np: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        target = self._input_spec.static_frames
        if target is None:
            return fbank_np, weights_np

        current = int(fbank_np.shape[1])
        if current == target:
            return fbank_np, weights_np

        if current < target:
            pad = target - current
            fbank_np = np.pad(fbank_np, ((0, 0), (0, pad), (0, 0)), mode="constant")
            weights_np = np.pad(weights_np, ((0, 0), (0, pad)), mode="constant")
            return fbank_np, weights_np

        # NPU static-shape safety: deterministic tail crop when frame count exceeds
        # compiled input length.
        fbank_np = fbank_np[:, :target, :]
        weights_np = weights_np[:, :target]
        return fbank_np, weights_np

    def _run_ov_head(self, fbank_np: np.ndarray, weights_np: np.ndarray) -> np.ndarray:
        ov_result = self._compiled(
            {
                self._input_spec.fbank_name: fbank_np,
                self._input_spec.weights_name: weights_np,
            }
        )
        out = next(iter(ov_result.values()))
        return out

    def forward(self, waveforms: torch.Tensor, weights: torch.Tensor | None = None) -> torch.Tensor:
        with torch.no_grad():
            fbank = self._frontend_model.compute_fbank(waveforms)
        if weights is None:
            weights = self._default_weights(fbank)

        fbank_np = fbank.detach().cpu().numpy().astype(np.float32, copy=False)
        weights_np = weights.detach().cpu().numpy().astype(np.float32, copy=False)
        fbank_np, weights_np = self._adapt_frames(fbank_np, weights_np)

        static_batch = self._input_spec.static_batch
        if static_batch is None or int(fbank_np.shape[0]) == static_batch:
            out = self._run_ov_head(fbank_np, weights_np)
            return torch.from_numpy(out)

        if static_batch <= 0:
            raise RuntimeError(
                f"Invalid static embedding batch size ({static_batch}) for device {self._device_label}."
            )

        outputs: list[np.ndarray] = []
        total = int(fbank_np.shape[0])
        for start in range(0, total, static_batch):
            end = min(start + static_batch, total)
            f_chunk = fbank_np[start:end]
            w_chunk = weights_np[start:end]

            valid = end - start
            if valid < static_batch:
                pad = static_batch - valid
                f_chunk = np.pad(f_chunk, ((0, pad), (0, 0), (0, 0)), mode="constant")
                w_chunk = np.pad(w_chunk, ((0, pad), (0, 0)), mode="constant")
                chunk_out = self._run_ov_head(f_chunk, w_chunk)[:valid]
            else:
                chunk_out = self._run_ov_head(f_chunk, w_chunk)

            outputs.append(chunk_out)

        out = np.concatenate(outputs, axis=0)
        return torch.from_numpy(out)

    def to(self, *args, **kwargs):  # type: ignore[override]
        return self

    def eval(self):  # pragma: no cover
        return self

    def train(self, mode: bool = True):  # pragma: no cover
        return self

    def parameters(self, recurse: bool = True):  # pragma: no cover
        return iter(())

    def __repr__(self) -> str:  # pragma: no cover
        return f"_OVWeSpeakerEmbeddingModule(device={self._device_label!r})"


def _ov_cache_path(model_dir: str, stage: str, device: str) -> tuple[str, str]:
    tag = str(device).strip().lower()
    base = os.path.join(model_dir, f"ov_{stage}_{tag}")
    return base + ".xml", base + ".bin"


def _export_to_onnx_bytes(
    torch_model: torch.nn.Module,
    *,
    example_input: torch.Tensor,
    input_name: str,
    output_name: str,
    dynamic_axes: dict | None,
) -> bytes:
    if hasattr(torch_model, "eval"):
        torch_model.eval()
    buf = io.BytesIO()
    torch.onnx.export(
        torch_model,
        example_input,
        buf,
        opset_version=17,
        input_names=[input_name],
        output_names=[output_name],
        dynamic_axes=dynamic_axes,
    )
    return buf.getvalue()


def _build_or_load_ov_model(
    torch_model: torch.nn.Module,
    *,
    ov_device: str,
    model_dir: str,
    stage: str,
    example_input: torch.Tensor,
    dynamic_axes: dict | None,
) -> "ov.CompiledModel":
    import openvino as ov

    xml_path, _ = _ov_cache_path(model_dir, stage, ov_device)
    core = ov.Core()

    if os.path.exists(xml_path):
        logger.info(
            "[DIARIZATION] Loading cached OV %s model from %s (device=%s)",
            stage,
            xml_path,
            ov_device,
        )
        ov_model = core.read_model(xml_path)
    else:
        logger.info(
            "[DIARIZATION] Exporting %s model to OpenVINO IR (device=%s)",
            stage,
            ov_device,
        )
        onnx_bytes = _export_to_onnx_bytes(
            torch_model,
            example_input=example_input,
            input_name="waveform",
            output_name=stage,
            dynamic_axes=dynamic_axes,
        )
        ov_model = ov.convert_model(io.BytesIO(onnx_bytes))
        os.makedirs(model_dir, exist_ok=True)
        ov.save_model(ov_model, xml_path)
        logger.info("[DIARIZATION] Cached OV %s IR at %s", stage, xml_path)

    compiled = core.compile_model(ov_model, ov_device)
    logger.info("[DIARIZATION] Compiled OV %s model on device=%s", stage, ov_device)
    return compiled


def _embedding_input_spec(compiled_model) -> _EmbeddingInputSpec:
    def _find_input(named_tokens: tuple[str, ...]):
        for inp in compiled_model.inputs:
            try:
                name = inp.get_any_name()
            except Exception:
                continue
            lname = str(name).lower()
            if any(token in lname for token in named_tokens):
                return inp, str(name)
        return None, ""

    fbank_port, fbank_name = _find_input(("fbank", "feature"))
    weights_port, weights_name = _find_input(("weight", "mask"))

    # Fallback: rely on declared order from export function.
    if fbank_port is None:
        fbank_port = compiled_model.input(0)
        fbank_name = fbank_port.get_any_name()
    if weights_port is None:
        weights_port = compiled_model.input(1)
        weights_name = weights_port.get_any_name()

    static_batch = None
    static_frames = None
    try:
        shape = list(fbank_port.shape)
        if len(shape) >= 1 and int(shape[0]) > 0:
            static_batch = int(shape[0])
        if len(shape) >= 2 and int(shape[1]) > 0:
            static_frames = int(shape[1])
    except Exception:
        static_batch = None
        static_frames = None

    return _EmbeddingInputSpec(
        fbank_name=str(fbank_name),
        weights_name=str(weights_name),
        static_batch=static_batch,
        static_frames=static_frames,
    )


def _build_or_load_ov_embedding_head(
    emb_model: torch.nn.Module,
    *,
    ov_device: str,
    model_dir: str,
    example_samples: int,
    is_npu: bool,
) -> tuple[object, _EmbeddingInputSpec]:
    import openvino as ov

    xml_path, _ = _ov_cache_path(model_dir, "embedding_head", ov_device)
    core = ov.Core()

    if os.path.exists(xml_path):
        logger.info(
            "[DIARIZATION] Loading cached OV embedding head from %s (device=%s)",
            xml_path,
            ov_device,
        )
        ov_model = core.read_model(xml_path)
    else:
        logger.info(
            "[DIARIZATION] Exporting embedding head to OpenVINO IR (device=%s)",
            ov_device,
        )
        head = _WeSpeakerEmbeddingHead(emb_model)
        head.eval()
        with torch.no_grad():
            waveform = torch.zeros(1, 1, example_samples, dtype=torch.float32)
            fbank = emb_model.compute_fbank(waveform)
            weights = torch.ones(
                (fbank.shape[0], fbank.shape[1]),
                dtype=fbank.dtype,
            )

        dynamic_axes = None
        if not is_npu:
            dynamic_axes = {
                "fbank": {0: "batch", 1: "frames"},
                "weights": {0: "batch", 1: "frames"},
            }

        buf = io.BytesIO()
        torch.onnx.export(
            head,
            (fbank, weights),
            buf,
            opset_version=17,
            input_names=["fbank", "weights"],
            output_names=["embedding"],
            dynamic_axes=dynamic_axes,
        )
        ov_model = ov.convert_model(io.BytesIO(buf.getvalue()))
        os.makedirs(model_dir, exist_ok=True)
        ov.save_model(ov_model, xml_path)
        logger.info("[DIARIZATION] Cached OV embedding head IR at %s", xml_path)

    compiled = core.compile_model(ov_model, ov_device)
    spec = _embedding_input_spec(compiled)
    logger.info(
        "[DIARIZATION] Compiled OV embedding head on device=%s (static_frames=%s)",
        ov_device,
        spec.static_frames,
    )
    return compiled, spec


def _copy_model_metadata(dst: torch.nn.Module, src: torch.nn.Module) -> None:
    for attr in (
        "audio",
        "specifications",
        "receptive_field",
        "dimension",
        "num_frames",
        "frames",
        "sample_rate",
    ):
        if hasattr(src, attr):
            setattr(dst, attr, getattr(src, attr))


class OVBackedPyannoteDiarizer(PyannoteDiarizer):
    """Pyannote diarizer that keeps full CPU interface parity and OV execution."""

    def __init__(
        self,
        ov_device: str,
        hf_token: str | None = None,
        model_dir: str = "",
    ) -> None:
        requested = str(ov_device).strip().upper()
        if requested not in {"CPU", "GPU", "NPU"}:
            raise RuntimeError(
                f"Unsupported OpenVINO diarization device '{ov_device}'. "
                "Supported values: CPU, GPU, NPU"
            )

        self._ov_device = requested
        self._is_npu = self._ov_device == "NPU"
        self._ov_model_dir = model_dir or get_diarization_model_path()

        # Load the standard pyannote pipeline and preserve all behavior/API.
        super().__init__(device="cpu", hf_token=hf_token)

        # Switch segmentation inference model to OpenVINO.
        seg_inference = getattr(self.pipeline, "_inferences", {}).get("_segmentation")
        if seg_inference is None or not hasattr(seg_inference, "model"):
            raise RuntimeError(
                "Could not find segmentation inference in pyannote pipeline. "
                "Expected key '_segmentation' in pipeline._inferences."
            )
        seg_torch_model = seg_inference.model
        seg_dynamic_axes = None if self._is_npu else {"waveform": {0: "batch"}}
        seg_compiled = _build_or_load_ov_model(
            seg_torch_model,
            ov_device=self._ov_device,
            model_dir=self._ov_model_dir,
            stage="segmentation",
            example_input=torch.zeros(1, 1, _SEG_CHUNK_SAMPLES, dtype=torch.float32),
            dynamic_axes=seg_dynamic_axes,
        )
        ov_seg_model = _OVModelModule(seg_compiled, self._ov_device)
        _copy_model_metadata(ov_seg_model, seg_torch_model)
        seg_inference.model = ov_seg_model
        if self._is_npu and hasattr(seg_inference, "batch_size") and seg_inference.batch_size != 1:
            seg_inference.batch_size = 1

        # Switch embedding model to OpenVINO-compatible split path:
        # exact pyannote frontend (compute_fbank) + OV embedding head.
        emb_wrapper = getattr(self.pipeline, "_embedding", None)
        if emb_wrapper is None:
            raise RuntimeError(
                "Could not find embedding model in pyannote pipeline (pipeline._embedding)."
            )
        emb_torch_model = getattr(emb_wrapper, "model_", emb_wrapper)
        if not hasattr(emb_torch_model, "forward"):
            raise RuntimeError(
                "Pyannote embedding model is not exportable: missing forward() on embedding backend."
            )
        if not hasattr(emb_torch_model, "compute_fbank") or not hasattr(emb_torch_model, "resnet"):
            raise RuntimeError(
                "Unexpected embedding model type. Expected WeSpeaker-compatible model with "
                "compute_fbank and resnet attributes."
            )

        emb_compiled, emb_spec = _build_or_load_ov_embedding_head(
            emb_torch_model,
            ov_device=self._ov_device,
            model_dir=self._ov_model_dir,
            example_samples=_EMB_EXAMPLE_SAMPLES,
            is_npu=self._is_npu,
        )

        ov_emb_model = _OVWeSpeakerEmbeddingModule(
            frontend_model=emb_torch_model,
            compiled_model=emb_compiled,
            input_spec=emb_spec,
            device_label=self._ov_device,
        )

        if hasattr(emb_wrapper, "model_"):
            emb_wrapper.model_ = ov_emb_model
            self.pipeline._embedding = emb_wrapper
        else:
            self.pipeline._embedding = ov_emb_model

        emb_inference = getattr(self.pipeline, "_inferences", {}).get("_embedding")
        if emb_inference is not None and hasattr(emb_inference, "model"):
            emb_inference.model = self.pipeline._embedding
            if self._is_npu and hasattr(emb_inference, "batch_size") and emb_inference.batch_size != 1:
                emb_inference.batch_size = 1

        logger.info(
            "[DIARIZATION] OVBackedPyannoteDiarizer ready on %s: segmentation+embedding via OpenVINO",
            self._ov_device,
        )
