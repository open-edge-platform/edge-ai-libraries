# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

import config

# Canonical layout kinds; fine-grained detector labels (PP-DocLayoutV3, MinerU) map onto these.
TEXT = "text"
EQUATION = "equation"
IMAGE = "image"
TABLE = "table"

#: Textual kinds become TEXT blocks, visual kinds IMAGE blocks.
TEXTUAL_TYPES = frozenset({TEXT, EQUATION})
VISUAL_TYPES = frozenset({IMAGE, TABLE})

_TEXT_LIKE = frozenset({
    "text", "title", "code", "algorithm", "header", "footer", "page_number",
    "page_footnote", "aside_text", "ref_text", "list", "phonetic",
    "table_caption", "image_caption", "code_caption", "table_footnote",
    "image_footnote", "abstract", "content", "doc_title", "figure_title",
    "footnote", "number", "paragraph_title", "reference", "reference_content",
    "vision_footnote", "formula_number",
})
_IMAGE_LIKE = frozenset({"image", "chart", "figure", "seal"})
_TABLE_LIKE = frozenset({"table"})
_EQUATION_LIKE = frozenset({"equation", "equation_block", "formula"})


def normalize_label(raw_label: Any) -> str:
    """One of `text` / `equation` / `image` / `table`, or the (lowercased) unknown label unchanged."""
    label = str(raw_label or "unknown").strip().lower()
    if label in _TEXT_LIKE:
        return TEXT
    if label in _EQUATION_LIKE:
        return EQUATION
    if label in _IMAGE_LIKE:
        return IMAGE
    if label in _TABLE_LIKE:
        return TABLE
    return label


@dataclass
class LayoutBlock:
    """One detected region; `bbox` is `[x1, y1, x2, y2]` in page-image pixels."""

    bbox: Tuple[float, float, float, float]
    label: str
    score: float
    raw_label: str


def _bbox_iou(left: Sequence[float], right: Sequence[float]) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def merge_layout_blocks(
    blocks: Sequence[LayoutBlock], iou_threshold: float = 0.9
) -> List[LayoutBlock]:
    """Merge near-identical detections of the same canonical layout kind."""
    merged: List[LayoutBlock] = []
    for block in sorted(blocks, key=lambda item: item.score, reverse=True):
        match = next(
            (
                index
                for index, existing in enumerate(merged)
                if existing.label == block.label
                and _bbox_iou(existing.bbox, block.bbox) >= iou_threshold
            ),
            None,
        )
        if match is None:
            merged.append(block)
            continue
        existing = merged[match]
        merged[match] = LayoutBlock(
            bbox=(
                min(existing.bbox[0], block.bbox[0]),
                min(existing.bbox[1], block.bbox[1]),
                max(existing.bbox[2], block.bbox[2]),
                max(existing.bbox[3], block.bbox[3]),
            ),
            label=existing.label,
            score=existing.score,
            raw_label=existing.raw_label,
        )
    return sorted(merged, key=lambda item: (round(item.bbox[1] / 20.0), item.bbox[0]))


class LayoutDetector(ABC):
    """Turns page images into positioned blocks, whatever the backend."""

    @abstractmethod
    def detect(self, images: Sequence[Any]) -> List[List[LayoutBlock]]:
        """One reading-ordered list of blocks per input image."""


def as_pil_image(image: Any):
    """Normalize a supported layout input to an RGB PIL image."""
    from PIL import Image, ImageOps

    if isinstance(image, Image.Image):
        return ImageOps.exif_transpose(image).convert("RGB")
    if isinstance(image, (str, os.PathLike)):
        with Image.open(image) as handle:
            return ImageOps.exif_transpose(handle).convert("RGB")
    if isinstance(image, np.ndarray):
        return Image.fromarray(image.astype("uint8")).convert("RGB")
    if isinstance(image, (bytes, bytearray)):
        from io import BytesIO

        with Image.open(BytesIO(image)) as handle:
            return ImageOps.exif_transpose(handle).convert("RGB")
    raise TypeError(f"Unsupported image input: {type(image).__name__}")


_ONNX_FILENAME = "pp_doclayout_v3.onnx"

# Fallback when the model has no config.json; duplicate labels are intentional upstream.
_DEFAULT_ID2LABEL = {
    0: "abstract",
    1: "algorithm",
    2: "aside_text",
    3: "chart",
    4: "content",
    5: "formula",
    6: "doc_title",
    7: "figure_title",
    8: "footer",
    9: "footer",
    10: "footnote",
    11: "formula_number",
    12: "header",
    13: "header",
    14: "image",
    15: "formula",
    16: "number",
    17: "paragraph_title",
    18: "reference",
    19: "reference_content",
    20: "seal",
    21: "table",
    22: "text",
    23: "text",
    24: "vision_footnote",
}


def pp_doclayout_v3_onnx_path(model_dir: str) -> str:
    return os.path.join(model_dir, _ONNX_FILENAME)


def _load_id2label(model_dir: str) -> Dict[int, str]:
    for filename in ("id2label.json", "config.json"):
        path = os.path.join(model_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        labels = data if filename == "id2label.json" else data.get("id2label", {})
        if labels:
            return {int(key): str(value) for key, value in labels.items()}
    return dict(_DEFAULT_ID2LABEL)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -60.0, 60.0)))


class _PPDocLayoutV3Preprocessor:
    """Apply the fixed preprocessing stored in PP-DocLayoutV3's config."""

    def __call__(self, images, return_tensors=None):
        del return_tensors
        from PIL import Image

        arrays = []
        for image in images:
            resized = image.resize((800, 800), resample=Image.Resampling.BICUBIC)
            array = np.asarray(resized, dtype=np.float32) / 255.0
            arrays.append(np.transpose(array, (2, 0, 1)))
        return {"pixel_values": np.stack(arrays)}


class PPDocLayoutV3Runtime:
    """Preprocess and decode PP-DocLayoutV3 around a backend inference call."""

    def __init__(
        self,
        score_threshold: float = 0.5,
        image_processor: Any = None,
        id2label: Optional[Mapping[int, str]] = None,
    ):
        self.score_threshold = float(score_threshold)
        self.image_processor = image_processor or _PPDocLayoutV3Preprocessor()
        self._id2label = dict(id2label) if id2label is not None else None

    def load_metadata(self, model_dir: str) -> None:
        if self._id2label is None:
            self._id2label = _load_id2label(model_dir)

    def preprocess(self, images: Sequence[Any]) -> np.ndarray:
        encoded = self.image_processor(images=list(images), return_tensors="np")
        return np.asarray(encoded["pixel_values"])

    def postprocess(
        self,
        logits: np.ndarray,
        boxes: np.ndarray,
        image_sizes: Sequence[Tuple[int, int]],
    ) -> List[List[LayoutBlock]]:
        if logits.shape[0] != len(image_sizes) or boxes.shape[0] != len(image_sizes):
            raise ValueError(
                "PP-DocLayoutV3 output batch does not match the input batch: "
                f"{logits.shape[0]} logits, {boxes.shape[0]} boxes, "
                f"{len(image_sizes)} images"
            )
        return [
            self._postprocess_page(logits[index], boxes[index], width, height)
            for index, (width, height) in enumerate(image_sizes)
        ]

    def _postprocess_page(
        self,
        logits: np.ndarray,
        boxes: np.ndarray,
        width: int,
        height: int,
    ) -> List[LayoutBlock]:
        """Same sigmoid and flat top-k as PPDocLayoutV3ImageProcessor."""
        scores = _sigmoid(np.asarray(logits))
        flat_scores = scores.reshape(-1)
        top_k = min(scores.shape[0], flat_scores.size)
        if top_k == 0:
            return []
        indices = np.argpartition(-flat_scores, top_k - 1)[:top_k]
        indices = indices[np.argsort(-flat_scores[indices])]
        class_count = scores.shape[1]
        labels = indices % class_count
        queries = indices // class_count

        selected_boxes = np.asarray(boxes)[queries]
        xyxy = np.concatenate(
            [
                selected_boxes[:, :2] - 0.5 * selected_boxes[:, 2:],
                selected_boxes[:, :2] + 0.5 * selected_boxes[:, 2:],
            ],
            axis=-1,
        )
        xyxy *= np.asarray([width, height, width, height], dtype=xyxy.dtype)

        blocks: List[LayoutBlock] = []
        id2label = self._id2label or _DEFAULT_ID2LABEL
        for score, label_id, box in zip(flat_scores[indices], labels, xyxy):
            if float(score) < self.score_threshold:
                continue
            raw_label = id2label.get(int(label_id))
            if raw_label is None:
                continue
            x0, y0, x1, y1 = (float(value) for value in box)
            x0, x1 = max(0.0, min(width, x0)), max(0.0, min(width, x1))
            y0, y1 = max(0.0, min(height, y0)), max(0.0, min(height, y1))
            if x1 <= x0 or y1 <= y0:
                continue
            blocks.append(
                LayoutBlock(
                    bbox=(x0, y0, x1, y1),
                    label=normalize_label(raw_label),
                    score=float(score),
                    raw_label=raw_label,
                )
            )
        return merge_layout_blocks(blocks)


_CACHE: Dict[Tuple, LayoutDetector] = {}
_CACHE_LOCK = threading.Lock()


def build_layout_detector(
    backend: Optional[str] = None,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    score_threshold: Optional[float] = None,
) -> LayoutDetector:
    """A layout detector, built at most once per configuration; unset arguments use config defaults."""
    backend = (backend or config.LAYOUT_BACKEND).lower()
    if backend != config.LOCAL_OPENVINO:
        raise ValueError(
            f"Layout backend {backend!r} is not supported; "
            f"supported: {config.LOCAL_OPENVINO}"
        )
    model_id = model_id or config.LAYOUT_MODEL_ID
    device = device or config.LAYOUT_DEVICE
    threshold = (
        config.LAYOUT_SCORE_THRESHOLD if score_threshold is None else score_threshold
    )

    key = (backend, model_id, device, threshold)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(backend, model_id, device, threshold)
            _CACHE[key] = cached
    return cached


def _build(
    backend: str, model_id: str, device: str, threshold: float
) -> LayoutDetector:
    from inference.ov_adapter import OpenVINOLayoutDetector

    return OpenVINOLayoutDetector(
        model_path=model_id,
        device=device,
        model_id=model_id,
        score_threshold=threshold,
    )


__all__ = [
    "LayoutBlock",
    "LayoutDetector",
    "PPDocLayoutV3Runtime",
    "TEXTUAL_TYPES",
    "VISUAL_TYPES",
    "as_pil_image",
    "build_layout_detector",
    "merge_layout_blocks",
    "normalize_label",
    "pp_doclayout_v3_onnx_path",
]
