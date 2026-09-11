# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face SigLIP embeddings with automatic OpenVINO conversion."""

from __future__ import annotations

import gc
import os
import time
from pathlib import Path
from typing import Any

import openvino as ov
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoProcessor, SiglipModel

from ...utils import ParallelImagePreprocessor, logger
from ..base import BaseEmbeddingModel
from ..utils import (
    AsyncBatchInference,
    check_and_convert_openvino_models,
    infer_with_batch_support,
    load_openvino_models,
)


class _ImageEncoder(torch.nn.Module):
    """Expose pooled vision features as a single-output exportable module."""

    def __init__(self, encoder: torch.nn.Module) -> None:
        super().__init__()
        self.encoder = encoder

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        return self.encoder(pixel_values=pixel_values).pooler_output


class _TextEncoder(torch.nn.Module):
    """Expose projected text features with a traceable attention mask."""

    def __init__(self, encoder: torch.nn.Module) -> None:
        super().__init__()
        self.encoder = encoder
        self.dtype = next(encoder.parameters()).dtype

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # SigLIP attends to padding too. An explicit additive mask preserves that
        # behavior without tracing Transformers' dynamic mask construction.
        batch_size, sequence_length = input_ids.shape
        attention_mask = torch.zeros(
            (batch_size, 1, sequence_length, sequence_length),
            dtype=self.dtype,
            device=input_ids.device,
        )
        return self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        ).pooler_output


class SigLIPTransformersHandler(BaseEmbeddingModel):
    """Load Hugging Face SigLIP checkpoints for text, image, and video embeddings."""

    def __init__(self, model_config: dict[str, Any]) -> None:
        super().__init__(model_config)
        self.hf_model_id = model_config["hf_model_id"]
        self.revision = model_config.get("revision")
        self.processor_id = model_config["processor_id"]
        self.image_size = model_config.get("image_size", 224)
        self.max_length = model_config.get("max_length", 64)
        self.use_openvino = model_config.get("use_openvino", False)
        self.weight_format = model_config.get("weight_format", "int8")
        if self.weight_format not in {"fp16", "int8"}:
            raise ValueError("SigLIP weight_format must be 'fp16' or 'int8'")

        batch_size = model_config.get("infer_batch_size", 64)
        self.preprocess_shape = (batch_size, 3, self.image_size, self.image_size)
        self._preprocess_workers = model_config.get(
            "preprocess_workers", min(16, (os.cpu_count() or 4) * 2)
        )
        self.processor = None
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        self._image_encoder = None
        self._text_encoder = None
        self._embedding_dim: int | None = None
        self.parallel_preprocessor = None
        self.async_infer = None

    def load_model(self) -> None:
        """Load preprocessing and either PyTorch weights or cached OpenVINO IR."""
        logger.info("Loading Hugging Face SigLIP model: %s", self.hf_model_id)
        self.processor = AutoProcessor.from_pretrained(
            self.processor_id, trust_remote_code=False
        )
        self.tokenizer = self.processor.tokenizer
        self.preprocess = self._preprocess_image
        if self.use_openvino:
            self._load_openvino_models()
        else:
            self.model = self._load_pytorch_model()
            self._image_encoder = _ImageEncoder(self.model.vision_model).eval()
            self._text_encoder = _TextEncoder(self.model.text_model).eval()
            self._embedding_dim = self.model.config.text_config.projection_size
        logger.info("Hugging Face SigLIP model loaded: %s", self.hf_model_id)

    def _load_pytorch_model(self) -> SiglipModel:
        return SiglipModel.from_pretrained(
            self.hf_model_id,
            revision=self.revision,
            trust_remote_code=False,
            use_safetensors=True,
            attn_implementation="eager",
        ).eval()

    def _tokenize_text(self, texts: list[str]) -> torch.Tensor:
        return self.tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )["input_ids"]

    def _preprocess_image(self, image: Image.Image) -> torch.Tensor:
        return self.processor.image_processor(
            images=image.convert("RGB"), return_tensors="pt"
        )["pixel_values"][0]

    def _model_key(self) -> str:
        key = f"{self.hf_model_id}_{self.revision or 'main'}_{self.weight_format}"
        return key.replace("/", "_").replace("-", "_")

    def _load_openvino_models(self) -> None:
        image_path, text_path = check_and_convert_openvino_models(
            model_key=self._model_key(),
            model_loader=None,
            tokenizer_loader=None,
            convert_func=lambda directory, _model, _tokenizer: (
                self.convert_to_openvino(directory)
            ),
            ov_models_dir=self.ov_models_dir,
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_path, text_path, self.device, self.preprocess_shape,
            (self.preprocess_shape[0], self.max_length),
        )
        self._embedding_dim = (
            self.ov_image_encoder.output().get_partial_shape()[-1].get_length()
        )
        self.parallel_preprocessor = ParallelImagePreprocessor(
            preprocess_fn=self.preprocess,
            max_workers=self._preprocess_workers,
            preprocess_shape=self.preprocess_shape,
        )
        self.async_infer = AsyncBatchInference(
            compiled_model=self.ov_image_encoder,
            embedding_dim=self._embedding_dim,
            preprocess_shape=self.preprocess_shape,
        )

    def encode_text(self, texts: str | list[str]) -> torch.Tensor:
        """Return L2-normalized, projected text embeddings."""
        if isinstance(texts, str):
            texts = [texts]
        tokens = self._tokenize_text(texts)
        if self.use_openvino:
            features = torch.from_numpy(
                infer_with_batch_support(
                    self.ov_text_encoder, {self.ov_text_encoder.input(): tokens}
                )
            )
        else:
            with torch.no_grad():
                features = self._text_encoder(tokens)
        return F.normalize(features, dim=-1)

    def encode_image(
        self, images: Image.Image | list[Image.Image], metrics_out: bool = False
    ) -> torch.Tensor | dict[str, Any]:
        """Return normalized image embeddings and optional inference metrics."""
        if isinstance(images, Image.Image):
            images = [images]
        start = time.perf_counter()
        if self.use_openvino:
            stream = self.parallel_preprocessor.preprocess_stream(images)
            try:
                features = torch.from_numpy(
                    self.async_infer.infer_stream(
                        batch_generator=stream, total_images=len(images)
                    )
                )
            finally:
                stream.close()
        else:
            with torch.no_grad():
                pixels = torch.stack([self.preprocess(image) for image in images])
                features = self._image_encoder(pixels)
        elapsed = time.perf_counter() - start
        features = F.normalize(features, dim=-1)
        if metrics_out:
            return {
                "embeddings": features,
                "inference_time_s": elapsed,
                "processed_images": len(images),
            }
        return features

    def convert_to_openvino(self, ov_models_dir: str) -> tuple[str, str]:
        """Export separate pooled encoders, compress weights, and persist IR."""
        directory = Path(ov_models_dir)
        directory.mkdir(parents=True, exist_ok=True)
        image_path = directory / f"{self._model_key()}_image_encoder.xml"
        text_path = directory / f"{self._model_key()}_text_encoder.xml"
        if image_path.exists() and text_path.exists():
            return str(image_path), str(text_path)

        model = (
            self.model if self.model is not None else self._load_pytorch_model()
        )
        sample_image = torch.zeros(1, 3, self.image_size, self.image_size)
        sample_text = self._tokenize_text(["sample text"])
        encoders = (
            (image_path, _ImageEncoder(model.vision_model), sample_image),
            (text_path, _TextEncoder(model.text_model), sample_text),
        )
        for path, encoder, sample in encoders:
            if path.exists():
                continue
            logger.info(
                "Converting SigLIP encoder to %s (%s)", path, self.weight_format
            )
            converted = ov.convert_model(
                encoder.eval(), example_input=sample,
                input=[-1, *sample.shape[1:]],
            )
            if self.weight_format == "int8":
                import nncf

                converted = nncf.compress_weights(
                    converted, mode=nncf.CompressWeightsMode.INT8_ASYM
                )
            ov.save_model(converted, path)
            del converted
            gc.collect()
        return str(image_path), str(text_path)

    def get_embedding_dim(self) -> int:
        """Return the loaded encoder's output dimension without probing weights."""
        if self._embedding_dim is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self._embedding_dim
