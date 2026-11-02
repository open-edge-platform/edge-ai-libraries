# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Document layout detection, as a standalone capability.

**A layout detector turns a page image into positioned blocks** -- for each
region it reports a bounding box, a label, and a confidence. It does not read the
text inside a block (that is OCR's job) and it is not a llama-index component:
the extractor calls it directly to decide what regions a PDF page holds, then
crops and OCRs each one.

The engine speaks to a stable *capability interface* -- `LayoutDetector.detect`
-- and never to a backend or a device. `PP-DocLayoutV3` is a pure object
detector: it only draws boxes, so every block's text is supplied by a separate
OCR step. Preprocessing and NumPy post-processing live here; the standalone
`scripts/export_pp_doclayout_v3.py` prepares its ONNX artifact beforehand.
`inference.ov_adapter.OpenVINOLayoutDetector` owns OpenVINO compilation and inference.

This mirrors `core/embedding.py:build_embedding`: `build_layout_detector` takes
the model per call and caches by `(backend, model, device)`, imports everything
heavy lazily, and resolves model paths against the workspace. Swapping the
device (CPU/GPU/NPU) or the backend never reaches this file's callers.
"""

import json
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

import config

# --- label normalization ------------------------------------------------------
# A detector reports fine-grained labels (`paragraph_title`, `chart`, `seal`,
# ...); the engine only cares about four canonical kinds. Ported from mmdir
# `detect.py`, covering PP-DocLayoutV3 and MinerU vocabularies so a later backend
# swap does not silently relabel. TEXTUAL kinds become TEXT blocks downstream,
# VISUAL kinds become IMAGE blocks (`extractor.extract_layout`).

TEXT = "text"
EQUATION = "equation"
IMAGE = "image"
TABLE = "table"

#: What each canonical label means for the content stream.
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
    """One of `text` / `equation` / `image` / `table`, or the label unchanged.

    Case-insensitive. An unknown label is returned as-is rather than forced into
    a bucket -- a new label a model starts emitting shows up in the data instead
    of being silently miscounted as text.
    """
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


# --- capability interface -----------------------------------------------------


@dataclass
class LayoutBlock:
    """One detected region of a page.

    `bbox` is `[x1, y1, x2, y2]` in absolute pixels of the page image. `label`
    is the canonical kind (`normalize_label`); `raw_label` keeps what the model
    actually said, so a surprising normalization can be traced back.
    """

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


# --- PP-DocLayoutV3 model semantics ------------------------------------------

_ONNX_FILENAME = "pp_doclayout_v3.onnx"

# Upstream intentionally maps several internal classes to the same display
# label. This fallback also lets an exported model run without config.json.
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
        """Mirror PPDocLayoutV3ImageProcessor's sigmoid and flat top-k."""
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


def _result_to_blocks(
    result: Mapping[str, Any], id2label: Mapping[int, str]
) -> List[LayoutBlock]:
    """The `(scores, labels, boxes)` of one image as `LayoutBlock`s.

    Shared by both backends: transformers' `post_process_object_detection`
    returns this shape whether the model ran under torch or as an exported IR,
    so the label mapping and box coercion live here rather than in each backend.
    """
    blocks: List[LayoutBlock] = []
    for score, label, box in zip(result["scores"], result["labels"], result["boxes"]):
        label_id = int(_to_scalar(label))
        raw_label = str(id2label.get(label_id, label_id))
        bbox = tuple(float(v) for v in np.asarray(_to_list(box)).reshape(-1)[:4])
        blocks.append(
            LayoutBlock(
                bbox=bbox,
                label=normalize_label(raw_label),
                score=float(_to_scalar(score)),
                raw_label=raw_label,
            )
        )
    return blocks


def _to_scalar(value: Any) -> float:
    if hasattr(value, "item"):
        return value.item()
    return float(value)


def _to_list(value: Any):
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


# --- torch backend ------------------------------------------------------------


class TorchLayoutDetector(LayoutDetector):
    """Runs a layout detector as its source transformers model on CPU/GPU.

    This is the reference path (`config.LAYOUT_BACKENDS` "torch"), ported from
    mmdir `layout_wrapper.PPDocLayoutDetector`: `AutoModelForObjectDetection`
    reads the region boxes and `AutoImageProcessor.post_process_object_detection`
    un-normalizes them, with no OpenVINO export in between. `PP-DocLayoutV3` is a
    native transformers architecture (`model_type = pp_doclayout_v3`), so this
    needs no `trust_remote_code` and no IR conversion -- it just loads the
    `model.safetensors` from the workspace and runs it.

    Model and processor load lazily on the first `detect`, so constructing one is
    cheap; they can also be injected, which is how a test drives the pipeline
    against a synthetic model without a download.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "CPU",
        model_id: Optional[str] = None,
        score_threshold: float = 0.5,
        model: Any = None,
        image_processor: Any = None,
    ):
        self.model_path = model_path
        # transformers wants a torch device string ("cpu"/"cuda:0"); the engine
        # speaks OpenVINO's ("CPU"/"GPU"), so "CPU" maps to torch "cpu".
        self.device = "cpu" if str(device).upper() == "CPU" else str(device).lower()
        self.model_id = model_id
        self.score_threshold = float(score_threshold)
        self._model = model
        self._image_processor = image_processor
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._image_processor is not None:
            return
        with self._lock:
            if self._model is not None and self._image_processor is not None:
                return
            from core.embedding import resolve_model_path

            resolved = resolve_model_path(self.model_path)
            if not os.path.isdir(resolved):
                raise FileNotFoundError(
                    f"No prepared layout checkpoint at {resolved!r}. Prepare the "
                    "model and image processor before starting the engine; "
                    "it does not download models."
                )
            from transformers import AutoImageProcessor, AutoModelForObjectDetection

            model = AutoModelForObjectDetection.from_pretrained(
                resolved, local_files_only=True
            )
            self._model = model.to(self.device).eval()
            self._image_processor = AutoImageProcessor.from_pretrained(
                resolved, use_fast=True, local_files_only=True
            )

    def detect(self, images: Sequence[Any]) -> List[List[LayoutBlock]]:
        self._ensure_loaded()
        import torch

        pils = [as_pil_image(image) for image in images]
        if not pils:
            return []
        encoded = self._image_processor(images=pils, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self._model(**encoded)
        target_sizes = [(pil.height, pil.width) for pil in pils]
        results = self._image_processor.post_process_object_detection(
            outputs, threshold=self.score_threshold, target_sizes=target_sizes
        )
        id2label = {int(k): str(v) for k, v in (self._model.config.id2label or {}).items()}
        return [
            merge_layout_blocks(_result_to_blocks(result, id2label))
            for result in results
        ]

# --- factory ------------------------------------------------------------------

_CACHE: Dict[Tuple, LayoutDetector] = {}
_CACHE_LOCK = threading.Lock()


def build_layout_detector(
    backend: Optional[str] = None,
    model_id: Optional[str] = None,
    model_path: Optional[str] = None,
    device: Optional[str] = None,
    score_threshold: Optional[float] = None,
) -> LayoutDetector:
    """A layout detector, built at most once per configuration.

    Unset arguments fall back to the engine's configured defaults, so a caller
    with no opinion still gets a working detector. Caches like `build_embedding`:
    compiling an IR is expensive and several asset libraries usually share one.
    """
    backend = (backend or config.LAYOUT_BACKEND).lower()
    if backend not in config.LAYOUT_BACKENDS:
        raise ValueError(
            f"Layout backend {backend!r} is not supported; "
            f"supported: {', '.join(config.LAYOUT_BACKENDS)}"
        )
    model_id = model_id or config.LAYOUT_MODEL_ID
    model_path = model_path or config.LAYOUT_MODEL_PATH
    device = device or config.LAYOUT_DEVICE
    threshold = (
        config.LAYOUT_SCORE_THRESHOLD if score_threshold is None else score_threshold
    )

    key = (backend, model_id, model_path, device, threshold)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(backend, model_id, model_path, device, threshold)
            _CACHE[key] = cached
    return cached


def _build(
    backend: str, model_id: str, model_path: str, device: str, threshold: float
) -> LayoutDetector:
    if backend == "openvino":
        from inference.ov_adapter import OpenVINOLayoutDetector

        return OpenVINOLayoutDetector(
            model_path=model_path,
            device=device,
            model_id=model_id,
            score_threshold=threshold,
        )
    if backend == "torch":
        return TorchLayoutDetector(
            model_path=model_path,
            device=device,
            model_id=model_id,
            score_threshold=threshold,
        )
    raise NotImplementedError(f"Layout backend {backend!r} is not implemented yet")


__all__ = [
    "LayoutBlock",
    "LayoutDetector",
    "PPDocLayoutV3Runtime",
    "TorchLayoutDetector",
    "TEXTUAL_TYPES",
    "VISUAL_TYPES",
    "as_pil_image",
    "build_layout_detector",
    "merge_layout_blocks",
    "normalize_label",
    "pp_doclayout_v3_onnx_path",
]
