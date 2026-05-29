# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Embedding client abstraction.

Provides two backends for generating image embeddings:

* :class:`HTTPEmbeddingClient` - posts base64 images one-by-one to the
  multimodal-embedding-serving (MME) HTTP API. Concurrent requests are
  fired through a thread pool.
* :class:`SDKEmbeddingClient` - loads the ``multimodal_embedding_serving``
  model in-process and runs batched ``encode_image`` calls.

The :func:`create_embedding_client` factory chooses between them based on
the ``USE_SDK_EMBEDDING`` env var (default: True).
"""

from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import requests
from PIL import Image

from utils import encode_image_to_base64


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    try:
        return max(min_value, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class BaseEmbeddingClient(ABC):
    """Abstract embedding backend used by the indexer."""

    @abstractmethod
    def embed_images(self, images: List[Image.Image]) -> List[List[float]]:
        """Return one embedding (list[float]) per input PIL image, in order."""

    @abstractmethod
    def get_embedding_dim(self) -> int:
        """Return the dimensionality of an embedding vector."""


class HTTPEmbeddingClient(BaseEmbeddingClient):
    """Embeds images by posting them, one at a time, to the MME HTTP API."""

    def __init__(self, base_url: str, model_name: str, max_concurrent: int = 8, timeout_s: int = 30):
        if not base_url:
            raise ValueError("HTTPEmbeddingClient requires EMBEDDING_BASE_URL to be set")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.max_concurrent = max(1, max_concurrent)
        self.timeout_s = timeout_s
        self._dim: Optional[int] = None

    def _embed_one(self, image: Image.Image) -> List[float]:
        payload = {
            "model": self.model_name,
            "encoding_format": "float",
            "input": {
                "type": "image_base64",
                "image_base64": encode_image_to_base64(image),
            },
        }
        response = requests.post(
            f"{self.base_url}/embeddings",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def embed_images(self, images: List[Image.Image]) -> List[List[float]]:
        if not images:
            return []
        workers = min(self.max_concurrent, len(images))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            embeddings = list(executor.map(self._embed_one, images))
        if self._dim is None and embeddings:
            self._dim = len(embeddings[0])
        return embeddings

    def get_embedding_dim(self) -> int:
        # Lazy probe: HTTP service may not be ready at startup. Probe with a
        # dummy 224x224 image only when explicitly asked.
        if self._dim is None:
            dummy = Image.new("RGB", (224, 224))
            self._dim = len(self._embed_one(dummy))
        return self._dim


class SDKEmbeddingClient(BaseEmbeddingClient):
    """Embeds images in-process via the multimodal_embedding_serving SDK.

    Loads the model eagerly at construction time and probes the embedding
    dimension once. ``embed_images`` is chunked by ``batch_size`` to keep
    peak memory bounded, and serialised with a lock because the underlying
    model handler is not guaranteed to be thread-safe.
    """

    def __init__(
        self,
        model_name: str,
        device: str = "CPU",
        use_openvino: bool = False,
        ov_models_dir: Optional[str] = None,
        batch_size: int = 16,
    ):
        if not model_name:
            raise ValueError("SDKEmbeddingClient requires EMBEDDING_MODEL_NAME to be set")

        self.model_name = model_name
        self.device = device
        self.use_openvino = use_openvino
        self.ov_models_dir = ov_models_dir
        self.batch_size = max(1, batch_size)
        self._lock = threading.Lock()
        self._model_handler = None
        self._embedding_model = None
        self._dim: Optional[int] = None

        if use_openvino and ov_models_dir:
            os.makedirs(ov_models_dir, exist_ok=True)

        # Eagerly load so the container only reports healthy once the model
        # is ready to serve. Any load failure (HF unreachable, bad device,
        # missing weights) surfaces as a container restart, not a slow first
        # request.
        self._ensure_model_loaded()
        self._dim = self._probe_dim()

    def _ensure_model_loaded(self):
        if self._model_handler is not None:
            return
        with self._lock:
            if self._model_handler is not None:
                return
            # Imported lazily so HTTP-only deployments don't pay the import cost.
            from multimodal_embedding_serving import EmbeddingModel, get_model_handler

            handler = get_model_handler(
                model_id=self.model_name,
                device=self.device,
                ov_models_dir=self.ov_models_dir,
                use_openvino=self.use_openvino,
            )
            handler.load_model()
            if not handler.supports_image():
                raise RuntimeError(f"Model '{self.model_name}' does not support image embeddings")
            self._embedding_model = EmbeddingModel(handler)
            self._model_handler = handler

    def _probe_dim(self) -> int:
        self._ensure_model_loaded()
        try:
            dim = int(self._model_handler.get_embedding_dim())
            if dim > 0:
                return dim
        except Exception:
            pass
        dummy = Image.new("RGB", (224, 224))
        with self._lock:
            tensor = self._model_handler.encode_image([dummy])
        return len(self._tensor_to_list(tensor)[0])

    @staticmethod
    def _tensor_to_list(tensor) -> List[List[float]]:
        # encode_image returns either a torch.Tensor or a list-of-lists; normalise.
        if hasattr(tensor, "detach"):
            tensor = tensor.detach().cpu().tolist()
        elif hasattr(tensor, "tolist"):
            tensor = tensor.tolist()
        return [list(row) for row in tensor]

    def embed_images(self, images: List[Image.Image]) -> List[List[float]]:
        if not images:
            return []
        self._ensure_model_loaded()
        out: List[List[float]] = []
        for start in range(0, len(images), self.batch_size):
            chunk = images[start : start + self.batch_size]
            with self._lock:
                tensor = self._model_handler.encode_image(chunk)
            out.extend(self._tensor_to_list(tensor))
        if self._dim is None and out:
            self._dim = len(out[0])
        return out

    def get_embedding_dim(self) -> int:
        if self._dim is None:
            self._dim = self._probe_dim()
        return self._dim


def create_embedding_client() -> BaseEmbeddingClient:
    """Build an embedding client based on environment variables."""
    use_sdk = _env_bool("USE_SDK_EMBEDDING", True)
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "CLIP/clip-vit-h-14")

    if use_sdk:
        return SDKEmbeddingClient(
            model_name=model_name,
            device=os.getenv("EMBEDDING_DEVICE", os.getenv("DEVICE", "CPU")),
            use_openvino=_env_bool("EMBEDDING_USE_OV", False),
            ov_models_dir=os.getenv("EMBEDDING_OV_MODELS_DIR", "/home/user/models"),
            batch_size=_env_int("EMBEDDING_BATCH_SIZE", 16),
        )

    return HTTPEmbeddingClient(
        base_url=os.getenv("EMBEDDING_BASE_URL", ""),
        model_name=model_name,
        max_concurrent=_env_int("MAX_CONCURRENT_EMBEDDINGS", 8),
    )
