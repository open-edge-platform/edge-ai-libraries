# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GME (gme-Qwen2-VL-2B-Instruct) handler over an OpenVINO package.

GME is not a CLIP-style pair of independent encoders: an image goes through the
visual IR and its tokens are then decoded by the language IR together with a
prompt, so text, image and image+text inputs all come out of the language IR
as one 1536-d, L2-normalized vector in a shared space. All of that lives in
``models.gme_runtime``; this handler loads the package, picks the prompt side
(query, document or fused) per call and adapts arrays to tensors.

Like the other OpenVINO handlers, the package is exported on first use (see
``models.gme_export``) into ``<EMBEDDING_OV_MODELS_DIR>/<package_dir>`` and
reused afterwards. An existing package directory is loaded as-is, so a package
exported elsewhere can be placed there instead. Precision, embedding dim and
processor limits are read from the package's ``gme_openvino_config.json``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import torch
from PIL import Image

from ..base import BaseEmbeddingModel
from ..gme_export import SUPPORTED_WEIGHT_FORMATS, export_package
from ..gme_runtime import DEFAULT_INSTRUCTION, GmeOpenVINO, package_ir_files
from ...utils import logger


class GMEHandler(BaseEmbeddingModel):
    """Handler for the GME multimodal embedding model (OpenVINO only)."""

    # What the Hugging Face Qwen2-VL processor reads from the package. The
    # package also carries an OpenVINO tokenizer IR, which this Python runtime
    # does not use.
    PROCESSOR_FILES = (
        "config.json",
        "preprocessor_config.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "vocab.json",
        "merges.txt",
    )

    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.hf_model_id: str = model_config["hf_model_id"]
        self.revision: Optional[str] = model_config.get("revision")
        self.package_dir: str = model_config["package_dir"]
        self.weight_format: str = model_config.get("weight_format", "int8")
        if self.weight_format not in SUPPORTED_WEIGHT_FORMATS:
            raise ValueError(f"GME weight_format must be one of {SUPPORTED_WEIGHT_FORMATS}")
        # Both known only once the package is loaded.
        self.embedding_dim: Optional[int] = None
        self.precision: Optional[str] = None
        self.use_openvino: bool = bool(model_config.get("use_openvino", False))
        self.batch_size: int = int(model_config.get("infer_batch_size") or 32)
        self.runtime: Optional[GmeOpenVINO] = None
        self._max_text_tokens: Optional[int] = None
        # One public call at a time: the runtime's request pools are locked, but
        # the Hugging Face processor in front of them is not known to be
        # reentrant. The prompt side is a per-call argument, so nothing
        # request-specific is stored on the instance.
        self._lock = threading.Lock()

    @property
    def model_dir(self) -> Path:
        return Path(self.ov_models_dir) / self.package_dir

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_model(self) -> None:
        if not self.use_openvino:
            raise RuntimeError(
                "GME runs only on OpenVINO and has no PyTorch fallback: set "
                "EMBEDDING_USE_OV=true (or use_openvino=True in the SDK)"
            )
        model_dir = self.model_dir
        if model_dir.exists():
            logger.info("Reusing existing GME OpenVINO package at %s", model_dir)
        else:
            self.convert_to_openvino(self.ov_models_dir)
        self._check_package(model_dir)
        if self.device.upper().startswith("NPU"):
            logger.warning("GME has not been validated on NPU; compilation may fail.")

        streams = self._streams()
        cache_dir = self._resolve_cache_dir()
        logger.info(
            "Loading GME OpenVINO package %s (device=%s, streams=%s, cache_dir=%s)",
            model_dir,
            self.device,
            streams,
            cache_dir,
        )
        # No precision argument: the runtime takes the one the package declares.
        self.runtime = GmeOpenVINO(
            model_dir,
            device=self.device,
            streams=streams,
            cache_dir=cache_dir,
        )
        self.model = self.runtime
        self.precision = self.runtime.precision
        self.embedding_dim = self.runtime.embedding_dim
        self._max_text_tokens = self._text_token_budget()
        logger.info(
            "GME loaded: precision=%s, dim=%d, batch_mode=%s, max_length=%d, text token budget=%d",
            self.precision,
            self.embedding_dim,
            self.runtime.batch_mode,
            self.runtime.max_length,
            self._max_text_tokens,
        )
        if self.device.upper().startswith("GPU"):
            # Shows whether the stock or a rebuilt (patched) GPU plugin is in use.
            for name, version in self.runtime.core.get_versions(self.device).items():
                logger.info("OpenVINO %s plugin: %s %s", name, version.description, version.build_number)

    def _check_package(self, model_dir: Path) -> None:
        """Fail with the exact missing file instead of deep inside the runtime."""
        if not model_dir.is_dir():
            raise FileNotFoundError(f"GME OpenVINO package not found at {model_dir}")
        config_path = model_dir / "gme_openvino_config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"Not an exported GME OpenVINO package (no {config_path.name}): {model_dir}")
        try:
            _, language_xml, visual_xml = package_ir_files(model_dir, json.loads(config_path.read_text()))
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Invalid {config_path}: {exc}") from exc
        required = []
        for xml_name in (language_xml, visual_xml):
            xml_path = model_dir / xml_name
            required += [xml_path, xml_path.with_suffix(".bin")]
        required += [model_dir / name for name in self.PROCESSOR_FILES]
        missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
        if missing:
            raise FileNotFoundError(f"GME package {model_dir} is incomplete; missing or empty: {missing}")

    @staticmethod
    def _streams() -> Union[int, str]:
        """Follow the service-wide OV_PERFORMANCE_MODE: THROUGHPUT lets OpenVINO pick streams."""
        mode = (os.getenv("OV_PERFORMANCE_MODE") or os.getenv("OPENVINO_PERFORMANCE_MODE") or "LATENCY")
        return "auto" if "THROUGHPUT" in mode.strip().upper() else 1

    def _resolve_cache_dir(self) -> Optional[str]:
        """Compiled-model cache, opt-in via OV_ENABLE_MODEL_CACHE like the other OV handlers.

        The cache never goes inside the model package, which is usually mounted
        read-only: it defaults to ``<EMBEDDING_OV_MODELS_DIR>/ov_cache/<package>``.
        """
        flag = (os.getenv("OV_ENABLE_MODEL_CACHE") or "").strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            return None
        base = os.getenv("OV_CACHE_DIR") or os.getenv("EMBEDDING_OV_CACHE_DIR")
        cache_dir = Path(base) if base else Path(self.ov_models_dir) / "ov_cache"
        cache_dir = cache_dir / self.package_dir
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create OpenVINO cache directory %s: %s; compiling without cache.", cache_dir, exc)
            return None
        return str(cache_dir)

    def _text_token_budget(self) -> int:
        """Tokens left for text once the fixed prompt template is paid for."""
        tokenizer = self.runtime.processor.tokenizer
        overhead = len(tokenizer(GmeOpenVINO._prompt("", has_image=False, instruction=DEFAULT_INSTRUCTION))["input_ids"])
        return max(1, self.runtime.max_length - overhead)

    def _require_runtime(self) -> GmeOpenVINO:
        if self.runtime is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self.runtime

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------
    @staticmethod
    def _to_tensor(embeddings: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(np.ascontiguousarray(embeddings, dtype=np.float32))

    @staticmethod
    def _to_pil_images(images: Union[Image.Image, np.ndarray, Sequence[Any]]) -> List[Image.Image]:
        if isinstance(images, (Image.Image, np.ndarray)):
            images = [images]
        converted = []
        for image in images:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            if not isinstance(image, Image.Image):
                raise TypeError(f"GME images must be PIL images or numpy arrays, got {type(image).__name__}")
            converted.append(image)
        return converted

    def _text(self, texts: List[str], is_query: bool) -> torch.Tensor:
        runtime = self._require_runtime()
        with self._lock:
            embeddings = runtime.get_text_embeddings(
                texts,
                is_query=is_query,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
        return self._to_tensor(embeddings)

    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Document-side text embeddings, ``[N, 1536]``."""
        if isinstance(texts, str):
            texts = [texts]
        return self.encode_documents(list(texts))

    def encode_query(self, text: str) -> torch.Tensor:
        return self._text([text], is_query=True)

    def encode_documents(self, texts: List[str]) -> torch.Tensor:
        return self._text(list(texts), is_query=False)

    def encode_image(
        self,
        images: Union[Image.Image, List[Image.Image]],
        metrics_out: bool = False,
    ) -> Union[Dict[str, Any], torch.Tensor]:
        """Image-only embeddings on the document side, ``[N, 1536]``."""
        runtime = self._require_runtime()
        pil_images = self._to_pil_images(images)
        with self._lock:
            start = time.perf_counter()
            embeddings = runtime.get_image_embeddings(
                pil_images,
                is_query=False,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
            elapsed = time.perf_counter() - start
        tensor = self._to_tensor(embeddings)
        if metrics_out:
            return {
                "embeddings": tensor,
                "inference_time_s": elapsed,
                "processed_images": len(pil_images),
            }
        return tensor

    def supports_fused(self) -> bool:
        return True

    def encode_fused(self, texts: List[str], images: List[Image.Image]) -> torch.Tensor:
        """One joint embedding per (text, image) pair, ``[N, 1536]``."""
        runtime = self._require_runtime()
        texts = list(texts)
        pil_images = self._to_pil_images(images)
        if not texts or len(texts) != len(pil_images):
            raise ValueError("fused input needs the same, non-zero number of texts and images")
        with self._lock:
            embeddings = runtime.get_fused_embeddings(
                texts,
                pil_images,
                is_query=False,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
        return self._to_tensor(embeddings)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    def get_embedding_dim(self) -> int:
        return self.embedding_dim

    def get_max_text_tokens(self) -> Optional[int]:
        """Text tokens a text-only input can use; images consume the same budget in fused inputs."""
        return self._max_text_tokens

    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        """Export the package into ``ov_models_dir`` unless it is already there."""
        package = Path(ov_models_dir) / self.package_dir
        if not package.exists():
            logger.info(
                "Exporting GME model %s to OpenVINO (%s) at %s; this downloads the checkpoint "
                "and takes several minutes on first use",
                self.hf_model_id,
                self.weight_format.upper(),
                package,
            )
            export_package(self.hf_model_id, package, self.weight_format, self.revision)
        _, language_xml, visual_xml = package_ir_files(
            package, json.loads((package / "gme_openvino_config.json").read_text())
        )
        return str(package / language_xml), str(package / visual_xml)
