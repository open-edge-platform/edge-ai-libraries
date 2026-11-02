# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Standalone-media adapter over main's shared GME runtime.

Role discovery and package inspection never load OpenVINO or a processor. Both
adapters acquire one runtime from core.embedding; its lock protects preprocessing
and inference across document, image and derived-text sources.
"""

import json
from pathlib import Path
from typing import Any, List, Optional, Sequence

from core.content import (
    ROLE_DOC_IMAGE,
    ROLE_IMAGE,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    ROLE_L3_WIKI,
)
from core.multimodal.embeddings import Vector, normalize

GME_DIMENSION = 1536
PACKAGE_CONFIG = "gme_openvino_config.json"


def find_package(model_path: str) -> Path:
    """The package here, or the single package unpacked directly inside it."""
    root = Path(model_path)
    if (root / PACKAGE_CONFIG).is_file():
        return root
    nested = (
        [child for child in root.iterdir() if (child / PACKAGE_CONFIG).is_file()]
        if root.is_dir() else []
    )
    if len(nested) == 1:
        return nested[0]
    raise FileNotFoundError(
        f"No exported GME OpenVINO package at {model_path!r} (looked for "
        f"{PACKAGE_CONFIG}). Put the package under ENGINE_MODEL_ROOT_PATH, "
        "and select its model ID with the source's embedding_model."
    )


def choose_precision(package: Path) -> str:
    """Use main's precision resolution and require complete XML/weights pairs."""
    from inference.gme_runtime import package_ir_files

    metadata = json.loads((package / PACKAGE_CONFIG).read_text())
    precision, language, visual = package_ir_files(package, metadata)
    for name in (language, visual):
        path = package / name
        if not path.is_file() or not path.with_suffix(".bin").is_file():
            raise FileNotFoundError(
                f"GME precision {precision!r} is incomplete at {str(package)!r}: "
                f"expected {path.name} and {path.with_suffix('.bin').name}"
            )
    return precision


class GmeQwen2VLEmbedding:
    """GME's image and derived-text paths, sharing main's compiled runtime."""

    dimension = GME_DIMENSION
    supported_roles = frozenset(
        {ROLE_IMAGE, ROLE_DOC_IMAGE, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}
    )

    def __init__(
        self,
        model_path: str,
        device: str = "CPU",
        max_image_tokens: Optional[int] = None,
    ):
        from core.embedding import build_gme_runtime

        self._runtime = build_gme_runtime(
            model_path, device, max_image_tokens=max_image_tokens
        )
        self.model_path = str(self._runtime.model_dir)
        self.device = self._runtime.device
        self.precision = self._runtime.precision
        self.max_image_tokens = self._runtime._engine_settings[1]
        if self._runtime.embedding_dim != GME_DIMENSION:
            raise ValueError(
                f"GME package at {self.model_path!r} embeds at "
                f"{self._runtime.embedding_dim}, expected {GME_DIMENSION}"
            )

    def _text(self, texts: Sequence[str], is_query: bool) -> List[Vector]:
        texts = list(texts)
        if not texts:
            return []
        vectors = self._runtime.get_text_embeddings(
            texts, is_query=is_query, show_progress_bar=False
        )
        return [normalize(vector.tolist()) for vector in vectors]

    def embed_text(self, texts: Sequence[str]) -> List[Vector]:
        return self._text(texts, is_query=True)

    def embed_documents(self, texts: Sequence[str]) -> List[Vector]:
        """Captions and transcripts are corpus inputs, never query inputs."""
        return self._text(texts, is_query=False)

    def embed_image(self, images: Sequence[Any]) -> List[Vector]:
        images = list(images)
        if not images:
            return []
        vectors = self._runtime.get_image_embeddings(
            images, is_query=False, show_progress_bar=False
        )
        return [normalize(vector.tolist()) for vector in vectors]

    def embed_video(self, frames: Sequence[Any]) -> Vector:
        raise NotImplementedError(
            "GME embeds images, not clips; route video blocks to a video source"
        )


__all__ = ["GME_DIMENSION", "GmeQwen2VLEmbedding", "choose_precision", "find_package"]
